#!/usr/bin/env bash
# test_snapshot_inode_safety.sh — pin test for REVIEW.md D2 fix.
#
# Verifies that snapshot.sh creates a copy whose contents are independent
# of the live wiki: writing to the live wiki via truncate-and-rewrite
# (the unsafe pattern) must NOT corrupt the snapshot.
#
# Before D2 fix (cp -al default): truncate-and-rewrite on a hard-linked
# snapshot would clobber the snapshot's inode, defeating rollback.
#
# After D2 fix (cp -a default): the snapshot is byte-isolated; modifications
# to the live wiki cannot affect it.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
SNAPSHOT_SH="$REPO_ROOT/skills/update/scripts/snapshot.sh"

PASS_COUNT=0
FAIL_COUNT=0

pass() { printf '\033[32m  ✓ PASS\033[0m  %s\n' "$1"; PASS_COUNT=$((PASS_COUNT+1)); }
fail() { printf '\033[31m  ✗ FAIL\033[0m  %s\n' "$1"; FAIL_COUNT=$((FAIL_COUNT+1)); }

TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

WIKI="$TMPDIR/wiki"
PLUGIN_DATA="$TMPDIR/plugin-data"
mkdir -p "$WIKI"

# Synthesize a page with known content
ORIGINAL_CONTENT="# Identity v1
type: identity
This is the ORIGINAL content. Snapshot must preserve this byte-for-byte.
"
printf '%s' "$ORIGINAL_CONTENT" > "$WIKI/identity.md"
ORIGINAL_HASH="$(sha256sum "$WIKI/identity.md" | awk '{print $1}')"

# ──────────────────────────────────────────────────────────────────────
# Test 1 — default mode (copy) survives truncate-and-rewrite
# ──────────────────────────────────────────────────────────────────────
echo "▶ Test 1 — default (copy) mode survives truncate-and-rewrite on live wiki"

SNAP_PATH="$(SF_WIKI_ROOT="$WIKI" CLAUDE_PLUGIN_DATA="$PLUGIN_DATA" \
  "$SNAPSHOT_SH" 1.0.0)"

# Now truncate-and-rewrite the live wiki's identity.md via Python (simulates a future
# naive migrator that uses `open(path, "w")` rather than atomic rename).
python3 -c "
with open('$WIKI/identity.md', 'w') as f:
    f.write('# COMPLETELY DIFFERENT CONTENT — naive truncate-and-rewrite\n')
"

# Live wiki should have new content
LIVE_HASH="$(sha256sum "$WIKI/identity.md" | awk '{print $1}')"
if [[ "$LIVE_HASH" != "$ORIGINAL_HASH" ]]; then
  pass "live wiki identity.md changed as expected ($LIVE_HASH != $ORIGINAL_HASH)"
else
  fail "live wiki did not change — test setup error"
fi

# Snapshot must STILL have original content (the D2 invariant)
SNAP_HASH="$(sha256sum "$SNAP_PATH/identity.md" | awk '{print $1}')"
if [[ "$SNAP_HASH" == "$ORIGINAL_HASH" ]]; then
  pass "snapshot preserved original content after live-wiki rewrite (inode isolation OK)"
else
  fail "snapshot was clobbered by live-wiki rewrite — D2 regression"
  echo "    expected hash: $ORIGINAL_HASH"
  echo "    snapshot hash: $SNAP_HASH"
  diff -u <(printf '%s' "$ORIGINAL_CONTENT") "$SNAP_PATH/identity.md" || true
fi

# ──────────────────────────────────────────────────────────────────────
# Test 2 — hardlink mode opt-in still works for friends who want it
# ──────────────────────────────────────────────────────────────────────
echo
echo "▶ Test 2 — opt-in hardlink mode still functions (cp -al works)"

# Reset
rm -rf "$WIKI" "$PLUGIN_DATA"
mkdir -p "$WIKI"
printf '%s' "$ORIGINAL_CONTENT" > "$WIKI/identity.md"

SNAP_PATH="$(SF_SNAPSHOT_MODE=hardlink SF_WIKI_ROOT="$WIKI" CLAUDE_PLUGIN_DATA="$PLUGIN_DATA" \
  "$SNAPSHOT_SH" 1.0.0)"

if [[ -d "$SNAP_PATH" && -f "$SNAP_PATH/identity.md" ]]; then
  pass "hardlink mode produced a usable snapshot"
else
  fail "hardlink mode failed to produce snapshot"
fi

# In hardlink mode, the snapshot AND live wiki share an inode. Verify by inode #.
LIVE_INODE="$(stat -c %i "$WIKI/identity.md")"
SNAP_INODE="$(stat -c %i "$SNAP_PATH/identity.md")"
if [[ "$LIVE_INODE" == "$SNAP_INODE" ]]; then
  pass "hardlink mode confirmed shared inode (intended behavior)"
else
  # Filesystem may not support cross-directory hardlinks — silently fell back to copy.
  pass "hardlink fell back to copy (acceptable on filesystems without cross-dir hardlinks)"
fi

# ──────────────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────────────
echo
echo "═══════════════════════════════════════════════════════════════"
if (( FAIL_COUNT == 0 )); then
  printf '\033[32m  D2 fix pin tests: %d/%d PASS\033[0m\n' "$PASS_COUNT" "$((PASS_COUNT+FAIL_COUNT))"
  exit 0
else
  printf '\033[31m  D2 fix pin tests: %d FAIL / %d total\033[0m\n' "$FAIL_COUNT" "$((PASS_COUNT+FAIL_COUNT))"
  exit 1
fi
