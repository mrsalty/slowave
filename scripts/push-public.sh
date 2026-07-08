#!/bin/bash
# push-public.sh — sync public-main with main and push to public remote.
#
# Two-repo strategy:
#   origin → slowave-private.git  (main branch, includes private/)
#   public → slowave.git          (public-main branch, excludes private/)
#
# Exclusions are read from .publicignore (one path per line, # comments).
# This script squashes all new commits from main into a single clean commit
# on public-main, excluding everything listed in .publicignore via pathspec.
# Usage: bash scripts/push-public.sh

set -euo pipefail

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
REPO_ROOT=$(git rev-parse --show-toplevel)

# ------------------------------------------------------------------
# Read exclusions from .publicignore → pathspec array + raw paths
# ------------------------------------------------------------------
EXCLUSION_PATHS=()
EXCLUSION_PATHSPECS=()

if [ -f "$REPO_ROOT/.publicignore" ]; then
    while IFS= read -r line; do
        # Strip inline comments and trim whitespace
        line="${line%%#*}"
        line="${line## }"
        line="${line%% }"
        [[ -z "$line" ]] && continue
        EXCLUSION_PATHS+=("$line")
        EXCLUSION_PATHSPECS+=(":!$line")
    done < "$REPO_ROOT/.publicignore"
fi

# ------------------------------------------------------------------
# 1. One-time setup: create public-main if it doesn't exist
# ------------------------------------------------------------------
if ! git rev-parse --verify public-main >/dev/null 2>&1; then
    echo "→ Creating public-main branch from main (one-time setup)"
    git checkout -b public-main main

    # Remove every path listed in .publicignore
    for path in "${EXCLUSION_PATHS[@]}"; do
        if git ls-files --error-unmatch "$path" >/dev/null 2>&1; then
            git rm -r --cached "$path" 2>/dev/null || true
        fi
    done

    git commit -m "Initial public release" --allow-empty
    git push public public-main:main
    git checkout "$CURRENT_BRANCH"
    echo "✓ public-main created and pushed to public remote"
    exit 0
fi

# ------------------------------------------------------------------
# 2. Sync: squash main into public-main, excluding .publicignore paths
# ------------------------------------------------------------------
echo "→ Syncing main → public-main"
git checkout public-main

if [ ${#EXCLUSION_PATHSPECS[@]} -gt 0 ]; then
    git merge --squash main -- . "${EXCLUSION_PATHSPECS[@]}"
else
    git merge --squash main
fi

git commit -m "$(date +'%Y-%m-%d') sync" --allow-empty

# 3. Push to public remote as main
echo "→ Pushing to public"
git push public public-main:main

# 4. Back to wherever we were
git checkout "$CURRENT_BRANCH"
echo "✓ Done — public remote updated"