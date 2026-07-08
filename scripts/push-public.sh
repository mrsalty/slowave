#!/usr/bin/env bash
# push-public.sh — publish sanitized private main to public repository.
#
# origin -> private repository
# public -> public repository
#
# Files listed in .publicignore NEVER appear in public repository.

set -euo pipefail

SOURCE_BRANCH="main"
PUBLIC_BRANCH="main"

REPO_ROOT=$(git rev-parse --show-toplevel)
CURRENT_BRANCH=$(git branch --show-current)
TMP_DIR=$(mktemp -d)

cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

# ---------------------------------------------------------
# Safety checks
# ---------------------------------------------------------

if [[ "$CURRENT_BRANCH" != "$SOURCE_BRANCH" ]]; then
    echo "ERROR: Run this script from '$SOURCE_BRANCH' (currently on '$CURRENT_BRANCH')."
    exit 1
fi

if ! git remote get-url public >/dev/null 2>&1; then
    echo "ERROR: Remote 'public' not configured."
    exit 1
fi

# ---------------------------------------------------------
# Commit message
# ---------------------------------------------------------

if [[ $# -gt 0 ]]; then
    COMMIT_MESSAGE="$*"
else
    DEFAULT_MESSAGE="chore(public): sync private repository"

    echo
    read -r -p "Public commit message [$DEFAULT_MESSAGE]: " COMMIT_MESSAGE
    COMMIT_MESSAGE="${COMMIT_MESSAGE:-$DEFAULT_MESSAGE}"
fi

echo "→ Exporting $SOURCE_BRANCH"

git archive "$SOURCE_BRANCH" | tar -x -C "$TMP_DIR"

cd "$TMP_DIR"

# ---------------------------------------------------------
# Load exclusions
# ---------------------------------------------------------

EXCLUSIONS=()

if [[ -f "$REPO_ROOT/.publicignore" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%%#*}"
        line="$(echo "$line" | xargs)"

        [[ -z "$line" ]] && continue

        EXCLUSIONS+=("$line")
    done < "$REPO_ROOT/.publicignore"
fi

echo "→ Removing excluded paths"

for path in "${EXCLUSIONS[@]}"; do
    rm -rf "$path"
done

# ---------------------------------------------------------
# Prepare clean public repository
# ---------------------------------------------------------

git init -q
git checkout -b "$PUBLIC_BRANCH"

git add .

git commit -m "$COMMIT_MESSAGE"

# ---------------------------------------------------------
# Connect and sync public repository
# ---------------------------------------------------------

PUBLIC_URL=$(git -C "$REPO_ROOT" remote get-url public)

git remote add public "$PUBLIC_URL"

echo "→ Syncing public repository"

git fetch public "$PUBLIC_BRANCH" || true

git push public \
    "$PUBLIC_BRANCH:$PUBLIC_BRANCH" \
    --force-with-lease

echo
echo "✓ Public release completed"
echo "✓ Commit: $COMMIT_MESSAGE"
echo "✓ .publicignore paths excluded"