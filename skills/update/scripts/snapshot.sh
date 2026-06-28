#!/usr/bin/env bash
# snapshot.sh — capture a pre-migration snapshot of the wiki.
#
# Per ADR-027 + lead-approved override: snapshots live at
#   ${CLAUDE_PLUGIN_DATA}/wiki-snapshots/v<from>-pre-update-<ISO8601>/
#
# Usage:
#   snapshot.sh <from-version>
#     Creates a snapshot. Prints the snapshot path on stdout.
#     Exits 0 on success, non-zero on failure.
#
# Idempotency: if a snapshot for the current second already exists, we suffix
# with -2, -3, etc. so concurrent invocations don't clobber.
#
# Side effects:
#   - Creates ${CLAUDE_PLUGIN_DATA}/wiki-snapshots/<name>/ (entire wiki copy, hard-linked where possible)
#   - Prunes oldest snapshots beyond CLAUDE_PLUGIN_OPTION_SNAPSHOTRETAIN (default 3)
#   - Logs the new snapshot path to ${SF_WIKI_ROOT}/log.md (append-only)

set -euo pipefail

FROM_VER="${1:-unknown}"
WIKI_ROOT="${SF_WIKI_ROOT:-${CLAUDE_PLUGIN_OPTION_WIKIROOT:-$HOME/.startup-framework/wiki}}"
PLUGIN_DATA="${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugins/data/ren-ren-os}"
SNAPSHOT_BASE="${PLUGIN_DATA}/wiki-snapshots"
RETAIN="${CLAUDE_PLUGIN_OPTION_SNAPSHOTRETAIN:-3}"

if [[ ! -d "$WIKI_ROOT" ]]; then
  echo "ERROR: wiki root not found at $WIKI_ROOT" >&2
  exit 2
fi

mkdir -p "$SNAPSHOT_BASE"

# Generate the snapshot name. ISO 8601, UTC, second precision. Append -N if collision.
TS="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="v${FROM_VER}-pre-update-${TS}"
SUFFIX=1
while [[ -e "$SNAPSHOT_BASE/$NAME" ]]; do
  SUFFIX=$((SUFFIX+1))
  NAME="v${FROM_VER}-pre-update-${TS}-${SUFFIX}"
done

SNAP_DIR="$SNAPSHOT_BASE/$NAME"

# Use cp -a (real archive copy) by default. Per REVIEW.md D2:
# hard-linked snapshots (cp -al) share inodes between snapshot and live wiki, which
# is unsafe if any downstream tool (now or future) writes via naive truncate-and-rewrite
# (`open(path, "w")`) rather than atomic rename-on-write. GNU `sed -i` uses rename-on-write
# so it would be safe, but we can't enforce that contract across every future migration
# script or LLM-driven prompt. Real copy is the safe-by-default choice.
#
# Cost: wikis are KB-MB scale; real copy is negligible at v1.0 wiki sizes.
# Configurable: friends with massive wikis (>1GB) can opt into hard-link mode by setting
# SF_SNAPSHOT_MODE=hardlink in their environment. Documented in MIGRATION_PATTERN.md as
# requiring downstream tools to use atomic-rename semantics.
SNAPSHOT_MODE="${SF_SNAPSHOT_MODE:-copy}"
if [[ "$SNAPSHOT_MODE" == "hardlink" ]]; then
  if ! cp -al "$WIKI_ROOT" "$SNAP_DIR" 2>/dev/null; then
    # Hard link unavailable on this filesystem — fall back to real copy silently.
    cp -a "$WIKI_ROOT" "$SNAP_DIR" || { echo "ERROR: snapshot copy failed" >&2; exit 2; }
  fi
else
  cp -a "$WIKI_ROOT" "$SNAP_DIR" || { echo "ERROR: snapshot copy failed" >&2; exit 2; }
fi

# Prune old snapshots: keep newest $RETAIN. Sort by directory name (which embeds ISO8601 → lexicographic == chronological).
mapfile -t ALL_SNAPS < <(find "$SNAPSHOT_BASE" -maxdepth 1 -mindepth 1 -type d -name 'v*-pre-update-*' | sort)
TOTAL=${#ALL_SNAPS[@]}
if (( TOTAL > RETAIN )); then
  TO_DELETE=$(( TOTAL - RETAIN ))
  for (( i=0; i<TO_DELETE; i++ )); do
    rm -rf "${ALL_SNAPS[i]}"
  done
fi

# Log to wiki/log.md (append-only). Best-effort; never fails the snapshot if logging fails.
LOG_MD="$WIKI_ROOT/log.md"
if [[ -w "$LOG_MD" ]]; then
  # We do NOT touch the frontmatter; we append a chronological entry per ADR-004 invariant.
  printf '\n## [%s] snapshot | %s | pre-update snapshot saved at %s\n' \
    "$(date -u +'%Y-%m-%d %H:%M')" "${USER:-system}" "$SNAP_DIR" >> "$LOG_MD" 2>/dev/null || true
fi

echo "$SNAP_DIR"
exit 0
