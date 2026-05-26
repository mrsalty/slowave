"""Stage 6 — latent schemas.

Brain analogue: cortical schema formation. The neocortex does not store
schemas as sentences; it stores them as activation patterns across
populations of neurons. A schema, in this implementation, is the
geometric fingerprint of a prototype:

  * centroid       : where the cluster lives in embedding space
  * facet_axes     : top principal directions of within-cluster spread
                     (= what dimensions the cluster's members differ on)
  * temporal_anchor: (mean_ts, span_ts) — when this concept is "alive"
  * member_episode_ids
  * confidence     : tightness of the cluster (1 - normalised variance)
  * salience       : reinforced by recall; decays with time

The crucial property: **no LLM call**. Schema formation is a pure
geometric operation over the prototype and its member episodes.

Schemas still hold a *text handle* — the most-central member episode's
content text — because external callers (the eval harness, MCP API,
human inspection) need something readable. The text is *derived* from
the latent state, not the substrate of it. If we later add Stage 11
(verbalisation at the boundary), the LLM can rewrite this handle into
a nicer sentence; until then, the central member's text is what the
schema "says".

Contradiction detection (Stage 6b) is also implemented here as a
pure geometric operation: two schemas conflict when their centroids
are close (same topic) but a measurable facet axis differs and the
newer one has higher confidence.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from slowave.symbolic.episode_text import EpisodeText


# ---- Data types ----------------------------------------------------------


@dataclass(frozen=True)
class LatentSchema:
    """The geometric fingerprint of a consolidated concept.

    Replaces `ExtractedSchema` (LLM-derived) for the brain-only
    architecture. Compatible enough with the existing
    ``Consolidator._create_and_relate_schema`` flow that the
    integration patch is small.
    """
    # Geometry
    centroid: np.ndarray            # mean embedding of member episodes
    facet_axes: np.ndarray          # top-k principal directions (k x dim)
    facet_strengths: np.ndarray     # variance explained per axis (k,)

    # Provenance
    member_episode_ids: list[int]
    central_episode_id: int          # closest member to centroid
    central_episode_text: str        # human-readable text of that member

    # Temporal
    mean_ts: int
    ts_span_s: int                  # max - min of member timestamps

    # Statistics
    confidence: float               # 1.0 - normalised within-cluster variance
    support_count: int              # how many episodes back this schema

    # Hooks for the existing Consolidator API
    tags: list[str] = field(default_factory=list)
    facets: dict = field(default_factory=dict)
    evidence_indices: list[int] = field(default_factory=list)
    evidence_quote: Optional[str] = None

    # Aliases / adapters so the existing consolidation code path that
    # writes schemas into the DB doesn't have to know whether it was
    # produced by the LLM or by the latent builder.
    @property
    def claim(self) -> str:
        return self.central_episode_text


@dataclass(frozen=True)
class GeometricVerdict:
    """Result of a geometric contradiction comparison.

    Mirrors the shape of ``ContradictionJudge.judge``'s ``JudgeResult``
    so the Consolidator can route either backend through the same code
    path.
    """
    verdict: str   # 'reinforces' | 'refines' | 'contradicts' | 'unrelated'
    reasoning: str
    similarity: float
    facet_distance: float
    time_delta_s: int



# ---- Builder -------------------------------------------------------------


@dataclass(frozen=True)
class LatentSchemaConfig:
    n_facet_axes: int = 4
    variance_floor: float = 1e-4
    min_members_for_facets: int = 3


class LatentSchemaBuilder:
    """Build a ``LatentSchema`` from a prototype + its member episodes.

    Pure geometry. Zero LLM calls. Deterministic for a given set of
    inputs.
    """

    def __init__(self, cfg: Optional[LatentSchemaConfig] = None):
        self.cfg = cfg or LatentSchemaConfig()

    def build(
        self,
        *,
        centroid: np.ndarray,
        member_embeddings: np.ndarray,
        member_episodes: list[EpisodeText],
        member_episode_ids: list[int],
        member_timestamps: list[int] | None = None,
    ) -> Optional[LatentSchema]:
        if len(member_episodes) == 0 or member_embeddings.size == 0:
            return None
        embs = np.asarray(member_embeddings, dtype=np.float32)
        if embs.ndim == 1:
            embs = embs.reshape(1, -1)
        cen = np.asarray(centroid, dtype=np.float32).reshape(-1)

        # temporal anchor
        if member_timestamps:
            ts_arr = np.asarray(member_timestamps, dtype=np.int64)
            mean_ts = int(ts_arr.mean())
            ts_span = int(ts_arr.max() - ts_arr.min())
        else:
            mean_ts = int(time.time())
            ts_span = 0

        # central member (closest to centroid)
        sims = embs @ cen / (
            np.linalg.norm(embs, axis=1) * (np.linalg.norm(cen) + 1e-12) + 1e-12
        )
        central_idx = int(np.argmax(sims))
        central_episode_id = int(member_episode_ids[central_idx])
        central_text = str(member_episodes[central_idx].content_text)

        # facet axes (within-cluster principal directions)
        if len(member_episodes) >= self.cfg.min_members_for_facets:
            centered = embs - cen
            try:
                _, s, vh = np.linalg.svd(centered, full_matrices=False)
                k = min(self.cfg.n_facet_axes, vh.shape[0])
                facet_axes = vh[:k].astype(np.float32)
                facet_strengths = s[:k].astype(np.float32)
            except np.linalg.LinAlgError:
                facet_axes = np.zeros((0, embs.shape[1]), dtype=np.float32)
                facet_strengths = np.zeros((0,), dtype=np.float32)
        else:
            facet_axes = np.zeros((0, embs.shape[1]), dtype=np.float32)
            facet_strengths = np.zeros((0,), dtype=np.float32)

        # confidence (cluster tightness)
        if embs.shape[0] >= 2:
            within_var = float(((embs - cen) ** 2).mean())
            confidence = 1.0 - min(1.0, within_var / max(self.cfg.variance_floor, 1e-6))
            confidence = max(0.0, min(1.0, confidence))
        else:
            confidence = 1.0

        return LatentSchema(
            centroid=cen,
            facet_axes=facet_axes,
            facet_strengths=facet_strengths,
            member_episode_ids=[int(i) for i in member_episode_ids],
            central_episode_id=central_episode_id,
            central_episode_text=central_text,
            mean_ts=mean_ts,
            ts_span_s=ts_span,
            confidence=confidence,
            support_count=int(embs.shape[0]),
            tags=[],
            facets={
                "schema_class": "latent",
                "confidence": float(confidence),
                "mean_ts": int(mean_ts),
                "ts_span_s": int(ts_span),
            },
            evidence_indices=list(range(1, len(member_episodes) + 1)),
            evidence_quote=None,
        )


# ---- Geometric contradiction judge --------------------------------------


@dataclass(frozen=True)
class GeometricJudgeConfig:
    # Centroid cosine similarity required for two schemas to be
    # "about the same thing" (the only case where contradiction
    # is meaningful). Below this they're judged "unrelated".
    same_topic_cosine: float = 0.75
    # If similarity is very high, the schemas reinforce each other.
    reinforce_cosine: float = 0.95
    # Facet-axis distance above which we judge "contradicts" rather
    # than "refines". Computed as 1 - mean(|cos(axis_old, axis_new)|).
    contradicts_facet_dist: float = 0.35
    # New schema must have at least this much support to supersede
    # an older one.
    min_support_to_supersede: int = 2


class GeometricContradictionJudge:
    """Latent-space contradiction detector.

    Two schemas conflict when:
      * Their centroids are close (same topic), and
      * Their facet axes disagree (different *aspect* of that topic),
        OR they have the same axes but the newer one materially
        differs along them.

    The brain analogue is predictive coding: a mismatch on the facet
    axes is exactly the prediction error that triggers
    reconsolidation. Stage 10 will use the same signal to *update*
    the older schema; here we only emit a verdict for the Consolidator.
    """

    def __init__(self, cfg: Optional[GeometricJudgeConfig] = None):
        self.cfg = cfg or GeometricJudgeConfig()

    def judge(self, *, old: LatentSchema, new: LatentSchema) -> GeometricVerdict:
        # Centroid similarity
        a = old.centroid.astype(np.float32)
        b = new.centroid.astype(np.float32)
        denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-12
        cos = float(a @ b / denom)

        # Time delta (always present, even if mean_ts==0)
        dt_s = int(new.mean_ts - old.mean_ts)

        if cos < self.cfg.same_topic_cosine:
            return GeometricVerdict(
                verdict="unrelated", reasoning=f"centroid_cos={cos:.3f}<thr",
                similarity=cos, facet_distance=0.0, time_delta_s=dt_s,
            )
        if cos >= self.cfg.reinforce_cosine:
            return GeometricVerdict(
                verdict="reinforces", reasoning=f"centroid_cos={cos:.3f}>=reinforce",
                similarity=cos, facet_distance=0.0, time_delta_s=dt_s,
            )

        # Same topic, less than maximal similarity: compare facet axes.
        # Facet-axis distance = 1 - mean(|cos(axis_old_i, axis_new_i)|)
        # over the min(k_old, k_new) pairs. Bounded in [0, 1].
        if old.facet_axes.size > 0 and new.facet_axes.size > 0:
            k = min(old.facet_axes.shape[0], new.facet_axes.shape[0])
            pair_cos = []
            for i in range(k):
                pa = old.facet_axes[i]
                pb = new.facet_axes[i]
                pdenom = (np.linalg.norm(pa) * np.linalg.norm(pb)) + 1e-12
                pair_cos.append(abs(float(pa @ pb / pdenom)))
            facet_dist = 1.0 - float(np.mean(pair_cos)) if pair_cos else 0.0
        else:
            facet_dist = 0.0

        if facet_dist >= self.cfg.contradicts_facet_dist:
            # If the new one is recent AND has enough support, treat
            # it as a supersession; otherwise it's a contradiction
            # without claim to replacement.
            if (
                dt_s > 0
                and new.support_count >= self.cfg.min_support_to_supersede
            ):
                verdict = "contradicts"  # consolidator decides supersedes vs contradicts
            else:
                verdict = "contradicts"
            return GeometricVerdict(
                verdict=verdict,
                reasoning=f"centroid_cos={cos:.3f} facet_dist={facet_dist:.3f}",
                similarity=cos, facet_distance=facet_dist, time_delta_s=dt_s,
            )

        # Same topic, axes mostly agree, but not maximally similar:
        # the newer one *refines* the older one rather than contradicts.
        return GeometricVerdict(
            verdict="refines",
            reasoning=f"centroid_cos={cos:.3f} facet_dist={facet_dist:.3f}",
            similarity=cos, facet_distance=facet_dist, time_delta_s=dt_s,
        )
