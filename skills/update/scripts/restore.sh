#!/usr/bin/env bash
# restore.sh — restore the wiki from a snapshot.
#
# Two modes:
#   restore.sh --whole <snapshot-path>
#     Full wiki restore. Overwrites $REN_WIKI_ROOT.
#
#   restore.sh --page <snapshot-path> <relative-page-path>
#     Single page restore. Copies snapshot/<rel> → wiki_root/<rel>.
#
#   restore.sh --list
#     Lists available snapshots in chronological order (oldest first).
#     Used by /ren:update --restore-snapshot for the interactive picker.
#
# Side effects:
#   --whole: rewrites the wiki tree. Logs to wiki/log.md.
#   --page: rewrites a single file. Logs to wiki/log.md.
#   --list: read-only.

set -euo pipefail

WIKI_ROOT="${REN_WIKI_ROOT:-${CLAUDE_PLUGIN_OPTION_WIKIROOT:-$HOME/.renos/wiki}}"
PLUGIN_DATA="${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugins/data/renos}"
SNAPSHOT_BASE="${PLUGIN_DATA}/wiki-snapshots"

case "${1:-}" in
  --list)
    if [[ ! -d "$SNAPSHOT_BASE" ]]; then
      echo "no snapshots present at $SNAPSHOT_BASE"
      exit 0
    fi
    find "$SNAPSHOT_BASE" -maxdepth 1 -mindepth 1 -type d -name 'v*-pre-update-*' | sort
    ;;

  --whole)
    SNAP="${2:-}"
    if [[ -z "$SNAP" || ! -d "$SNAP" ]]; then
      echo "ERROR: --whole requires a valid snapshot directory" >&2
      exit 2
    fi
    if [[ ! -d "$WIKI_ROOT" ]]; then
      mkdir -p "$WIKI_ROOT"
    fi

    # Stash the current (potentially-broken) wiki state for inspection.
    STASH="${SNAPSHOT_BASE}/STASH-broken-$(date -u +%Y%m%dT%H%M%SZ)"
    if cp -al "$WIKI_ROOT" "$STASH" 2>/dev/null || cp -a "$WIKI_ROOT" "$STASH"; then
      echo "stashed pre-restore wiki state at $STASH" >&2
    fi

    rm -rf "$WIKI_ROOT"
    cp -a "$SNAP" "$WIKI_ROOT"

    # Log the restore (this MIGHT be writing to a freshly-restored log.md — by design;
    # the entry will appear as the latest in the restored file).
    LOG_MD="$WIKI_ROOT/log.md"
    if [[ -w "$LOG_MD" ]]; then
      printf '\n## [%s] restore | %s | wiki restored from snapshot %s; pre-restore state stashed at %s\n' \
        "$(date -u +'%Y-%m-%d %H:%M')" "${USER:-system}" "$SNAP" "$STASH" >> "$LOG_MD" 2>/dev/null || true
    fi

    echo "restored from $SNAP"
    ;;

  --page)
    SNAP="${2:-}"
    REL="${3:-}"
    if [[ -z "$SNAP" || -z "$REL" ]]; then
      echo "ERROR: --page requires <snapshot-dir> <relative-page-path>" >&2
      exit 2
    fi
    if [[ ! -f "$SNAP/$REL" ]]; then
      echo "ERROR: $REL not found in snapshot $SNAP" >&2
      exit 2
    fi
    # Ensure target directory exists
    mkdir -p "$(dirname "$WIKI_ROOT/$REL")"
    cp -a "$SNAP/$REL" "$WIKI_ROOT/$REL"

    # Log
    LOG_MD="$WIKI_ROOT/log.md"
    if [[ -w "$LOG_MD" ]]; then
      printf '\n## [%s] restore | %s | restored single page %s from snapshot %s\n' \
        "$(date -u +'%Y-%m-%d %H:%M')" "${USER:-system}" "$REL" "$(basename "$SNAP")" >> "$LOG_MD" 2>/dev/null || true
    fi

    echo "restored $REL from $SNAP"
    ;;

  ""|--help|-h)
    cat <<EOF
usage: restore.sh --list
       restore.sh --whole <snapshot-dir>
       restore.sh --page  <snapshot-dir> <relative-page-path>

Snapshot location: \$CLAUDE_PLUGIN_DATA/wiki-snapshots/
Current target:    \$REN_WIKI_ROOT or \$CLAUDE_PLUGIN_OPTION_WIKIROOT or ~/.renos/wiki
EOF
    ;;

  *)
    echo "ERROR: unknown subcommand '$1'. Run restore.sh --help" >&2
    exit 2
    ;;
esac
