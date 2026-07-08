#!/usr/bin/env python3
"""Evaluate Slowave on the original MemGPT DMR source dataset candidate.

Dataset:
  data/dmr_original/msc_self_instruct.jsonl

Source:
  https://huggingface.co/datasets/MemGPT/MSC-Self-Instruct

This is the MSC self-instruct dataset used by the MemGPT paper. It has 500
records, each with prior MSC dialogs and one self-instruct QA pair.

Important: this harness measures keyword presence in retrieved Slowave context.
It does NOT reproduce the published MemGPT/Zep LLM-judge protocol yet.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.WARNING)
for _n in (
    "sentence_transformers",
    "transformers",
    "httpx",
    "httpcore",
    "huggingface_hub",
    "filelock",
    "tqdm",
):
    logging.getLogger(_n).setLevel(logging.ERROR)
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine
from slowave.latent.replay_engine import ReplayConfig
from slowave.latent.retrieval import RetrievalConfig
from slowave.latent.salience import SalienceConfig
from slowave.symbolic.encoder import EncoderConfig, TextEncoder

HIT_THRESHOLD = 0.5
STOP = {
    "the",
    "a",
    "an",
    "is",
    "was",
    "were",
    "are",
    "i",
    "my",
    "me",
    "it",
    "its",
    "of",
    "in",
    "on",
    "at",
    "to",
    "for",
    "and",
    "or",
    "that",
    "this",
    "with",
    "be",
    "have",
    "has",
    "had",
}


def keyword_score(hypothesis: str, answer: str) -> float:
    def tokens(s: str) -> set[str]:
        return {
            w
            for w in re.findall(r"[a-z0-9]+", str(s).lower())
            if w not in STOP and (len(w) > 1 or w.isdigit())
        }

    answer_tokens = tokens(answer)
    if not answer_tokens:
        return 0.0
    return len(answer_tokens & tokens(hypothesis)) / len(answer_tokens)


@dataclass
class DMROriginalResult:
    idx: int
    source_initial_data_id: str | None
    source_session_id: int | None
    question: str
    expected: str
    hypothesis: str
    keyword_score: float
    hit: bool
    n_schemas: int
    n_episodes: int
    latency_ingest_s: float
    latency_recall_s: float
    error: str | None = None


def _dialog_to_turns(dialog: list[dict[str, Any]]) -> list[tuple[str, str]]:
    turns: list[tuple[str, str]] = []
    for i, msg in enumerate(dialog or []):
        text = str(msg.get("text", "")).strip()
        if not text:
            continue
        ident = str(msg.get("id", ""))
        # Previous dialogs often omit Speaker 1/2 ids; MSC alternates speakers.
        if ident in {"Speaker 1", "A"}:
            role = "user_message"
        elif ident in {"Speaker 2", "B"}:
            role = "assistant_message"
        else:
            role = "user_message" if i % 2 == 0 else "assistant_message"
        turns.append((role, text))
    return turns


def _extract_qa(record: dict[str, Any]) -> tuple[str, str]:
    self_instruct = record.get("self_instruct") or {}
    question = str(self_instruct.get("B", "")).strip()
    answer = str(self_instruct.get("A", "")).strip()
    return question, answer


def run_record(
    idx: int,
    record: dict[str, Any],
    encoder: TextEncoder,
    *,
    top_k: int,
    assignment_threshold: float = 0.65,
    salience_weight: float = 0.3,
    no_consolidate: bool = False,
    no_salience_rerank: bool = False,
    tau_seconds: float = 86400.0,
    surprise_weight: float = 0.3,
) -> DMROriginalResult:
    metadata = record.get("metadata") or {}
    q, a = _extract_qa(record)
    # Deterministic seed per record so consolidation sampling is reproducible.
    import hashlib as _hashlib

    import numpy as _np

    _seed = int.from_bytes(_hashlib.sha256(str(idx).encode("utf-8")).digest()[:4], "big") % (2**31)
    _np.random.seed(_seed)
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        # Apply ablation parameters
        if no_salience_rerank:
            salience_weight = 0.0

        cfg = SlowaveConfig(
            db_path=db_path,
            dim=encoder.dim,
            encoder=EncoderConfig(),
            salience=SalienceConfig(tau_seconds=tau_seconds, surprise_weight=surprise_weight),
            replay=ReplayConfig(
                assignment_threshold=assignment_threshold,
                sample_size=256,
                max_prototypes_per_replay=32,
            ),
            retrieval=RetrievalConfig(salience_weight=salience_weight, neighbor_top_k=6),
            disable_encoder=False,
        )
        eng = SlowaveEngine(cfg, shared_encoder=encoder)
        t0 = time.time()
        dialogs: list[list[dict[str, Any]]] = []
        for prev in record.get("previous_dialogs", []):
            dialogs.append(prev.get("dialog", []))
        dialogs.append(record.get("dialog", []))

        for dialog in dialogs:
            sid = eng.session_start(agent="dmr_original")
            for role, text in _dialog_to_turns(dialog):
                eng.event_append(session_id=sid, type=role, content=text)
            eng.session_end(sid, consolidate=False)

        if not no_consolidate:
            eng.consolidate_once()
        latency_ingest = time.time() - t0

        t1 = time.time()
        recalled = eng.recall(q, top_k=top_k, evidence=False)
        latency_recall = time.time() - t1
        schemas_text = " ".join(s.content_text for s in recalled.schemas)
        episodes_text = " ".join(
            ep["content_text"] for ep in recalled.episode_texts if ep.get("content_text")
        )
        hyp = (schemas_text + " " + episodes_text).strip()
        score = keyword_score(hyp, a)
        eng.close()
        return DMROriginalResult(
            idx=idx,
            source_initial_data_id=metadata.get("initial_data_id"),
            source_session_id=metadata.get("session_id"),
            question=q,
            expected=a,
            hypothesis=hyp[:600],
            keyword_score=round(score, 3),
            hit=score >= HIT_THRESHOLD,
            n_schemas=len(recalled.schemas),
            n_episodes=len(recalled.episode_texts),
            latency_ingest_s=round(latency_ingest, 3),
            latency_recall_s=round(latency_recall, 4),
        )
    except Exception as e:
        return DMROriginalResult(
            idx=idx,
            source_initial_data_id=metadata.get("initial_data_id"),
            source_session_id=metadata.get("session_id"),
            question=q,
            expected=a,
            hypothesis="",
            keyword_score=0.0,
            hit=False,
            n_schemas=0,
            n_episodes=0,
            latency_ingest_s=0.0,
            latency_recall_s=0.0,
            error=str(e),
        )
    finally:
        for ext in ("", "-wal", "-shm"):
            p = db_path + ext
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass


def _save(
    out_path: Path,
    results: list[DMROriginalResult],
    args: argparse.Namespace,
    *,
    partial: bool,
    elapsed_s: float,
) -> None:
    hits = sum(r.hit for r in results)
    payload = {
        "meta": {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "partial": partial,
            "dataset": str(args.dataset),
            "offset": args.offset,
            "limit": args.limit,
            "top_k": args.top_k,
            "hit_threshold": HIT_THRESHOLD,
            "scorer": "keyword overlap over retrieved schemas+episodes",
            "protocol_note": "Retrieval-context metric; not the published MemGPT/Zep LLM-judge protocol.",
            "elapsed_s": round(elapsed_s, 2),
        },
        "summary": {
            "n": len(results),
            "hits": hits,
            "score_pct": round(100 * hits / max(1, len(results)), 2),
            "errors": sum(1 for r in results if r.error),
        },
        "results": [asdict(r) for r in results],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, out_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="data/dmr_original/msc_self_instruct.jsonl")
    parser.add_argument(
        "--out", default="data/dmr_original/runs/slowave_dmr_original_retrieval.json"
    )
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--save-every", type=int, default=25)
    # Ablation flags
    parser.add_argument("--assignment-threshold", type=float, default=0.65)
    parser.add_argument("--salience-weight", type=float, default=0.3)
    parser.add_argument("--tau-seconds", type=float, default=86400.0)
    parser.add_argument("--surprise-weight", type=float, default=0.3)
    parser.add_argument("--no-consolidate", action="store_true")
    parser.add_argument("--no-salience-rerank", action="store_true")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.is_absolute():
        dataset_path = REPO_ROOT / dataset_path
    records = [json.loads(line) for line in dataset_path.open()]
    if args.offset:
        records = records[args.offset :]
    if args.limit:
        records = records[: args.limit]
    print(f"records={len(records)} dataset={dataset_path}", flush=True)

    print("Loading encoder... ", end="", flush=True)
    encoder = TextEncoder(EncoderConfig())
    _ = encoder.encode("warmup")
    print(f"OK dim={encoder.dim}", flush=True)

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path

    results: list[DMROriginalResult] = []
    start = time.time()
    for local_i, record in enumerate(records):
        idx = args.offset + local_i
        r = run_record(
            idx,
            record,
            encoder,
            top_k=args.top_k,
            assignment_threshold=args.assignment_threshold,
            salience_weight=args.salience_weight if not args.no_salience_rerank else 0.0,
            no_consolidate=args.no_consolidate,
            no_salience_rerank=args.no_salience_rerank,
            tau_seconds=args.tau_seconds,
            surprise_weight=args.surprise_weight,
        )
        results.append(r)
        if len(results) <= 5 or len(results) % args.save_every == 0:
            hits = sum(x.hit for x in results)
            print(
                f"[{len(results)}/{len(records)}] hits={hits}/{len(results)} "
                f"{100 * hits / len(results):.1f}% last={'HIT' if r.hit else 'miss'} "
                f"ks={r.keyword_score} ingest={r.latency_ingest_s:.2f}s "
                f"recall={r.latency_recall_s * 1000:.0f}ms",
                flush=True,
            )
            _save(out_path, results, args, partial=True, elapsed_s=time.time() - start)

    _save(out_path, results, args, partial=False, elapsed_s=time.time() - start)
    hits = sum(r.hit for r in results)
    print(
        f"SUMMARY n={len(results)} hits={hits} score={100 * hits / max(1, len(results)):.2f}% "
        f"out={out_path}",
        flush=True,
    )


if __name__ == "__main__":
    main()
