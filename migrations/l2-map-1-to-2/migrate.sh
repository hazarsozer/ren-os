#!/usr/bin/env bash
# migrate.sh — l2-map schema 1 → 2 (#53, RenOS 0.7.0).
#
# The repo's FIRST body-rewriting migration: arrow-form wiki pointers under
# "## Decision map" become markdown links (Obsidian-native); repo: refs and
# everything outside that section are untouched. The body transform lives in
# transform.py (BSD sed is the wrong tool for regex-group rewrites — see the
# 10-line BSD-vs-GNU comment routine-spec-2-to-3 needed for mere frontmatter
# inserts) and SELF-VERIFIES: every rewritten line is re-parsed with
# lib/pointer.py before the page is replaced, so this migration cannot emit
# a line its own consumers can't read.
#
# Contract (per donor's _template):
#   input:  $1 = absolute path to the page file (MODIFIED in place)
#   env:    REN_WIKI_ROOT, REN_SNAPSHOT_DIR
#   stdout: "OK" | "SKIP: <reason>"
#   exit:   0 ok/skip, 2 bad inputs, 1 transform failure
# Idempotent, deterministic, local-only, bounded to $1.

set -euo pipefail

PAGE="${1:-}"
if [[ -z "$PAGE" ]]; then echo "FAIL: missing page argument" >&2; exit 2; fi
if [[ ! -f "$PAGE" ]]; then echo "FAIL: $PAGE is not a regular file" >&2; exit 2; fi
if [[ -z "${REN_WIKI_ROOT:-}" || -z "${REN_SNAPSHOT_DIR:-}" ]]; then
  echo "FAIL: REN_WIKI_ROOT and REN_SNAPSHOT_DIR must be set" >&2; exit 2
fi

TARGET_SCHEMA=2

# Idempotency guard — already migrated → nothing to do.
if grep -q "^schema_version: ${TARGET_SCHEMA}\$" "$PAGE"; then
  echo "SKIP: already at schema ${TARGET_SCHEMA}"
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PYTHONPATH="$REPO_ROOT" python3 "$SCRIPT_DIR/transform.py" "$PAGE"
echo "OK"
