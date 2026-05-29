#!/usr/bin/env bash
#
# publish.sh — build a clean, allowlisted ORPHAN snapshot of the Startup Framework
# and stage it for publication to the private sf-marketplace repo (per ADR-019).
#
# WHY ORPHAN-PUBLISH (the security boundary):
#   This dev repo is PRIVATE and keeps everything — full history, wiki/, raw/,
#   REVIEW*.md, maintainer docs, tags. None of that may ever reach friends, who are
#   read-only collaborators on sf-marketplace. A plain `git push` of this repo would
#   leak the whole product brain via history. So instead we build a FRESH single
#   commit containing ONLY the shippable allowlist and push THAT (force) to
#   sf-marketplace. Friends get one commit, zero history, zero wiki.
#
# This script NEVER pushes. It builds + validates the snapshot, then PRINTS the exact
# push commands for the maintainer to run by hand. Outward-facing action stays human.
#
# Usage:
#   scripts/publish.sh [--channel stable|rc] [--version X.Y.Z] [--dry-run]
#
#   --channel   stable (default) → sf-marketplace ; rc → sf-marketplace-rc
#   --version   assert plugin.json#version equals this (else abort). Optional.
#   --dry-run   build + run ALL guards, then clean up. No commit, no push commands.
#               Reusable as a pre-tag gate (see docs/SHIP_CHECKLIST.md §5).
#
# Guards (any failure = non-zero exit, loud message):
#   1. no PLACEHOLDER-ORG anywhere in the snapshot
#   2. assert-absent: NONE of the maintainer-only paths leak into the snapshot
#      (this guard is the actual ADR-019 enforcement — it must never silently pass)
#   3. `claude plugin validate <snapshot> --strict` is green
#   4. snapshot has both manifests at root .claude-plugin/ with marketplace source "./"

set -euo pipefail

# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────
GITHUB_OWNER="hazarsozer"
STABLE_REPO="sf-marketplace"
RC_REPO="sf-marketplace-rc"
COMMIT_NAME="Hazar Sozer"
COMMIT_EMAIL="hsozer00@gmail.com"

# Shippable allowlist — ONLY these are copied into the snapshot.
# Dirs are copied whole (their per-module tests/ ride along — harmless); the docs/
# entries are individual files so the rest of docs/ (maintainer-only) never ships.
ALLOWLIST=(
  ".claude-plugin"
  "hooks"
  "skills"
  "feed"
  "wiki-skeleton"
  "README.md"
  "CHANGELOG.md"
  "LICENSES.md"
  "docs/ACTIVITY_FEED.md"
  "docs/RECOVERY.md"
)

# Maintainer-only paths that MUST NOT appear in a snapshot (defense-in-depth against
# allowlist drift). REVIEW*.md is checked separately via a glob.
DENYLIST=(
  "wiki"
  "raw"
  "tour"
  ".claude"
  ".github"
  "plugins"
  "tests"
  "docs/SHIP_CHECKLIST.md"
  "docs/RELEASING.md"
  "docs/RELEASE_v1.0.0.md"
  "docs/superpowers"
  "docs/PATTERNS"
)

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────
err()  { printf '\033[31mERROR:\033[0m %s\n' "$1" >&2; }
ok()   { printf '\033[32m  ✓\033[0m %s\n' "$1"; }

die() { err "$1"; exit 1; }

usage() {
  sed -n '2,30p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

# ──────────────────────────────────────────────────────────────────────
# Parse args
# ──────────────────────────────────────────────────────────────────────
CHANNEL="stable"
WANT_VERSION=""
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --channel) CHANNEL="${2:-}"; shift 2 ;;
    --version) WANT_VERSION="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage 0 ;;
    *) err "unknown argument: $1"; usage 1 ;;
  esac
done

case "$CHANNEL" in
  stable) TARGET_REPO="$STABLE_REPO" ;;
  rc)     TARGET_REPO="$RC_REPO" ;;
  *) die "--channel must be 'stable' or 'rc' (got: '$CHANNEL')" ;;
esac

# ──────────────────────────────────────────────────────────────────────
# Locate repo root (this script lives in scripts/)
# ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

PLUGIN_JSON=".claude-plugin/plugin.json"
MARKETPLACE_JSON=".claude-plugin/marketplace.json"
[[ -f "$PLUGIN_JSON" ]] || die "missing $PLUGIN_JSON (run from the dev repo; did the restructure land?)"

# ──────────────────────────────────────────────────────────────────────
# Resolve + validate version
# ──────────────────────────────────────────────────────────────────────
VERSION="$(python3 -c "import json,sys; print(json.load(open('$PLUGIN_JSON'))['version'])")"
[[ -n "$VERSION" ]] || die "could not read version from $PLUGIN_JSON"

if [[ -n "$WANT_VERSION" && "$WANT_VERSION" != "$VERSION" ]]; then
  die "version mismatch: --version=$WANT_VERSION but $PLUGIN_JSON#version=$VERSION. Bump plugin.json first."
fi

# Channel/suffix consistency: rc builds must carry an -rc suffix; stable must not.
if [[ "$CHANNEL" == "rc" && "$VERSION" != *-rc.* ]]; then
  die "channel=rc but version '$VERSION' has no -rc.N suffix (e.g. 1.3.0-rc.1)"
fi
if [[ "$CHANNEL" == "stable" && "$VERSION" == *-rc.* ]]; then
  die "channel=stable but version '$VERSION' carries an -rc suffix; drop it before a stable publish"
fi

echo "▶ Building $CHANNEL snapshot for startup-framework v$VERSION → $GITHUB_OWNER/$TARGET_REPO"

# ──────────────────────────────────────────────────────────────────────
# Build the snapshot
# ──────────────────────────────────────────────────────────────────────
SNAP="$(mktemp -d)"
cleanup() { [[ -n "${SNAP:-}" && -d "$SNAP" ]] && rm -rf "$SNAP"; }
# Keep the snapshot on a real (non-dry) build so the maintainer can inspect + push it.
if (( DRY_RUN )); then trap cleanup EXIT; fi

for entry in "${ALLOWLIST[@]}"; do
  [[ -e "$entry" ]] || die "allowlist entry missing from repo: $entry"
  cp -r --parents "$entry" "$SNAP/"
done
ok "copied ${#ALLOWLIST[@]} allowlist entries"

# ──────────────────────────────────────────────────────────────────────
# Guard 1 — no PLACEHOLDER-ORG
# ──────────────────────────────────────────────────────────────────────
if grep -rqn 'PLACEHOLDER-ORG' "$SNAP"; then
  err "PLACEHOLDER-ORG found in snapshot — unresolved placeholder would ship:"
  grep -rn 'PLACEHOLDER-ORG' "$SNAP" >&2 || true
  die "aborting: fix the placeholder(s) before publishing"
fi
ok "no PLACEHOLDER-ORG in snapshot"

# ──────────────────────────────────────────────────────────────────────
# Guard 2 — assert-absent (the load-bearing ADR-019 boundary). FAIL LOUD.
# ──────────────────────────────────────────────────────────────────────
LEAKS=()
for path in "${DENYLIST[@]}"; do
  [[ -e "$SNAP/$path" ]] && LEAKS+=("$path")
done
# REVIEW*.md anywhere in the snapshot
while IFS= read -r leak; do LEAKS+=("${leak#"$SNAP"/}"); done < <(find "$SNAP" -name 'REVIEW*.md' 2>/dev/null)

if (( ${#LEAKS[@]} > 0 )); then
  err "MAINTAINER-ONLY CONTENT LEAKED INTO THE SNAPSHOT (ADR-019 violation):"
  for leak in "${LEAKS[@]}"; do printf '       ✗ %s\n' "$leak" >&2; done
  die "aborting: the allowlist drifted. Friends must NEVER receive these paths."
fi
ok "assert-absent passed — no maintainer-only content in snapshot"

# ──────────────────────────────────────────────────────────────────────
# Guard 3 — claude plugin validate --strict
# ──────────────────────────────────────────────────────────────────────
if ! command -v claude >/dev/null 2>&1; then
  die "claude CLI not found — required to validate the snapshot before publishing. Install Claude Code."
fi
if ! claude plugin validate "$SNAP" --strict; then
  die "claude plugin validate --strict failed on the snapshot"
fi
ok "claude plugin validate --strict passed"

# ──────────────────────────────────────────────────────────────────────
# Guard 4 — manifests present at root with source "./"
# ──────────────────────────────────────────────────────────────────────
[[ -f "$SNAP/$PLUGIN_JSON" ]]      || die "snapshot missing $PLUGIN_JSON"
[[ -f "$SNAP/$MARKETPLACE_JSON" ]] || die "snapshot missing $MARKETPLACE_JSON"
SNAP_SOURCE="$(python3 -c "import json; print(json.load(open('$SNAP/$MARKETPLACE_JSON'))['plugins'][0]['source'])")"
[[ "$SNAP_SOURCE" == "./" ]] || die "marketplace source is '$SNAP_SOURCE', expected './' (Crucible one-repo layout)"
ok "manifests present; marketplace source = \"./\""

# ──────────────────────────────────────────────────────────────────────
# Dry-run stops here
# ──────────────────────────────────────────────────────────────────────
if (( DRY_RUN )); then
  echo
  echo "✅ DRY-RUN PASSED — snapshot for v$VERSION ($CHANNEL) is clean and would publish."
  exit 0
fi

# ──────────────────────────────────────────────────────────────────────
# Make the orphan commit (fresh repo = single commit, no parent, no history)
# ──────────────────────────────────────────────────────────────────────
git -C "$SNAP" init -q
git -C "$SNAP" add -A
git -C "$SNAP" -c user.name="$COMMIT_NAME" -c user.email="$COMMIT_EMAIL" \
  commit -q -m "Release v$VERSION"
ok "orphan commit created (1 commit, no history)"

REMOTE_URL="git@github.com:${GITHUB_OWNER}/${TARGET_REPO}.git"

cat <<EOF

✅ SNAPSHOT READY — v$VERSION ($CHANNEL)

  Location:  $SNAP
  Target:    $GITHUB_OWNER/$TARGET_REPO

Inspect it first (recommended):
  ls -la "$SNAP" && git -C "$SNAP" show --stat

Then publish by hand (this script does NOT push):
  git -C "$SNAP" remote add origin $REMOTE_URL
  git -C "$SNAP" push --force origin HEAD:main

⚠️  Do NOT push tags to the marketplace (git push --tags). Release tags live ONLY
    in the private dev repo. The marketplace carries a single orphan commit per
    release; friends pick up changes with: /plugin marketplace update $TARGET_REPO

EOF
