#!/usr/bin/env bash
#
# status.sh — print Activity Feed status as JSON for /sf:doctor consumption.
#
# Output shape (stable contract with distribution-2's sf-doctor):
#
#   {
#     "remote": "git@github.com:friend-group/activity-feed.git" | null,
#     "last_sync_iso": "2026-05-28T14:30:00+00:00" | null,
#     "push_ok": true | false,
#     "pending_commit_count": 0,
#     "consecutive_push_failures": 0,
#     "local_path": "/home/hazar/.startup-framework/activity-feed",
#     "auth_ok": true | false,
#     "schema_version_expected": 1
#   }
#
# Exit codes:
#   0 = JSON printed successfully (even when individual fields report failures)
#   1 = catastrophic failure (Python helper crashed; stderr carries detail)
#
# Usage:
#   bash skills/activity-feed/scripts/status.sh
#
# Notes:
#   - This script is intentionally THIN. All logic lives in feed/io_github.py +
#     feed/config.py. The script just bridges between sf-doctor's shell context and
#     the Python module surface.
#   - Honors SF_FRAMEWORK_ROOT for test isolation (passed through to the helper).
#   - Does NOT make network calls beyond what feed.check_auth() does (`gh auth status`).
#     Pull/push history is read from the local .state.json, not re-fetched.

set -euo pipefail

# Resolve the plugin root (where the feed/ package lives). Prefer the env CC
# sets ($CLAUDE_PLUGIN_ROOT); else fall back to the relative ../../.. from this
# script (skills/activity-feed/scripts → plugin root). Mirrors sf-wake-up.py's
# _plugin_root() so the feed import resolves in the installed runtime (C2).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  REPO_ROOT="${CLAUDE_PLUGIN_ROOT}"
else
  REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
fi

# Honor PYTHON env override for environments that pin a specific interpreter.
PYTHON_BIN="${PYTHON:-python3}"

cd "${REPO_ROOT}"

exec "${PYTHON_BIN}" - <<'PY'
import json
import subprocess
import sys
from pathlib import Path

# feed package is at the repo root; we cd'd there before exec
sys.path.insert(0, str(Path.cwd()))

try:
    from feed import config, io_github
except Exception as e:
    print(f"ERROR: failed to import feed module: {e}", file=sys.stderr)
    sys.exit(1)

local_path = config.local_path()

# Resolve the remote URL via git (best-effort; returns None if no remote)
remote = None
try:
    result = subprocess.run(
        ["git", "-C", str(local_path), "remote", "get-url", "origin"],
        capture_output=True, text=True, timeout=5,
    )
    if result.returncode == 0:
        remote = result.stdout.strip() or None
except (FileNotFoundError, subprocess.TimeoutExpired):
    pass

# Auth status (best-effort; reports cleanly on missing gh CLI)
auth = io_github.check_auth()

# State from .state.json (filesystem-only; no network)
last_sync = io_github.last_pull_at(local_path)
last_sync_iso = last_sync.isoformat() if last_sync else None
pending = io_github.pending_commit_count(local_path)
failures = io_github.consecutive_push_failures(local_path)

payload = {
    "remote": remote,
    "last_sync_iso": last_sync_iso,
    "push_ok": failures == 0,
    "pending_commit_count": pending,
    "consecutive_push_failures": failures,
    "local_path": str(local_path),
    "auth_ok": auth.authed,
    "auth_reason": auth.reason,
    "schema_version_expected": config.EXPECTED_FEED_SCHEMA_VERSION,
}

print(json.dumps(payload, indent=2, sort_keys=True))
PY
