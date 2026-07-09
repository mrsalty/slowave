#!/usr/bin/env bash
# push-public.sh — publish sanitized private main to public repository.
#
# origin -> private repository
# public -> public repository
#
# Files listed in .publicignore NEVER appear in public repository.
#
# Strategy: clone the public repo (preserving its history), overlay the
# sanitized private tree, commit on top.  This keeps public git history
# linear so that Release Please (and other tooling) can see incremental
# conventional-commit messages and bump versions correctly.
#
# Release Please owns these files on the public side; they are restored
# from the public clone after the private-tree overlay:
#   .release-please-manifest.json
#   CHANGELOG.md
#   pyproject.toml  (version line only — all other content flows from private)

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

# ---------------------------------------------------------
# Load exclusions from .publicignore
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

echo "→ Exporting $SOURCE_BRANCH tree"

# Export the private tree into a staging area
STAGING="$TMP_DIR/staging"
mkdir -p "$STAGING"

git archive "$SOURCE_BRANCH" | tar -x -C "$STAGING"

echo "→ Removing excluded paths"

for path in "${EXCLUSIONS[@]}"; do
    rm -rf "$STAGING/$path"
done

# ---------------------------------------------------------
# Clone public repo (or bootstrap if empty)
# ---------------------------------------------------------

PUBLIC_URL=$(git -C "$REPO_ROOT" remote get-url public)
PUBLIC_CLONE="$TMP_DIR/public"

echo "→ Cloning public repository"

# Try a normal clone; fall back to init if the remote has no commits yet.
if git clone --branch "$PUBLIC_BRANCH" "$PUBLIC_URL" "$PUBLIC_CLONE" 2>/dev/null; then
    echo "   (existing repo — preserving history, tags, manifest)"
    BOOTSTRAP=false
else
    echo "   (empty remote — bootstrapping first commit)"
    git init -q "$PUBLIC_CLONE"
    git -C "$PUBLIC_CLONE" checkout -b "$PUBLIC_BRANCH"
    # Create an empty initial commit so there's a parent to build on
    git -C "$PUBLIC_CLONE" commit -q --allow-empty -m "chore: initial empty commit"
    git -C "$PUBLIC_CLONE" remote add public "$PUBLIC_URL"
    BOOTSTRAP=true
fi

# ---------------------------------------------------------
# Save Release-Please-owned files from the public clone
# ---------------------------------------------------------

# These files are managed by Release Please on the public side.
# We restore them after overlaying the private tree so that
# version bumps, changelog entries, and manifest state survive.
#
# pyproject.toml: we only save the version line — all other content
# (dependencies, scripts, metadata) flows from the private tree.

SAVED_MANIFEST="$TMP_DIR/.release-please-manifest.json.public"
SAVED_CHANGELOG="$TMP_DIR/CHANGELOG.md.public"
SAVED_VERSION="$TMP_DIR/version.txt"

if [[ -f "$PUBLIC_CLONE/.release-please-manifest.json" ]]; then
    cp "$PUBLIC_CLONE/.release-please-manifest.json" "$SAVED_MANIFEST"
fi

if [[ -f "$PUBLIC_CLONE/CHANGELOG.md" ]]; then
    cp "$PUBLIC_CLONE/CHANGELOG.md" "$SAVED_CHANGELOG"
fi

# Extract just the version string from the public pyproject.toml
if [[ -f "$PUBLIC_CLONE/pyproject.toml" ]]; then
    grep -E '^version\s*=' "$PUBLIC_CLONE/pyproject.toml" > "$SAVED_VERSION" || true
fi

# ---------------------------------------------------------
# Overlay the sanitized private tree onto the public clone
# ---------------------------------------------------------

echo "→ Overlaying sanitized tree"

cd "$PUBLIC_CLONE"

# Remove everything except .git from the working tree
find . -not -path './.git' -not -path './.git/*' -delete 2>/dev/null || true

# Copy the sanitized staging tree in
(
    cd "$STAGING"
    find . -mindepth 1 -maxdepth 1 | while read -r entry; do
        cp -a "$entry" "$PUBLIC_CLONE/"
    done
)

# ---------------------------------------------------------
# Restore Release-Please-owned files
# ---------------------------------------------------------

echo "→ Restoring Release-Please-owned files"

if [[ -f "$SAVED_MANIFEST" ]]; then
    cp "$SAVED_MANIFEST" "$PUBLIC_CLONE/.release-please-manifest.json"
fi

if [[ -f "$SAVED_CHANGELOG" ]]; then
    cp "$SAVED_CHANGELOG" "$PUBLIC_CLONE/CHANGELOG.md"
fi

# Restore the public version into pyproject.toml (while keeping everything
# else from the private tree — dependencies, scripts, metadata, etc.)
if [[ -f "$SAVED_VERSION" && -f "$PUBLIC_CLONE/pyproject.toml" ]]; then
    PUBLIC_VER=$(cat "$SAVED_VERSION")
    if [[ -n "$PUBLIC_VER" ]]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s/^version = .*/$PUBLIC_VER/" "$PUBLIC_CLONE/pyproject.toml"
        else
            sed -i "s/^version = .*/$PUBLIC_VER/" "$PUBLIC_CLONE/pyproject.toml"
        fi
    fi
fi

# ---------------------------------------------------------
# Commit and push
# ---------------------------------------------------------

echo "→ Committing"

git add -A

# Check if there are any changes to commit
if git diff --cached --quiet; then
    echo "   (no changes — everything up to date)"
    echo
    echo "✓ Nothing to push"
    exit 0
fi

git commit -m "$COMMIT_MESSAGE"

echo "→ Pushing to public"

# First push: need --set-upstream if we bootstrapped
if $BOOTSTRAP; then
    git push --set-upstream public "$PUBLIC_BRANCH:$PUBLIC_BRANCH"
else
    git push public "$PUBLIC_BRANCH:$PUBLIC_BRANCH"
fi

echo
echo "✓ Public sync completed"
echo "✓ Commit: $COMMIT_MESSAGE"
echo "✓ .publicignore paths excluded"
echo "✓ Release-Please-owned files preserved from public repo"
