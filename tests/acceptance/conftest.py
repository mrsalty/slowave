"""Acceptance test configuration.

The end-to-end tests are stateful: each phase builds on the DB state left
by the previous one and MUST run in definition order.

Run with:
    pytest tests/acceptance/ -v -p no:randomly
or simply:
    pytest tests/acceptance/test_e2e.py -v
"""

import pytest


def pytest_collection_modifyitems(config, items):
    """Re-sort acceptance tests back to definition order after any randomisation."""
    acceptance = [i for i in items if i.fspath.dirpath().basename == "acceptance"]
    if len(acceptance) < 2:
        return
    acceptance.sort(key=lambda i: (str(i.fspath), i.function.__code__.co_firstlineno))
    non_acceptance = [i for i in items if i.fspath.dirpath().basename != "acceptance"]
    items[:] = non_acceptance + acceptance


_PHASES: dict[str, str] = {
    "test_phase0_register_scopes": "Phase  0 — Register 10 scopes",
    "test_phase1_inject_dataset": "Phase  1 — Ingest dataset + cross-scope remember L1",
    "test_phase2_context_ranking": "Phase  2 — Context ranking (P@1 = 3/3)",
    "test_phase3_recall": "Phase  3 — Semantic recall + cross-scope isolation",
    "test_phase4_demotion": "Phase  4 — Noise demotion (S1 → needs_review)",
    "test_phase5_consolidation_hygiene": "Phase  5 — Consolidation hygiene (no duplicates)",
    "test_phase6_promotion_ladder": "Phase  6 — Promotion ladder (0 → 1 → 2 → 3)",
    "test_phase7_decay": "Phase  7 — Salience decay",
    "test_relations_schema_evidence": "Relations — Schema evidence links",
    "test_relations_cross_scope_isolation": "Relations — Cross-scope isolation",
    "test_relations_supersession": "Relations — Supersession edges",
    "test_relations_coactivation": "Relations — Co-activation edges",
}


def pytest_runtest_logstart(nodeid: str, location) -> None:
    """Print a one-line phase description before each acceptance test."""
    test_name = nodeid.split("::")[-1]
    desc = _PHASES.get(test_name)
    if desc:
        print(f"\n  {desc}", flush=True)
