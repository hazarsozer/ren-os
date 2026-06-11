#!/usr/bin/env bash
# prune-snapshots.sh — keep latest N snapshots; delete older ones.
#
# Per ADR-027 + userConfig.snapshotRetain. Called by snapshot.sh after every snapshot,
# and can be invoked manually by the user if they want to free disk.
#
# Usage:
#   prune-snapshots.sh                  # uses CLAUDE_PLUGIN_OPTION_SNAPSHOTRETAIN, default 3
#   prune-snapshots.sh <N>              # override retention count
#   prune-snapshots.sh --dry-run        # report what would be deleted; no action
#
# Side effects: deletes snapshot directories. STASH-* directories (created by restore.sh)
# are also pruned beyond the retain count, but separately (their own bucket of latest N).

set -euo pipefail

PLUGIN_DATA="${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugins/data/ren-ren-os}"
SNAPSHOT_BASE="${PLUGIN_DATA}/wiki-snapshots"

DRY_RUN=0
RETAIN="${CLAUDE_PLUGIN_OPTION_SNAPSHOTRETAIN:-3}"
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    [0-9]*) RETAIN="$arg" ;;
  esac
done

if [[ ! -d "$SNAPSHOT_BASE" ]]; then
  echo "no snapshots present at $SNAPSHOT_BASE"
  exit 0
fi

# Prune normal snapshots
mapfile -t SNAPS < <(find "$SNAPSHOT_BASE" -maxdepth 1 -mindepth 1 -type d -name 'v*-pre-update-*' | sort)
TOTAL=${#SNAPS[@]}
TO_DELETE=$(( TOTAL > RETAIN ? TOTAL - RETAIN : 0 ))

echo "snapshots: $TOTAL total, retain $RETAIN, will delete $TO_DELETE"
if (( TO_DELETE > 0 )); then
  for (( i=0; i<TO_DELETE; i++ )); do
    if (( DRY_RUN )); then
      echo "  [dry-run] would delete ${SNAPS[i]}"
    else
      echo "  delete ${SNAPS[i]}"
      rm -rf "${SNAPS[i]}"
    fi
  done
fi

# Prune STASH-* (broken-state stashes from restore.sh). Keep latest N as well.
mapfile -t STASHES < <(find "$SNAPSHOT_BASE" -maxdepth 1 -mindepth 1 -type d -name 'STASH-broken-*' | sort)
TOTAL_S=${#STASHES[@]}
TO_DELETE_S=$(( TOTAL_S > RETAIN ? TOTAL_S - RETAIN : 0 ))

if (( TO_DELETE_S > 0 )); then
  echo "stashes: $TOTAL_S total, retain $RETAIN, will delete $TO_DELETE_S"
  for (( i=0; i<TO_DELETE_S; i++ )); do
    if (( DRY_RUN )); then
      echo "  [dry-run] would delete ${STASHES[i]}"
    else
      rm -rf "${STASHES[i]}"
    fi
  done
fi

exit 0
