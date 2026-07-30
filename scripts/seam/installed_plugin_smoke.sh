#!/usr/bin/env bash
# Simulate an installed plugin: shipped files only, foreign root,
# CLAUDE_PLUGIN_ROOT set. Exit 0 = smoke passed (issue #11 §1 item 2).
#
# Ship list: neither .claude-plugin/plugin.json nor marketplace.json
# enumerates shipped paths (marketplace "source" is just "./" — the whole
# repo is the plugin), and there is no publish.sh filter-repo step in the
# 0.2+ publish model (scripts/publish-checklist.md: "publishing is now
# just a push" — the whole git-tracked tree ships as-is). So instead of
# hardcoding a directory list that can silently drift from what actually
# ships, this derives the copy from `git archive HEAD`: exactly the
# tracked files a `git push` would send, nothing gitignored/untracked.
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

git -C "$repo_root" archive HEAD | (cd "$scratch" && tar -xf -)

export CLAUDE_PLUGIN_ROOT="$scratch"
cd "$scratch"   # crucially: NOT the git clone

python3 "$scratch/scripts/seam/hook_contract_check.py" \
  --hook-cmd "python3 $scratch/hooks/wake-up/ren-wake-up.py"
echo "installed-plugin smoke OK"
