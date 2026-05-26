#!/usr/bin/env bash
# Run Slowave LongMemEval diagnostic experiments.
#
# Default: sequential execution. This is safest for local Ollama because LLM
# consolidation is CPU/GPU-bound and parallel model calls usually make every run
# slower/noisier.
#
# Optional parallel mode:
#   PARALLEL=1 scripts/run-longmemeval-debug-matrix.sh
#
# Useful overrides:
#   MODEL=qwen2.5-coder:1.5b LIMIT=10 scripts/run-longmemeval-debug-matrix.sh
#   CATEGORIES="knowledge-update single-session-preference" LIMIT=30 ...
#   RUN_LLM=0 scripts/run-longmemeval-debug-matrix.sh       # no-LLM only
#   RUN_NO_LLM=0 scripts/run-longmemeval-debug-matrix.sh    # LLM only

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export KMP_DUPLICATE_LIB_OK="${KMP_DUPLICATE_LIB_OK:-TRUE}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export TOKENIZERS_PARALLELISM="${TOKENIZERS_PARALLELISM:-false}"

PY="${PY:-./.venv/bin/python}"
MODEL="${MODEL:-qwen2.5-coder:1.5b}"
LIMIT="${LIMIT:-10}"
CATEGORIES="${CATEGORIES:-knowledge-update}"
PARALLEL="${PARALLEL:-0}"
RUN_LLM="${RUN_LLM:-1}"
RUN_NO_LLM="${RUN_NO_LLM:-1}"
KEEP_DEBUG_DBS="${KEEP_DEBUG_DBS:-1}"

STAMP="${STAMP:-$(date +%Y%m%d_%H%M%S)}"
OUTDIR="${OUTDIR:-data/longmemeval/runs}"
LOGDIR="${LOGDIR:-data/longmemeval/logs}"
mkdir -p "$OUTDIR" "$LOGDIR" data/longmemeval/debug_dbs

KEEP_DB_FLAG=()
if [[ "$KEEP_DEBUG_DBS" == "1" ]]; then
  KEEP_DB_FLAG=(--keep-debug-dbs)
fi

echo "== Slowave LongMemEval debug matrix =="
echo "root        : $ROOT"
echo "python      : $PY"
echo "model       : $MODEL"
echo "categories  : $CATEGORIES"
echo "limit       : $LIMIT"
echo "parallel    : $PARALLEL"
echo "run_llm     : $RUN_LLM"
echo "run_no_llm  : $RUN_NO_LLM"
echo "stamp       : $STAMP"
echo

run_one() {
  local name="$1"
  shift
  local out="$OUTDIR/${STAMP}_${name}.json"
  local log="$LOGDIR/${STAMP}_${name}.log"
  echo "[$(date +%H:%M:%S)] START $name"
  echo "  out: $out"
  echo "  log: $log"
  "$PY" tests/integration/longmemeval_eval.py \
    --categories $CATEGORIES \
    --limit "$LIMIT" \
    --debug \
    "${KEEP_DB_FLAG[@]}" \
    --out "$out" \
    "$@" 2>&1 | tee "$log"
  echo "[$(date +%H:%M:%S)] DONE  $name"
  echo
}

pids=()
names=()

launch() {
  local name="$1"
  shift
  if [[ "$PARALLEL" == "1" ]]; then
    (run_one "$name" "$@") &
    pids+=("$!")
    names+=("$name")
  else
    run_one "$name" "$@"
  fi
}

# No-LLM retrieval baselines. These are safe to parallelize and are the fastest
# way to isolate whether the episode/retrieval path contains the answer.
if [[ "$RUN_NO_LLM" == "1" ]]; then
  launch "no_llm_episodes_top5"  --no-consolidate --recall-mode episodes --top-k 5
  launch "no_llm_episodes_top10" --no-consolidate --recall-mode episodes --top-k 10
  launch "no_llm_hybrid_top10"   --no-consolidate --recall-mode hybrid   --top-k 10
fi

# LLM consolidation diagnostics. Sequential is strongly recommended with local
# Ollama; use PARALLEL=1 only if the backend can handle concurrent calls.
if [[ "$RUN_LLM" == "1" ]]; then
  launch "llm_hybrid_top5"   --model "$MODEL" --recall-mode hybrid   --top-k 5
  launch "llm_hybrid_top10"  --model "$MODEL" --recall-mode hybrid   --top-k 10
  launch "llm_episodes_top10" --model "$MODEL" --recall-mode episodes --top-k 10
  launch "llm_schemas_top10"  --model "$MODEL" --recall-mode schemas  --top-k 10
fi

if [[ "$PARALLEL" == "1" ]]; then
  failed=0
  for i in "${!pids[@]}"; do
    pid="${pids[$i]}"
    name="${names[$i]}"
    if wait "$pid"; then
      echo "OK: $name"
    else
      echo "FAILED: $name" >&2
      failed=1
    fi
  done
  if [[ "$failed" != "0" ]]; then
    exit 1
  fi
fi

echo "== Matrix complete =="
echo "Results: $OUTDIR/${STAMP}_*.json"
echo "Logs   : $LOGDIR/${STAMP}_*.log"
echo
echo "Summary command:"
cat <<'PY'
python - <<'PY2'
import json, glob
for p in sorted(glob.glob('data/longmemeval/runs/*_*.json')):
    if '/runs/' not in p: continue
    try: d=json.load(open(p))
    except Exception: continue
    meta=d.get('meta',{}); s=d.get('summary',{})
    if not meta.get('debug'): continue
    print('\n', p)
    print(' partial=', meta.get('partial'), 'mode=', 'llm' if meta.get('consolidate') else 'no_llm',
          'recall=', meta.get('recall_mode'), 'top_k=', meta.get('top_k'),
          'n=', s.get('n'), 'hits=', s.get('hits'), 'pct=', s.get('score_pct'))
    rs=d.get('results',[])
    for comp in ['schemas','episodes','hybrid']:
        vals=[r.get('component_scores',{}).get(comp) for r in rs]
        vals=[v for v in vals if v is not None]
        if vals:
            print(' ', comp, 'avg=', round(sum(vals)/len(vals),3), 'hits=', sum(v>=0.5 for v in vals), '/', len(vals))
    keys=['in_retrieved_schemas','in_retrieved_episodes','in_all_schemas','in_all_episodes']
    pres={k:0 for k in keys}; total=0
    for r in rs:
        ap=r.get('debug',{}).get('answer_presence')
        if ap:
            total += 1
            for k in keys: pres[k] += bool(ap.get(k))
    if total: print(' presence=', {k:f'{v}/{total}' for k,v in pres.items()})
PY2
PY
