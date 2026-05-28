"""Retrieval pipeline.

Two modes are supported:

* **cosine-only** (legacy) — FAISS top-k on episodic embeddings, optionally
  re-ranked by salience. This is the path the system shipped with up to
  May 2026; ablation studies show all brain-inspired components contribute
  zero under this mode because the graph and the transition model never
  affect what evidence is selected.

* **spreading activation** (new, default on) — the query is used to seed
  an activation pattern over the prototype graph, the activation is
  propagated for ``spread_steps`` iterations along ``prototype_edges``
  weights, and episodes are harvested from the activated prototypes. The
  cosine-direct episodes are merged with the graph-harvested ones, so
  this strictly generalises the legacy path.

The point of spreading activation is **pattern completion**: an episode
that cosine-matches the query weakly can still be retrieved if it lives
on a prototype reachable through high-weight edges from a strongly
cosine-matched prototype. This is the only mechanism in the system
that can solve multi-hop / cue-completion queries.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from slowave.latent.episodic_store import EpisodicStore
from slowave.latent.graph_manager import GraphManager
from slowave.latent.semantic_store import SemanticStore
from slowave.latent.temporal import TemporalContext
from slowave.latent.transition_model import TransitionModel
from slowave.latent.types import RetrievedMemorySet


@dataclass(frozen=True)
class RetrievalConfig:
    # Legacy / shared
    episodic_top_k: int = 10
    semantic_top_k: int = 6
    neighbor_top_k: int = 6
    salience_weight: float = 0.3

    # Spreading-activation knobs (Stage 1)
    use_spreading: bool = True
    spread_steps: int = 2
    spread_decay: float = 0.6
    spread_activation_floor: float = 1e-3
    episodes_per_prototype: int = 6
    # Score awarded to a fully-activated graph-harvested episode. This is
    # deliberately low — graph episodes should fill gaps below cosine
    # candidates, not compete with them on equal footing. Pattern
    # completion still works because PC-style queries have NO strong
    # cosine match, so graph-harvested episodes don't have anything to
    # compete with; LoCoMo-style queries have many moderate cosine
    # matches and graph noise must not displace them.
    spread_episode_weight: float = 0.15
    # Hard ceiling on the harvest score expressed as a fraction of the
    # worst cosine-top-k score, so graph candidates can never out-rank
    # a real cosine candidate by themselves. Salience can still re-rank
    # within each tier.
    spread_score_ceiling: float = 0.9
    salience_gate: bool = True
    # Diversity cap on graph-harvested episodes only — cosine-direct
    # episodes are exempt. 0 disables the cap entirely.
    diversity_per_prototype: int = 2

    # Temporal context (Stage 7): every episode/prototype carries an
    # intrinsic temporal coordinate (multi-scale sinusoidal embedding).
    # At recall time, a temporal-proximity bonus is added to each
    # candidate's score. Default query temporal context = "now". When
    # the caller knows the query carries an explicit temporal anchor
    # (e.g. a date in the question) they can pass it through; otherwise
    # the recall biases toward recent memories, which is the brain's
    # default behaviour.
    use_temporal: bool = True
    temporal_weight: float = 0.25

    # Stage 9 — multi-scale retrieval. When True the pipeline queries
    # both the fine (CA3-like) and coarse (CA1-like) prototype graphs
    # in parallel. Episodes harvested from both scales receive a
    # co-occurrence bonus — agreement across representational levels
    # is genuine evidence, not just lucky alignment.
    # See docs/2026-05-26_stage9_proposal.md.
    use_multi_scale: bool = True
    coarse_semantic_top_k: int = 6
    multi_scale_co_occurrence_bonus: float = 0.25
    # Predictive completion (Stage 3): ask the trained TransitionModel
    # what the next embedding after the query would be, and use that as a
    # second cosine seed. Lets queries like "what do I usually do after
    # the Monday standup" surface the on-call review even when the cue
    # text has no cosine overlap with the answer text.
    use_transition: bool = True
    # How many episodes to retrieve via the predicted next-state cue.
    transition_top_k: int = 6
    # Discount applied to predictive-seed cosine scores so a noisy
    # prediction never beats a real cue match. 0.7 means a perfect
    # predictive hit (cosine 1.0) only competes with a real cue match
    # at cosine 0.7. Higher = trust the prediction more.
    transition_score_weight: float = 0.7
    # Minimum norm of the prediction vector before we use it. The
    # untrained transition model produces near-zero vectors; this gate
    # avoids polluting retrieval with predictions made before any
    # consolidation has happened.
    transition_min_norm: float = 1e-2
    # Reserve this many head slots for predictive-seed-best episodes
    # that did *not* survive the merged cosine ranking. The brain-
    # inspired rationale: a learned sequential continuation is
    # qualitatively different evidence from a literal cue match, and
    # working memory should see both. Set to 0 to disable.
    transition_reserved_slots: int = 1
    # Only spend the reserved-slot budget when the prediction is
    # meaningfully *different* from the cue, i.e. cos(q, predict(q))
    # is below this threshold. If the model just returns ~q (e.g. on a
    # cue with no learned continuation), reserving a slot for the
    # prediction is the same as duplicating the cue match. 0.85 means
    # we only reserve when the prediction has moved at least ~30
    # degrees away from the query.
    transition_reserve_max_qsim: float = 0.85


class RetrievalPipeline:
    def __init__(
        self,
        *,
        episodic: EpisodicStore,
        semantic: SemanticStore,
        graph: GraphManager,
        cfg: RetrievalConfig,
        transition_model: TransitionModel | None = None,
    ):
        self.episodic = episodic
        self.semantic = semantic
        self.graph = graph
        self.cfg = cfg
        # Optional: provides predict(e_t) -> e_hat_{t+1}. When given,
        # the retrieval pipeline uses the predicted next-state embedding
        # as a second cosine seed (predictive completion, Stage 3).
        self.transition_model = transition_model
        # Stage 7: deterministic multi-scale sinusoidal temporal context.
        # Cheap to instantiate; held once per pipeline.
        self._temporal = TemporalContext()

    def retrieve(self, query_embedding: np.ndarray) -> RetrievedMemorySet:
        # 1) Cosine seed for episodes and prototypes (legacy behaviour).
        ep_scores, ep_ids = self.episodic.search(query_embedding, self.cfg.episodic_top_k)
        ep_ids = [int(i) for i in ep_ids if int(i) != -1]
        ep_score_by_id: dict[int, float] = {
            int(i): float(s)
            for i, s in zip(ep_ids, ep_scores[: len(ep_ids)], strict=False)
        }

        # Stage 9: fine + coarse prototype seeds. Fine (CA3-like) gives
        # narrow precise matches; coarse (CA1-like) gives broader topic
        # matches. Both contribute to seed activation; episodes harvested
        # from both later receive a co-occurrence bonus.
        if self.cfg.use_multi_scale:
            p_scores, p_ids = self.semantic.search_by_scale(
                query_embedding, scale="fine", top_k=self.cfg.semantic_top_k,
            )
        else:
            p_scores, p_ids = self.semantic.search(query_embedding, self.cfg.semantic_top_k)
        p_ids = [int(i) for i in p_ids if int(i) != -1]
        proto_seed = self.semantic.get_many(p_ids)
        seed_activation: dict[int, float] = {
            int(p): float(s)
            for p, s in zip(p_ids, p_scores[: len(p_ids)], strict=False)
        }

        # Stage 9 — coarse-scale seed contributes its own prototypes to
        # the seed activation. We track which episodes the coarse pass
        # would surface so the final ranker can apply a co-occurrence
        # bonus when an episode is seen at both scales.
        coarse_episodes: set[int] = set()
        if self.cfg.use_multi_scale:
            c_scores, c_ids = self.semantic.search_by_scale(
                query_embedding, scale="coarse",
                top_k=self.cfg.coarse_semantic_top_k,
            )
            c_ids = [int(i) for i in c_ids if int(i) != -1]
            for cp, cs in zip(c_ids, c_scores[: len(c_ids)], strict=False):
                pid_i = int(cp)
                if float(cs) > seed_activation.get(pid_i, -1e9):
                    seed_activation[pid_i] = float(cs)
            # Harvest episodes from the coarse prototypes so the
            # co-occurrence bonus has something to match against.
            if c_ids:
                harvested = self.semantic.episodes_for_prototypes(
                    c_ids, per_prototype=self.cfg.episodes_per_prototype,
                )
                for eps in harvested.values():
                    for eid in eps:
                        coarse_episodes.add(int(eid))

        # 1b) Predictive completion: ask the trained transition model what
        #     comes after a memory like the query, and use the predicted
        #     embedding as a second cosine seed (Stage 3). This is the
        #     mechanism the prompt "what comes next after X" actually
        #     needs — cosine-on-the-cue cannot match an answer that lives
        #     downstream in a learned sequence.
        predictive_seed_used = False
        predictive_top_ids: list[int] = []
        q_pred_sim = 1.0  # 1.0 = "no useful prediction", suppresses reserve
        if (
            self.cfg.use_transition
            and self.transition_model is not None
            and getattr(self.transition_model, "trained_steps", 0) > 0
        ):
            try:
                pred = self.transition_model.predict(
                    np.asarray(query_embedding, dtype=np.float32).reshape(1, -1)
                ).reshape(-1).astype(np.float32)
                pred_norm = float(np.linalg.norm(pred))
            except Exception:
                pred = None
                pred_norm = 0.0
            if pred is not None and pred_norm >= self.cfg.transition_min_norm:
                pred /= pred_norm
                # Measure how far the prediction moved from the cue. A
                # prediction that barely moved adds nothing new.
                q_norm = float(np.linalg.norm(query_embedding) + 1e-12)
                q_pred_sim = float(
                    np.asarray(query_embedding, dtype=np.float32).reshape(-1).dot(pred)
                    / q_norm
                )
                predictive_seed_used = True
                # Discounted episode cosine via the predicted next-state.
                t_scores, t_ids = self.episodic.search(pred, self.cfg.transition_top_k)
                w = float(self.cfg.transition_score_weight)
                for tid, ts in zip(t_ids, t_scores[: len(t_ids)], strict=False):
                    tid_i = int(tid)
                    if tid_i == -1:
                        continue
                    discounted = w * float(ts)
                    # max-merge with cosine-direct so a strong literal match
                    # is never demoted by a weaker prediction.
                    if discounted > ep_score_by_id.get(tid_i, -1e9):
                        ep_score_by_id[tid_i] = discounted
                    predictive_top_ids.append(tid_i)
                # Also seed prototype activation so spreading benefits from
                # the predicted state. Same discount.
                tp_scores, tp_ids = self.semantic.search(pred, self.cfg.semantic_top_k)
                for pid_, ps in zip(tp_ids, tp_scores[: len(tp_ids)], strict=False):
                    pid_i = int(pid_)
                    if pid_i == -1:
                        continue
                    val = w * float(ps)
                    if val > seed_activation.get(pid_i, -1e9):
                        seed_activation[pid_i] = val

        # 2) Spreading activation over the prototype graph (new).
        spread_activation: dict[int, float] = {}
        if self.cfg.use_spreading and seed_activation:
            spread_activation = self._spread(seed_activation)

        # 3) Backwards-compatible neighbour expansion field.
        expanded: dict[int, list[tuple[int, float]]] = {}
        if self.cfg.neighbor_top_k > 0:
            for p in proto_seed:
                expanded[p.id] = self.graph.neighbors(p.id, top_k=self.cfg.neighbor_top_k)

        # 4) Harvest episodes from activated prototypes and merge with the
        #    cosine-direct episodes.
        #
        # Graph-harvested episodes are given a uniform base score
        # ``spread_episode_weight * activation`` and never overwrite a
        # cosine-direct score (which is per-episode and typically
        # stronger). The salience reinforcement step that follows is
        # restricted to cosine-direct episodes, so the graph never feeds
        # itself.
        merged_score: dict[int, float] = dict(ep_score_by_id)
        cosine_episodes_set: set[int] = set(ep_score_by_id.keys())
        if spread_activation:
            # Worst cosine top-k score sets the ceiling: graph-harvested
            # episodes can compete only *below* this score, so they fill
            # gaps rather than displacing real cosine candidates.
            cosine_floor = (
                min(ep_score_by_id.values()) if ep_score_by_id else 0.0
            )
            ceiling = float(self.cfg.spread_score_ceiling) * cosine_floor
            harvested = self.semantic.episodes_for_prototypes(
                spread_activation.keys(),
                per_prototype=self.cfg.episodes_per_prototype,
            )
            harvested_ids = {eid for ids in harvested.values() for eid in ids}
            harvested_ids -= cosine_episodes_set
            sal_by_id: dict[int, float] = {}
            if harvested_ids:
                for m in self.episodic.get_many(list(harvested_ids)):
                    sal_by_id[int(m.id)] = float(m.salience)
            for proto_id, episode_ids in harvested.items():
                act = spread_activation.get(proto_id, 0.0)
                if act <= self.cfg.spread_activation_floor:
                    continue
                base = float(self.cfg.spread_episode_weight) * min(1.0, act)
                # Cap at the cosine-floor-based ceiling so graph
                # candidates can never out-rank a real cosine candidate.
                base = min(base, ceiling) if ceiling > 0.0 else base
                for eid in episode_ids:
                    if eid in cosine_episodes_set:
                        continue  # already scored by cosine — never downgrade
                    sal = sal_by_id.get(int(eid), 0.0)
                    weight = base * (0.5 + 0.5 * sal)
                    prev = merged_score.get(eid, -1e9)
                    merged_score[eid] = max(prev, weight)

        # 5) Materialise + final re-rank by:
        #      merged cosine/spread score
        #      + α_salience * salience
        #      + α_temporal * cos(query_temporal, episode_temporal)   (Stage 7)
        #
        # The temporal term is a small additive bonus: it nudges
        # retrieval toward memories whose temporal context is close to
        # the query's temporal context (defaults to "now"). It is never
        # large enough to outrank a real semantic match — same
        # discipline as the salience term.
        all_episode_ids = list(merged_score.keys())
        episodes = self.episodic.get_many(all_episode_ids)

        temporal_bonus_by_id: dict[int, float] = {}
        if self.cfg.use_temporal and self.cfg.temporal_weight > 0.0 and episodes:
            q_temporal = self._temporal.now()
            ep_ts = np.asarray([int(m.ts) for m in episodes], dtype=np.int64)
            ep_temporal = self._temporal.encode_many(ep_ts)
            sims = ep_temporal @ q_temporal
            for m, sim in zip(episodes, sims, strict=False):
                temporal_bonus_by_id[int(m.id)] = float(sim)

        def _final_score(m) -> float:
            score = merged_score.get(int(m.id), 0.0)
            score += self.cfg.salience_weight * float(m.salience)
            if temporal_bonus_by_id:
                score += self.cfg.temporal_weight * temporal_bonus_by_id.get(int(m.id), 0.0)
            # Stage 9: episodes seen at BOTH fine and coarse scales get
            # a small multiplicative bonus. Cosine top-k always counts
            # as "fine-side endorsed" (those episodes belong to fine
            # prototypes via their canonical assignment).
            if (
                self.cfg.use_multi_scale
                and self.cfg.multi_scale_co_occurrence_bonus > 0.0
                and int(m.id) in coarse_episodes
            ):
                score *= (1.0 + self.cfg.multi_scale_co_occurrence_bonus)
            return score

        episodes_sorted = sorted(episodes, key=_final_score, reverse=True)

        # 6) Diversity cap: rebalance the head so a single prototype with
        #    many near-duplicate episodes cannot saturate the top slots.
        #    Two important guards:
        #      (a) cosine-direct episodes are never demoted — they
        #          earned their slot on real similarity; only the graph-
        #          harvested cluster duplicates get pushed down.
        #      (b) the cap only kicks in for graph-harvested episodes,
        #          so when retrieval is effectively cosine-only the
        #          legacy ranking is preserved.
        if self.cfg.diversity_per_prototype > 0 and len(episodes_sorted) > 1 and spread_activation:
            proto_lookup: dict[int, int | None] = {}
            for m in episodes_sorted:
                pid = self.semantic.prototype_for_episode(int(m.id))
                proto_lookup[int(m.id)] = pid
            head: list = []
            tail: list = []
            per_proto: dict[int, int] = {}
            for m in episodes_sorted:
                # Cosine-direct episodes always go to the head, no cap.
                if int(m.id) in cosine_episodes_set:
                    head.append(m)
                    pid = proto_lookup.get(int(m.id))
                    key = -1 if pid is None else int(pid)
                    per_proto[key] = per_proto.get(key, 0) + 1
                    continue
                pid = proto_lookup.get(int(m.id))
                key = -1 if pid is None else int(pid)
                if per_proto.get(key, 0) >= self.cfg.diversity_per_prototype:
                    tail.append(m)
                    continue
                head.append(m)
                per_proto[key] = per_proto.get(key, 0) + 1
            episodes_sorted = head + tail

        # 7) Reserve a small number of head slots for predictive-seed
        #    candidates that did not survive the merged ranking.
        #    Brain-inspired rationale: a learned sequential continuation
        #    is qualitatively different evidence from a literal cue
        #    match, so working memory should see both — even if the
        #    cue match has higher cosine. The reservation deduplicates
        #    against the current head so we never displace evidence
        #    that already represents the predicted continuation.
        if (
            predictive_seed_used
            and self.cfg.transition_reserved_slots > 0
            and predictive_top_ids
            and q_pred_sim <= self.cfg.transition_reserve_max_qsim
        ):
            reserve_n = int(self.cfg.transition_reserved_slots)
            head_ids = [int(m.id) for m in episodes_sorted[: max(reserve_n * 4, 8)]]
            head_proto_ids: set[int] = set()
            for m in episodes_sorted[: max(reserve_n * 4, 8)]:
                pid = self.semantic.prototype_for_episode(int(m.id))
                if pid is not None:
                    head_proto_ids.add(int(pid))
            # Deduplicate predictive ids while preserving order (best first).
            seen: set[int] = set()
            unique_pred: list[int] = []
            for pid_ in predictive_top_ids:
                if pid_ in seen:
                    continue
                seen.add(pid_)
                unique_pred.append(pid_)
            to_promote: list[int] = []
            for pid_ in unique_pred:
                if pid_ in head_ids:
                    continue
                pproto = self.semantic.prototype_for_episode(pid_)
                # Skip if the head already has an episode from the same
                # predicted prototype — that means the continuation is
                # already represented, no need to splice a near-duplicate.
                if pproto is not None and pproto in head_proto_ids:
                    continue
                to_promote.append(pid_)
                if len(to_promote) >= reserve_n:
                    break
            if to_promote:
                promote_set = set(to_promote)
                promoted = [m for m in episodes_sorted if int(m.id) in promote_set]
                rest = [m for m in episodes_sorted if int(m.id) not in promote_set]
                # Insert promoted episodes just after the strongest cosine
                # match so they sit in the head but don't displace the
                # very best literal hit.
                episodes_sorted = rest[:1] + promoted + rest[1:]

        # Reinforcement: ONLY for cosine-direct episodes in the top slice.
        # Reinforcing graph-harvested episodes would create a self-rewarding
        # feedback loop where any prototype activated by the graph
        # accumulates salience independently of whether its content was
        # actually relevant to the query.
        cap = max(self.cfg.episodic_top_k, 1)
        self.episodic.increment_recall(
            [m.id for m in episodes_sorted[:cap] if int(m.id) in cosine_episodes_set],
            reinforcement=self.cfg.salience_weight,
        )

        return RetrievedMemorySet(
            query_embedding=np.asarray(query_embedding, dtype=np.float32),
            episodic=episodes_sorted,
            prototypes=proto_seed,
            expanded_neighbors=expanded,
        )

    # ------------------------------------------------------------------
    def _spread(self, seed: dict[int, float]) -> dict[int, float]:
        """Iterative activation propagation over the prototype graph.

        Update rule per step:

            a_{t+1}[p] = alpha * a_t[p]
                       + (1 - alpha) * sum_q( w_norm(q -> p) * a_t[q] )

        ``w(q -> p)`` is the stored ``prototype_edges.weight`` (a fused
        mix of similarity, transition, and coactivation — see
        ``GraphManager``). Weights out of each source are L1-normalised so
        propagation is locally probabilistic and a super-hub cannot
        dominate.

        Below ``spread_activation_floor`` the activation is pruned each
        step to keep the front sparse.

        Optional salience gate: the final activation of each prototype is
        modulated by ``(1 + 0.1 * sqrt(1 + support_count))`` — a soft
        boost for prototypes with accumulated repeated evidence,
        approximating "more strongly consolidated patterns activate more
        easily" (Hebbian intuition).

        Returns the final activation vector keyed by prototype id.
        """
        alpha = float(self.cfg.spread_decay)
        floor = float(self.cfg.spread_activation_floor)

        seed_max = max(seed.values()) if seed else 0.0
        if seed_max <= 0.0:
            return {}
        activation = {p: max(0.0, v) / seed_max for p, v in seed.items()}

        for _ in range(int(self.cfg.spread_steps)):
            new_act: dict[int, float] = {p: alpha * v for p, v in activation.items()}
            for src, src_act in activation.items():
                if src_act < floor:
                    continue
                neighbors = self.graph.neighbors(src, top_k=self.cfg.neighbor_top_k)
                if not neighbors:
                    continue
                total_w = sum(max(0.0, w) for _, w in neighbors) + 1e-12
                for dst, w in neighbors:
                    if w <= 0.0:
                        continue
                    contrib = (1.0 - alpha) * (w / total_w) * src_act
                    new_act[dst] = new_act.get(dst, 0.0) + contrib

            activation = {p: v for p, v in new_act.items() if v >= floor}
            if not activation:
                break

        if self.cfg.salience_gate and activation:
            protos = self.semantic.get_many(activation.keys())
            for p in protos:
                gate = (1.0 + float(p.support_count)) ** 0.5
                activation[int(p.id)] = activation.get(int(p.id), 0.0) * (
                    1.0 + 0.1 * gate
                )

        return activation
