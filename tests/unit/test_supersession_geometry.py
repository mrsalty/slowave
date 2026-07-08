"""Supersession geometry test set — domain-general, multilingual.

Covers 8 domains (tech, medical, business, personal, financial, hr, legal,
science) across EN/IT/FR/DE/ES and cross-lingual pairs.

Two uses:
  1. Data source for _run_geometry_investigation.py (imports CASES)
  2. Standalone runner: python tests/unit/test_supersession_geometry.py

The pytest threshold test is marked skip — thresholds are determined by
the investigation script after encoder selection, not hard-coded here.

Run standalone:
  .venv/bin/python tests/unit/test_supersession_geometry.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from slowave.symbolic.encoder import EncoderConfig, TextEncoder


@dataclass
class Case:
    label: str
    old: str
    new: str
    expected_zone: str
    lang: str = "en"
    domain: str = "tech"


# ---------------------------------------------------------------------------
# Test pairs
# ---------------------------------------------------------------------------
CASES: list[Case] = [
    # ── TECH / TOOL ──────────────────────────────────────────────────────────
    # Database switch
    Case(
        "tech/en/db",
        "The project uses SQLite for storage.",
        "The project uses DuckDB for storage.",
        "supersession",
        "en",
        "tech",
    ),
    Case(
        "tech/en/db2",
        "The system stores data in MySQL.",
        "The system stores data in PostgreSQL.",
        "supersession",
        "en",
        "tech",
    ),
    Case(
        "tech/en/db3",
        "Caching is handled by Redis.",
        "Caching is handled by Memcached.",
        "supersession",
        "en",
        "tech",
    ),
    # Language / runtime switch
    Case(
        "tech/en/lang",
        "The backend is written in Python.",
        "The backend is written in Go.",
        "supersession",
        "en",
        "tech",
    ),
    Case(
        "tech/en/lang2",
        "The API is implemented in Java.",
        "The API is implemented in Kotlin.",
        "supersession",
        "en",
        "tech",
    ),
    # Cloud / infra switch
    Case(
        "tech/en/cloud",
        "The service is deployed on AWS.",
        "The service is deployed on GCP.",
        "supersession",
        "en",
        "tech",
    ),
    Case(
        "tech/en/cloud2",
        "CI/CD is handled by Jenkins.",
        "CI/CD is handled by GitHub Actions.",
        "supersession",
        "en",
        "tech",
    ),
    # AI model switch
    Case(
        "tech/en/model",
        "We use GPT-4 as the language model.",
        "We use Claude 3 as the language model.",
        "supersession",
        "en",
        "tech",
    ),
    # Version bump
    Case(
        "tech/en/ver",
        "The app runs on React 17.",
        "The app runs on React 18.",
        "supersession",
        "en",
        "tech",
    ),
    Case(
        "tech/en/ver2",
        "The server runs Ubuntu 20.04.",
        "The server runs Ubuntu 22.04.",
        "supersession",
        "en",
        "tech",
    ),
    # UI preference
    Case(
        "tech/en/pref",
        "The user prefers dark mode in their editor.",
        "The user prefers light mode in their editor.",
        "supersession",
        "en",
        "tech",
    ),
    # Multilingual
    Case(
        "tech/it/db",
        "Il progetto usa SQLite per lo storage.",
        "Il progetto usa DuckDB per lo storage.",
        "supersession",
        "it",
        "tech",
    ),
    Case(
        "tech/it/lang",
        "Il backend è scritto in Python.",
        "Il backend è scritto in Go.",
        "supersession",
        "it",
        "tech",
    ),
    Case(
        "tech/fr/db",
        "Le projet utilise SQLite pour le stockage.",
        "Le projet utilise DuckDB pour le stockage.",
        "supersession",
        "fr",
        "tech",
    ),
    Case(
        "tech/fr/lang",
        "Le backend est écrit en Python.",
        "Le backend est écrit en Go.",
        "supersession",
        "fr",
        "tech",
    ),
    Case(
        "tech/de/db",
        "Das Projekt verwendet SQLite zur Datenspeicherung.",
        "Das Projekt verwendet DuckDB zur Datenspeicherung.",
        "supersession",
        "de",
        "tech",
    ),
    Case(
        "tech/es/db",
        "El proyecto usa SQLite para el almacenamiento.",
        "El proyecto usa DuckDB para el almacenamiento.",
        "supersession",
        "es",
        "tech",
    ),
    Case(
        "tech/cross/en-it",
        "The project uses SQLite for storage.",
        "Il progetto usa DuckDB per lo storage.",
        "supersession",
        "cross",
        "tech",
    ),
    # ── MEDICAL / HEALTH ─────────────────────────────────────────────────────
    Case(
        "med/en/dosage",
        "The patient takes metformin 500 mg daily.",
        "The patient takes metformin 1000 mg daily.",
        "supersession",
        "en",
        "medical",
    ),
    Case(
        "med/en/med",
        "The patient is prescribed lisinopril.",
        "The patient is prescribed amlodipine.",
        "supersession",
        "en",
        "medical",
    ),
    Case(
        "med/en/diag",
        "The patient is diagnosed with hypertension.",
        "The patient is diagnosed with type 2 diabetes.",
        "supersession",
        "en",
        "medical",
    ),
    Case(
        "med/en/doc",
        "The patient's primary physician is Dr. Smith.",
        "The patient's primary physician is Dr. Johnson.",
        "supersession",
        "en",
        "medical",
    ),
    Case(
        "med/en/dosage2",
        "The child receives 250 mg of amoxicillin.",
        "The child receives 500 mg of amoxicillin.",
        "supersession",
        "en",
        "medical",
    ),
    Case(
        "med/it/dosage",
        "Il paziente assume metformina 500 mg al giorno.",
        "Il paziente assume metformina 1000 mg al giorno.",
        "supersession",
        "it",
        "medical",
    ),
    Case(
        "med/it/med",
        "Il paziente è in cura con lisinopril.",
        "Il paziente è in cura con amlodipina.",
        "supersession",
        "it",
        "medical",
    ),
    Case(
        "med/fr/dosage",
        "Le patient prend 500 mg de metformine par jour.",
        "Le patient prend 1000 mg de metformine par jour.",
        "supersession",
        "fr",
        "medical",
    ),
    Case(
        "med/de/dosage",
        "Der Patient nimmt täglich Metformin 500 mg.",
        "Der Patient nimmt täglich Metformin 1000 mg.",
        "supersession",
        "de",
        "medical",
    ),
    Case(
        "med/cross/en-it",
        "The patient takes metformin 500 mg daily.",
        "Il paziente assume metformina 1000 mg al giorno.",
        "supersession",
        "cross",
        "medical",
    ),
    # ── BUSINESS / CRM ───────────────────────────────────────────────────────
    Case(
        "biz/en/am",
        "The account manager for Acme Corp is Alice.",
        "The account manager for Acme Corp is Bob.",
        "supersession",
        "en",
        "business",
    ),
    Case(
        "biz/en/stage",
        "The deal is in the negotiation stage.",
        "The deal is in the closing stage.",
        "supersession",
        "en",
        "business",
    ),
    Case(
        "biz/en/contact",
        "The primary contact at Acme is the CEO.",
        "The primary contact at Acme is the CFO.",
        "supersession",
        "en",
        "business",
    ),
    Case(
        "biz/en/status",
        "The account status is active.",
        "The account status is churned.",
        "supersession",
        "en",
        "business",
    ),
    Case(
        "biz/it/am",
        "Il responsabile commerciale di Acme è Alice.",
        "Il responsabile commerciale di Acme è Bob.",
        "supersession",
        "it",
        "business",
    ),
    Case(
        "biz/es/am",
        "El responsable de cuenta de Acme es Alice.",
        "El responsable de cuenta de Acme es Bob.",
        "supersession",
        "es",
        "business",
    ),
    Case(
        "biz/fr/stage",
        "Le dossier est en phase de négociation.",
        "Le dossier est en phase de clôture.",
        "supersession",
        "fr",
        "business",
    ),
    Case(
        "biz/cross/en-es",
        "The account manager for Acme Corp is Alice.",
        "El responsable de cuenta de Acme es Bob.",
        "supersession",
        "cross",
        "business",
    ),
    # ── PERSONAL PREFERENCE ───────────────────────────────────────────────────
    Case(
        "pref/en/contact",
        "The user prefers to be contacted by email.",
        "The user prefers to be contacted by phone.",
        "supersession",
        "en",
        "personal",
    ),
    Case(
        "pref/en/time",
        "The user's preferred meeting time is 9 AM.",
        "The user's preferred meeting time is 2 PM.",
        "supersession",
        "en",
        "personal",
    ),
    Case(
        "pref/en/diet",
        "The user follows a vegetarian diet.",
        "The user follows a vegan diet.",
        "supersession",
        "en",
        "personal",
    ),
    Case(
        "pref/en/lang",
        "The user communicates in English.",
        "The user communicates in Italian.",
        "supersession",
        "en",
        "personal",
    ),
    Case(
        "pref/it/contact",
        "L'utente preferisce essere contattato per email.",
        "L'utente preferisce essere contattato per telefono.",
        "supersession",
        "it",
        "personal",
    ),
    Case(
        "pref/it/time",
        "L'orario preferito per le riunioni è le 9:00.",
        "L'orario preferito per le riunioni è le 14:00.",
        "supersession",
        "it",
        "personal",
    ),
    Case(
        "pref/fr/diet",
        "L'utilisateur suit un régime végétarien.",
        "L'utilisateur suit un régime végétalien.",
        "supersession",
        "fr",
        "personal",
    ),
    Case(
        "pref/es/contact",
        "El usuario prefiere ser contactado por email.",
        "El usuario prefiere ser contactado por teléfono.",
        "supersession",
        "es",
        "personal",
    ),
    # ── FINANCIAL ─────────────────────────────────────────────────────────────
    Case(
        "fin/en/budget",
        "The project budget is $50,000.",
        "The project budget is $75,000.",
        "supersession",
        "en",
        "financial",
    ),
    Case(
        "fin/en/price",
        "The annual subscription costs €99.",
        "The annual subscription costs €129.",
        "supersession",
        "en",
        "financial",
    ),
    Case(
        "fin/en/rate",
        "The agreed hourly rate is $120.",
        "The agreed hourly rate is $150.",
        "supersession",
        "en",
        "financial",
    ),
    Case(
        "fin/it/budget",
        "Il budget del progetto è di 50.000 euro.",
        "Il budget del progetto è di 75.000 euro.",
        "supersession",
        "it",
        "financial",
    ),
    Case(
        "fin/fr/budget",
        "Le budget du projet est de 50 000 euros.",
        "Le budget du projet est de 75 000 euros.",
        "supersession",
        "fr",
        "financial",
    ),
    Case(
        "fin/de/price",
        "Das Jahresabonnement kostet 99 Euro.",
        "Das Jahresabonnement kostet 129 Euro.",
        "supersession",
        "de",
        "financial",
    ),
    Case(
        "fin/es/budget",
        "El presupuesto del proyecto es de 50.000 euros.",
        "El presupuesto del proyecto es de 75.000 euros.",
        "supersession",
        "es",
        "financial",
    ),
    Case(
        "fin/cross/en-fr",
        "The project budget is $50,000.",
        "Le budget du projet est de 75 000 dollars.",
        "supersession",
        "cross",
        "financial",
    ),
    # ── HR / ORGANIZATIONAL ──────────────────────────────────────────────────
    Case(
        "hr/en/report",
        "Alice reports to John.",
        "Alice reports to Sarah.",
        "supersession",
        "en",
        "hr",
    ),
    Case(
        "hr/en/lead",
        "The team lead is Marco.",
        "The team lead is Elena.",
        "supersession",
        "en",
        "hr",
    ),
    Case(
        "hr/en/size",
        "The engineering team has 5 members.",
        "The engineering team has 8 members.",
        "supersession",
        "en",
        "hr",
    ),
    Case(
        "hr/en/office",
        "The Milan office is the headquarters.",
        "The Rome office is the headquarters.",
        "supersession",
        "en",
        "hr",
    ),
    Case(
        "hr/it/report",
        "Alice riporta a Giovanni.",
        "Alice riporta a Sara.",
        "supersession",
        "it",
        "hr",
    ),
    Case(
        "hr/de/size",
        "Das Engineering-Team hat 5 Mitglieder.",
        "Das Engineering-Team hat 8 Mitglieder.",
        "supersession",
        "de",
        "hr",
    ),
    Case(
        "hr/fr/lead",
        "Le responsable de l'équipe est Marco.",
        "Le responsable de l'équipe est Elena.",
        "supersession",
        "fr",
        "hr",
    ),
    Case(
        "hr/cross/en-it",
        "The team lead is Marco.",
        "Il responsabile del team è Elena.",
        "supersession",
        "cross",
        "hr",
    ),
    # ── LEGAL / CONTRACT ─────────────────────────────────────────────────────
    Case(
        "leg/en/date",
        "The NDA expires on January 1, 2025.",
        "The NDA expires on January 1, 2026.",
        "supersession",
        "en",
        "legal",
    ),
    Case(
        "leg/en/law",
        "The governing law is New York law.",
        "The governing law is California law.",
        "supersession",
        "en",
        "legal",
    ),
    Case(
        "leg/en/value",
        "The contract value is $200,000.",
        "The contract value is $250,000.",
        "supersession",
        "en",
        "legal",
    ),
    Case(
        "leg/it/date",
        "Il contratto scade il 1° gennaio 2025.",
        "Il contratto scade il 1° gennaio 2026.",
        "supersession",
        "it",
        "legal",
    ),
    Case(
        "leg/fr/date",
        "Le contrat expire le 1er janvier 2025.",
        "Le contrat expire le 1er janvier 2026.",
        "supersession",
        "fr",
        "legal",
    ),
    Case(
        "leg/es/value",
        "El valor del contrato es de 200.000 euros.",
        "El valor del contrato es de 250.000 euros.",
        "supersession",
        "es",
        "legal",
    ),
    # ── SCIENTIFIC / RESEARCH ────────────────────────────────────────────────
    Case(
        "sci/en/temp",
        "The experiment runs at 37°C.",
        "The experiment runs at 42°C.",
        "supersession",
        "en",
        "science",
    ),
    Case(
        "sci/en/n",
        "The study uses a sample size of 50 participants.",
        "The study uses a sample size of 100 participants.",
        "supersession",
        "en",
        "science",
    ),
    Case(
        "sci/en/method",
        "The primary endpoint is overall survival.",
        "The primary endpoint is progression-free survival.",
        "supersession",
        "en",
        "science",
    ),
    Case(
        "sci/de/temp",
        "Das Experiment läuft bei 37°C.",
        "Das Experiment läuft bei 42°C.",
        "supersession",
        "de",
        "science",
    ),
    Case(
        "sci/fr/n",
        "L'étude utilise un échantillon de 50 participants.",
        "L'étude utilise un échantillon de 100 participants.",
        "supersession",
        "fr",
        "science",
    ),
    # ── ADDITIVE — easy (clearly different predicates) ───────────────────────
    Case(
        "add/en/tech/easy1",
        "The project uses DuckDB for storage.",
        "The project is written in Python.",
        "additive",
        "en",
        "tech",
    ),
    Case(
        "add/en/tech/easy2",
        "The service is deployed on AWS.",
        "The API is implemented in Go.",
        "additive",
        "en",
        "tech",
    ),
    Case(
        "add/it/tech/easy1",
        "Il progetto usa DuckDB per lo storage.",
        "Il progetto è scritto in Python.",
        "additive",
        "it",
        "tech",
    ),
    # ── ADDITIVE — hard (same subject, adjacent attribute, NOT supersession) ─
    Case(
        "add/en/med/hard1",
        "The patient takes metformin 500 mg daily.",
        "The patient was diagnosed with type 2 diabetes.",
        "additive",
        "en",
        "medical",
    ),
    Case(
        "add/en/med/hard2",
        "The patient's primary physician is Dr. Smith.",
        "The patient is scheduled for a follow-up in March.",
        "additive",
        "en",
        "medical",
    ),
    Case(
        "add/en/biz/hard1",
        "The account manager for Acme is Alice.",
        "The Acme Corp deal is worth $200,000.",
        "additive",
        "en",
        "business",
    ),
    Case(
        "add/en/biz/hard2",
        "The deal is in the negotiation stage.",
        "The deal was opened in Q1 2024.",
        "additive",
        "en",
        "business",
    ),
    Case(
        "add/en/pref/hard1",
        "The user prefers to be contacted by email.",
        "The user works from home on Fridays.",
        "additive",
        "en",
        "personal",
    ),
    Case(
        "add/en/pref/hard2",
        "The user follows a vegetarian diet.",
        "The user's preferred meeting time is 9 AM.",
        "additive",
        "en",
        "personal",
    ),
    Case(
        "add/en/fin/hard1",
        "The project budget is $50,000.",
        "The project has a team of 3 engineers.",
        "additive",
        "en",
        "financial",
    ),
    Case(
        "add/en/hr/hard1",
        "Alice reports to John.",
        "Alice joined the company in 2019.",
        "additive",
        "en",
        "hr",
    ),
    Case(
        "add/en/hr/hard2",
        "The team lead is Marco.",
        "The team focuses on backend development.",
        "additive",
        "en",
        "hr",
    ),
    Case(
        "add/en/leg/hard1",
        "The NDA expires on January 1, 2025.",
        "The NDA is governed by New York law.",
        "additive",
        "en",
        "legal",
    ),
    Case(
        "add/en/sci/hard1",
        "The experiment runs at 37°C.",
        "The study uses a sample size of 50 participants.",
        "additive",
        "en",
        "science",
    ),
    # ── ADDITIVE — expansion (old fact still true, new adds info) ────────────
    Case(
        "add/en/expand1",
        "The team uses Python.",
        "The team uses Python and TypeScript.",
        "additive",
        "en",
        "tech",
    ),
    Case(
        "add/en/expand2",
        "The project budget is $50,000.",
        "The project has a $50,000 budget and a 6-month timeline.",
        "additive",
        "en",
        "financial",
    ),
    Case(
        "add/it/biz/hard1",
        "Il responsabile commerciale di Acme è Alice.",
        "Il contratto con Acme vale 200.000 euro.",
        "additive",
        "it",
        "business",
    ),
    # ── UNRELATED — adversarial (same value, different subject) ──────────────
    Case(
        "unrel/en/sv1",
        "Project A uses SQLite for storage.",
        "Project B uses SQLite for storage.",
        "unrelated",
        "en",
        "tech",
    ),
    Case(
        "unrel/en/sv2",
        "Alice's budget is $50,000.",
        "Bob's budget is $50,000.",
        "unrelated",
        "en",
        "financial",
    ),
    Case(
        "unrel/en/sv3",
        "Patient A takes metformin 500 mg.",
        "Patient B takes metformin 500 mg.",
        "unrelated",
        "en",
        "medical",
    ),
    Case(
        "unrel/en/sv4",
        "The account manager for Acme is Alice.",
        "The account manager for Globex is Alice.",
        "unrelated",
        "en",
        "business",
    ),
    # ── UNRELATED — general statements (neither supersedes the other) ─────────
    Case(
        "unrel/en/gen1",
        "Python is good for data science.",
        "R is good for data science.",
        "unrelated",
        "en",
        "tech",
    ),
    Case(
        "unrel/en/gen2",
        "Metformin is prescribed for diabetes.",
        "Insulin is prescribed for diabetes.",
        "unrelated",
        "en",
        "medical",
    ),
    Case(
        "unrel/en/gen3",
        "NDA agreements protect confidential information.",
        "Non-compete clauses restrict future employment.",
        "unrelated",
        "en",
        "legal",
    ),
    # ── UNRELATED — clearly unrelated (topic switch) ──────────────────────────
    Case(
        "unrel/en/far1",
        "The project uses SQLite for storage.",
        "Tomorrow there will be thunderstorms in Milan.",
        "unrelated",
        "en",
        "tech",
    ),
    Case(
        "unrel/en/far2",
        "The patient takes metformin 500 mg.",
        "The carbonara recipe uses guanciale, not pancetta.",
        "unrelated",
        "en",
        "medical",
    ),
    Case(
        "unrel/it/sv1",
        "Il progetto A usa SQLite per lo storage.",
        "Il progetto B usa SQLite per lo storage.",
        "unrelated",
        "it",
        "tech",
    ),
    # ── DUPLICATE (trivial rewording / paraphrase) ────────────────────────────
    Case(
        "dup/en/tech",
        "The project uses SQLite for storage.",
        "The project stores data using SQLite.",
        "duplicate",
        "en",
        "tech",
    ),
    Case(
        "dup/en/med",
        "The patient takes 500 mg of metformin daily.",
        "The patient's daily metformin dose is 500 mg.",
        "duplicate",
        "en",
        "medical",
    ),
    Case("dup/en/hr", "Alice is the team lead.", "Alice leads the team.", "duplicate", "en", "hr"),
    Case(
        "dup/en/fin",
        "The project budget is $50,000.",
        "The total project budget amounts to $50,000.",
        "duplicate",
        "en",
        "financial",
    ),
    Case(
        "dup/en/backend",
        "The backend is written in Python.",
        "Python is used for the backend.",
        "duplicate",
        "en",
        "tech",
    ),
    Case(
        "dup/it/tech",
        "Il progetto usa SQLite per lo storage.",
        "Il progetto archivia i dati in SQLite.",
        "duplicate",
        "it",
        "tech",
    ),
]

# Sanity checks
_zones = {c.expected_zone for c in CASES}
assert _zones == {"supersession", "additive", "unrelated", "duplicate"}, _zones
_n_sup = sum(1 for c in CASES if c.expected_zone == "supersession")
_n_add = sum(1 for c in CASES if c.expected_zone == "additive")
_n_unr = sum(1 for c in CASES if c.expected_zone == "unrelated")
_n_dup = sum(1 for c in CASES if c.expected_zone == "duplicate")
_domains = sorted({c.domain for c in CASES if c.expected_zone == "supersession"})


# ---------------------------------------------------------------------------
# Standalone runner — reports cosine stats per zone/domain (no thresholds)
# ---------------------------------------------------------------------------


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def run_all() -> None:
    enc = TextEncoder(EncoderConfig())
    print(f"\n  Model: {enc.cfg.model_name}")
    print(
        f"  Pairs: {len(CASES)} total — "
        f"{_n_sup} supersession ({len(_domains)} domains), "
        f"{_n_add} additive, {_n_unr} unrelated, {_n_dup} duplicate"
    )

    by_zone: dict[str, list[float]] = {
        "supersession": [],
        "additive": [],
        "unrelated": [],
        "duplicate": [],
    }
    by_domain: dict[str, list[float]] = {d: [] for d in _domains}

    for c in CASES:
        sim = cosine(enc.encode(c.old), enc.encode(c.new))
        by_zone[c.expected_zone].append(sim)
        if c.expected_zone == "supersession":
            by_domain[c.domain].append(sim)

    print("\n  Zone cosine summary:")
    for z, vals in by_zone.items():
        lo, hi, mean = min(vals), max(vals), sum(vals) / len(vals)
        print(f"    {z:13}  n={len(vals):3}  [{lo:.4f}, {hi:.4f}]  mean={mean:.4f}")

    print("\n  Supersession by domain:")
    for d, vals in by_domain.items():
        lo, hi, mean = min(vals), max(vals), sum(vals) / len(vals)
        print(f"    {d:10}  n={len(vals):2}  [{lo:.4f}, {hi:.4f}]  mean={mean:.4f}")


# ---------------------------------------------------------------------------
# Pytest entry point — skipped until encoder + thresholds are finalised
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason="Thresholds TBD after encoder selection. Run _run_geometry_investigation.py instead."
)
def test_supersession_geometry():
    """Placeholder — will be activated with calibrated thresholds post encoder switch."""
    pass


if __name__ == "__main__":
    run_all()
