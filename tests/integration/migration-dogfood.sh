#!/usr/bin/env bash
# migration-dogfood.sh — end-to-end migration pipeline dogfood
#
# Per Task #43. Proves the WHOLE pipeline composes correctly across:
#   snapshot.sh → apply-migration.sh → verify-page.sh → idempotency → restore.sh
#
# Each step's pass/fail surfaces clearly. CI-runnable (no human input).
# Exits non-zero if ANY step fails. v1.0 ship-blocker if it fails.
#
# Does NOT touch the friend's wiki, ${HOME}, or any persistent state outside its tmpdir.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMPROOT="$(mktemp -d -t sf-migration-dogfood.XXXXXX)"
WIKI="$TMPROOT/wiki"
SNAPDIR="$TMPROOT/plugin-data"
MIG_PARENT="$TMPROOT/migrations"
MIG_DIR="$MIG_PARENT/identity-1-to-2"

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────
PASS_COUNT=0
FAIL_COUNT=0

step() {
  echo
  echo "──────────────────────────────────────────────────────────────"
  echo "▶ $1"
  echo "──────────────────────────────────────────────────────────────"
}

pass() {
  printf '\033[32m  ✓ PASS\033[0m  %s\n' "$1"
  PASS_COUNT=$((PASS_COUNT+1))
}

fail() {
  printf '\033[31m  ✗ FAIL\033[0m  %s\n' "$1"
  FAIL_COUNT=$((FAIL_COUNT+1))
}

cleanup() {
  rm -rf "$TMPROOT"
}
trap cleanup EXIT

# ──────────────────────────────────────────────────────────────────────
# Setup: synthesize a real-looking wiki + migration directory
# ──────────────────────────────────────────────────────────────────────
step "Setup: synthesize friend wiki + identity-1-to-2 migration"

mkdir -p "$WIKI" "$SNAPDIR" "$MIG_DIR"

# Pre-migration identity.md at schema 1 with the kebab-case field that the migration renames
cat > "$WIKI/identity.md" <<'EOF'
---
type: identity
schema_version: 1
framework_version: 1.0.0
handle: alice
name: Alice Example
tech-preferences: python, fastapi, pytorch
working_style: terse
created: 2026-05-28
updated: 2026-05-28
---

# Alice

A 4th-year AI/Data Engineering student building side projects.

## Notes

Custom body content that must survive the migration byte-identically.
EOF
pass "synthesized friend wiki at $WIKI"

# Synthesize the migration directory (NOT committed to the repo per template.md instructions)
cat > "$MIG_DIR/README.md" <<'EOF'
# Identity v1 → v2

## What changes
- ADD optional field `phase` (default: ideation)
- RENAME field `tech-preferences` → `tech_preferences` (snake_case)

## Mode: scripted
EOF

cat > "$MIG_DIR/migrate.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
PAGE="$1"
[[ -f "$PAGE" ]] || { echo "FAIL: $PAGE not found" >&2; exit 2; }
if grep -q '^schema_version: 2$' "$PAGE"; then echo "SKIP: already at schema 2"; exit 0; fi
sed -i.bak 's/^schema_version: 1$/schema_version: 2/' "$PAGE"
sed -i 's/^tech-preferences:/tech_preferences:/' "$PAGE"
if ! grep -q '^phase:' "$PAGE"; then
  sed -i '/^schema_version: 2$/a phase: ideation' "$PAGE"
fi
rm -f "$PAGE.bak"
echo "OK"
EOF
chmod +x "$MIG_DIR/migrate.sh"

# A stub migrate.md so the dispatcher recognises hybrid mode
echo "# Stub LLM prompt — scripted handles this migration" > "$MIG_DIR/migrate.md"

cat > "$MIG_DIR/verify.json" <<EOF
{
  "\$schema": "$REPO_ROOT/skills/wiki-migration/verify.schema.json",
  "migration": "identity-1-to-2",
  "page_type": "identity",
  "assertions": [
    {"id": "yaml-valid", "description": "valid frontmatter", "predicate": "yaml.valid"},
    {"id": "schema-bumped", "description": "schema_version = 2", "predicate": "yaml.equals", "field": "schema_version", "value": 2},
    {"id": "phase-present", "description": "phase in enum", "predicate": "yaml.in", "field": "phase", "values": ["ideation", "building", "shipping", "other"]},
    {"id": "tech-pref-old-absent", "description": "old key removed", "predicate": "yaml.absent", "field": "tech-preferences"},
    {"id": "tech-pref-new-preserved", "description": "value preserved under new key", "predicate": "snapshot.value-preserved", "snapshot_field": "tech-preferences", "post_field": "tech_preferences"},
    {"id": "body-identical", "description": "body unchanged", "predicate": "snapshot.body-identical"}
  ]
}
EOF
pass "synthesized $MIG_DIR with migrate.sh + migrate.md + verify.json"

# Capture original byte content for restore comparison
ORIGINAL_HASH="$(sha256sum "$WIKI/identity.md" | awk '{print $1}')"
pass "captured pre-migration hash: $ORIGINAL_HASH"

# ──────────────────────────────────────────────────────────────────────
# Step 1: snapshot.sh creates pre-migration snapshot
# ──────────────────────────────────────────────────────────────────────
step "Step 1 — snapshot.sh creates pre-migration snapshot"

SNAP_PATH="$(SF_WIKI_ROOT="$WIKI" CLAUDE_PLUGIN_DATA="$SNAPDIR" CLAUDE_PLUGIN_OPTION_SNAPSHOTRETAIN=3 \
  "$REPO_ROOT/skills/update/scripts/snapshot.sh" 1.0.0)"

if [[ -d "$SNAP_PATH" && -f "$SNAP_PATH/identity.md" ]]; then
  pass "snapshot created at $SNAP_PATH"
else
  fail "snapshot creation failed (expected dir + identity.md at $SNAP_PATH)"
  exit 1
fi

SNAP_HASH="$(sha256sum "$SNAP_PATH/identity.md" | awk '{print $1}')"
if [[ "$SNAP_HASH" == "$ORIGINAL_HASH" ]]; then
  pass "snapshot byte-identical to source"
else
  fail "snapshot drifted from source ($SNAP_HASH vs $ORIGINAL_HASH)"
fi

# ──────────────────────────────────────────────────────────────────────
# Step 2: apply-migration.sh dispatches scripted mode
# ──────────────────────────────────────────────────────────────────────
step "Step 2 — apply-migration.sh runs migrate.sh"

set +e  # capture exit code without exiting
APPLY_OUT="$(SF_WIKI_ROOT="$WIKI" SF_SNAPSHOT_DIR="$SNAP_PATH" \
  "$REPO_ROOT/skills/wiki-migration/scripts/apply-migration.sh" "$MIG_DIR" "$WIKI/identity.md" 2>&1)"
APPLY_RC=$?
set -e

if (( APPLY_RC == 0 )); then
  pass "apply-migration.sh exit 0"
else
  fail "apply-migration.sh exit $APPLY_RC"
  echo "$APPLY_OUT"
  exit 1
fi

# Verify the file content actually changed (schema_version: 2, tech_preferences key)
if grep -q '^schema_version: 2$' "$WIKI/identity.md"; then
  pass "schema_version bumped to 2"
else
  fail "schema_version not bumped"
fi

if grep -q '^tech_preferences:' "$WIKI/identity.md"; then
  pass "tech-preferences renamed to tech_preferences"
else
  fail "rename did not apply"
fi

if grep -q '^phase: ideation' "$WIKI/identity.md"; then
  pass "phase field added with default 'ideation'"
else
  fail "phase field missing"
fi

POST_MIGRATION_HASH="$(sha256sum "$WIKI/identity.md" | awk '{print $1}')"
if [[ "$POST_MIGRATION_HASH" != "$ORIGINAL_HASH" ]]; then
  pass "post-migration content differs from original (expected)"
else
  fail "post-migration content unchanged — migration was a no-op"
fi

# ──────────────────────────────────────────────────────────────────────
# Step 3: verify-page.sh asserts all 6 predicates pass
# ──────────────────────────────────────────────────────────────────────
step "Step 3 — verify-page.sh runs verify.json against the migrated page"

set +e
VERIFY_OUT="$(SF_WIKI_ROOT="$WIKI" \
  "$REPO_ROOT/skills/wiki-migration/scripts/verify-page.sh" \
  "$MIG_DIR/verify.json" "$WIKI/identity.md" "$SNAP_PATH/identity.md" 2>&1)"
VERIFY_RC=$?
set -e

echo "$VERIFY_OUT"
if (( VERIFY_RC == 0 )); then
  pass "verify-page.sh exit 0 (all assertions PASS)"
else
  fail "verify-page.sh exit $VERIFY_RC"
fi

# ──────────────────────────────────────────────────────────────────────
# Step 4: idempotency — second apply returns SKIP without change
# ──────────────────────────────────────────────────────────────────────
step "Step 4 — idempotency: re-apply produces no-op SKIP"

HASH_BEFORE_RERUN="$(sha256sum "$WIKI/identity.md" | awk '{print $1}')"
APPLY2_OUT="$(SF_WIKI_ROOT="$WIKI" SF_SNAPSHOT_DIR="$SNAP_PATH" \
  "$REPO_ROOT/skills/wiki-migration/scripts/apply-migration.sh" "$MIG_DIR" "$WIKI/identity.md" 2>&1)"
HASH_AFTER_RERUN="$(sha256sum "$WIKI/identity.md" | awk '{print $1}')"

if [[ "$HASH_BEFORE_RERUN" == "$HASH_AFTER_RERUN" ]]; then
  pass "re-apply did not modify the file (idempotent)"
else
  fail "re-apply changed the file ($HASH_BEFORE_RERUN → $HASH_AFTER_RERUN)"
fi

if echo "$APPLY2_OUT" | grep -q 'OUTPUT=SKIP'; then
  pass "re-apply emitted 'SKIP: already at schema 2' as expected"
else
  echo "$APPLY2_OUT"
  fail "re-apply did not emit SKIP — guard isn't working"
fi

# ──────────────────────────────────────────────────────────────────────
# Step 5: restore.sh --whole reverts the wiki from snapshot
# ──────────────────────────────────────────────────────────────────────
step "Step 5 — restore.sh --whole reverts wiki from snapshot"

set +e
RESTORE_OUT="$(SF_WIKI_ROOT="$WIKI" CLAUDE_PLUGIN_DATA="$SNAPDIR" \
  "$REPO_ROOT/skills/update/scripts/restore.sh" --whole "$SNAP_PATH" 2>&1)"
RESTORE_RC=$?
set -e

if (( RESTORE_RC == 0 )); then
  pass "restore.sh exit 0"
else
  fail "restore.sh exit $RESTORE_RC"
  echo "$RESTORE_OUT"
  exit 1
fi

# The restored wiki should be byte-identical to the snapshot EXCEPT that restore.sh appends
# a `## [<ts>] restore | ...` line to log.md (which is by design + would not change identity.md).
# So check identity.md specifically:
RESTORED_HASH="$(sha256sum "$WIKI/identity.md" | awk '{print $1}')"
if [[ "$RESTORED_HASH" == "$ORIGINAL_HASH" ]]; then
  pass "restored identity.md byte-identical to pre-migration state"
else
  fail "post-restore identity.md drifted ($RESTORED_HASH vs $ORIGINAL_HASH)"
  diff -u "$SNAP_PATH/identity.md" "$WIKI/identity.md" || true
fi

# Confirm the rename is undone (tech-preferences is back; tech_preferences is gone)
if grep -q '^tech-preferences:' "$WIKI/identity.md" && ! grep -q '^tech_preferences:' "$WIKI/identity.md"; then
  pass "rename undone (tech-preferences restored, tech_preferences gone)"
else
  fail "rename not properly undone"
fi

# ──────────────────────────────────────────────────────────────────────
# Step 6: a STASH was created by restore.sh
# ──────────────────────────────────────────────────────────────────────
step "Step 6 — restore.sh stashed pre-restore (broken) state for inspection"

STASH_COUNT="$(find "$SNAPDIR/wiki-snapshots" -maxdepth 1 -type d -name 'STASH-broken-*' 2>/dev/null | wc -l)"
if (( STASH_COUNT >= 1 )); then
  pass "found $STASH_COUNT STASH-broken-* dir(s) in $SNAPDIR/wiki-snapshots"
else
  fail "no STASH-broken-* dir created during restore"
fi

# ──────────────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────────────
echo
echo "══════════════════════════════════════════════════════════════"
if (( FAIL_COUNT == 0 )); then
  printf '\033[32m  END-TO-END MIGRATION DOGFOOD: %d/%d PASS\033[0m\n' "$PASS_COUNT" "$((PASS_COUNT+FAIL_COUNT))"
  echo "  Full pipeline composes correctly. v1.0 ship NOT blocked on migration mechanics."
  exit 0
else
  printf '\033[31m  END-TO-END MIGRATION DOGFOOD: %d FAIL / %d total\033[0m\n' "$FAIL_COUNT" "$((PASS_COUNT+FAIL_COUNT))"
  echo "  Pipeline composition broken — v1.0 ship is BLOCKED until fixed."
  exit 1
fi
