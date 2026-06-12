#!/usr/bin/env bash
# test_check_routines.sh — hermetic tests for /ren:doctor ROUTINES section (ADR-034).
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK_SCRIPT="$(cd "$SCRIPT_DIR/.." && pwd)/check-routines.sh"

PASS_COUNT=0; FAIL_COUNT=0
pass() { printf '\033[32m  ✓ PASS\033[0m  %s\n' "$1"; PASS_COUNT=$((PASS_COUNT+1)); }
fail() { printf '\033[31m  ✗ FAIL\033[0m  %s\n' "$1"; FAIL_COUNT=$((FAIL_COUNT+1)); }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
ROUTINES="$TMP/wiki/routines"; mkdir -p "$ROUTINES"

mk_routine() {  # $1=slug $2=trigger $3=tier
  cat > "$ROUTINES/$1.md" <<EOF
---
type: routine-spec
schema_version: 1
framework_version: "1.0.0"
name: "$1"
trigger_type: "$2"
linked_repo: "https://github.com/u/$1"
network_tier: "$3"
---

# $1
EOF
}

echo "▶ Scenario A — no routines dir: skip, exit 0"
OUT_A="$(env -u SF_PLAN_TIER CLAUDE_PLUGIN_OPTION_WIKIROOT="$TMP/empty-wiki" bash "$CHECK_SCRIPT" 2>&1)"; RC_A=$?
[[ $RC_A -eq 0 ]] && pass "exits 0" || fail "expected 0 got $RC_A"
echo "$OUT_A" | grep -q '^routines|skip|' && pass "emits routines|skip" || fail "expected routines|skip"

echo "▶ Scenario B — a 'full' tier routine is flagged warn"
mk_routine "scraper" "cron" "full"
mk_routine "digest" "cron" "trusted"
OUT_B="$(SF_PLAN_TIER=max CLAUDE_PLUGIN_OPTION_WIKIROOT="$TMP/wiki" bash "$CHECK_SCRIPT" 2>&1)"; RC_B=$?
[[ $RC_B -eq 0 ]] && pass "exits 0" || fail "expected 0 got $RC_B"
echo "$OUT_B" | grep -q '^routine-net:scraper|warn|network tier = full|' \
  && pass "flags full-tier routine" || fail "expected routine-net:scraper|warn"

echo "▶ Scenario C — quota line reflects cron count vs Max cap"
echo "$OUT_B" | grep -q '^routine-quota|ok|2/15 scheduled (max cap)|' \
  && pass "quota 2/15 for max" || fail "expected routine-quota|ok|2/15 scheduled (max cap)"

echo "▶ Scenario D — pro cap is 5; 8 cron routines => warn"
for i in 1 2 3 4 5 6; do mk_routine "r$i" "cron" "trusted"; done
OUT_D="$(SF_PLAN_TIER=pro CLAUDE_PLUGIN_OPTION_WIKIROOT="$TMP/wiki" bash "$CHECK_SCRIPT" 2>&1)"
echo "$OUT_D" | grep -q '^routine-quota|warn|' && pass "warns over pro cap" || fail "expected routine-quota|warn"

echo "▶ Scenario E — api/github triggers do NOT count toward the cron quota"
mk_routine "webhook-r" "api" "trusted"
mk_routine "ci-r" "github" "trusted"
OUT_E="$(SF_PLAN_TIER=pro CLAUDE_PLUGIN_OPTION_WIKIROOT="$TMP/wiki" bash "$CHECK_SCRIPT" 2>&1)"
# scenario D left 8 cron routines; adding api+github must keep the cron count at 8 (8/5 pro = warn)
echo "$OUT_E" | grep -q '^routine-quota|warn|8/5 scheduled (pro cap)|' && pass "api/github not counted toward quota" || fail "non-cron trigger counted toward quota"

echo "═══════════════════════════════════════════════"
if (( FAIL_COUNT == 0 )); then
  printf '\033[32m  check-routines tests: %d PASS\033[0m\n' "$PASS_COUNT"; exit 0
else
  printf '\033[31m  check-routines: %d FAIL / %d total\033[0m\n' "$FAIL_COUNT" "$((PASS_COUNT+FAIL_COUNT))"; exit 1
fi
