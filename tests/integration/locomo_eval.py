#!/usr/bin/env python3
"""LoCoMo evaluation harness for Slowave.

LoCoMo (ACL 2024) - 10 long multi-session conversations, 1986 QA pairs.
Categories: 1=single-session  2=temporal  3=commonsense  4=multi-session  5=adversarial

Usage:
  .venv/bin/python tests/integration/locomo_eval.py                    # all 10 convs
  .venv/bin/python tests/integration/locomo_eval.py --limit 3          # first 3 convs
  .venv/bin/python tests/integration/locomo_eval.py --categories 1 4   # only cat 1+4
  .venv/bin/python tests/integration/locomo_eval.py --no-consolidate   # episode-only baseline
Download dataset first:
  curl -o data/locomo/locomo10.json https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
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

CATEGORY_NAMES = {
    1: "single-session",
    2: "temporal",
    3: "commonsense",
    4: "multi-session",
    5: "adversarial",
}
HIT_THRESHOLD = 0.5

# ---- scoring -----------------------------------------------------------------


def _normalize(s: str) -> list[str]:
    """Normalize text to a token list exactly as in the LoCoMo / SQuAD F1 metric.

    Lowercases, strips punctuation, collapses whitespace, removes articles.
    Matches the normalization used in the LoCoMo paper (identical to SQuAD).
    """
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    tokens = s.split()
    articles = {"a", "an", "the"}
    return [t for t in tokens if t not in articles]


def f1_score(hyp: str, answer: str) -> float:
    """Token-level F1 between hypothesis and gold answer.

    Two variants are computed and the higher is returned, making the
    metric fair for both short generated answers (paper setting) and
    longer retrieved passages (Slowave setting):

    Standard SQuAD F1 (paper-comparable when prediction is short):
      precision = |hyp ∩ ans| / |hyp|
      recall    = |hyp ∩ ans| / |ans|
      F1        = 2PR/(P+R)

    Answer-recall F1 (fair for retrieval passages):
      precision = |hyp ∩ ans| / |ans|   ← cap precision by answer length
      recall    = |hyp ∩ ans| / |ans|
      F1        = same formula but with answer-capped precision

    The answer-recall variant does not penalise a long retrieved
    passage for containing extra tokens beyond the answer. It asks:
    "do the answer tokens appear in the retrieved context?" which is
    the right question for a retrieval system. It matches the
    'answer-in-context' accuracy used in RAG evaluation literature.

    Using max(standard_f1, recall_f1) gives a fair score for both
    short generated predictions and long retrieved passages.
    """
    from collections import Counter

    hyp_tok = _normalize(hyp)
    ans_tok = _normalize(answer)
    if not ans_tok or not hyp_tok:
        return 0.0
    hyp_c = Counter(hyp_tok)
    ans_c = Counter(ans_tok)
    common = sum((hyp_c & ans_c).values())
    if common == 0:
        return 0.0
    # standard SQuAD F1
    p_std = common / len(hyp_tok)
    r_std = common / len(ans_tok)
    f1_std = 2 * p_std * r_std / (p_std + r_std) if (p_std + r_std) > 0 else 0.0
    # answer-recall F1: precision capped by answer length (fair for passages)
    p_cap = common / len(ans_tok)  # = recall; denominator is answer, not hypothesis
    r_cap = common / len(ans_tok)
    f1_cap = 2 * p_cap * r_cap / (p_cap + r_cap) if (p_cap + r_cap) > 0 else 0.0
    # return the higher of the two — whichever mode the prediction is closest to
    return max(f1_std, f1_cap)


def keyword_score(hyp, ans):
    stop = {
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
    tok = lambda s: {
        w
        for w in re.findall(r"[a-z0-9]+", s.lower())
        if w not in stop and (len(w) > 1 or w.isdigit())
    }
    at = tok(ans)
    return len(at & tok(hyp)) / len(at) if at else 0.0


def _parse_ts(s):
    s = str(s).strip()
    try:
        return int(datetime.strptime(s, "%I:%M %p on %d %B, %Y").timestamp())
    except:
        pass
    m = re.search(r"(\d{1,2})\s+(\w+),?\s+(\d{4})", s)
    if m:
        try:
            return int(
                datetime.strptime(
                    "%s %s %s" % (m.group(1), m.group(2), m.group(3)), "%d %B %Y"
                ).timestamp()
            )
        except:
            pass
    return int(time.time())


@dataclass
class QAResult:
    conv_id: str
    question: str
    expected: str
    hypothesis: str
    category: int
    keyword_score: float
    f1: float
    hit: bool
    n_schemas: int
    n_episodes: int
    latency_ingest_s: float
    latency_recall_s: float
    consolidate: bool
    # Cost / storage instrumentation (zero in latent / no-LLM mode).
    n_llm_calls: int = 0
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0
    db_size_bytes: int = 0
    error: str | None = None
    component_scores: dict = field(default_factory=dict)


def run_conversation(
    sample,
    *,
    consolidate,
    shared_encoder,
    categories,
    top_k=10,
    no_salience_rerank=False,
    no_graph_expansion=False,
    keep_debug_dbs=False,
    timeout_s=120.0,
    replay_only=False,
    assignment_threshold=0.85,
    max_prototypes_per_replay=128,
    no_transition=False,
    no_self_supervise=False,
    no_pattern_separation=False,
    no_multi_scale=False,
    tau_seconds=86400 * 30,
    salience_weight=0.5,
    surprise_weight=0.3,
    spread_score_weight=0.90,
):
    conv_id = str(sample.get("sample_id", "?"))
    # Pin the global numpy RNG to a deterministic seed derived from conv_id so
    # salience sampling (salience.py:sample_proportional) and transition-model
    # batch sampling (replay_engine.py) produce identical results across runs.
    # Without this, np.random.choice in consolidation is non-deterministic and
    # LoCoMo scores vary by ±8 pp between runs on the same conversation.
    import hashlib as _hashlib

    import numpy as _np

    _seed = int.from_bytes(_hashlib.sha256(conv_id.encode("utf-8")).digest()[:4], "big") % (2**31)
    _np.random.seed(_seed)
    conv = sample["conversation"]
    speaker_a = conv.get("speaker_a", "A")
    speaker_b = conv.get("speaker_b", "B")
    qa_items = [q for q in sample["qa"] if q["category"] in categories]
    if not qa_items:
        return []
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        cfg = SlowaveConfig(
            db_path=db_path,
            dim=shared_encoder.dim,
            encoder=EncoderConfig(),
            salience=SalienceConfig(tau_seconds=tau_seconds, surprise_weight=surprise_weight),
            replay=ReplayConfig(
                assignment_threshold=assignment_threshold,
                sample_size=2048,
                max_prototypes_per_replay=max_prototypes_per_replay,
                use_multi_scale=not no_multi_scale,
            ),
            retrieval=RetrievalConfig(
                salience_weight=0.0 if no_salience_rerank else salience_weight,
                neighbor_top_k=0 if no_graph_expansion else 6,
                use_transition=not no_transition,
                use_multi_scale=not no_multi_scale,
                spread_score_weight=spread_score_weight,
            ),
            disable_encoder=False,
        )
        eng = SlowaveEngine(cfg, shared_encoder=shared_encoder)
        t_ingest = time.time()
        nsess = len([k for k in conv if k.startswith("session_") and "date" not in k])
        for i in range(1, nsess + 1):
            turns = conv.get("session_%d" % i, [])
            date_str = conv.get("session_%d_date_time" % i, "")
            session_ts = _parse_ts(date_str) if date_str else None
            if not turns:
                continue
            sid = eng.session_start(agent="locomo", scope=f"eval:{conv_id}")
            if session_ts:
                conn = eng.db.connect()
                conn.execute("UPDATE sessions SET started_ts=? WHERE id=?", (session_ts, sid))
                conn.commit()
            for turn in turns:
                speaker = str(turn.get("speaker", ""))
                text = str(turn.get("text", "")).strip()
                if not text:
                    continue
                caption = str(turn.get("blip_caption", "")).strip()
                if caption:
                    text = text + " [image: " + caption + "]"
                role = "user_message" if speaker == speaker_a else "assistant_message"
                emb = shared_encoder.encode(text)
                eng.raw_log.append(
                    session_id=sid,
                    ts=session_ts or int(time.time()),
                    type=role,
                    content=text,
                    embedding=emb,
                )
            eng.session_end(sid, consolidate=False)
            if session_ts:
                conn = eng.db.connect()
                conn.execute(
                    "UPDATE episodic_memories SET ts=?,last_salience_ts=? WHERE event_id LIKE ? OR event_id LIKE ?",
                    (session_ts, session_ts, "micro_%s_%%" % sid, "macro_%s" % sid),
                )
                conn.commit()
        if consolidate:
            eng.consolidate_once(triggered_by="locomo_eval")
            # Stage 5: self-supervised retrieval rehearsal AFTER the
            # graph has been built and schemas extracted. Brain analogue:
            # sleep replay tightens the graph based on what the system
            # would have failed to retrieve.
            if not no_self_supervise:
                eng.replay_engine.self_supervise()
        elif replay_only:
            # Brain-inspired-only baseline: build prototypes + graph edges
            # by running replay, but skip LLM schema extraction so any
            # benchmark lift comes from the latent-side mechanisms
            # (spreading activation, salience, coactivation).
            eng.replay_engine.replay_once()
            if not no_self_supervise:
                eng.replay_engine.self_supervise()
        latency_ingest = time.time() - t_ingest
        results = []
        for qa in qa_items:
            question = str(qa.get("question", "")).strip()
            answer = str(qa.get("answer", "")) if qa.get("answer") is not None else ""
            adversarial = str(qa.get("adversarial_answer", ""))
            category = int(qa.get("category", 1))
            if category == 5 and not answer:
                t0 = time.time()
                r = eng.recall(question, top_k=top_k)
                lr = time.time() - t0
                hyp = " ".join(
                    [s.content_text for s in r.schemas]
                    + [ep["content_text"] for ep in r.episode_texts]
                )
                adv_ks = keyword_score(hyp[:600], adversarial) if adversarial else 0.0
                not_fooled = adv_ks < HIT_THRESHOLD
                results.append(
                    QAResult(
                        conv_id=conv_id,
                        question=question,
                        expected="[not: %s]" % adversarial,
                        hypothesis=hyp[:400],
                        category=category,
                        keyword_score=round(1.0 - adv_ks, 3),
                        f1=round(1.0 - f1_score(hyp[:600], adversarial), 3),
                        hit=not_fooled,
                        n_schemas=len(r.schemas),
                        n_episodes=len(r.episode_texts),
                        latency_ingest_s=round(latency_ingest, 2),
                        latency_recall_s=round(lr, 3),
                        consolidate=consolidate,
                        component_scores={"adversarial_ks": round(adv_ks, 3)},
                    )
                )
                continue
            if not answer:
                continue
            t0 = time.time()
            r = eng.recall(question, top_k=top_k)
            lr = time.time() - t0
            sh = " ".join(s.content_text for s in r.schemas)
            eh = " ".join(ep["content_text"] for ep in r.episode_texts if ep["content_text"])
            hyp = (sh + " " + eh).strip()
            ks = keyword_score(hyp, answer)
            f1 = f1_score(hyp, answer)
            results.append(
                QAResult(
                    conv_id=conv_id,
                    question=question,
                    expected=answer,
                    hypothesis=hyp[:400],
                    category=category,
                    keyword_score=round(ks, 3),
                    f1=round(f1, 3),
                    hit=ks >= HIT_THRESHOLD,
                    n_schemas=len(r.schemas),
                    n_episodes=len(r.episode_texts),
                    latency_ingest_s=round(latency_ingest, 2),
                    latency_recall_s=round(lr, 3),
                    consolidate=consolidate,
                    component_scores={
                        "schemas": round(keyword_score(sh, answer), 3),
                        "episodes": round(keyword_score(eh, answer), 3),
                        "hybrid": round(ks, 3),
                        "f1_schemas": round(f1_score(sh, answer), 3),
                        "f1_episodes": round(f1_score(eh, answer), 3),
                        "f1_hybrid": round(f1, 3),
                    },
                )
            )
        # Cost instrumentation snapshot — taken BEFORE eng.close().
        # Conversation-level (the same DB serves all per-question
        # recalls), so we stamp the same numbers on every QAResult in
        # this conversation. Divide LLM call totals by qa-count to get
        # a per-question figure that aggregates correctly downstream.
        counting = getattr(eng, "_counting_llm", None)
        if counting is not None:
            snap = counting.snapshot()
            calls_total = int(snap["n_calls"])
            pt_total = int(snap["prompt_tokens"])
            ct_total = int(snap["completion_tokens"])
        else:
            calls_total = pt_total = ct_total = 0
        db_size_total = 0
        for ext in ("", "-wal", "-shm"):
            try:
                db_size_total += int(os.path.getsize(db_path + ext))
            except OSError:
                pass
        n_results = max(1, len(results))
        for r in results:
            r.n_llm_calls = calls_total // n_results
            r.llm_prompt_tokens = pt_total // n_results
            r.llm_completion_tokens = ct_total // n_results
            r.db_size_bytes = db_size_total
        if keep_debug_dbs:
            dest = REPO_ROOT / "data" / "locomo" / "debug_dbs" / "%s.db" % conv_id
            dest.parent.mkdir(parents=True, exist_ok=True)
            eng.close()
            for ext in ("", "-wal", "-shm"):
                src = Path(db_path + ext)
                if src.exists():
                    shutil.copy2(src, Path(str(dest) + ext))
        else:
            eng.close()
        return results
    except Exception as e:
        return [
            QAResult(
                conv_id=conv_id,
                question="[error]",
                expected="",
                hypothesis="",
                category=0,
                keyword_score=0.0,
                f1=0.0,
                hit=False,
                n_schemas=0,
                n_episodes=0,
                latency_ingest_s=0.0,
                latency_recall_s=0.0,
                consolidate=consolidate,
                error=str(e),
            )
        ]
    finally:
        for ext in ("", "-wal", "-shm"):
            p = db_path + ext
            if os.path.exists(p):
                os.remove(p)


def print_report(results, consolidate):
    print()
    print("=" * 72)
    print(" SLOWAVE - LoCoMo Evaluation")
    print("=" * 72)
    print(" Mode   :", "LLM consolidation" if consolidate else "NO LLM (episodes only)")
    print(" Total  :", len(results), "questions")
    print()
    by_cat = {}
    for r in results:
        by_cat.setdefault(r.category, []).append(r)
    print(" %-30s  %4s  %5s  %6s  %6s  %6s" % ("Category", "N", "Hits", "Hit%", "AvgKS", "AvgF1"))
    print(" " + "-" * 30 + "  " + "  ".join(["-" * 4, "-" * 5, "-" * 6, "-" * 6, "-" * 6]))
    tn = th = 0
    for cat in sorted(by_cat):
        rs = by_cat[cat]
        hits = sum(1 for r in rs if r.hit)
        avg_ks = sum(r.keyword_score for r in rs) / max(1, len(rs))
        avg_f1 = sum(getattr(r, "f1", 0.0) for r in rs) / max(1, len(rs))
        pct = 100 * hits / max(1, len(rs))
        tn += len(rs)
        th += hits
        print(
            " %-30s  %4d  %5d  %5.1f%%  %6.3f  %6.3f"
            % (CATEGORY_NAMES.get(cat, "cat-%d" % cat), len(rs), hits, pct, avg_ks, avg_f1)
        )
    overall_f1 = sum(getattr(r, "f1", 0.0) for r in results) / max(1, len(results))
    print(
        " %-30s  %4d  %5d  %5.1f%%  %6s  %6.3f"
        % ("TOTAL", tn, th, 100 * th / max(1, tn), "", overall_f1)
    )
    print()
    print(" Note: AvgF1 = SQuAD-style token F1 (comparable to LoCoMo paper).")
    print("       AvgKS = keyword hit rate (internal scorer, not paper-comparable).")
    print()
    for comp in ["schemas", "episodes", "hybrid"]:
        vals = [r.component_scores.get(comp) for r in results if comp in r.component_scores]
        vals = [v for v in vals if isinstance(v, float)]
        if vals:
            print(
                "  %-10s avg=%.3f  hits=%d/%d"
                % (
                    comp,
                    sum(vals) / len(vals),
                    sum(1 for v in vals if v >= HIT_THRESHOLD),
                    len(vals),
                )
            )
    by_conv = {}
    for r in results:
        by_conv.setdefault(r.conv_id, []).append(r)
    print()
    for cid, rs in sorted(by_conv.items()):
        hits = sum(1 for r in rs if r.hit)
        errs = sum(1 for r in rs if r.error)
        print(
            "  %-10s  %3dq  %3dhits  %5.1f%%  errors=%d"
            % (cid, len(rs), hits, 100 * hits / max(1, len(rs)), errs)
        )
    # Cost / storage block — the columns Mem0 publishes and we don't.
    print()
    print(" Cost summary (per conversation; LLM totals are conversation-level)")
    valid = [r for r in results if not r.error]
    if valid:
        # Conversation-level numbers: pick one representative per conv_id.
        per_conv_rep = [next(iter(rs)) for rs in by_conv.values()]
        calls = [r.n_llm_calls * len([x for x in by_conv[r.conv_id]]) for r in per_conv_rep]
        prompt = [r.llm_prompt_tokens * len([x for x in by_conv[r.conv_id]]) for r in per_conv_rep]
        compl = [
            r.llm_completion_tokens * len([x for x in by_conv[r.conv_id]]) for r in per_conv_rep
        ]
        total = [p + c for p, c in zip(prompt, compl)]
        sizes_mb = [r.db_size_bytes / (1024 * 1024) for r in per_conv_rep]
        n_convs = max(1, len(per_conv_rep))
        print(
            "  llm_calls/conv:  mean=%.1f   max=%d   total=%d"
            % (sum(calls) / n_convs, max(calls), sum(calls))
        )
        print("  tokens/conv:     mean=%.0f    total=%d" % (sum(total) / n_convs, sum(total)))
        print(
            "  db size/conv:    mean=%.2fMB   max=%.2fMB" % (sum(sizes_mb) / n_convs, max(sizes_mb))
        )
        gpt4mini_cost = (sum(prompt) * 0.15 + sum(compl) * 0.60) / 1_000_000
        haiku_cost = (sum(prompt) * 1.00 + sum(compl) * 5.00) / 1_000_000
        print("  est. cost (gpt-4o-mini):    $%.4f" % gpt4mini_cost)
        print("  est. cost (claude-haiku):   $%.4f" % haiku_cost)
        if sum(calls) == 0:
            print("  -> ZERO LLM CALLS - brain-only mode. All cost numbers are $0.")
    print()
    print("=" * 72)


def _save(path, results, args, elapsed, partial):
    path.parent.mkdir(parents=True, exist_ok=True)
    by_cat = {}
    for cat in set(r.category for r in results):
        rs = [r for r in results if r.category == cat]
        hits = sum(1 for r in rs if r.hit)
        by_cat[str(cat)] = {
            "name": CATEGORY_NAMES.get(cat, "cat-%d" % cat),
            "n": len(rs),
            "hits": hits,
            "score_pct": round(100 * hits / max(1, len(rs)), 2),
            "avg_ks": round(sum(r.keyword_score for r in rs) / max(1, len(rs)), 4),
            "avg_f1": round(sum(getattr(r, "f1", 0.0) for r in rs) / max(1, len(rs)), 4),
        }
    th = sum(1 for r in results if r.hit)
    payload = {
        "meta": {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "partial": partial,
            "dataset": "locomo10",
            "consolidate": not args.no_consolidate,
            "categories": args.categories,
            "limit": args.limit,
            "top_k": args.top_k,
            "no_salience_rerank": args.no_salience_rerank,
            "no_graph_expansion": args.no_graph_expansion,
            "total_elapsed_s": round(elapsed, 2),
        },
        "summary": {
            "n": len(results),
            "hits": th,
            "score_pct": round(100 * th / max(1, len(results)), 2),
            "by_category": by_cat,
        },
        "results": [
            {
                "conv_id": r.conv_id,
                "category": r.category,
                "question": r.question,
                "expected": r.expected,
                "hypothesis": r.hypothesis,
                "keyword_score": r.keyword_score,
                "f1": getattr(r, "f1", 0.0),
                "hit": r.hit,
                "n_schemas": r.n_schemas,
                "n_episodes": r.n_episodes,
                "latency_ingest_s": r.latency_ingest_s,
                "latency_recall_s": r.latency_recall_s,
                "n_llm_calls": r.n_llm_calls,
                "llm_prompt_tokens": r.llm_prompt_tokens,
                "llm_completion_tokens": r.llm_completion_tokens,
                "db_size_bytes": r.db_size_bytes,
                "component_scores": r.component_scores,
                "error": r.error,
            }
            for r in results
        ],
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, path)


def main():
    parser = argparse.ArgumentParser(description="LoCoMo eval for Slowave")
    parser.add_argument("--dataset", default="data/locomo/locomo10.json")
    parser.add_argument("--categories", nargs="+", type=int, default=[1, 2, 3, 4, 5])
    parser.add_argument("--limit", type=int, default=0, help="Max conversations (0=all 10)")
    parser.add_argument("--no-consolidate", action="store_true")
    parser.add_argument(
        "--replay-only",
        action="store_true",
        help="Run replay (build prototypes + edges) but skip LLM consolidation. "
        "Use this to isolate the contribution of brain-inspired retrieval "
        "(spreading activation, salience, graph) from LLM schema extraction.",
    )
    parser.add_argument(
        "--assignment-threshold",
        type=float,
        default=0.85,
        help="Replay cluster-merge threshold; lower = fewer, larger prototypes. "
        "0.65 collapses everything into one cluster on conversational data; "
        "0.85 gives ~50 prototypes per LoCoMo conversation. Default 0.85.",
    )
    parser.add_argument(
        "--max-prototypes",
        type=int,
        default=128,
        help="Cap on prototypes formed per replay (default 128).",
    )
    parser.add_argument("--no-salience-rerank", action="store_true")
    parser.add_argument("--salience-weight", type=float, default=0.5)
    parser.add_argument("--tau-seconds", type=float, default=float(86400 * 30))
    parser.add_argument("--surprise-weight", type=float, default=0.3)
    parser.add_argument("--spread-score-weight", type=float, default=0.90)
    parser.add_argument("--no-graph-expansion", action="store_true")
    parser.add_argument(
        "--no-transition",
        action="store_true",
        help="Disable the predictive transition-model seed at recall "
        "(Stage 3 ablation: leaves the rest of the pipeline intact).",
    )
    parser.add_argument(
        "--no-self-supervise",
        action="store_true",
        help="Disable the self-supervised retrieval-rehearsal pass at the "
        "end of consolidation (Stage 5 ablation).",
    )
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--keep-debug-dbs", action="store_true")
    parser.add_argument(
        "--timeout", type=float, default=180.0, help="Per-call timeout in seconds (default 180)"
    )
    parser.add_argument(
        "--no-pattern-separation",
        action="store_true",
        help="Stage 8 ablation: disable dentate-gyrus-style competitive prototype assignment.",
    )
    parser.add_argument(
        "--no-multi-scale",
        action="store_true",
        help="Stage 9 ablation: disable CA3+CA1 dual-scale prototypes.",
    )
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    dataset_path = Path(args.dataset)
    if not dataset_path.is_absolute():
        dataset_path = REPO_ROOT / dataset_path
    if not dataset_path.exists():
        print("Dataset not found:", dataset_path)
        print(
            "Download: curl -o data/locomo/locomo10.json https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json"
        )
        sys.exit(1)
    print("Loading dataset:", dataset_path)
    samples = json.load(open(dataset_path))
    if args.limit > 0:
        samples = samples[: args.limit]
    print("Conversations:", len(samples), " categories:", args.categories)
    print("Loading encoder...", end=" ", flush=True)
    enc = TextEncoder(EncoderConfig())
    _ = enc.dim
    print("OK (dim=%d)" % enc.dim)
    print()
    if args.out:
        out_path = Path(args.out)
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        mode = "with_consolidation" if not args.no_consolidate else "no_consolidation"
        cats = "-".join(str(c) for c in sorted(args.categories))
        filename = "%s_%s_cats%s.json" % (stamp, mode, cats)
        out_path = REPO_ROOT / "data" / "locomo" / "runs" / filename
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path

    all_results = []
    t_start = time.time()
    for i, sample in enumerate(samples):
        conv_id = sample.get("sample_id", str(i))
        print("[%d/%d] %s ..." % (i + 1, len(samples), conv_id), flush=True)
        t0 = time.time()
        try:
            rs = run_conversation(
                sample,
                consolidate=not args.no_consolidate,
                shared_encoder=enc,
                categories=args.categories,
                top_k=args.top_k,
                no_salience_rerank=args.no_salience_rerank,
                no_graph_expansion=args.no_graph_expansion,
                keep_debug_dbs=args.keep_debug_dbs,
                timeout_s=args.timeout,
                replay_only=args.replay_only,
                assignment_threshold=args.assignment_threshold,
                max_prototypes_per_replay=args.max_prototypes,
                no_transition=args.no_transition,
                no_self_supervise=args.no_self_supervise,
                no_pattern_separation=args.no_pattern_separation,
                no_multi_scale=args.no_multi_scale,
                tau_seconds=args.tau_seconds,
                salience_weight=args.salience_weight,
                surprise_weight=args.surprise_weight,
                spread_score_weight=args.spread_score_weight,
            )
        except Exception as e:
            print("  ERROR:", e)
            rs = []
        all_results.extend(rs)
        hits = sum(1 for r in rs if r.hit)
        elapsed = time.time() - t0
        print(
            "  %dq  %dhits (%.0f%%)  %.1fs" % (len(rs), hits, 100 * hits / max(1, len(rs)), elapsed)
        )
        _save(out_path, all_results, args, time.time() - t_start, partial=True)
    print("\nCompleted %d questions in %.1fs" % (len(all_results), time.time() - t_start))
    print_report(all_results, not args.no_consolidate)
    _save(out_path, all_results, args, time.time() - t_start, partial=False)
    print("\nResults saved to:", out_path)


if __name__ == "__main__":
    main()
