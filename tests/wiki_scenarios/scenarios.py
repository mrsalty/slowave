"""WikiScenarios: 18 black-box scenarios across 6 capability families.

Ground truth is always a keyword in the answer text — no DB introspection,
no scope parsing.  Pattern: same as tests/temporal_eval/scenarios/*.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.temporal_eval.harness import ScenarioResult, keyword_hit
from tests.wiki_scenarios.harness import WikiHarness
from slowave.symbolic.encoder import TextEncoder


@dataclass
class WikiScenario:
    id: str
    family: str
    description: str
    expected_keyword: str
    anti_keyword: str | None
    requires_consolidation: bool = False


SCENARIOS: list[WikiScenario] = [
    # R: basic retrieval within one domain cluster
    WikiScenario("R-1","retrieval","ML cluster → neural network query","network","Caesar"),
    WikiScenario("R-2","retrieval","Rome cluster → Roman expansion query","military","neuron"),
    WikiScenario("R-3","retrieval","Music cluster → jazz improvisation query","improvisation","photosynthesis"),
    WikiScenario("R-4","retrieval","Controls (bio+phys) → photosynthesis query","chlorophyll","rhythm"),
    # I: two dissimilar clusters ingested together; query must not cross domains
    WikiScenario("I-1","isolation","ML + Music → ML query must not surface music","network","rhythm"),
    WikiScenario("I-2","isolation","Rome + Biology → Rome query must not surface biology","province","mitochondria"),
    WikiScenario("I-3","isolation","Music + Physics → music query must not surface physics","blues","quantum"),
    # G: two similar pages in separate sessions; query should draw from both
    WikiScenario("G-1","generalization","ML + Deep Learning (sep sessions) → architecture query","layer","Caesar",True),
    WikiScenario("G-2","generalization","AncientRome + RomanEmpire (sep sessions) → institutions query","Senate","neuron",True),
    WikiScenario("G-3","generalization","Jazz + Blues (sep sessions, 7d gap) → origins query","African","chlorophyll",True),
    # D: older page at t=0, newer page at t=N; recency should dominate
    WikiScenario("D-1","decay","ML at t=0, Deep Learning at t=30d → prefer newer","deep","Caesar"),
    WikiScenario("D-2","decay","AncientRome at t=0, JuliusCaesar at t=14d → prefer Caesar","Caesar","neuron"),
    WikiScenario("D-3","decay","Blues at t=0, Jazz at t=14d → prefer newer jazz","jazz","chlorophyll"),
    # S: remember() v1, then v2 with "now uses" pattern to trigger supersession
    WikiScenario("S-1","supersession","ML context + gradient-descent→Adam fact update","Adam",None,True),
    WikiScenario("S-2","supersession","Rome context + republic→imperial fact update","imperial",None,True),
    # C: indirect-cue completion — query matches one page aspect; graph bridges to fact
    WikiScenario("C-1","completion","Rome page + Thermacrete fact (chemistry vs military query)","Thermacrete","neuron",True),
    WikiScenario("C-2","completion","ANN page + NeuroSync fact (hardware vs algorithm query)","NeuroSync","Caesar",True),
    WikiScenario("C-3","completion","Jazz page + ChromaShift fact (notation vs performance query)","ChromaShift","chlorophyll",True),
]

assert len(SCENARIOS) == 18


# ---------------------------------------------------------------------------
# RUNNER
# ---------------------------------------------------------------------------

def run_scenario(scenario: WikiScenario, *, shared_enc: TextEncoder,
                 ablation: str = "full", tau_days: float = 7.0) -> ScenarioResult:
    """Run one scenario in a fresh harness, return ScenarioResult."""
    h = WikiHarness(shared_encoder=shared_enc,
                    consolidate=scenario.requires_consolidation,
                    tau_days=tau_days, ablation=ablation)
    detail: dict[str, Any] = {}
    try:
        hyp = _dispatch(scenario, h, detail)
    finally:
        h.close()
    hit = keyword_hit(hyp, scenario.expected_keyword)
    if scenario.anti_keyword:
        hit = hit and not keyword_hit(hyp, scenario.anti_keyword)
    return ScenarioResult(
        scenario_id=scenario.id, description=scenario.description,
        component=scenario.family, expected_keyword=scenario.expected_keyword,
        hypothesis=hyp[:500], hit=hit, detail=detail,
    )


def _dispatch(s: WikiScenario, h: WikiHarness, d: dict) -> str:
    return {"retrieval": _retrieval, "isolation": _isolation,
            "generalization": _generalization, "decay": _decay,
            "supersession": _supersession, "completion": _completion}[s.family](s, h, d)


_R_PAGES = {
    "R-1": ["Machine_learning","Deep_learning","Artificial_neural_network"],
    "R-2": ["Ancient_Rome","Roman_Empire","Julius_Caesar"],
    "R-3": ["Jazz","Blues","Improvisation"],
    "R-4": ["Cell_(biology)","Photosynthesis","Quantum_mechanics"],
}
_R_QUERIES = {
    "R-1": "How do neural networks learn representations?",
    "R-2": "How did Rome expand its empire?",
    "R-3": "What is the role of improvisation in jazz?",
    "R-4": "What is the role of chlorophyll in photosynthesis?",
}

def _retrieval(s: WikiScenario, h: WikiHarness, d: dict) -> str:
    for p in _R_PAGES[s.id]:
        d[f"n_{p}"] = h.ingest_page(p)
    result = h.query(_R_QUERIES[s.id], top_k=10)
    d["n_schemas"] = h.n_schemas()
    return h.build_hypothesis(result)


_I_SETUP: dict[str, tuple] = {
    "I-1": (["Machine_learning","Deep_learning","Artificial_neural_network"],
            ["Jazz","Blues","Improvisation"],
            "How do machines learn patterns from data?"),
    "I-2": (["Ancient_Rome","Roman_Empire","Julius_Caesar"],
            ["Cell_(biology)","Photosynthesis"],
            "How did Rome govern its provinces?"),
    "I-3": (["Jazz","Blues","Improvisation"],
            ["Quantum_mechanics"],
            "What is the history of blues music?"),
}

def _isolation(s: WikiScenario, h: WikiHarness, d: dict) -> str:
    target, noise, query = _I_SETUP[s.id]
    for p in target + noise:
        h.ingest_page(p)
    result = h.query(query, top_k=10)
    d["n_schemas"] = h.n_schemas()
    return h.build_hypothesis(result)


_G_SETUP: dict[str, tuple] = {
    "G-1": (["Machine_learning"],  ["Deep_learning"],  7,
            "What are common architectures used in machine learning?"),
    "G-2": (["Ancient_Rome"],      ["Roman_Empire"],   7,
            "What were Roman political institutions?"),
    "G-3": (["Jazz"],              ["Blues"],          7,
            "What are the origins of American popular music?"),
}

def _generalization(s: WikiScenario, h: WikiHarness, d: dict) -> str:
    pages_a, pages_b, gap, query = _G_SETUP[s.id]
    for p in pages_a:
        h.ingest_page(p, consolidate=True)
    h.advance(gap)
    for p in pages_b:
        h.ingest_page(p, consolidate=True)
    h.advance(1)
    result = h.query(query, top_k=10)
    d["n_schemas"] = h.n_schemas()
    return h.build_hypothesis(result)


_D_SETUP: dict[str, tuple] = {
    "D-1": ("Machine_learning", "Deep_learning", 30,
            "What is the cutting edge of machine learning?"),
    "D-2": ("Ancient_Rome",     "Julius_Caesar", 14,
            "Who was a famous Roman ruler?"),
    "D-3": ("Blues",            "Jazz",          14,
            "What style of music uses improvisation?"),
}

def _decay(s: WikiScenario, h: WikiHarness, d: dict) -> str:
    old_p, new_p, gap, query = _D_SETUP[s.id]
    h.ingest_page(old_p)
    h.advance(gap)
    h.ingest_page(new_p)
    h.advance(1)
    result = h.query(query, top_k=10)
    d["sal_expected"] = round(h.salience_of(s.expected_keyword), 4)
    if s.anti_keyword:
        d["sal_anti"] = round(h.salience_of(s.anti_keyword), 4)
    d["n_schemas"] = h.n_schemas()
    return h.build_hypothesis(result)


# "now uses" triggers pattern 1 in slowave/core/supersession.py
_S_SETUP: dict[str, dict] = {
    "S-1": {
        "context": ["Machine_learning", "Deep_learning"],
        "v1": "machine learning now uses gradient descent for optimisation",
        "v2": "machine learning now uses Adam optimiser instead of gradient descent",
        "query": "What optimisation method is used in machine learning?",
        "v1_kw": "gradient descent",
    },
    "S-2": {
        "context": ["Ancient_Rome", "Roman_Empire"],
        "v1": "Rome now uses a Senate-led republic as its governing structure",
        "v2": "Rome now uses imperial autocracy instead of the republic",
        "query": "What was the governing structure of Rome?",
        "v1_kw": "republic",
    },
}

def _supersession(s: WikiScenario, h: WikiHarness, d: dict) -> str:
    cfg = _S_SETUP[s.id]
    for p in cfg["context"]:
        h.ingest_page(p, consolidate=True)
    v1_result = h.eng.remember(content=cfg["v1"], type="fact",
                               scope="wikiscenarios:supersession_test")
    h.advance(1)
    v2_result = h.eng.remember(content=cfg["v2"], type="fact",
                               scope="wikiscenarios:supersession_test")
    h.advance(0)
    h.eng.refresh_indices()
    result = h.query(cfg["query"], top_k=10)
    hyp = h.build_hypothesis(result)
    # Check if the *specific* v1 schema is still active (not whether any
    # active schema contains the v1 keyword — the v2 schema itself may
    # mention the old value in its "instead of" clause, and Wikipedia
    # page schemas may contain the keyword in broad text).
    try:
        v1_schema = h.eng.schemas.get(v1_result.schema_id)
        v1_still_active = v1_schema.status == "active"
        v1_status = v1_schema.status
    except KeyError:
        v1_still_active = False
        v1_status = "missing"
    d["v1_kw_still_active"] = v1_still_active
    d["v1_schema_id"] = v1_result.schema_id
    d["v1_status"] = v1_status
    d["v2_superseded_ids"] = v2_result.superseded_schema_ids
    d["n_schemas"] = h.n_schemas()
    return hyp


# Indirect-cue completion: a fact about one aspect of the Wikipedia page
# domain is stored in a separate consolidate=True session (so it gets a
# prototype mapping).  The query targets a DIFFERENT aspect of the page,
# producing a low cosine overlap with the fact.  Graph spreading activation
# is the only path that can surface the fact through prototype edges.
#
# Design notes (2026-06-17):
#   - remember() schemas have NO prototype mapping (schema_prototype_map
#     empty) — the graph path via get_many_by_prototypes is a dead end.
#   - The fact MUST be ingested via a consolidate=True session to get
#     prototype assignment.
#   - Even with correct prototype mapping, the graph currently contributes
#     zero measurable boost at Wikipedia scale — see P3 analysis.
#   - These scenarios serve as a measurement baseline.  Expected:
#     hit=False in both full and no_graph.  Any hit=True under full only
#     would be evidence graph improvement.
_C_SETUP: dict[str, dict] = {
    "C-1": {
        "context": ["Ancient_Rome"],
        # Fact about Roman chemistry (different aspect from military query)
        "fact": "The Thermacrete formula requires precise heating of volcanic materials to 900 degrees.",
        # Query about military expansion (different aspect from chemistry fact)
        "query": "How did Roman soldiers build defensive fortifications during military campaigns?",
    },
    "C-2": {
        "context": ["Artificial_neural_network"],
        # Fact about hardware (different aspect from algorithm query)
        "fact": "NeuroSync accelerators use custom ASIC chips for parallel computation.",
        "query": "How do errors propagate through the layers of a neural network?",
    },
    "C-3": {
        "context": ["Jazz"],
        # Fact about notation (different aspect from performance query)
        "fact": "ChromaShift manuscript paper uses coloured ink for different harmonic regions.",
        "query": "How do jazz musicians create spontaneous melodies during solos?",
    },
}

def _completion(s: WikiScenario, h: WikiHarness, d: dict) -> str:
    """Indirect-cue completion: ingest page + fact in separate consolidate=True
    sessions so both get prototype mappings.  The query targets a different
    page aspect than the fact, producing a low cosine gap that graph
    spreading activation could theoretically bridge.

    Records diagnostic detail for measuring graph contribution:
      - proto_id: whether the fact schema was assigned a prototype
      - cos_qf:   cosine(query_embedding, fact_embedding)
      - hit:      whether the keyword appears in top-k retrieved results
    """
    cfg = _C_SETUP[s.id]
    for p in cfg["context"]:
        h.ingest_page(p, consolidate=True)
    h.advance(1)
    # Store fact as a separate consolidate=True session so it gets
    # prototype assignment via the latent schema builder.
    h.session([("user", cfg["fact"])], consolidate=True)
    h.advance(0)
    h.eng.refresh_indices()

    # Record cosine distance between query and fact for diagnostics
    try:
        import numpy as np
        q_emb = h.shared_encoder.encode(cfg["query"])
        f_emb = h.shared_encoder.encode(cfg["fact"])
        qn = float(np.linalg.norm(q_emb))
        fn = float(np.linalg.norm(f_emb))
        d["cos_qf"] = round(float(np.dot(q_emb, f_emb) / (qn * fn + 1e-12)), 4)
    except Exception:
        d["cos_qf"] = None

    # Check if fact got a prototype mapping
    try:
        conn = h.eng.db.connect()
        row = conn.execute(
            "SELECT spm.prototype_id FROM schema_prototype_map spm "
            "JOIN schemas sc ON sc.id = spm.schema_id "
            "WHERE sc.content_text LIKE ?",
            (f"%{s.expected_keyword}%",),
        ).fetchone()
        d["proto_id"] = int(row["prototype_id"]) if row else None
    except Exception:
        d["proto_id"] = None

    result = h.query(cfg["query"], top_k=10)
    d["n_schemas"] = h.n_schemas()
    return h.build_hypothesis(result)
