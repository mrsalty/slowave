"""Tests for stability_score, recurrence_score, schema_utility, and decay_unused."""
from __future__ import annotations

import os
import tempfile
import time

import numpy as np

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine


def _tmp_engine() -> tuple[SlowaveEngine, str]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    cfg = SlowaveConfig(db_path=tmp.name, dim=8, disable_encoder=True)
    return SlowaveEngine(cfg), tmp.name


def _cleanup(path: str) -> None:
    for ext in ("", "-wal", "-shm"):
        p = path + ext
        if os.path.exists(p):
            os.remove(p)


def _create_schema(eng: SlowaveEngine, text: str, *, explicit: bool = False) -> int:
    rng = np.random.default_rng(42)
    emb = rng.normal(size=(8,)).astype(np.float32)
    emb /= np.linalg.norm(emb) + 1e-12
    facets: dict = {}
    if explicit:
        facets["source_kind"] = "explicit_remember"
    return eng.schemas.create(
        content_text=text,
        facets=facets,
        tags=[],
        embedding=emb,
        confidence=1.0,
        salience=1.0,
    )


class TestStabilityScore:
    def test_brand_new_schema_has_low_stability(self) -> None:
        eng, path = _tmp_engine()
        try:
            sid = _create_schema(eng, "brand new memory")
            eng.schemas.reinforce(sid, amount=0.01)
            s = eng.schemas.get(sid)
            stability = s.facets.get("stability_score", None)
            assert stability is not None
            assert stability < 0.3, f"Expected low stability for new schema, got {stability}"
        finally:
            eng.close()
            _cleanup(path)

    def test_stability_score_between_0_and_1(self) -> None:
        eng, path = _tmp_engine()
        try:
            sid = _create_schema(eng, "some claim")
            eng.schemas.reinforce(sid, amount=0.01)
            s = eng.schemas.get(sid)
            score = s.facets.get("stability_score", -1)
            assert 0.0 <= score <= 1.0
        finally:
            eng.close()
            _cleanup(path)

    def test_stability_increases_with_more_supports(self) -> None:
        eng, path = _tmp_engine()
        try:
            sid = _create_schema(eng, "a well-supported claim")
            eng.schemas.reinforce_schema(sid, supporting_episode_ids=list(range(1, 12)))
            s = eng.schemas.get(sid)
            score = s.facets.get("stability_score", 0.0)
            assert score > 0.25
        finally:
            eng.close()
            _cleanup(path)


class TestRecurrenceScore:
    def test_zero_recurrence_on_fresh_schema(self) -> None:
        eng, path = _tmp_engine()
        try:
            sid = _create_schema(eng, "a fresh claim")
            s = eng.schemas.get(sid)
            assert s.facets.get("recurrence_count", 0) == 0
        finally:
            eng.close()
            _cleanup(path)

    def test_recurrence_count_increments_on_reinforce(self) -> None:
        eng, path = _tmp_engine()
        try:
            sid = _create_schema(eng, "recalled claim")
            eng.schemas.reinforce(sid, amount=0.01)
            eng.schemas.reinforce(sid, amount=0.01)
            s = eng.schemas.get(sid)
            assert s.facets.get("recurrence_count") == 2
        finally:
            eng.close()
            _cleanup(path)

    def test_recurrence_score_formula(self) -> None:
        eng, path = _tmp_engine()
        try:
            sid = _create_schema(eng, "another claim")
            for _ in range(5):
                eng.schemas.reinforce(sid, amount=0.01)
            s = eng.schemas.get(sid)
            count = s.facets.get("recurrence_count", 0)
            expected = round(count / (count + 5.0), 4)
            assert s.facets.get("recurrence_score") == expected
        finally:
            eng.close()
            _cleanup(path)

    def test_reinforce_schema_does_not_bump_recurrence(self) -> None:
        eng, path = _tmp_engine()
        try:
            sid = _create_schema(eng, "consolidation target")
            eng.schemas.reinforce_schema(sid, supporting_episode_ids=[1, 2])
            s = eng.schemas.get(sid)
            assert s.facets.get("recurrence_count", 0) == 0
        finally:
            eng.close()
            _cleanup(path)


class TestSchemaUtility:
    def test_utility_is_composite(self) -> None:
        eng, path = _tmp_engine()
        try:
            sid = _create_schema(eng, "utility test claim")
            eng.schemas.reinforce(sid, amount=0.01)
            s = eng.schemas.get(sid)
            stability = s.facets.get("stability_score", 0.0)
            recurrence = s.facets.get("recurrence_score", 0.0)
            expected = round(0.5 * stability + 0.5 * recurrence, 4)
            assert s.facets.get("schema_utility") == expected
        finally:
            eng.close()
            _cleanup(path)

    def test_utility_between_0_and_1(self) -> None:
        eng, path = _tmp_engine()
        try:
            sid = _create_schema(eng, "bounded utility claim")
            for _ in range(10):
                eng.schemas.reinforce(sid, amount=0.01)
            s = eng.schemas.get(sid)
            utility = s.facets.get("schema_utility", -1)
            assert 0.0 <= utility <= 1.0
        finally:
            eng.close()
            _cleanup(path)



class TestDecayUnused:
    def _backdate(self, eng: SlowaveEngine, sid: int, days: int) -> None:
        conn = eng.db.connect()
        conn.execute(
            "UPDATE schemas SET first_formed_ts = ? WHERE id = ?",
            (int(time.time()) - days * 86400, sid),
        )
        conn.commit()

    def test_dry_run_does_not_mutate(self) -> None:
        eng, path = _tmp_engine()
        try:
            sid = _create_schema(eng, "idle schema")
            self._backdate(eng, sid, 40)
            before = eng.schemas.get(sid).salience
            result = eng.schemas.decay_unused(idle_days=30.0, dry_run=True)
            after = eng.schemas.get(sid).salience
            assert result["dry_run"] is True
            assert result["decayed"] >= 1
            assert before == after
        finally:
            eng.close()
            _cleanup(path)

    def test_decay_reduces_salience(self) -> None:
        eng, path = _tmp_engine()
        try:
            sid = _create_schema(eng, "never recalled")
            self._backdate(eng, sid, 40)
            before = eng.schemas.get(sid).salience
            eng.schemas.decay_unused(idle_days=30.0, dry_run=False)
            after = eng.schemas.get(sid).salience
            assert after < before
        finally:
            eng.close()
            _cleanup(path)

    def test_explicit_remember_not_decayed(self) -> None:
        eng, path = _tmp_engine()
        try:
            sid = _create_schema(eng, "explicit user memory", explicit=True)
            self._backdate(eng, sid, 40)
            before = eng.schemas.get(sid).salience
            result = eng.schemas.decay_unused(idle_days=30.0, dry_run=False)
            after = eng.schemas.get(sid).salience
            assert before == after
            assert result["decayed"] == 0
        finally:
            eng.close()
            _cleanup(path)

    def test_recalled_schema_not_decayed(self) -> None:
        eng, path = _tmp_engine()
        try:
            sid = _create_schema(eng, "recalled at least once")
            eng.schemas.reinforce(sid, amount=0.01)
            self._backdate(eng, sid, 40)
            before = eng.schemas.get(sid).salience
            eng.schemas.decay_unused(idle_days=30.0, dry_run=False)
            after = eng.schemas.get(sid).salience
            assert after == before
        finally:
            eng.close()
            _cleanup(path)

    def test_fresh_schema_not_decayed(self) -> None:
        eng, path = _tmp_engine()
        try:
            sid = _create_schema(eng, "just created today")
            before = eng.schemas.get(sid).salience
            eng.schemas.decay_unused(idle_days=30.0, dry_run=False)
            after = eng.schemas.get(sid).salience
            assert after == before
        finally:
            eng.close()
            _cleanup(path)

    def test_flags_needs_review_below_threshold(self) -> None:
        eng, path = _tmp_engine()
        try:
            sid = _create_schema(eng, "low salience idle")
            conn = eng.db.connect()
            conn.execute(
                "UPDATE schemas SET salience = 0.35, first_formed_ts = ? WHERE id = ?",
                (int(time.time()) - 40 * 86400, sid),
            )
            conn.commit()
            result = eng.schemas.decay_unused(
                idle_days=30.0, decay_amount=0.15, review_threshold=0.30, dry_run=False,
            )
            s = eng.schemas.get(sid)
            assert s.needs_review is True
            assert result["flagged_review"] >= 1
        finally:
            eng.close()
            _cleanup(path)


class TestConsolidateOnceIncludesDecay:
    def test_consolidate_once_returns_decay_key(self) -> None:
        eng, path = _tmp_engine()
        try:
            result = eng.consolidate_once()
            assert "decay" in result
            assert "decayed" in result["decay"]
            assert "flagged_review" in result["decay"]
        finally:
            eng.close()
            _cleanup(path)

