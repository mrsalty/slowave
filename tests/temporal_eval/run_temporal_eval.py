#!/usr/bin/env python3
"""Temporal memory evaluation runner."""
from __future__ import annotations
import argparse, json, logging, os, sys, time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
logging.basicConfig(level=logging.WARNING)
for _n in ("sentence_transformers","transformers","httpx","httpcore","huggingface_hub","filelock","tqdm"):
    logging.getLogger(_n).setLevel(logging.ERROR)

from slowave.symbolic.encoder import EncoderConfig, TextEncoder
from tests.temporal_eval.harness import ScenarioResult, TemporalHarness
from tests.temporal_eval.scenarios import (
    decay,
    reinforcement,
    coactivation,
    supersession,
    chain,
    completion,
)

ABLATIONS = ["full", "no_salience", "no_graph", "no_llm"]

def run_ablation(ablation, *, model, ollama_url, tau_days, shared_enc):
    consolidate = ablation != "no_llm"
    results = []
    for fam_name, fam_mod, fam_cons in [
        ("decay",         decay,         False),
        ("reinforcement", reinforcement, False),
        ("coactivation",  coactivation,  False),
        ("chain",         chain,         False),
        ("completion",    completion,    False),
        ("supersession",  supersession,  True),
    ]:
        if fam_cons and not consolidate:
            print(f"  [{ablation}] skipping {fam_name} (no LLM)")
            continue
        print(f"  [{ablation}] {fam_name}...", end=" ", flush=True)
        h = TemporalHarness(shared_encoder=shared_enc, model=model, ollama_url=ollama_url,
                            consolidate=fam_cons and consolidate, tau_days=tau_days, ablation=ablation)
        try:
            t0 = time.time()
            rs = fam_mod.run_all(h)
            results += rs
            hits = sum(1 for r in rs if r.hit)
            print(f"{hits}/{len(rs)} hits  {time.time()-t0:.1f}s")
        except Exception as e:
            print(f"ERROR: {e}")
        finally:
            h.close()
    return results

def print_report(all_results):
    print("\n" + "="*80)
    print(" SLOWAVE — Temporal Memory Evaluation")
    print("="*80)
    all_ids = list(dict.fromkeys(r.scenario_id for rs in all_results.values() for r in rs))
    print(f"\n {'Scenario':<8} {'Component':<16} {'Expected':<14}", end="")
    for abl in all_results: print(f"  {abl:<14}", end="")
    print()
    print(f" {'-'*8} {'-'*16} {'-'*14}", end="")
    for _ in all_results: print(f"  {'-'*14}", end="")
    print()
    for sid in sorted(all_ids):
        first = next((r for rs in all_results.values() for r in rs if r.scenario_id==sid), None)
        if not first: continue
        print(f" {sid:<8} {first.component:<16} {first.expected_keyword:<14}", end="")
        for abl, results in all_results.items():
            r = next((r for r in results if r.scenario_id==sid), None)
            mark = ("HIT " if r.hit else "miss") if r else "n/a "
            print(f"  {mark:<14}", end="")
        print()
    print()
    print(f" {'Ablation':<16}  {'Hits':<8}  {'Score':<8}  Per component")
    print(f" {'-'*16}  {'-'*8}  {'-'*8}  {'-'*40}")
    for abl, results in all_results.items():
        n=len(results); h=sum(1 for r in results if r.hit)
        by={}
        for r in results: by.setdefault(r.component,[]).append(r.hit)
        comp_str="  ".join(f"{c}:{sum(v)}/{len(v)}" for c,v in sorted(by.items()))
        print(f" {abl:<16}  {h}/{n:<6}  {100*h/max(1,n):>6.1f}%  {comp_str}")
    print("\nKey:")
    print("  full vs no_salience => decay/reinforcement scenarios should differ")
    print("  full vs no_graph    => coactivation/chain/completion scenarios should differ")
    print("  full vs no_llm      => supersession scenarios should differ")
    print("  chain / completion  => currently expected to mostly miss (Stage 0 baseline)")
    print("="*80)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ablation", choices=ABLATIONS, default="full")
    parser.add_argument("--compare-all", action="store_true")
    parser.add_argument("--model", default=os.environ.get("SLOWAVE_MODEL","qwen2.5-coder:1.5b"))
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--tau-days", type=float, default=7.0)
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    ablations_to_run = ABLATIONS if args.compare_all else [args.ablation]

    print("Loading encoder...", end=" ", flush=True)
    enc = TextEncoder(EncoderConfig()); _ = enc.dim
    print(f"OK (dim={enc.dim})")

    all_results = {}
    for abl in ablations_to_run:
        print(f"\n{'='*50}\nAblation: {abl}\n{'='*50}")
        all_results[abl] = run_ablation(abl, model=args.model, ollama_url=args.ollama_url,
                                        tau_days=args.tau_days, shared_enc=enc)
    print_report(all_results)

    out = args.out or (f"data/temporal_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json" if args.compare_all else "")
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        payload={"meta":{"created_at":datetime.now().isoformat(),"model":args.model,
                          "tau_days":args.tau_days,"ablations":ablations_to_run},
                 "results":{abl:[{"scenario_id":r.scenario_id,"description":r.description,
                                   "component":r.component,"expected_keyword":r.expected_keyword,
                                   "hypothesis":r.hypothesis,"hit":r.hit,"detail":r.detail}
                                  for r in rs] for abl,rs in all_results.items()}}
        with open(out,"w") as f: json.dump(payload,f,indent=2)
        print(f"\nSaved to: {out}")

if __name__=="__main__": main()
