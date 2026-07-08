#!/usr/bin/env bash
# Grid search: spread_score_weight on LoCoMo (limit=3, fast iteration).
#
# Runs locomo_eval.py with different spread_score_weight values and
# tabulates the results. Designed to find the optimal discount for
# spread-projection FAISS scores vs cosine-direct scores.
#
# Usage:
#   LIMIT=3 bash private/docs/consolidation/scripts/grid_search_spread_weight.sh
#   LIMIT=10 bash private/docs/consolidation/scripts/grid_search_spread_weight.sh
#
# Requires: LoCoMo dataset at data/locomo/locomo10.json

set -euo pipefail

cd "$(dirname "$0")/../../../.."

VALUES=(0.50 0.60 0.65 0.70 0.75 0.80 0.85 0.90 0.95)
LIMIT=${LIMIT:-3}
OUTDIR="tmp/grid_spread_weight"
LOGDIR="$OUTDIR/logs"
TALLY="$OUTDIR/tally.tsv"
mkdir -p "$OUTDIR" "$LOGDIR"
> "$TALLY"

N=${#VALUES[@]}

echo "================================================================"
echo "Grid Search: spread_score_weight"
echo "Values: ${VALUES[*]}"
echo "Limit:  $LIMIT conversations"
echo "Output: $OUTDIR/"
echo "================================================================"
echo ""

t_start=$(date +%s)

for i in "${!VALUES[@]}"; do
    sw="${VALUES[$i]}"
    idx=$((i + 1))
    echo "[$idx/$N] spread_score_weight=$sw  …" | tee -a "$TALLY"

    OUTFILE="$OUTDIR/sw_${sw}.json"
    LOGFILE="$LOGDIR/sw_${sw}.log"

    # Run eval; capture full log, show per-conversation progress lines
    set +e
    uv run python tests/integration/locomo_eval.py \
        --limit "$LIMIT" \
        --spread-score-weight "$sw" \
        --out "$OUTFILE" \
        > "$LOGFILE" 2>&1
    rc=$?
    set -e

    if [ "$rc" -ne 0 ]; then
        echo "  FAILED (exit code $rc) — see $LOGFILE" | tee -a "$TALLY"
        echo ""
        continue
    fi

    # Extract per-conversation lines from log for live output
    grep -E '^\[[0-9]+/[0-9]+\]' "$LOGFILE" || true

    # Extract overall score from the final summary line
    # Format: "OVERALL  nq  nhits (XX.X%)" or "Completed N questions in Xs"
    if [ -f "$OUTFILE" ]; then
        P90=$(python3 -c "
import json
with open('$OUTFILE') as f:
    d = json.load(f)
results = d['results']
hits = sum(1 for r in results if r.get('hit'))
total = len(results)
overall = 100*hits/max(1,total)
cats = {}
for r in results:
    c = r.get('category',0)
    cats.setdefault(c,{'hits':0,'total':0})
    cats[c]['total'] += 1
    if r.get('hit'): cats[c]['hits'] += 1
print(f'{overall:.1f}')
" 2>/dev/null || echo "ERR")
        printf "  OVERALL %s%%  →  %s/sw_%s.json\n" "$P90" "$OUTDIR" "$sw" | tee -a "$TALLY"
    else
        echo "  NO JSON — see $LOGFILE" | tee -a "$TALLY"
    fi
    echo ""
done

# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------
elapsed=$(($(date +%s) - t_start))
echo "================================================================"
echo "Summary Table  (${elapsed}s elapsed)"
echo "================================================================"
printf "%-12s %s\n" "sw" "Overall%"
printf "%-12s %s\n" "-----------" "--------"

for sw in "${VALUES[@]}"; do
    OUTFILE="$OUTDIR/sw_${sw}.json"
    if [ -f "$OUTFILE" ]; then
        ACC=$(python3 -c "
import json
with open('$OUTFILE') as f:
    d = json.load(f)
hits = sum(1 for r in d['results'] if r.get('hit'))
total = len(d['results'])
pct = 100*hits/max(1,total)
print(f'{pct:.1f}')
" 2>/dev/null || echo "ERR")
        printf "%-12s %s%%\n" "$sw" "$ACC"
    else
        printf "%-12s %s\n" "$sw" "N/A"
    fi
done

echo ""
echo "Raw results: $OUTDIR/"
echo "Full logs:    $LOGDIR/"
echo "Tally:        $TALLY"