#!/usr/bin/env bash
# Slowave + Cline TUI wrapper (Path 1).
#
# What it does:
#   1. Prints a memory brief from Slowave to stderr before Cline starts.
#   2. Starts an Slowave session and exports SLOWAVE_SESSION_ID into Cline's env.
#   3. Runs Cline normally (preserving its TTY – we do NOT pipe its output).
#   4. On exit, closes the session (which triggers replay + LLM consolidation).
#
# What it does NOT do:
#   - Automatically capture Cline's turns. Piping a TUI's stdout breaks its TTY.
#     Instead, the agent (or you) should call `slowave event append` directly
#     using $SLOWAVE_SESSION_ID. Allowlist `slowave` as a shell tool in Cline.
#
# Environment:
#   SLOWAVE_PROJECT  override the project name (default: current dir basename)
#   SLOWAVE_AGENT    override the agent name  (default: cline-tui)
#   SLOWAVE_BIN      explicit path to the slowave binary or wrapper
#   SLOWAVE_PY       Python executable that has slowave installed (fallback)
#   CLINE_CMD         the cline command/binary to exec (default: cline)

set -uo pipefail

# Resolve the slowave invocation.
resolve_slowave() {
  if [ -n "${SLOWAVE_BIN:-}" ]; then
    echo "$SLOWAVE_BIN"
    return 0
  fi
  if command -v slowave >/dev/null 2>&1; then
    echo "slowave"
    return 0
  fi
  local py="${SLOWAVE_PY:-python3}"
  if "$py" -c "import slowave" >/dev/null 2>&1; then
    echo "$py -m slowave"
    return 0
  fi
  return 1
}

if ! AMB=$(resolve_slowave); then
  cat >&2 <<MSG
error: slowave is not installed or not importable.

Fix one of:
  1. Install the package:
       cd $(cd "$(dirname "$0")/.." && pwd)
       python3 -m venv .venv && source .venv/bin/activate
       pip install -e .
  2. Or set SLOWAVE_PY to a Python that has slowave available, e.g.:
       export SLOWAVE_PY=/path/to/venv/bin/python
  3. Or set SLOWAVE_BIN to an explicit slowave launcher path.

Run scripts/slowave-check.sh for a fuller diagnostic.
MSG
  exit 1
fi

PROJECT="${SLOWAVE_PROJECT:-$(basename "$PWD")}"
AGENT="${SLOWAVE_AGENT:-cline-tui}"
CLINE_CMD="${CLINE_CMD:-cline}"

if ! command -v "$CLINE_CMD" >/dev/null 2>&1; then
  echo "error: cline command not found ('$CLINE_CMD'). Set CLINE_CMD=..." >&2
  exit 1
fi

echo "=== Slowave memory brief (project: $PROJECT) ===" >&2
$AMB --no-llm context --project "$PROJECT" --limit 10 >&2 || echo "  (no memories yet, or LLM disabled)" >&2
echo "=================================================" >&2

# Start session. Parse JSON robustly; fall back to running cline anyway.
SESSION_JSON=$($AMB --no-llm --json session start --agent "$AGENT" --project "$PROJECT" 2>/dev/null || true)
SID=$(printf '%s' "$SESSION_JSON" | "${SLOWAVE_PY:-python3}" -c 'import sys,json
try: d = json.load(sys.stdin)
except Exception: d = {}
print(d.get("session_id",""))' 2>/dev/null || true)

if [ -z "$SID" ]; then
  echo "warn: slowave session start failed; running cline without session capture" >&2
  exec "$CLINE_CMD" "$@"
fi

echo "slowave: session $SID started" >&2
export SLOWAVE_SESSION_ID="$SID"
export SLOWAVE_PROJECT="$PROJECT"

cleanup() {
  echo "" >&2
  echo "slowave: closing session $SID (consolidating)" >&2
  $AMB session end "$SID" >&2 || true
}
trap cleanup EXIT INT TERM

# Run cline natively. Do NOT pipe – that breaks its TTY.
"$CLINE_CMD" "$@"
