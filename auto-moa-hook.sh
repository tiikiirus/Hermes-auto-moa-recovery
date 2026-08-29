#!/usr/bin/env bash
#
# Git post-merge hook: re-apply auto-MoA patch after `git pull`.
# Runs only if the patch file exists alongside this hook and patch is still needed.
#
# NOTE: `hermes update` uses `git reset --hard` which does NOT trigger this hook.
#       For hermes update, use hermes-update.bat wrapper instead.
#       This hook covers manual `git pull` / `git merge` operations.
#
set -euo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$HOOK_DIR" rev-parse --show-toplevel 2>/dev/null || echo "")"

if [ -z "$REPO_ROOT" ]; then
  echo "[auto-moa-hook] not inside a git worktree; skip."
  exit 0
fi

# Patch is copied alongside this hook by install-auto-moa.bat
PATCH_FILE="$HOOK_DIR/auto-moa/auto-moa-current.patch"

if [ ! -f "$PATCH_FILE" ]; then
  echo "[auto-moa-hook] no auto-moa-current.patch found; skip."
  exit 0
fi

cd "$REPO_ROOT"

# Idempotency: only apply if moa_auto_router.py is NOT already present
if [ -f "agent/moa_auto_router.py" ]; then
  if git apply --reverse --check "$PATCH_FILE" >/dev/null 2>&1; then
    echo "[auto-moa-hook] patch already applied; skip."
    exit 0
  fi
  echo "[auto-moa-hook] divergence detected; re-applying..."
fi

echo "[auto-moa-hook] applying auto-MoA patch: $PATCH_FILE"
if git apply --whitespace=nowarn --check "$PATCH_FILE" 2>/dev/null; then
  git apply --whitespace=nowarn "$PATCH_FILE"
  echo "[auto-moa-hook] patch applied successfully."
elif git apply --3way --check "$PATCH_FILE" 2>/dev/null; then
  git apply --3way "$PATCH_FILE"
  echo "[auto-moa-hook] patch applied (3-way merge)."
else
  echo "[auto-moa-hook] ERROR: patch cannot be applied cleanly. Resolve manually."
  exit 1
fi
