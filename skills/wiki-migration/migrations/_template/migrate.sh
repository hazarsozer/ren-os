#!/usr/bin/env bash
# migrate.sh — TEMPLATE (not a real migration)
#
# Contract (read before editing):
#   input:    $1 = absolute path to the page file (in place; this script MODIFIES it)
#   env:      SF_WIKI_ROOT    = absolute path to friend's wiki root
#             SF_SNAPSHOT_DIR = absolute path to pre-migration snapshot of the wiki
#                               (resolve same relative path under here to read the old content)
#   stdout:   one of "OK", "SKIP: <reason>"; lines are parsed by the update driver
#   stderr:   diagnostics (printed by the driver only on failure)
#   exit:     0 on success or skip; 2 on bad inputs; 1 on any transformation failure
#
# Must be:
#   - idempotent: running twice yields the same result as running once
#   - deterministic: same input + same snapshot = same output
#   - local-only: no network calls
#   - bounded: writes only to "$1"; never to siblings or anywhere else

set -euo pipefail

PAGE="${1:-}"
if [[ -z "$PAGE" ]]; then
  echo "FAIL: missing page argument" >&2
  exit 2
fi
if [[ ! -f "$PAGE" ]]; then
  echo "FAIL: $PAGE is not a regular file" >&2
  exit 2
fi
if [[ -z "${SF_WIKI_ROOT:-}" || -z "${SF_SNAPSHOT_DIR:-}" ]]; then
  echo "FAIL: SF_WIKI_ROOT and SF_SNAPSHOT_DIR must be set" >&2
  exit 2
fi

# ──────────────────────────────────────────────────────────────────────
# 1. Idempotency guard
# ──────────────────────────────────────────────────────────────────────
# Replace TARGET_SCHEMA with the version number this migration produces.
# If the page is already at the target schema, exit clean — no work to do.
TARGET_SCHEMA=2
if grep -q "^schema_version: ${TARGET_SCHEMA}\$" "$PAGE"; then
  echo "SKIP: already at schema ${TARGET_SCHEMA}"
  exit 0
fi

# ──────────────────────────────────────────────────────────────────────
# 2. Transformations
# ──────────────────────────────────────────────────────────────────────
# EDIT THIS BLOCK. The example below shows: bump schema_version, rename a
# field, insert a new optional field with a default. Keep edits frontmatter-
# bounded (lines between the two `---` delimiters) unless your migration
# explicitly targets body content.

# Example: bump schema_version 1 → 2
sed -i.bak "s/^schema_version: 1\$/schema_version: ${TARGET_SCHEMA}/" "$PAGE"

# Example: rename a frontmatter key (kebab-case → snake_case)
# sed -i 's/^example-old-key:/example_new_key:/' "$PAGE"

# Example: add an optional field with a default, only if not already present.
# The `# default — please review` comment surfaces in the DIFF_REVIEW UI so
# the friend can edit before approving.
# if ! grep -q '^example_added_field:' "$PAGE"; then
#   sed -i "/^schema_version: ${TARGET_SCHEMA}\$/a example_added_field: default-value  # default — please review" "$PAGE"
# fi

# ──────────────────────────────────────────────────────────────────────
# 3. Cleanup
# ──────────────────────────────────────────────────────────────────────
rm -f "${PAGE}.bak"
echo "OK"
