"""Working-memory gating for prompt context.

This module is deliberately generic: ``scope`` (e.g. ``project:x``, ``domain:y``)
is only one optional environmental cue.  The gate models the brain-like step
between broad long-term
memory activation and the tiny set of memories admitted into active working
context for an agent/chatbot prompt.
"""

from __future__ import annotations

import re

import numpy as np
from dataclasses import dataclass, field, replace
from typing import Any, Iterable

from slowave.symbolic.schema_store import Schema

_STOPWORDS = {
    "a",
    "about",
    "after",
    "all",
    "also",
    "am",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "been",
    "being",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "doing",
    "for",
    "from",
    "get",
    "give",
    "had",
    "has",
    "have",
    "help",
    "her",
    "here",
    "him",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "me",
    "more",
    "my",
    "of",
    "on",
    "or",
    "our",
    "please",
    "she",
    "should",
    "so",
    "tell",
    "than",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "this",
    "to",
    "up",
    "us",
    "use",
    "user",
    "was",
    "we",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
    "would",
    "you",
    "your",
}

_DEFAULT_ALLOWED_CLASSES = (
    "fact",
    "preference",
    "interaction_preference",
    "constraint",
    "habit",
    "decision",
    "lesson",
    "relationship",
    "artifact",
    "task",
    "open_question",
    "warning",
    "procedure",
)

_DEFAULT_EXCLUDED_LAYERS = ("raw_event", "episodic_summary", "assistant_summary")
_DEFAULT_EXCLUDED_SOURCES = ("assistant_summary", "tool_result_summary")

# Ceiling for the query-independent identity prior (class, layer, provenance,
# scope, salience, utility bonuses combined). Uncapped, these bonuses summed to
# ~0.58 for a same-scope explicit schema versus a 0.40 maximum cosine
# contribution, making context briefs nearly query-invariant: what a memory IS
# must only tie-break, never outrank, how well it matches the current query.
_IDENTITY_BONUS_CAP = 0.15

# Multiplier for the context_noise_score penalty (computed at consolidation
# from shown/used/irrelevant feedback counts). A memory repeatedly surfaced
# but never marked used loses up to 0.30 activation — the feedback loop that
# actually cleans ranking (salience deltas alone move activation by ~0.0004).
_NOISE_PENALTY_WEIGHT = 0.30


@dataclass(frozen=True)
class MemoryCue:
    """Current cognitive/environmental cue used to prime memory.

    Scope is the primary contextual boundary. All other fields (query, topics,
    entities, application) are semantic cues that spread activation through
    long-term memory independent of scope.
    """

    query: str | None = None
    scope: str | None = None
    goal: str | None = None
    task_type: str | None = None
    situation: dict[str, Any] = field(default_factory=dict)
    requirements: tuple[str, ...] = ()
    application: str | None = None
    topics: tuple[str, ...] = ()
    entities: tuple[str, ...] = ()
    mode: str = "default"  # default | broad | debug


@dataclass(frozen=True)
class GatePolicy:
    """Policy for admitting long-term memories into working context."""

    max_items: int = 8
    max_chars: int = 4000
    max_item_chars: int = 500
    min_activation: float = 0.20
    # When more admitted items exist than max_items, this many trailing slots
    # are filled by salience instead of relevance — the serendipity channel
    # that keeps apparently-unrelated memories circulating (and generating the
    # exposure data cross-scope generalization needs) without ever displacing
    # a relevant memory from the top of the brief.
    exploration_slots: int = 2
    allowed_classes: tuple[str, ...] = _DEFAULT_ALLOWED_CLASSES
    excluded_layers: tuple[str, ...] = _DEFAULT_EXCLUDED_LAYERS
    excluded_source_kinds: tuple[str, ...] = _DEFAULT_EXCLUDED_SOURCES


@dataclass(frozen=True)
class ActivationTrace:
    """Inspectable activation/inhibition breakdown for a candidate schema."""

    schema_id: int
    activation: float
    reason: str
    admitted: bool


@dataclass(frozen=True)
class WorkingMemoryItem:
    schema: Schema
    activation: float
    reason: str
    text: str
    peripheral: bool = False


@dataclass(frozen=True)
class WorkingMemoryState:
    items: list[WorkingMemoryItem]
    rendered: str
    cue_terms: list[str]
    suppressed: dict[str, int] = field(default_factory=dict)
    activation_trace: list[ActivationTrace] = field(default_factory=list)

    @property
    def schemas(self) -> list[Schema]:
        return [item.schema for item in self.items]


class WorkingMemoryGate:
    """Select which schemas enter active prompt context.

    The gate approximates a prefrontal/thalamic working-memory bottleneck:
    current cues spread activation through long-term memory, then irrelevant or
    low-source-quality memories are inhibited before a small capacity-limited
    state is rendered for the downstream agent.
    """

    def select(
        self,
        candidates: Iterable[Schema],
        *,
        cue: MemoryCue,
        policy: GatePolicy | None = None,
        cue_embedding: "np.ndarray | None" = None,
    ) -> WorkingMemoryState:
        policy = policy or GatePolicy()
        cue_terms = _cue_terms(cue)
        suppressed: dict[str, int] = {}
        traces: list[ActivationTrace] = []
        items: list[WorkingMemoryItem] = []

        for schema in candidates:
            ok, reason = self._eligible(schema, cue=cue, policy=policy)
            if not ok:
                suppressed[reason] = suppressed.get(reason, 0) + 1
                traces.append(ActivationTrace(schema.id, 0.0, reason, False))
                continue

            activation, reason = self._activation(schema, cue=cue, cue_terms=cue_terms, cue_embedding=cue_embedding)
            if activation < policy.min_activation:
                suppressed["below_activation"] = suppressed.get("below_activation", 0) + 1
                traces.append(ActivationTrace(schema.id, activation, reason, False))
                continue

            # Stage 11 noise floor: cross-scope Stage 1/2 schemas that passed
            # eligibility but have insufficient relevance to the current query
            # are suppressed.  Two independent gates must both pass:
            #
            # Gate A — activation floor (0.30):
            #   Blocks memories whose combined signal (cosine + overlap +
            #   salience + class bonuses) falls below the threshold.
            #   Raised from 0.20 to 0.30 because the lower value still admitted
            #   generic memories that scored ~0.33 purely from salience/utility
            #   boosts with no real semantic match (the "pytest on password" case).
            #
            # Gate B — cosine floor (0.25, when embeddings available):
            #   Ensures the schema is geometrically related to the query, not
            #   just lexically noisy.  A memory passing on cue_overlap alone
            #   (shared surface words like "test", "data") but with cosine < 0.25
            #   is rejected.
            #
            # Stage 3 (global) is exempt from both gates — it earned unrestricted
            # admission through demonstrated cross-domain utility.
            if cue.scope and schema.scope_id and schema.scope_id != cue.scope:
                _gs = getattr(schema, "generalization_stage", 0)
                if _gs in (1, 2):
                    _min_cross_activation = 0.30  # matches GeneralizationConfig.cross_scope_min_score
                    if activation < _min_cross_activation:
                        suppressed["cross_scope_below_floor"] = suppressed.get("cross_scope_below_floor", 0) + 1
                        traces.append(ActivationTrace(schema.id, activation, "cross_scope_below_floor", False))
                        continue
                    # Cosine gate: when both query and schema embeddings are present,
                    # require minimum geometric similarity so surface-word overlap
                    # alone cannot admit an unrelated promoted memory.
                    if cue_embedding is not None and schema.embedding is not None:
                        _q = np.asarray(cue_embedding, dtype=np.float32)
                        _v = np.asarray(schema.embedding, dtype=np.float32)
                        _qn = float(np.linalg.norm(_q)) + 1e-12
                        _vn = float(np.linalg.norm(_v)) + 1e-12
                        _cosine = float(_q.dot(_v) / (_qn * _vn))
                        if _cosine < 0.25:
                            suppressed["cross_scope_low_cosine"] = suppressed.get("cross_scope_low_cosine", 0) + 1
                            traces.append(ActivationTrace(schema.id, activation, f"cross_scope_low_cosine:{_cosine:.2f}", False))
                            continue

            item = WorkingMemoryItem(
                schema=schema,
                activation=activation,
                reason=reason,
                text=_compact(schema.content_text, policy.max_item_chars),
            )
            items.append(item)
            traces.append(ActivationTrace(schema.id, activation, reason, True))

        items.sort(
            key=lambda i: (i.activation, i.schema.salience, i.schema.last_updated_ts),
            reverse=True,
        )
        items = _mmr_deduplicate(items, cos_threshold=0.92)

        # Exploration slots: when more admitted items exist than fit, the top
        # slots are earned by relevance-ranked activation and the trailing
        # slots by salience — a bounded serendipity channel, labelled
        # "(peripheral)" in the rendered brief.
        slots = 0
        if len(items) > policy.max_items:
            slots = min(policy.exploration_slots, max(0, policy.max_items - 1))
        selected = _apply_budget(items[: max(policy.max_items * 3, policy.max_items)], policy)
        if slots:
            chosen = {item.schema.id for item in selected}
            rest = [item for item in items if item.schema.id not in chosen]
            rest.sort(key=lambda i: (i.schema.salience, i.schema.last_updated_ts), reverse=True)
            for item in rest[:slots]:
                selected.append(replace(item, peripheral=True, reason=item.reason + ",peripheral"))
        return WorkingMemoryState(
            items=selected,
            rendered=_render(selected),
            cue_terms=sorted(cue_terms),
            suppressed=suppressed,
            activation_trace=traces,
        )

    def _eligible(
        self,
        schema: Schema,
        *,
        cue: MemoryCue,
        policy: GatePolicy,
    ) -> tuple[bool, str]:
        # Mode-gated status filtering:
        # needs_review visible only in broad/debug; superseded only in debug.
        if cue.mode == "debug":
            # Debug mode shows everything
            pass
        elif cue.mode == "broad":
            # Broad mode shows active and needs_review, but not superseded
            if schema.status not in ("active", "needs_review"):
                return False, "inactive"
        else:
            # Default/strict_scope: only active
            if schema.status != "active":
                return False, "inactive"
        
        if cue.mode == "debug":
            return True, "debug"

        # Strict scope: hard-block memories whose scope doesn't match the cue.
        # Stage 11 — generalization override: promoted schemas bypass the hard wall
        # based on their earned stage.
        #   Stage 0 (scoped)      : strict wall applies as before.
        #   Stage 1 (portable)    : allowed if same scope_kind as origin.
        #   Stage 2 (contextual)  : always passed through; activation is penalised below.
        #   Stage 3 (global)      : fully transparent, no restriction.
        if cue.mode == "strict_scope" and cue.scope:
            layer = (schema.facets or {}).get("memory_layer")
            is_profile = layer == "profile"
            is_global = not schema.scope_id  # None or "" both treated as global
            is_same_scope = schema.scope_id == cue.scope
            gen_stage = getattr(schema, "generalization_stage", 0)
            if not (is_same_scope or is_global or is_profile):
                if gen_stage >= 3:
                    pass  # global: no restriction
                elif gen_stage == 2:
                    pass  # contextual: passes eligibility, penalty applied in activation
                elif gen_stage == 1:
                    # portable: only pass if same scope_kind
                    from slowave.core.scope import scope_kind as _scope_kind
                    if _scope_kind(schema.scope_id) != _scope_kind(cue.scope):
                        return False, "strict_scope_excluded"
                else:
                    return False, "strict_scope_excluded"

        facets = schema.facets or {}
        if facets.get("injectable") is False:
            return False, "not_injectable"

        schema_class = _lower(facets.get("schema_class"))
        if schema_class == "latent" and cue.mode != "broad":
            return False, "class_excluded:latent"
        if schema_class and schema_class not in policy.allowed_classes and cue.mode != "broad":
            return False, f"class_excluded:{schema_class}"

        layer = _lower(facets.get("memory_layer"))
        if layer in policy.excluded_layers and cue.mode != "broad":
            return False, f"layer_excluded:{layer}"

        source_kind = _source_kind(facets)
        if source_kind in policy.excluded_source_kinds and cue.mode != "broad":
            return False, f"source_excluded:{source_kind}"

        text = schema.content_text or ""
        if _looks_like_transcript_summary(text) and cue.mode != "broad":
            return False, "transcript_summary"

        # Belt-and-suspenders gate for multi-sentence consolidated summaries.
        # Excludes them from default context unless explicitly remembered or in broad/debug.
        # Catches untagged legacy schemas that predate schema_class tagging at consolidation.
        schema_class = _lower(facets.get("schema_class"))
        source_kind = _source_kind(facets)
        if schema_class != "episodic_summary" and source_kind != "explicit_remember":
            sentence_count = len(re.findall(r"[.!?]", text))
            text_length = len(text)
            if (sentence_count >= 3 or text_length > 300) and cue.mode not in ("broad", "debug"):
                return False, "multi_sentence_summary"

        return True, "eligible"

    def _activation(
        self,
        schema: Schema,
        *,
        cue: MemoryCue,
        cue_terms: set[str],
        cue_embedding: "np.ndarray | None" = None,
    ) -> tuple[float, str]:
        facets = schema.facets or {}
        schema_terms = _schema_terms(schema)
        overlap = len(cue_terms & schema_terms) / max(1, len(cue_terms)) if cue_terms else 0.0

        activation = 0.0
        reasons: list[str] = []

        # Geometric cue similarity — primary signal when both embeddings present.
        # Cosine is clamped to [0, 1]: negative scores mean "unrelated", which
        # should not actively suppress (there are explicit penalties for that).
        if cue_embedding is not None and schema.embedding is not None:
            q = np.asarray(cue_embedding, dtype=np.float32)
            v = np.asarray(schema.embedding, dtype=np.float32)
            qn = float(np.linalg.norm(q)) + 1e-12
            vn = float(np.linalg.norm(v)) + 1e-12
            cosine = float(q.dot(v) / (qn * vn))
            cosine_clamped = max(0.0, cosine)
            activation += 0.40 * cosine_clamped
            reasons.append(f"cosine={cosine_clamped:.2f}")

        # Lexical overlap — full weight as fallback when embeddings absent,
        # reduced to a complement signal when the cosine path is active.
        lexical_weight = 0.15 if (cue_embedding is not None and schema.embedding is not None) else 0.40
        if overlap:
            activation += lexical_weight * overlap
            reasons.append(f"cue_overlap={overlap:.2f}")

        # Identity prior: query-independent bonuses accumulate separately and
        # are capped at _IDENTITY_BONUS_CAP so relevance (cosine + overlap)
        # always dominates ranking.
        prior = 0.0

        salience = min(1.0, max(0.0, float(schema.salience) / 20.0))
        prior += 0.15 * salience
        reasons.append(f"salience={salience:.2f}")

        schema_class = _lower(facets.get("schema_class"))
        if schema_class in {"preference", "interaction_preference", "constraint"}:
            prior += 0.12
            reasons.append(schema_class)
        elif schema_class in {"decision", "lesson", "habit", "fact", "procedure", "warning"}:
            prior += 0.07
            reasons.append(schema_class)

        stability = _lower(facets.get("stability"))
        if stability in {"current", "recurring"}:
            prior += 0.08
            reasons.append(f"stability={stability}")

        # schema_utility: composite of stability_score + recurrence_score.
        # High-utility schemas (frequently recalled AND old/well-supported) get
        # a modest activation bonus. Capped at 0.12 so it tilts ties, not dominates.
        schema_utility = float(facets.get("schema_utility") or 0.0)
        if schema_utility > 0.0:
            utility_bonus = round(min(0.12, schema_utility * 0.15), 4)
            prior += utility_bonus
            reasons.append(f"utility={schema_utility:.2f}")

        layer = _lower(facets.get("memory_layer"))
        if layer == "profile":
            prior += 0.12
            reasons.append("profile")
        elif layer in {"domain", "workspace"}:
            prior += 0.06
            reasons.append(layer)

        source_kind = _source_kind(facets)
        if source_kind == "explicit_remember":
            prior += 0.12
            reasons.append("explicit")
        elif source_kind in {"assistant_summary", "tool_result_summary"}:
            activation -= 0.30
            reasons.append(f"inhibit:{source_kind}")

        activation += min(_IDENTITY_BONUS_CAP, prior)

        # Scope bonus: added AFTER the cap so same-scope and global schemas are
        # never starved below min_activation by the identity ceiling.  Without
        # this, a generic query with low cosine can push every schema below the
        # 0.20 floor even though scope-matched and global schemas belong there.
        if cue.scope and schema.scope_id == cue.scope:
            activation += 0.20
            reasons.append(f"scope_match={cue.scope}")
        elif not schema.scope_id:
            activation += 0.15
            reasons.append("global")

        if cue.scope and schema.scope_id and schema.scope_id != cue.scope:
            # Stage 11: graduated penalty for cross-scope generalization.
            # Stage 2 (contextual) gets a reduced mismatch penalty.
            # Stage 3 (global) gets no mismatch penalty at all.
            # Stage 0/1 keep the full penalty (stage 1 is already gated by scope_kind in _eligible).
            _gs = getattr(schema, "generalization_stage", 0)
            if _gs >= 3:
                pass  # global — no mismatch penalty
            elif _gs == 2:
                activation -= 0.12  # contextual — reduced penalty (~1/3 of normal)
                reasons.append("scope_mismatch:stage2")
            else:
                activation -= 0.35
                reasons.append("scope_mismatch")

        if len(schema.content_text or "") > 500:
            activation -= 0.12
            reasons.append("verbose_inhibition")
        if "Assistant:" in (schema.content_text or ""):
            activation -= 0.15
            reasons.append("assistant_text_inhibition")

        # Feedback-driven noise penalty: context_noise_score is maintained at
        # consolidation time from shown/used/irrelevant counts.
        noise = float(facets.get("context_noise_score") or 0.0)
        if noise > 0.0:
            activation -= _NOISE_PENALTY_WEIGHT * noise
            reasons.append(f"noise={noise:.2f}")

        return activation, ",".join(reasons) if reasons else "baseline"


def _lower(value: Any) -> str:
    return str(value or "").strip().lower()


def _source_kind(facets: dict[str, Any]) -> str:
    return _lower(facets.get("source_kind") or facets.get("source"))


def _terms(text: str) -> set[str]:
    terms = set()
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_/-]{2,}", text.lower()):
        token = token.strip("_-/")
        if token and token not in _STOPWORDS:
            terms.add(token)
            terms.add(_normalize_token(token))
            for part in re.split(r"[_/-]+", token):
                if len(part) >= 3 and part not in _STOPWORDS:
                    terms.add(part)
                    terms.add(_normalize_token(part))
    return terms


def _normalize_token(token: str) -> str:
    """Tiny no-dependency normalization for lexical cue overlap.

    Embeddings handle real semantic matching when available. This conservative
    fallback only catches common morphology such as meal/meals and plan/planning
    for encoder-free MCP/context calls.
    """
    t = token.strip().lower()
    if len(t) > 5 and t.endswith("ing"):
        stem = t[:-3]
        if len(stem) > 2 and stem[-1] == stem[-2]:
            stem = stem[:-1]
        return stem
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        return t[:-1]
    return t


def _cue_terms(cue: MemoryCue) -> set[str]:
    return _terms(
        " ".join(
            [
                cue.query or "",
                cue.scope or "",
                cue.goal or "",
                cue.task_type or "",
                " ".join(f"{k} {v}" for k, v in sorted(cue.situation.items())),
                " ".join(cue.requirements),
                cue.application or "",
                " ".join(cue.topics),
                " ".join(cue.entities),
            ]
        )
    )


def _schema_terms(schema: Schema) -> set[str]:
    facets = schema.facets or {}
    chunks = [schema.content_text or "", schema.scope_id or "", " ".join(schema.tags)]
    for key in (
        "scope",
        "topics",
        "entities",
        "positive",
        "negative",
        "memory_layer",
    ):
        value = facets.get(key)
        if isinstance(value, list):
            chunks.append(" ".join(str(v) for v in value))
        elif value not in (None, "", {}, []):
            chunks.append(str(value))
    attrs = facets.get("attributes")
    if isinstance(attrs, dict):
        chunks.extend(str(k) for k in attrs.keys())
        chunks.extend(str(v) for v in attrs.values())
    return _terms(" ".join(chunks))


def _looks_like_transcript_summary(text: str) -> bool:
    return "User:" in text and "Assistant:" in text


def _mmr_deduplicate(
    items: list[WorkingMemoryItem], cos_threshold: float = 0.92
) -> list[WorkingMemoryItem]:
    """Remove near-duplicate schemas from the ranked item list.

    Iterates in activation order (highest first). Each candidate is kept only
    if its cosine similarity to every already-kept schema is below cos_threshold.
    Schemas without embeddings are always kept.

    This is context compression, not brain-faithful lateral inhibition. It
    prevents two near-identical schemas from both occupying token budget.
    """
    kept: list[WorkingMemoryItem] = []
    kept_embs: list[np.ndarray] = []
    for item in items:
        emb = item.schema.embedding
        if emb is None or not kept_embs:
            kept.append(item)
            if emb is not None:
                kept_embs.append(np.asarray(emb, dtype=np.float32))
            continue
        v = np.asarray(emb, dtype=np.float32)
        vn = float(np.linalg.norm(v)) + 1e-12
        duplicate = False
        for kv in kept_embs:
            kvn = float(np.linalg.norm(kv)) + 1e-12
            sim = float(v.dot(kv) / (vn * kvn))
            if sim >= cos_threshold:
                duplicate = True
                break
        if not duplicate:
            kept.append(item)
            kept_embs.append(v)
    return kept


def _compact(text: str, max_chars: int) -> str:
    one_line = re.sub(r"\s+", " ", str(text).strip())
    if len(one_line) <= max_chars:
        return one_line
    return one_line[: max(0, max_chars - 1)].rstrip() + "…"


def _apply_budget(items: list[WorkingMemoryItem], policy: GatePolicy) -> list[WorkingMemoryItem]:
    selected: list[WorkingMemoryItem] = []
    used = 0
    for item in items:
        line_len = len(item.text) + 3
        if len(selected) >= policy.max_items:
            break
        if selected and used + line_len > policy.max_chars:
            continue
        selected.append(item)
        used += line_len
    return selected


def _render(items: list[WorkingMemoryItem]) -> str:
    if not items:
        return ""
    return "\n".join(
        f"- [sch_{item.schema.id}] {'(peripheral) ' if item.peripheral else ''}{item.text}"
        for item in items
    )
