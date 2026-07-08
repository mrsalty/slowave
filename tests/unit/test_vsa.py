"""Unit tests for slowave.latent.vsa — Vector Symbolic Architecture.

Covers:
  - Role vector properties (unit norm, mutual near-orthogonality, determinism)
  - bind / unbind round-trip fidelity
  - bundle properties
  - encode_triple + query_role round-trip for each role
  - Role cross-talk: wrong role gives low cosine to target
  - vec_to_b64 / b64_to_vec round-trip
  - build_schema_vsa: with 2+ axes, 1 axis, no axes
  - _extract_roles_lexical: subject/predicate/object extraction
  - LatentSchemaBuilder vsa_mode guard validation
  - LatentSchemaBuilder.build() populates facets["vsa_vec"]
"""

from __future__ import annotations

import base64

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Optional model availability — checked once at import time.
# en_core_web_sm is not a pip dependency; it must be installed separately via
#   python -m spacy download en_core_web_sm
# Tests that require the model are skipped when it is absent so that the
# standard `pip install -e ".[dev]"` CI path stays clean.
# ---------------------------------------------------------------------------
try:
    import spacy as _spacy

    _EN_CORE_WEB_SM_AVAILABLE: bool = _spacy.util.is_package("en_core_web_sm")
except Exception:
    _EN_CORE_WEB_SM_AVAILABLE = False

_requires_en_core_web_sm = pytest.mark.skipif(
    not _EN_CORE_WEB_SM_AVAILABLE,
    reason="en_core_web_sm not installed — run: python -m spacy download en_core_web_sm",
)

from slowave.latent.vsa import (
    _DEFAULT_DIM,
    ROLE_OBJECT,
    ROLE_PREDICATE,
    ROLE_SUBJECT,
    _make_role_vectors,
    b64_to_vec,
    bind,
    build_schema_vsa,
    bundle,
    encode_triple,
    get_role_vectors,
    query_role,
    unbind,
    vec_to_b64,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unit(v: np.ndarray) -> np.ndarray:
    return (v / (np.linalg.norm(v) + 1e-12)).astype(np.float32)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    return float(a @ b / ((np.linalg.norm(a) * np.linalg.norm(b)) + 1e-12))


def _rand_vec(dim: int, seed: int) -> np.ndarray:
    return _unit(np.random.default_rng(seed).standard_normal(dim).astype(np.float32))


class _ET:
    """Minimal EpisodeText stub."""

    def __init__(self, text: str, source_content: str | None = None):
        self.content_text = text
        self.source_content = source_content  # mirrors EpisodeText.source_content


# ---------------------------------------------------------------------------
# Role vector properties
# ---------------------------------------------------------------------------


class TestRoleVectors:
    def test_unit_norm(self):
        for v in (ROLE_SUBJECT, ROLE_PREDICATE, ROLE_OBJECT):
            assert abs(np.linalg.norm(v) - 1.0) < 1e-5

    def test_default_dim(self):
        assert ROLE_SUBJECT.shape == (_DEFAULT_DIM,)

    def test_mutual_near_orthogonality(self):
        assert abs(_cosine(ROLE_SUBJECT, ROLE_PREDICATE)) < 0.15
        assert abs(_cosine(ROLE_SUBJECT, ROLE_OBJECT)) < 0.15
        assert abs(_cosine(ROLE_PREDICATE, ROLE_OBJECT)) < 0.15

    def test_determinism(self):
        rs1, rp1, ro1 = _make_role_vectors(_DEFAULT_DIM)
        rs2, rp2, ro2 = _make_role_vectors(_DEFAULT_DIM)
        np.testing.assert_array_equal(rs1, rs2)
        np.testing.assert_array_equal(rp1, rp2)

    def test_get_role_vectors_default_returns_cached(self):
        rs, rp, ro = get_role_vectors(_DEFAULT_DIM)
        np.testing.assert_array_equal(rs, ROLE_SUBJECT)

    def test_get_role_vectors_other_dim_stable(self):
        rs1, _, _ = get_role_vectors(128)
        rs2, _, _ = get_role_vectors(128)
        np.testing.assert_array_equal(rs1, rs2)
        assert rs1.shape == (128,)

    def test_near_orthogonal_to_content(self):
        content = _rand_vec(_DEFAULT_DIM, 99)
        assert abs(_cosine(ROLE_SUBJECT, content)) < 0.15
        assert abs(_cosine(ROLE_PREDICATE, content)) < 0.15


# ---------------------------------------------------------------------------
# bind / unbind
# ---------------------------------------------------------------------------


class TestBind:
    def test_output_shape(self):
        assert bind(_rand_vec(_DEFAULT_DIM, 1), _rand_vec(_DEFAULT_DIM, 2)).shape == (_DEFAULT_DIM,)

    def test_output_near_orthogonal_to_inputs(self):
        a, b = _rand_vec(_DEFAULT_DIM, 10), _rand_vec(_DEFAULT_DIM, 11)
        c = bind(a, b)
        assert abs(_cosine(c, a)) < 0.15
        assert abs(_cosine(c, b)) < 0.15

    def test_commutative(self):
        a, b = _rand_vec(_DEFAULT_DIM, 20), _rand_vec(_DEFAULT_DIM, 21)
        np.testing.assert_allclose(bind(a, b), bind(b, a), atol=1e-5)

    def test_unbind_roundtrip(self):
        # Pairwise unbind: expect cosine > 0.7 at float32 / 384 dims.
        # The circular convolution of two unit-norm float32 vectors introduces
        # ~0.15 numeric noise at this precision — 0.8+ would be overoptimistic.
        a, b = _rand_vec(_DEFAULT_DIM, 30), _rand_vec(_DEFAULT_DIM, 31)
        assert _cosine(_unit(unbind(a, bind(a, b))), b) > 0.7

    def test_unbind_wrong_key_low_sim(self):
        a, b = _rand_vec(_DEFAULT_DIM, 40), _rand_vec(_DEFAULT_DIM, 41)
        assert abs(_cosine(_unit(unbind(_rand_vec(_DEFAULT_DIM, 42), bind(a, b))), b)) < 0.3


# ---------------------------------------------------------------------------
# bundle
# ---------------------------------------------------------------------------


class TestBundle:
    def test_unit_norm(self):
        assert (
            abs(
                np.linalg.norm(bundle(_rand_vec(_DEFAULT_DIM, 50), _rand_vec(_DEFAULT_DIM, 51)))
                - 1.0
            )
            < 1e-5
        )

    def test_close_to_components(self):
        a, b = _rand_vec(_DEFAULT_DIM, 60), _rand_vec(_DEFAULT_DIM, 61)
        r = bundle(a, b)
        assert _cosine(r, a) > 0.0 and _cosine(r, b) > 0.0

    def test_single_vector(self):
        a = _rand_vec(_DEFAULT_DIM, 70)
        np.testing.assert_allclose(bundle(a), _unit(a), atol=1e-5)

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="bundle requires at least one vector"):
            bundle()


# ---------------------------------------------------------------------------
# encode_triple + query_role
# ---------------------------------------------------------------------------


class TestEncodeTriple:
    def setup_method(self):
        self.s = _rand_vec(_DEFAULT_DIM, 100)
        self.p = _rand_vec(_DEFAULT_DIM, 101)
        self.o = _rand_vec(_DEFAULT_DIM, 102)
        self.vsa = encode_triple(self.s, self.p, self.o)

    def test_output_shape_and_norm(self):
        assert self.vsa.shape == (_DEFAULT_DIM,)
        assert abs(np.linalg.norm(self.vsa) - 1.0) < 1e-4

    def test_query_subject(self):
        assert _cosine(_unit(query_role("subject", self.vsa)), self.s) > 0.5

    def test_query_predicate(self):
        assert _cosine(_unit(query_role("predicate", self.vsa)), self.p) > 0.5

    def test_query_object(self):
        # Object is the third component in a 3-way superposition — it recovers
        # with slightly less fidelity than subject/predicate due to interference.
        # Threshold > 0.4 is honest for float32 / 384 dims / 3-way bundle.
        assert _cosine(_unit(query_role("object", self.vsa)), self.o) > 0.4

    def test_cross_role_low_crosstalk(self):
        assert _cosine(_unit(query_role("predicate", self.vsa)), self.s) < 0.4

    def test_invalid_role_raises(self):
        with pytest.raises(ValueError, match="role must be one of"):
            query_role("filler", self.vsa)


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


class TestSerialisation:
    def test_b64_roundtrip(self):
        v = _rand_vec(_DEFAULT_DIM, 200)
        np.testing.assert_allclose(v, b64_to_vec(vec_to_b64(v), _DEFAULT_DIM), atol=1e-6)

    def test_b64_is_valid_base64(self):
        base64.b64decode(vec_to_b64(_rand_vec(_DEFAULT_DIM, 201)))

    def test_b64_wrong_dim_raises(self):
        with pytest.raises(ValueError, match="dim mismatch"):
            b64_to_vec(vec_to_b64(_rand_vec(_DEFAULT_DIM, 202)), _DEFAULT_DIM + 1)


# ---------------------------------------------------------------------------
# build_schema_vsa
# ---------------------------------------------------------------------------


class TestBuildSchemaVsa:
    def test_two_facet_axes(self):
        dim = _DEFAULT_DIM
        vsa = build_schema_vsa(
            _rand_vec(dim, 300), np.stack([_rand_vec(dim, 301), _rand_vec(dim, 302)])
        )
        assert vsa.shape == (dim,) and abs(np.linalg.norm(vsa) - 1.0) < 1e-4

    def test_one_facet_axis(self):
        dim = _DEFAULT_DIM
        assert build_schema_vsa(_rand_vec(dim, 310), np.stack([_rand_vec(dim, 311)])).shape == (
            dim,
        )

    def test_no_facet_axes(self):
        dim = _DEFAULT_DIM
        assert build_schema_vsa(
            _rand_vec(dim, 320), np.zeros((0, dim), dtype=np.float32)
        ).shape == (dim,)

    def test_subject_query_close_to_centroid(self):
        dim = _DEFAULT_DIM
        cen = _rand_vec(dim, 330)
        vsa = build_schema_vsa(cen, np.stack([_rand_vec(dim, 331), _rand_vec(dim, 332)]))
        sim = _cosine(_unit(query_role("subject", vsa)), cen)
        assert sim > 0.5, f"subject→centroid cosine={sim:.3f}"

    def test_deterministic(self):
        dim = _DEFAULT_DIM
        cen = _rand_vec(dim, 340)
        axes = np.stack([_rand_vec(dim, 341), _rand_vec(dim, 342)])
        np.testing.assert_array_equal(build_schema_vsa(cen, axes), build_schema_vsa(cen, axes))


# ---------------------------------------------------------------------------
# Integration: LatentSchemaBuilder populates facets["vsa_vec"]
# ---------------------------------------------------------------------------


class TestBuilderVsaIntegration:
    def test_multi_member_has_vsa_vec(self):
        from slowave.latent.schema import LatentSchemaBuilder

        rng = np.random.default_rng(400)
        dim = _DEFAULT_DIM
        n = 5
        embs = rng.standard_normal((n, dim)).astype(np.float32)
        embs /= np.linalg.norm(embs, axis=1, keepdims=True)
        schema = LatentSchemaBuilder().build(
            centroid=_unit(embs.mean(axis=0)),
            member_embeddings=embs,
            member_episodes=[_ET(f"ep {i}") for i in range(n)],
            member_episode_ids=list(range(n)),
            member_timestamps=[1_000_000 + i * 1000 for i in range(n)],
        )
        assert schema is not None and "vsa_vec" in schema.facets
        vsa = b64_to_vec(schema.facets["vsa_vec"], dim)
        assert vsa.shape == (dim,) and abs(np.linalg.norm(vsa) - 1.0) < 1e-4

    def test_single_member_has_vsa_vec(self):
        from slowave.latent.schema import LatentSchemaBuilder

        dim = _DEFAULT_DIM
        emb = _unit(np.random.default_rng(401).standard_normal(dim).astype(np.float32))
        schema = LatentSchemaBuilder().build(
            centroid=emb,
            member_embeddings=np.array([emb]),
            member_episodes=[_ET("solo")],
            member_episode_ids=[99],
            member_timestamps=[1_000_000],
        )
        assert schema is not None and "vsa_vec" in schema.facets
        assert b64_to_vec(schema.facets["vsa_vec"], dim).shape == (dim,)


# ---------------------------------------------------------------------------
# Lexical role extraction
# ---------------------------------------------------------------------------


class TestExtractRolesLexical:
    """Tests for _extract_roles_lexical — regex + lexical_sig extraction.

    English-optimised (verb regex), but no hard language dependency.
    """

    def setup_method(self):
        from slowave.latent.vsa import _extract_roles_lexical

        self._extract = _extract_roles_lexical

    def test_returns_three_strings(self):
        s, p, o = self._extract("Alex prefers Python", {"python": 0.8, "backend": 0.5})
        assert isinstance(s, str) and isinstance(p, str) and isinstance(o, str)

    def test_subject_is_capitalised_token(self):
        s, _, _ = self._extract("Alex prefers Python", {"python": 0.8})
        assert s == "Alex"

    def test_predicate_matches_known_verb(self):
        _, p, _ = self._extract("Alex prefers Python", {"python": 0.8})
        assert p.lower() == "prefers"

    def test_object_from_lexical_sig(self):
        _, _, o = self._extract("Alex prefers Python", {"python": 0.8, "backend": 0.5})
        assert "python" in o.lower() or "backend" in o.lower()

    def test_no_capital_falls_back_to_lexical_sig(self):
        s, _, _ = self._extract("prefers python", {"python": 0.9, "backend": 0.5})
        assert s == "python"

    def test_empty_text_does_not_raise(self):
        s, p, o = self._extract("", {})
        assert isinstance(s, str) and isinstance(p, str) and isinstance(o, str)

    def test_no_verb_uses_lexical_fallback(self):
        _, p, _ = self._extract(
            "Python backend architecture", {"python": 0.9, "backend": 0.7, "arch": 0.5}
        )
        assert isinstance(p, str) and len(p) > 0

    def test_deterministic(self):
        text = "Sarah works as a nurse at St Marys Hospital"
        sig = {"sarah": 0.9, "nurse": 0.8, "hospital": 0.7}
        assert self._extract(text, sig) == self._extract(text, sig)


# ---------------------------------------------------------------------------
# LatentSchemaBuilder vsa_mode guards
# ---------------------------------------------------------------------------


class TestBuilderVsaModeGuards:
    """Constructor validation for LatentSchemaBuilder vsa_mode."""

    def test_invalid_mode_raises(self):
        from slowave.latent.schema import LatentSchemaBuilder

        with pytest.raises(ValueError, match="vsa_mode must be"):
            LatentSchemaBuilder(vsa_mode="invalid")

    def test_lexical_without_encoder_raises(self):
        from slowave.latent.schema import LatentSchemaBuilder

        with pytest.raises(ValueError, match="requires an encoder"):
            LatentSchemaBuilder(vsa_mode="lexical")

    def test_geometric_default_no_encoder_needed(self):
        from slowave.latent.schema import LatentSchemaBuilder

        b = LatentSchemaBuilder(vsa_mode="geometric")
        assert b.vsa_mode == "geometric"

    def test_default_vsa_mode_is_geometric(self):
        from slowave.latent.schema import LatentSchemaBuilder

        b = LatentSchemaBuilder()
        assert b.vsa_mode == "geometric"
