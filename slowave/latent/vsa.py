"""Stage 11 — Vector Symbolic Architecture (VSA) role binding.

**Experimental / internal use.** VSA vectors are stored in schema facets but
are not currently used in retrieval ranking or consolidation decisions.
This module is architecturally sound and retained for future retrieval
experiments, but external claims should not imply VSA materially affects
behavior unless it is connected to a measured retrieval path.

Brain analogue: hippocampal binding. The hippocampus binds arbitrary roles
(who, what, where, when) to content during encoding as a superposition over
cortical representations. This module provides a lightweight, deterministic
algebraic implementation of that process using Holographic Reduced
Representations (HRRs).

Core operations
---------------
bind(a, b)           Circular convolution — produces a vector "encoding a
                     bound to b". Nearly orthogonal to both inputs. Reversible.
unbind(key, result)  Approximate inverse — recovers b from bind(a, b) given a.
bundle(*vecs)        Element-wise sum + L2 normalise — superposition.
encode_triple(s,p,o) Bundle of three role-bound fillers.
query_role(role, v)  Recover the approximate filler for a role from a VSA vec.

Role vectors (Option A)
-----------------------
Three fixed role vectors are generated once from a seeded RNG:
  * Deterministic — same on every machine, every install, forever.
  * Nearly orthogonal to each other and to any real content vector.
  * Stored as module-level constants — zero runtime cost after import.

The seed constant (0x516C6176 = ASCII "Slav") is fixed in code.
Changing it would invalidate all stored VSA vectors.

Storage
-------
VSA vectors are stored in schema facets_json as base64-encoded float32 blobs
under the key "vsa_vec". No schema change required — fully backwards compatible.

VSA modes
---------
Two role-extraction strategies are provided, selectable via
``LatentSchemaBuilder(vsa_mode=...)``:

  "geometric" (default)
      Roles come from the prototype's own geometry: centroid → subject,
      dominant PCA axis → predicate, secondary PCA axis → object.
      No encoder call at consolidation time.  Zero extra dependencies.

  "lexical"
      Roles extracted from the schema's central-episode text via a
      regex-based verb detector + the cluster's lexical signature.
      Requires an encoder (encode_many is called once per schema).
      English-optimised but no language-specific model dependency.
"""

from __future__ import annotations

import base64
import re as _re

import numpy as np

# ---------------------------------------------------------------------------
# Seed constant — never change after 0.1.6 ships.
# ---------------------------------------------------------------------------
_SEED: int = 0x516C6176


def _make_role_vectors(dim: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Generate three fixed role vectors for a given embedding dimension."""
    rng = np.random.default_rng(seed=_SEED)
    vecs = []
    for _ in range(3):
        v = rng.standard_normal(dim).astype(np.float32)
        v /= np.linalg.norm(v) + 1e-12
        vecs.append(v)
    return vecs[0], vecs[1], vecs[2]


# Default dim matches the bge-small-en-v1.5 encoder (384).
_DEFAULT_DIM = 384
ROLE_SUBJECT, ROLE_PREDICATE, ROLE_OBJECT = _make_role_vectors(_DEFAULT_DIM)


def get_role_vectors(dim: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (ROLE_SUBJECT, ROLE_PREDICATE, ROLE_OBJECT) for any dim.

    For dim==384 returns the cached module-level constants.
    For other dims generates a fresh set from the same seed — still
    deterministic and stable across installs.
    """
    if dim == _DEFAULT_DIM:
        return ROLE_SUBJECT, ROLE_PREDICATE, ROLE_OBJECT
    return _make_role_vectors(dim)


# ---------------------------------------------------------------------------
# Core VSA operations
# ---------------------------------------------------------------------------


def bind(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Circular convolution binding.

    bind(a, b) is nearly orthogonal to both a and b.
    Reversible: unbind(a, bind(a, b)) ≈ b.
    FFT-based: O(d log d), exact float32, zero extra dependencies.
    """
    fa = np.fft.rfft(a.astype(np.float64))
    fb = np.fft.rfft(b.astype(np.float64))
    return np.fft.irfft(fa * fb, n=len(a)).astype(np.float32)


def unbind(key: np.ndarray, composite: np.ndarray) -> np.ndarray:
    """Approximate inverse of bind.

    unbind(key, bind(key, value)) ≈ value.
    Uses the complex conjugate of the key's FFT (equivalent to convolving
    with the time-reversed key).
    """
    fkey = np.fft.rfft(key.astype(np.float64))
    fcomp = np.fft.rfft(composite.astype(np.float64))
    return np.fft.irfft(np.conj(fkey) * fcomp, n=len(composite)).astype(np.float32)


def bundle(*vecs: np.ndarray) -> np.ndarray:
    """Superposition: element-wise sum, L2-normalised.

    The result is close (in cosine space) to each input — it represents
    "a OR b OR c" in VSA terms.
    """
    if not vecs:
        raise ValueError("bundle requires at least one vector")
    result = np.sum(np.stack([v.astype(np.float32) for v in vecs], axis=0), axis=0)
    norm = float(np.linalg.norm(result))
    if norm < 1e-12:
        return result
    return (result / norm).astype(np.float32)


# ---------------------------------------------------------------------------
# Schema-level helpers
# ---------------------------------------------------------------------------


def encode_triple(
    subject_vec: np.ndarray,
    predicate_vec: np.ndarray,
    object_vec: np.ndarray,
    *,
    dim: int | None = None,
) -> np.ndarray:
    """Encode a subject-predicate-object triple as a single VSA vector."""
    d = dim or int(subject_vec.shape[0])
    rs, rp, ro = get_role_vectors(d)
    return bundle(
        bind(rs, subject_vec),
        bind(rp, predicate_vec),
        bind(ro, object_vec),
    )


def query_role(
    role: str,
    composite: np.ndarray,
    *,
    dim: int | None = None,
) -> np.ndarray:
    """Recover the approximate filler for a named role from a VSA vector.

    role must be one of "subject", "predicate", "object".

    Example::

        vsa = encode_triple(subj_vec, pred_vec, obj_vec)
        recovered = query_role("subject", vsa)
        # cosine_sim(recovered, subj_vec) should be high (> 0.8)
    """
    d = dim or int(composite.shape[0])
    rs, rp, ro = get_role_vectors(d)
    role_map = {"subject": rs, "predicate": rp, "object": ro}
    if role not in role_map:
        raise ValueError(f"role must be one of {list(role_map)}; got {role!r}")
    return unbind(role_map[role], composite)


# ---------------------------------------------------------------------------
# Serialisation helpers (for facets_json storage)
# ---------------------------------------------------------------------------


def vec_to_b64(vec: np.ndarray) -> str:
    """Encode a float32 vector to a base64 string for JSON storage."""
    return base64.b64encode(vec.astype(np.float32).tobytes()).decode("ascii")


def b64_to_vec(s: str, dim: int) -> np.ndarray:
    """Decode a base64 string back to a float32 vector."""
    raw = base64.b64decode(s)
    vec = np.frombuffer(raw, dtype=np.float32)
    if vec.size != dim:
        raise ValueError(f"VSA vec dim mismatch: expected {dim}, got {vec.size}")
    return vec


# ---------------------------------------------------------------------------
# Schema-builder integration helper
# ---------------------------------------------------------------------------


def build_schema_vsa(
    centroid: np.ndarray,
    facet_axes: np.ndarray,
) -> np.ndarray:
    """Derive a VSA triple vector from a LatentSchema's geometry (geometric mode).

    Heuristic — inputs are geometric artefacts, not semantic roles:
      subject   → centroid        (overall concept embedding)
      predicate → facet_axes[0]   (dominant within-cluster PCA axis)
      object    → facet_axes[1]   (secondary PCA axis)

    Falls back gracefully when facet axes are absent.
    """
    cen = centroid.astype(np.float32)
    dim = cen.shape[0]

    if facet_axes.shape[0] >= 2:
        pred_vec = facet_axes[0].astype(np.float32)
        obj_vec = facet_axes[1].astype(np.float32)
    elif facet_axes.shape[0] == 1:
        pred_vec = facet_axes[0].astype(np.float32)
        obj_vec = np.roll(pred_vec, 1)
    else:
        pred_vec = np.roll(cen, dim // 3)
        obj_vec = np.roll(cen, 2 * (dim // 3))

    return encode_triple(cen, pred_vec, obj_vec, dim=dim)


# ---------------------------------------------------------------------------
# Lexical role extraction (English-optimised; no language-specific model needed)
# ---------------------------------------------------------------------------

_VERB_RE = _re.compile(
    r"\b(is|are|was|were|has|have|had|do|does|did|will|would|should|could|"
    r"can|may|might|prefer|use|work|like|want|need|learn|build|write|run|"
    r"develop|deploy|test|implement|design|create|start|stop|make|get|set|"
    r"keep|begin|show|provide|include|continue|become|follow|allow|add|"
    r"change|lead|understand|watch|turn|open|seem|try|leave|call|help|"
    r"works|uses|likes|wants|needs|prefers|builds|writes|runs|develops|"
    r"\w+ing|\w+ed|\w+ies|\w+izes|\w+ates)\b",
    _re.IGNORECASE,
)


def _extract_roles_lexical(text: str, lexical_sig: dict) -> tuple[str, str, str]:
    """Extract (subject, predicate, object) strings via regex + lexical signature.

    subject:   first capitalised token in text, or top lexical term
    predicate: first verb-pattern match
    object:    remaining top lexical terms not used above
    """
    tokens = _re.findall(r"\b[A-Za-z][a-zA-Z0-9_\-]*\b", text)
    subject = next((t for t in tokens if t[0].isupper() and len(t) > 1), "")
    if not subject:
        subject = (
            list(lexical_sig.keys())[0] if lexical_sig else (tokens[0] if tokens else "entity")
        )
    vm = _VERB_RE.search(text)
    predicate = vm.group(0).lower() if vm else ""
    if not predicate:
        keys = list(lexical_sig.keys())
        predicate = keys[1] if len(keys) >= 2 else "is"
    used = {subject.lower(), predicate.lower()}
    obj_terms = [t for t in lexical_sig.keys() if t.lower() not in used][:3]
    obj = " ".join(obj_terms) if obj_terms else (tokens[-1] if tokens else "thing")
    return subject, predicate, obj


# ---------------------------------------------------------------------------
# Encoder-based VSA builders
# ---------------------------------------------------------------------------


def build_schema_vsa_lexical(
    centroid: np.ndarray,
    text: str,
    lexical_sig: dict,
    encoder,
) -> np.ndarray:
    """VSA using lexical role extraction + TextEncoder. No new dependencies."""
    subj_str, pred_str, obj_str = _extract_roles_lexical(text, lexical_sig)
    vecs = encoder.encode_many([subj_str, pred_str, obj_str])
    return encode_triple(vecs[0], vecs[1], vecs[2])
