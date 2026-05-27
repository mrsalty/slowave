"""Working-memory gating for prompt context.

This module is deliberately generic: a coding ``project`` is only one possible
environmental cue.  The gate models the brain-like step between broad long-term
memory activation and the tiny set of memories admitted into active working
context for an agent/chatbot prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class MemoryCue:
    """Current cognitive/environmental cue used to prime memory.

    ``project`` remains useful for coding agents, but it is intentionally just
    one cue among query text, application, topics, and entities.
    """

    query: str | None = None
    project: str | None = None
    application: str | None = None
    topics: tuple[str, ...] = ()
    entities: tuple[str, ...] = ()
    mode: str = "default"  # default | broad | debug


@dataclass(frozen=True)
class GatePolicy:
    """Policy for admitting long-term memories into working context."""

    max_items: int = 8
    max_chars: int = 1800
    max_item_chars: int = 240
    min_activation: float = 0.20
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

            activation, reason = self._activation(schema, cue=cue, cue_terms=cue_terms)
            if activation < policy.min_activation:
                suppressed["below_activation"] = suppressed.get("below_activation", 0) + 1
                traces.append(ActivationTrace(schema.id, activation, reason, False))
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
        selected = _apply_budget(items[: max(policy.max_items * 3, policy.max_items)], policy)
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
        if schema.status != "active":
            return False, "inactive"
        if schema.needs_review and cue.mode != "debug":
            return False, "needs_review"
        if cue.mode == "debug":
            return True, "debug"

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

        return True, "eligible"

    def _activation(
        self,
        schema: Schema,
        *,
        cue: MemoryCue,
        cue_terms: set[str],
    ) -> tuple[float, str]:
        facets = schema.facets or {}
        schema_terms = _schema_terms(schema)
        overlap = len(cue_terms & schema_terms) / max(1, len(cue_terms)) if cue_terms else 0.0

        activation = 0.0
        reasons: list[str] = []

        if overlap:
            activation += 0.40 * overlap
            reasons.append(f"cue_overlap={overlap:.2f}")

        salience = min(1.0, max(0.0, float(schema.salience) / 20.0))
        activation += 0.15 * salience
        reasons.append(f"salience={salience:.2f}")

        schema_class = _lower(facets.get("schema_class"))
        if schema_class in {"preference", "interaction_preference", "constraint"}:
            activation += 0.12
            reasons.append(schema_class)
        elif schema_class in {"decision", "lesson", "habit", "fact"}:
            activation += 0.07
            reasons.append(schema_class)

        stability = _lower(facets.get("stability"))
        if stability in {"current", "recurring"}:
            activation += 0.08
            reasons.append(f"stability={stability}")

        layer = _lower(facets.get("memory_layer"))
        if layer == "profile":
            activation += 0.12
            reasons.append("profile")
        elif layer in {"domain", "workspace"}:
            activation += 0.06
            reasons.append(layer)

        source_kind = _source_kind(facets)
        if source_kind == "explicit_remember":
            activation += 0.12
            reasons.append("explicit")
        elif source_kind in {"assistant_summary", "tool_result_summary"}:
            activation -= 0.30
            reasons.append(f"inhibit:{source_kind}")

        if cue.project and schema.project == cue.project:
            activation += 0.18
            reasons.append(f"project={cue.project}")
        elif cue.project and schema.project and schema.project != cue.project:
            activation -= 0.08
            reasons.append("different_project")

        if len(schema.content_text or "") > 500:
            activation -= 0.12
            reasons.append("verbose_inhibition")
        if "Assistant:" in (schema.content_text or ""):
            activation -= 0.15
            reasons.append("assistant_text_inhibition")

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
                cue.project or "",
                cue.application or "",
                " ".join(cue.topics),
                " ".join(cue.entities),
            ]
        )
    )


def _schema_terms(schema: Schema) -> set[str]:
    facets = schema.facets or {}
    chunks = [schema.content_text or "", schema.project or "", " ".join(schema.tags)]
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
    return "\n".join(f"- [sch_{item.schema.id}] {item.text}" for item in items)
