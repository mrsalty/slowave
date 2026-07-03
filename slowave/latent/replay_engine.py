from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from slowave.latent.episodic_store import EpisodicStore
from slowave.latent.graph_manager import GraphManager
from slowave.latent.salience import SalienceEngine
from slowave.latent.semantic_store import SemanticStore
from slowave.latent.transition_model import TransitionModel
from slowave.storage.sqlite_db import SQLiteDB


@dataclass(frozen=True)
class ReplayConfig:
    sample_size: int = 256
    # KMeans-like clustering (simple, no sklearn dependency): we do online assignment to nearest centroid.
    max_prototypes_per_replay: int = 32
    assignment_threshold: float = 0.60  # cosine similarity to existing prototype to reuse
    transition_batch_size: int = 64
    transition_steps: int = 50

    # Self-supervised retrieval rehearsal (Stage 5):
    # Periodically, the replay engine picks a member episode of each
    # prototype as a "probe" cue, asks retrieval to find its siblings,
    # and updates the prototype graph based on what was missed (Hebbian
    # failure-driven update). Cumulative across worker passes.
    self_supervise: bool = True
    # Max prototypes to probe per pass.
    self_supervise_max_prototypes: int = 32
    # Min member episodes a prototype must have to be probed (need at
    # least one expected sibling to evaluate).
    self_supervise_min_members: int = 3
    # Top-k retrieval used for the probe. Higher → more lenient
    # success criterion; lower → more failures → more learning signal.
    self_supervise_top_k: int = 8
    # Magnitude of the coactivation reinforcement applied to bridges
    # between the probe's prototype and the prototype that *should*
    # have surfaced the missed sibling. Deliberately small so
    # learning accumulates over many passes rather than overshooting.
    self_supervise_miss_reward: float = 0.5
    # Magnitude of the coactivation penalty when a confuser episode
    # (from a foreign prototype) appears in the probe's top-k.
    self_supervise_confuser_penalty: float = 0.25

    # Stage 8 — Dentate-gyrus-style pattern separation in prototype assignment.
    # The brain's DG runs competitive assignment: an episode that is
    # similar to two existing prototypes is *pushed away* from both
    # rather than smeared into the closer one. This prevents similar
    # but distinct memories (e.g. "running routine, January" vs
    # "running routine, June after the injury") from collapsing.
    # Implementation: score(e, p) becomes
    #   cos(e, p) - dg_separation_lambda * runner_up_cos(e, p')
    # An episode only joins prototype p if its distinctive similarity
    # to p exceeds assignment_threshold. Otherwise a new prototype is
    # created.
    # Disabled by default: empirically neutral-to-negative on both
    # LongMemEval (0.00pp) and LoCoMo (-0.45pp aggregate, with per-
    # category swings of +5.2/-2.2pp that cancel). The mechanism is
    # architecturally sound and kept available for deployments where
    # the recurring-topic-with-drift structure does favour it; it just
    # does not net positive on the two public benchmarks we tested.
    # See docs/2026-05-26_stage8_results.md.
    use_pattern_separation: bool = False
    # Strength of the runner-up penalty. 0.0 = no separation (legacy
    # behaviour). 1.0 = an episode must be similarity_to_winner -
    # similarity_to_runner_up >= threshold; very strict. 0.5 is the
    # neutral architectural choice: an episode that is equally similar
    # to two existing prototypes (sim_winner == sim_runner_up) gets a
    # score halved from its raw cosine, which is usually enough to
    # trigger creation of a new (third) prototype.
    dg_separation_lambda: float = 0.5
    # Skip the separation rule when there are fewer than this many
    # prototypes: with very few prototypes there is no meaningful
    # "competition" yet, and every episode would look ambiguous.
    # Mirrors the brain's developmental DG taking time to mature.
    dg_min_prototypes: int = 3

    # Stage 9 — CA3 + CA1 dual-scale prototypes. Every episode is
    # assigned at both scales in parallel during replay. The two
    # graphs differ only in their assignment threshold. See
    # docs/2026-05-26_stage9_proposal.md for the full architecture.
    # NOTE: Both thresholds are currently set to 0.60 after grid-search
    # tuning (2026-05-28). The original proposal used distinct CA3/CA1
    # thresholds (0.85 / 0.55); distinct thresholds are available for
    # experimentation but the current default reflects benchmark tuning.
    use_multi_scale: bool = True
    coarse_assignment_threshold: float = 0.60
    # The fine-scale threshold reuses ``assignment_threshold`` above
    # (default 0.60). The coarse threshold is tuned to match fine-scale
    # for balanced dual-scale assignment — both set to 0.60 per grid
    # search Phase 1 results (2026-05-28).


class ReplayEngine:
    """Replay + consolidation.

    Steps:
      1) Sample episodes proportional to salience.
      2) Cluster/assign to prototypes (reuse nearest prototype if similarity above threshold; else create new).
      3) Update prototypes centroid/support/variance.
      4) Update sparse graph edges (similarity top-k + coactivation + transitions).
      5) Train transition model on (e_t -> e_{t+1}) pairs within sampled time-sorted episodes.
      6) Reduce episodic salience after consolidation.
    """

    def __init__(
        self,
        *,
        db: SQLiteDB,
        episodic: EpisodicStore,
        semantic: SemanticStore,
        graph: GraphManager,
        salience: SalienceEngine,
        transition_model: TransitionModel,
        cfg: ReplayConfig,
        retrieval: "Any | None" = None,
    ):
        self.db = db
        self.episodic = episodic
        self.semantic = semantic
        self.graph = graph
        self.salience = salience
        self.transition_model = transition_model
        self.cfg = cfg
        # Optional handle on the live RetrievalPipeline so the engine
        # can rehearse retrieval during sleep (Stage 5). Set after
        # construction via attach_retrieval(); circular wiring is
        # avoided by leaving it None until the engine is fully built.
        self.retrieval = retrieval

    def attach_retrieval(self, retrieval: Any) -> None:
        """Attach the live RetrievalPipeline after engine construction.

        The pipeline depends on the replay engine indirectly (through
        FAISS indexes) and vice versa, so we accept it post-init to keep
        construction order clean.
        """
        self.retrieval = retrieval

    def _cos(self, a: np.ndarray, b: np.ndarray) -> float:
        a = a.astype(np.float32)
        b = b.astype(np.float32)
        return float(a.dot(b) / ((np.linalg.norm(a) + 1e-12) * (np.linalg.norm(b) + 1e-12)))

    def _assign_to_prototypes(
        self,
        *,
        episode_ids: list[int],
        X: np.ndarray,
        scale: str = "fine",
        threshold: float | None = None,
    ) -> tuple[list[tuple[int, int]], list[int]]:
        """Return (episode->prototype pairs, prototype_ids_touched).

        Stage 9: when called with ``scale='coarse'`` and a lower threshold,
        operates on the coarse prototype graph independently of the fine
        one. Only loads prototypes of the requested scale, so fine and
        coarse graphs do not contaminate each other.
        """
        if threshold is None:
            threshold = self.cfg.assignment_threshold
        # Load only prototypes of the requested scale.
        conn = self.db.connect()
        proto_rows = conn.execute(
            "SELECT id, centroid, dim, support_count, variance FROM semantic_prototypes WHERE scale = ?",
            (str(scale),),
        ).fetchall()
        proto_ids: list[int] = []
        centroids: list[np.ndarray] = []
        supports: list[int] = []
        variances: list[float] = []
        for r in proto_rows:
            proto_ids.append(int(r["id"]))
            centroids.append(np.frombuffer(r["centroid"], dtype=np.float32))
            supports.append(int(r["support_count"]))
            variances.append(float(r["variance"]))

        touched: set[int] = set()
        pairs: list[tuple[int, int]] = []
        for eid, e in zip(episode_ids, X, strict=True):
            if centroids:
                sims = [self._cos(e, c) for c in centroids]
                best_idx = int(np.argmax(sims))
                best_sim = float(sims[best_idx])
            else:
                best_idx = -1
                best_sim = -1.0

            # Once we have created/updated enough distinct prototypes for this replay,
            # we stop *creating new ones*, but we still assign remaining episodes to
            # their nearest existing prototype so that mapping is complete.
            allow_create = len(touched) < self.cfg.max_prototypes_per_replay

            # Stage 8 — dentate-gyrus-style pattern separation.
            # An episode is only assigned to its closest prototype if its
            # similarity is *distinctively* high — i.e. clearly higher
            # than its similarity to every other prototype. If two
            # prototypes are about equally similar, the episode is
            # treated as novel and a new prototype is created.
            #
            # We compute the runner-up similarity (second-highest cosine
            # against any other prototype) and subtract it scaled by
            # dg_separation_lambda from the best similarity. This is
            # what the brain does in the DG: episodes near a decision
            # boundary are pushed apart from both candidates.
            effective_sim = best_sim
            if (
                self.cfg.use_pattern_separation
                and best_idx >= 0
                and len(centroids) >= self.cfg.dg_min_prototypes
                and allow_create
            ):
                # Find the best similarity to any prototype OTHER than
                # the winner. `sims` is a Python list; .pop is cheap at
                # cluster-set scale (<= 100).
                rest = sims[:best_idx] + sims[best_idx + 1:]
                runner_up_sim = float(max(rest)) if rest else 0.0
                effective_sim = best_sim - self.cfg.dg_separation_lambda * runner_up_sim

            if best_idx >= 0 and (effective_sim >= threshold or not allow_create):
                pid = proto_ids[best_idx]
                # incremental mean update
                n = supports[best_idx]
                c_old = centroids[best_idx]
                c_new = (n * c_old + e) / float(n + 1)
                # variance: crude running estimate: mean squared distance to centroid
                dist2 = float(np.mean((e - c_new) ** 2))
                var_new = (variances[best_idx] * n + dist2) / float(n + 1)
                supports[best_idx] = n + 1
                centroids[best_idx] = c_new
                variances[best_idx] = var_new

                self.semantic.upsert_prototype(
                    prototype_id=pid,
                    centroid=c_new,
                    support_count=n + 1,
                    variance=var_new,
                    ts=int(time.time()),
                    scale=scale,
                )
            else:
                # create new prototype
                pid = self.semantic.upsert_prototype(
                    prototype_id=None,
                    centroid=e,
                    support_count=1,
                    variance=0.0,
                    ts=int(time.time()),
                    scale=scale,
                )
                proto_ids.append(pid)
                centroids.append(e.copy())
                supports.append(1)
                variances.append(0.0)

            pairs.append((int(eid), int(pid)))
            touched.add(int(pid))

        # Map all sampled episodes (even those assigned after creation limit)

        self.semantic.bulk_map_episode_to_prototype(pairs)
        return pairs, sorted(touched)

    def _train_transition_model(self, *, episode_ids: list[int], X: np.ndarray) -> float:
        # Skip if transition model is not enabled
        if self.transition_model is None:
            return 0.0
        
        # build pairs along time-sorted episodes
        mems = self.episodic.get_many(episode_ids)
        mems_sorted = sorted(mems, key=lambda m: m.ts)
        if len(mems_sorted) < 2:
            return 0.0
        E = np.stack([m.embedding for m in mems_sorted], axis=0).astype(np.float32)
        e_t = E[:-1]
        e_next = E[1:]
        # subsample batches
        n_pairs = e_t.shape[0]
        if n_pairs == 0:
            return 0.0

        losses: list[float] = []
        for _ in range(self.cfg.transition_steps):
            idx = np.random.randint(0, n_pairs, size=min(self.cfg.transition_batch_size, n_pairs))
            losses.append(self.transition_model.train_batch(e_t[idx], e_next[idx]))
        return float(np.mean(losses))

    def replay_once(self) -> dict[str, float]:
        # Apply time decay before sampling.
        now = int(time.time())
        conn = self.db.connect()
        rows = conn.execute("SELECT id, salience, last_salience_ts FROM episodic_memories").fetchall()
        for r in rows:
            eid = int(r["id"])
            s = float(r["salience"])
            last_ts = int(r["last_salience_ts"])
            decayed = self.salience.decay(s, dt_seconds=float(max(0, now - last_ts)))
            if abs(decayed - s) > 1e-9:
                self.episodic.update_salience(eid, decayed)

        ids_and_salience = self.episodic.list_saliences()
        sampled_ids = self.salience.sample_proportional(ids_and_salience, self.cfg.sample_size)
        X = self.episodic.load_embeddings(sampled_ids)
        if X.shape[0] == 0:
            return {"replay_sampled": 0, "transition_loss": 0.0}

        # consolidation: create/update prototypes + mapping
        # Stage 9: assign at both scales in parallel. The two graphs
        # are independent — same episodes, different threshold ->
        # different clustering. See docs/2026-05-26_stage9_proposal.md.
        pairs, touched = self._assign_to_prototypes(
            episode_ids=sampled_ids, X=X,
            scale="fine", threshold=self.cfg.assignment_threshold,
        )
        if self.cfg.use_multi_scale:
            pairs_coarse, touched_coarse = self._assign_to_prototypes(
                episode_ids=sampled_ids, X=X,
                scale="coarse", threshold=self.cfg.coarse_assignment_threshold,
            )
            # Coactivation / transition graphs are shared across scales —
            # a fine prototype that co-fires with a coarse prototype is
            # exactly the architectural representation of "this category
            # contains these specific instances".
            pairs = pairs + pairs_coarse
            touched = sorted(set(touched) | set(touched_coarse))

        # coactivation counts: any pair of prototypes in batch
        proto_in_batch = [p for _, p in pairs]
        coact: dict[tuple[int, int], float] = {}
        unique = sorted(set(proto_in_batch))
        for i in range(len(unique)):
            for j in range(len(unique)):
                if i == j:
                    continue
                coact[(unique[i], unique[j])] = coact.get((unique[i], unique[j]), 0.0) + 1.0
        self.graph.apply_coactivation_counts(coact)

        # transition counts: estimate from time-sorted mapped prototypes
        mems = self.episodic.get_many(sampled_ids)
        mems_sorted = sorted(mems, key=lambda m: m.ts)
        transition_counts: dict[tuple[int, int], float] = {}
        for a, b in zip(mems_sorted[:-1], mems_sorted[1:], strict=False):
            pa = self.semantic.prototype_for_episode(a.id)
            pb = self.semantic.prototype_for_episode(b.id)
            if pa is None or pb is None or pa == pb:
                continue
            transition_counts[(pa, pb)] = transition_counts.get((pa, pb), 0.0) + 1.0
        # Convert counts -> conditional probabilities P(dst|src)
        totals: dict[int, float] = {}
        for (src, _dst), c in transition_counts.items():
            totals[src] = totals.get(src, 0.0) + float(c)
        transition_prob: dict[tuple[int, int], float] = {}
        for (src, dst), c in transition_counts.items():
            transition_prob[(src, dst)] = float(c) / float(totals.get(src, 1.0))
        self.graph.apply_transition_counts(transition_prob)

        # similarity edges among touched prototypes
        touched_protos = self.semantic.get_many(touched)
        if touched_protos:
            proto_ids = [p.id for p in touched_protos]
            centroids = np.stack([p.centroid for p in touched_protos], axis=0)
            self.graph.set_similarity_edges(prototype_ids=proto_ids, centroids=centroids)

        # train transition model
        transition_loss = self._train_transition_model(episode_ids=sampled_ids, X=X)

        # reduce episodic salience after consolidation
        for eid, _pid in pairs:
            mem = self.episodic.get(eid)
            self.episodic.update_salience(eid, self.salience.penalize_after_consolidation(mem.salience))

        return {
            "replay_sampled": float(len(sampled_ids)),
            "prototypes_touched": float(len(touched)),
            "transition_loss": float(transition_loss),
        }

    # ------------------------------------------------------------------
    # Stage 5: self-supervised retrieval rehearsal
    # ------------------------------------------------------------------
    def self_supervise(self) -> dict[str, float]:
        """Rehearse retrieval against the system's own prototype membership.

        Brain analogue: sleep replay strengthens trajectories the system
        later needs. For each prototype with enough members:

          1. Pick one member episode as a probe cue.
          2. Run the live RetrievalPipeline on the probe's embedding.
          3. Compare the retrieved set with the prototype's other
             members ("expected siblings").
          4. For each *missed* sibling, add a small coactivation
             reinforcement on the edge between the probe-prototype and
             the prototype where the sibling actually lives. The bridge
             that would have surfaced the sibling gets stronger.
          5. For each *confuser* (foreign episode in the top-k), apply
             a small coactivation penalty on its bridge to the
             probe-prototype.

        Two guards keep this honest:

          - Reward only on miss. If retrieval already succeeds, the
            graph is left alone. No success-feedback loop.
          - Update magnitudes are small and additive. Bounded by the
            existing prune-edges step.

        Returns counters for diagnostics; never raises.
        """
        if not self.cfg.self_supervise or self.retrieval is None:
            return {"probed": 0.0, "misses_reinforced": 0.0, "confusers_penalised": 0.0}

        conn = self.db.connect()
        rows = conn.execute(
            "SELECT prototype_id, COUNT(*) AS n FROM episode_prototype_map "
            "GROUP BY prototype_id HAVING n >= ? "
            "ORDER BY n DESC LIMIT ?",
            (int(self.cfg.self_supervise_min_members),
             int(self.cfg.self_supervise_max_prototypes)),
        ).fetchall()
        # Mutable counters so the helper can update them in place.
        probed = [0]
        miss_reinforced = [0]
        confuser_penalised = [0]
        coact_delta: dict[tuple[int, int], float] = {}
        self._self_supervise_collect(
            rows, conn, coact_delta,
            counters=(probed, miss_reinforced, confuser_penalised),
        )

        # Apply deltas additively through the graph's existing path.
        for (src, dst), delta in coact_delta.items():
            ws, wt, wc = self.graph._get_components(src, dst)
            new_wc = max(0.0, float(wc) + float(delta))
            self.graph._upsert_edge(
                src, dst,
                w_similarity=ws, w_transition=wt, w_coactivation=new_wc,
            )
        self.graph.prune_edges()

        return {
            "probed": float(probed[0]),
            "misses_reinforced": float(miss_reinforced[0]),
            "confusers_penalised": float(confuser_penalised[0]),
            "edges_touched": float(len(coact_delta)),
        }

    def _self_supervise_collect(
        self,
        rows: list,
        conn,
        coact_delta: dict[tuple[int, int], float],
        *,
        counters: tuple,
    ) -> None:
        probed, miss_reinforced, confuser_penalised = counters
        for r in rows:
            proto_id = int(r["prototype_id"])
            member_rows = conn.execute(
                "SELECT episode_id FROM episode_prototype_map WHERE prototype_id = ?",
                (proto_id,),
            ).fetchall()
            members = [int(mr["episode_id"]) for mr in member_rows]
            if len(members) < self.cfg.self_supervise_min_members:
                continue
            # Most recent member is the probe — deterministic, and
            # biologically natural (recent traces replay preferentially).
            probe_eid = members[-1]
            expected_siblings = set(members[:-1])

            # Dentate gyrus gate: skip prototypes whose associated schemas
            # carry contradiction evidence or are flagged needs_review.
            # Brain analogue: the dentate gyrus pattern-separates conflicting
            # traces rather than reinforcing them; rehearsing a contradicted
            # schema would strengthen the wrong association.
            schema_rows = conn.execute(
                "SELECT s.needs_review, s.contradicting_episode_ids "
                "FROM schemas s "
                "JOIN schema_prototype_map m ON m.schema_id = s.id "
                "WHERE m.prototype_id = ? AND s.status = 'active' LIMIT 5",
                (proto_id,),
            ).fetchall()
            skip_proto = False
            for sr in schema_rows:
                if int(sr["needs_review"]):
                    skip_proto = True
                    break
                try:
                    from slowave.utils.vec import loads_json as _lj
                    contra = _lj(sr["contradicting_episode_ids"])
                    if isinstance(contra, dict) and contra.get("ids"):
                        skip_proto = True
                        break
                except Exception:
                    pass
            if skip_proto:
                continue
            try:
                probe = self.episodic.get(probe_eid)
            except KeyError:
                continue
            try:
                retrieved = self.retrieval.retrieve(probe.embedding)
            except Exception:
                continue
            probed[0] += 1
            retrieved_ids = [int(m.id) for m in retrieved.episodic[: self.cfg.self_supervise_top_k]]
            retrieved_set = set(retrieved_ids)
            retrieved_set.discard(probe_eid)

            misses = expected_siblings - retrieved_set
            confusers = retrieved_set - expected_siblings - {probe_eid}

            for m_eid in misses:
                sib_proto = self.semantic.prototype_for_episode(m_eid)
                if sib_proto is None or sib_proto == proto_id:
                    continue
                key = (int(proto_id), int(sib_proto))
                coact_delta[key] = coact_delta.get(key, 0.0) + self.cfg.self_supervise_miss_reward
                key_r = (int(sib_proto), int(proto_id))
                coact_delta[key_r] = coact_delta.get(key_r, 0.0) + self.cfg.self_supervise_miss_reward
                miss_reinforced[0] += 1

            for c_eid in confusers:
                conf_proto = self.semantic.prototype_for_episode(c_eid)
                if conf_proto is None or conf_proto == proto_id:
                    continue
                key = (int(proto_id), int(conf_proto))
                coact_delta[key] = coact_delta.get(key, 0.0) - self.cfg.self_supervise_confuser_penalty
                confuser_penalised[0] += 1

