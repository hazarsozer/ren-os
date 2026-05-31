#!/usr/bin/env bash
# test_check_schemas.sh — pin test for REVIEW.md D1 fix.
#
# Builds a synthetic healthy wiki with multiple files sharing the same
# schema_version and asserts that check-schemas.sh reports OK with no
# false-positive "missing schema_version field" warnings.
#
# Per ADR-027: the fallback ("Assuming schema_version: 1") should fire
# ONLY when files genuinely lack the field — not when N files share the
# same value (which is the normal healthy case).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
CHECK_SCRIPT="$REPO_ROOT/skills/sf-doctor/scripts/check-schemas.sh"
SCHEMAS_JSON="$REPO_ROOT/skills/wiki-migration/schemas.json"

PASS_COUNT=0
FAIL_COUNT=0

pass() {
  printf '\033[32m  ✓ PASS\033[0m  %s\n' "$1"
  PASS_COUNT=$((PASS_COUNT+1))
}

fail() {
  printf '\033[31m  ✗ FAIL\033[0m  %s\n' "$1"
  FAIL_COUNT=$((FAIL_COUNT+1))
}

TMPWIKI=$(mktemp -d)
trap "rm -rf $TMPWIKI" EXIT

# ──────────────────────────────────────────────────────────────────────
# Test 1 — healthy wiki: 5 research files, all at schema_version: 1
# Before the D1 fix, len(yours_set) == 1 underflowed → reports 4/5 missing.
# After the fix: each file individually tracked → 0 missing → status "ok".
# ──────────────────────────────────────────────────────────────────────
echo "▶ Test 1 — 5 research files all at schema_version: 1 should report status=ok"
mkdir -p "$TMPWIKI/research"
for i in 1 2 3 4 5; do
  cat > "$TMPWIKI/research/topic-${i}.md" <<EOF
---
type: research
schema_version: 1
framework_version: 1.0.0
title: "Topic ${i}"
---

Body of topic ${i}.
EOF
done

OUTPUT="$(CLAUDE_PLUGIN_OPTION_WIKIROOT="$TMPWIKI" SF_PLUGIN_DIR="$REPO_ROOT" "$CHECK_SCRIPT" "$SCHEMAS_JSON" 2>&1)"
RESEARCH_LINE="$(echo "$OUTPUT" | grep "^research|" || echo "")"

if [[ -z "$RESEARCH_LINE" ]]; then
  fail "no research line in output"
elif echo "$RESEARCH_LINE" | grep -q "^research|ok|"; then
  pass "research status=ok (no false-positive warning)"
else
  fail "research status is NOT ok — false-positive bug regressed"
  echo "    output line: $RESEARCH_LINE"
fi

if echo "$RESEARCH_LINE" | grep -qi "missing schema_version field"; then
  fail "false-positive 'missing schema_version field' warning fired"
  echo "    output line: $RESEARCH_LINE"
else
  pass "no false-positive 'missing schema_version field' warning"
fi

# ──────────────────────────────────────────────────────────────────────
# Test 2 — truly missing field SHOULD trigger fallback
# ──────────────────────────────────────────────────────────────────────
echo
echo "▶ Test 2 — file genuinely missing schema_version should fire fallback"
rm "$TMPWIKI/research"/*.md
cat > "$TMPWIKI/research/legacy.md" <<'EOF'
---
type: research
title: "Legacy page predating ADR-027"
---

Body.
EOF

OUTPUT="$(CLAUDE_PLUGIN_OPTION_WIKIROOT="$TMPWIKI" SF_PLUGIN_DIR="$REPO_ROOT" "$CHECK_SCRIPT" "$SCHEMAS_JSON" 2>&1)"
RESEARCH_LINE="$(echo "$OUTPUT" | grep "^research|" || echo "")"

if echo "$RESEARCH_LINE" | grep -qi "no schema_version field in any file"; then
  pass "legacy-page fallback message fires when ALL files lack the field (status=warn)"
else
  fail "expected fallback message did NOT fire"
  echo "    output line: $RESEARCH_LINE"
fi

# ──────────────────────────────────────────────────────────────────────
# Test 3 — mixed: some files with field, some without → partial-fallback warning
# ──────────────────────────────────────────────────────────────────────
echo
echo "▶ Test 3 — partial coverage (2 with field, 1 without) should warn with partial-fallback message"
rm -f "$TMPWIKI/research"/*.md  # clean leftover from Test 2
cat > "$TMPWIKI/research/topic-a.md" <<'EOF'
---
type: research
schema_version: 1
framework_version: 1.0.0
---

ok
EOF

cat > "$TMPWIKI/research/topic-b.md" <<'EOF'
---
type: research
schema_version: 1
framework_version: 1.0.0
---

ok
EOF

cat > "$TMPWIKI/research/topic-c.md" <<'EOF'
---
type: research
title: missing-sv
---

legacy
EOF

OUTPUT="$(CLAUDE_PLUGIN_OPTION_WIKIROOT="$TMPWIKI" SF_PLUGIN_DIR="$REPO_ROOT" "$CHECK_SCRIPT" "$SCHEMAS_JSON" 2>&1)"
RESEARCH_LINE="$(echo "$OUTPUT" | grep "^research|" || echo "")"

if echo "$RESEARCH_LINE" | grep -qE "1/3 file\(s\) missing schema_version field|1/[0-9]+ file\(s\) missing schema_version field"; then
  pass "partial-fallback message reports correct count (1 of N missing)"
else
  fail "partial-fallback message does NOT report correct count"
  echo "    output line: $RESEARCH_LINE"
fi

# ──────────────────────────────────────────────────────────────────────
# Test 4 — files at different schema_versions (e.g., mixed 1 and 2) report mixed
# ──────────────────────────────────────────────────────────────────────
echo
echo "▶ Test 4 — mixed schema_versions (some at 1, some at 2) should report mixed"
rm "$TMPWIKI/research"/*.md
for i in 1 2; do
  cat > "$TMPWIKI/research/at-v1-${i}.md" <<EOF
---
type: research
schema_version: 1
framework_version: 1.0.0
---
EOF
done
cat > "$TMPWIKI/research/at-v2.md" <<EOF
---
type: research
schema_version: 2
framework_version: 1.0.0
---
EOF

OUTPUT="$(CLAUDE_PLUGIN_OPTION_WIKIROOT="$TMPWIKI" SF_PLUGIN_DIR="$REPO_ROOT" "$CHECK_SCRIPT" "$SCHEMAS_JSON" 2>&1)"
RESEARCH_LINE="$(echo "$OUTPUT" | grep "^research|" || echo "")"

# Schema 2 > registry.current=1 → should error or warn appropriately (forward drift).
# Important: the count tracking must NOT report any files as missing schema_version.
if echo "$RESEARCH_LINE" | grep -qi "missing schema_version field"; then
  fail "false-positive 'missing schema_version field' on mixed-version case"
  echo "    output line: $RESEARCH_LINE"
else
  pass "mixed-version case does not false-positive on missing-field"
fi

# ──────────────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────────────
echo
echo "═══════════════════════════════════════════════════════════════"
if (( FAIL_COUNT == 0 )); then
  printf '\033[32m  D1 fix pin tests: %d/%d PASS\033[0m\n' "$PASS_COUNT" "$((PASS_COUNT+FAIL_COUNT))"
  exit 0
else
  printf '\033[31m  D1 fix pin tests: %d FAIL / %d total\033[0m\n' "$FAIL_COUNT" "$((PASS_COUNT+FAIL_COUNT))"
  exit 1
fi
