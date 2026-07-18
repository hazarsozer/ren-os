#!/usr/bin/env bash
# migrate.sh — routine-spec schema 1 → 2 (C2, ADR-027). First real framework migration.
#
# Adds two additive frontmatter fields and bumps the schema:
#   verification_strategy: manual     (enum: visual|test-run|lint|llm-judge|manual)
#   verification_tools: []            (optional tool names backing the strategy)
#
# Contract (per _template):
#   input:  $1 = absolute path to the page file (MODIFIED in place)
#   env:    SF_WIKI_ROOT, SF_SNAPSHOT_DIR
#   stdout: "OK" | "SKIP: <reason>"
#   exit:   0 ok/skip, 2 bad inputs, 1 transform failure
# Idempotent, deterministic, local-only, bounded to $1, frontmatter-only.

set -euo pipefail

PAGE="${1:-}"
if [[ -z "$PAGE" ]]; then echo "FAIL: missing page argument" >&2; exit 2; fi
if [[ ! -f "$PAGE" ]]; then echo "FAIL: $PAGE is not a regular file" >&2; exit 2; fi
if [[ -z "${SF_WIKI_ROOT:-}" || -z "${SF_SNAPSHOT_DIR:-}" ]]; then
  echo "FAIL: SF_WIKI_ROOT and SF_SNAPSHOT_DIR must be set" >&2; exit 2
fi

TARGET_SCHEMA=2

# 1. Idempotency guard — already migrated → nothing to do.
if grep -q "^schema_version: ${TARGET_SCHEMA}\$" "$PAGE"; then
  echo "SKIP: already at schema ${TARGET_SCHEMA}"
  exit 0
fi

# 2. Bump schema_version 1 → 2 (frontmatter key, line-anchored).
sed -i.bak "s/^schema_version: 1\$/schema_version: ${TARGET_SCHEMA}/" "$PAGE"

# 3. Insert verification_strategy (default 'manual') after the schema line, if absent.
#    CLEAN value — no inline '# comment': the framework's frontmatter parsers do not
#    strip inline comments, so a commented value would fail the verify.json yaml.in
#    enum check. The default + "please review" guidance live in README.md and the diff.
if ! grep -q "^verification_strategy:" "$PAGE"; then
  sed -i.bak "/^schema_version: ${TARGET_SCHEMA}\$/a\\
verification_strategy: manual" "$PAGE"
fi

# 4. Insert verification_tools (default empty list) after verification_strategy, if absent.
if ! grep -q "^verification_tools:" "$PAGE"; then
  sed -i.bak "/^verification_strategy:/a\\
verification_tools: []" "$PAGE"
fi

rm -f "${PAGE}.bak"
echo "OK"
