#!/usr/bin/env bash
# Diagnose an Slowave install. Prints what's reachable and what's broken.
set -u

rc=0
say() { printf '%s\n' "$*"; }
ok()  { say "  OK   $*"; }
bad() { say "  FAIL $*"; rc=1; }

say "== Slowave self-check =="

say "-- slowave binary --"
if command -v slowave >/dev/null 2>&1; then
  ok "slowave on PATH ($(command -v slowave))"
else
  bad "slowave not on PATH; need 'pip install -e .' or set SLOWAVE_PY"
fi

say "-- slowave python import --"
PY="${SLOWAVE_PY:-python3}"
if "$PY" -c 'import slowave; print("  slowave", slowave.__version__, "OK from", slowave.__file__)' 2>/dev/null; then
  ok "$PY can import slowave"
else
  bad "$PY cannot import slowave (set SLOWAVE_PY to a venv that has it)"
fi

say "-- python deps --"
for dep in numpy torch faiss click sentence_transformers; do
  if "$PY" -c "import $dep" 2>/dev/null; then
    ok "$dep importable"
  else
    case "$dep" in
      sentence_transformers) bad "$dep missing (needed for text recall/event)";;
      *)                     bad "$dep missing";;
    esac
  fi
done

say "-- db --"
DB="${SLOWAVE_DB:-$HOME/.slowave/slowave.db}"
if [ -f "$DB" ]; then
  ok "db exists at $DB"
else
  say "  info  no db yet at $DB (will be created on first command)"
fi

exit $rc
