#!/usr/bin/env bash
# migrate.sh — routine-spec schema 2 → 3 (Task 6.3, RenOS 0.2 Phase 6).
# Mirrors donor's routine-spec-1-to-2/migrate.sh structure exactly.
#
# Spec §3.5: "pre-declared routines/loops: schedule, exit criterion, failure
# handler, AND a per-routine capability/path allowlist — declaration must
# bound WHAT IT MAY TOUCH, not just when it runs." Adds three frontmatter
# fields and bumps the schema:
#   allowlist:                (nested mapping; paths/capabilities default empty)
#     paths: []
#     capabilities: []
#   failure_handler: notify-journal   (OVERWRITES any prior free-text value —
#                                       0.2 has exactly one failure-handler
#                                       behavior: notify + journal; a v1/v2
#                                       spec's old free-text handler, e.g.
#                                       "email me@x via Resend MCP", described
#                                       a fundamentally different mechanism
#                                       that 0.2 doesn't implement)
#   exit_criterion: "MIGRATED — declare a real exit criterion"  (placeholder;
#                                       a NEW spec via /ren:routine-init
#                                       requires a real one — see
#                                       skills/routine-init/lib validation)
#
# Contract (per donor's _template):
#   input:  $1 = absolute path to the page file (MODIFIED in place)
#   env:    REN_WIKI_ROOT, REN_SNAPSHOT_DIR
#   stdout: "OK" | "SKIP: <reason>"
#   exit:   0 ok/skip, 2 bad inputs, 1 transform failure
# Idempotent, deterministic, local-only, bounded to $1, frontmatter-only.
#
# NOTE on validity post-migration: an empty allowlist.paths is VALID here (the
# migration can't know what the friend wants this routine to touch) but means
# the routine can propose nothing until filled in — `skills/routine-init/lib`'s
# `validate_routine_spec(..., migrated=True)` treats this as a WARNING, not an
# error; a brand-new spec (migrated=False, the default) requires non-empty.

set -euo pipefail

PAGE="${1:-}"
if [[ -z "$PAGE" ]]; then echo "FAIL: missing page argument" >&2; exit 2; fi
if [[ ! -f "$PAGE" ]]; then echo "FAIL: $PAGE is not a regular file" >&2; exit 2; fi
if [[ -z "${REN_WIKI_ROOT:-}" || -z "${REN_SNAPSHOT_DIR:-}" ]]; then
  echo "FAIL: REN_WIKI_ROOT and REN_SNAPSHOT_DIR must be set" >&2; exit 2
fi

TARGET_SCHEMA=3

# 1. Idempotency guard — already migrated → nothing to do.
if grep -q "^schema_version: ${TARGET_SCHEMA}\$" "$PAGE"; then
  echo "SKIP: already at schema ${TARGET_SCHEMA}"
  exit 0
fi

# 2. Bump schema_version 2 → 3 (frontmatter key, line-anchored).
sed -i.bak "s/^schema_version: 2\$/schema_version: ${TARGET_SCHEMA}/" "$PAGE"

# 3. Insert the allowlist mapping (paths + capabilities, both empty) right
#    after the schema line, if absent. Built as three separate anchored
#    inserts (each anchoring on the line the previous insert just added) so
#    the final block reads in the right order — same incremental technique
#    donor's 1-to-2 script uses for single-line inserts.
if ! grep -q "^allowlist:" "$PAGE"; then
  sed -i.bak "/^schema_version: ${TARGET_SCHEMA}\$/a\\
allowlist:" "$PAGE"
  sed -i.bak "/^allowlist:\$/a\\
  paths: []" "$PAGE"
  sed -i.bak "/^  paths: \[\]\$/a\\
  capabilities: []" "$PAGE"
fi

# 4. failure_handler: 0.2 has exactly ONE valid value. If a failure_handler
#    line already exists (v1/v2's free-text value), OVERWRITE it — the old
#    mechanism it described isn't implemented in 0.2. If absent, insert it.
if grep -q "^failure_handler:" "$PAGE"; then
  sed -i.bak "s/^failure_handler:.*/failure_handler: notify-journal/" "$PAGE"
elif grep -q "^  capabilities: \[\]\$" "$PAGE"; then
  sed -i.bak "/^  capabilities: \[\]\$/a\\
failure_handler: notify-journal" "$PAGE"
fi

# 5. exit_criterion — placeholder if absent (a real one is required for a NEW
#    spec via routine-init; a migrated spec gets a placeholder + a warning).
if ! grep -q "^exit_criterion:" "$PAGE"; then
  sed -i.bak "/^failure_handler: notify-journal\$/a\\
exit_criterion: \"MIGRATED — declare a real exit criterion\"" "$PAGE"
fi

rm -f "${PAGE}.bak"
echo "OK"
