#!/usr/bin/env bash
# Ablation study: measure the isolated contribution of each architectural component.
#
# Conditions (7 runs × ~180 questions each):
#
#   A  full          LLM on, salience rerank on, graph expansion on   (current system)
#   B  no_llm        LLM off (episodes only, no schema extraction)
#   C  no_salience   LLM on,  salience_weight=0
#   D  no_graph      LLM on,  graph neighbor_top_k=0
#   E  no_replay     LLM off, assignment_threshold=1.1 (nothing clusters)
#   F  no_llm_no_sal LLM off, salience_weight=0
#   G  pure_embed    LLM off, salience_weight=0, graph off  (pure FAISS baseline)
#
# Each run saves to data/longmemeval/runs/ablation_<condition>_<stamp>.json
# After all runs complete, run:
#   .venv/bin/python scripts/ablation_summary.py data/longmemeval/runs/ablation_*.json
#
# Usage:
#   LIMIT=30 MODEL=qwen2.5-coder:1.5b scripts/run-ablation.sh
#   LIMIT=10 RUN_LLM=0 scripts/run-ablation.sh   # fast smoke check, no-LLM conditions only

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export KMP_DUPLICATE_LIB_OK="${KMP_DUPLICATE_LIB_OK:-TRUE}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export TOKENIZERS_PARALLELISM="${TOKENIZERS_PARALLELISM:-false}"

PY="${PY:-./.venv/bin/python}"
MODEL="${MODEL:-qwen2.5-coder:1.5b}"
LIMIT="${LIMIT:-30}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUTDIR="${OUTDIR:-data/longmemeval/runs}"
LOGDIR="${LOGDIR:-data/longmemeval/logs}"
RUN_LLM="${RUN_LLM:-1}"      # set to 0 to skip LLM conditions (B/C/D/A)
RUN_NO_LLM="${RUN_NO_LLM:-1}" # set to 0 to skip no-LLM conditions

CATS="knowledge-update single-session-preference multi-session single-session-user single-session-assistant temporal-reasoning"

mkdir -p "$OUTDIR" "$LOGDIR"

echo "== Slowave Ablation Study =="
echo "model     : $MODEL"
echo "limit/cat : $LIMIT"
echo "stamp     : $STAMP"
echo "run_llm   : $RUN_LLM"
echo "run_no_llm: $RUN_NO_LLM"
echo

run_condition() {
    local name="$1"; shift
    local out="$OUTDIR/ablation_${name}_${STAMP}.json"
    local log="$LOGDIR/ablation_${name}_${STAMP}.log"
    echo "[$(date +%H:%M:%S)] START condition=$name"
    echo "  out: $out"
    "$PY" tests/integration/longmemeval_eval.py \
        --categories $CATS \
        --limit "$LIMIT" \
        --recall-mode hybrid \
        --top-k 10 \
        --out "$out" \
        "$@" 2>&1 | tee "$log"
    echo "[$(date +%H:%M:%S)] DONE  condition=$name"
    echo
}

# ---- no-LLM conditions (fast, no Ollama needed) ----
if [[ "$RUN_NO_LLM" == "1" ]]; then
    # B: no LLM — pure episode embedding recall
    run_condition "B_no_llm" \
        --no-consolidate

    # F: no LLM + no salience rerank
    run_condition "F_no_llm_no_sal" \
        --no-consolidate \
        --no-salience-rerank

    # G: pure embedding baseline — no LLM, no salience, no graph
    run_condition "G_pure_embed" \
        --no-consolidate \
        --no-salience-rerank \
        --no-graph-expansion

    # E: no replay / no prototypes — LLM off, assignment_threshold=1.1 so nothing clusters
    run_condition "E_no_replay" \
        --no-consolidate \
        --assignment-threshold 1.1
fi

# ---- LLM conditions (slower, requires Ollama) ----
if [[ "$RUN_LLM" == "1" ]]; then
    # C: LLM on, salience rerank off
    run_condition "C_no_salience" \
        --model "$MODEL" \
        --no-salience-rerank

    # D: LLM on, graph expansion off
    run_condition "D_no_graph" \
        --model "$MODEL" \
        --no-graph-expansion

    # A: full system (run last so it doesn't bias earlier conditions)
    run_condition "A_full" \
        --model "$MODEL"
fi

echo "== Ablation complete =="
echo
echo "Results saved to: $OUTDIR/ablation_*_${STAMP}.json"
echo
echo "Run summary:"
echo "  $PY scripts/ablation_summary.py $OUTDIR/ablation_*_${STAMP}.json"
