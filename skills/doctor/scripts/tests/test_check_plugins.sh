#!/usr/bin/env bash
# test_check_plugins.sh — pin test for REVIEW.md H1 fix.
#
# H1: check-plugins.sh + references/hook-id-registry.md grepped for `sf-wake-up.js`,
# but the shipped hook is `sf-wake-up.py` (hooks.json registers
# `python3 "$CLAUDE_PLUGIN_ROOT/hooks/wake-up/sf-wake-up.py"`). Result: every
# friend's first /sf:doctor falsely warned "command path is wrong" and pointed at
# a nonexistent .js file.
#
# Test 1 is the ADR-029 "real contract instance" assertion that would have caught
# H1: run check-plugins.sh against the REAL repo hooks.json and assert status=ok.
# Tests 2-4 exercise the secondary/missing/matcher branches via fixtures.
# Test 5 is a source-regression guard against re-introducing the `.js` grep.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
CHECK_SCRIPT="$REPO_ROOT/skills/doctor/scripts/check-plugins.sh"

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

TMPROOT=$(mktemp -d)
trap 'rm -rf "$TMPROOT"' EXIT

# Keep every run hermetic + fast: empty wiki path so the wiki section
# short-circuits without touching $HOME or the network.
HERMETIC_ENV=(
  "CLAUDE_PLUGIN_OPTION_WIKIROOT=$TMPROOT/nowiki"
)

run_check() {
  # $1 = SF_PLUGIN_DIR to point the checks at. Emits only the hooks-sessionstart line.
  env "${HERMETIC_ENV[@]}" SF_PLUGIN_DIR="$1" bash "$CHECK_SCRIPT" 2>/dev/null \
    | grep '^hooks-sessionstart|' || true
}

make_plugin_with_hooks() {
  # $1 = dest dir, $2 = hooks.json content
  local dir="$1"
  mkdir -p "$dir/hooks"
  printf '%s\n' "$2" > "$dir/hooks/hooks.json"
}

# ──────────────────────────────────────────────────────────────────────
# Test 1 — REAL contract: the shipped hooks.json registers sf-wake-up.py
# Before the H1 fix this returned warn "command path is wrong" (false alarm).
# After: PRIMARY_HIT on `sf-wake-up.py` → status=ok.
# ──────────────────────────────────────────────────────────────────────
echo "▶ Test 1 — real repo hooks.json (sf-wake-up.py) → hooks-sessionstart status=ok"
LINE="$(run_check "$REPO_ROOT")"
if [[ -z "$LINE" ]]; then
  fail "no hooks-sessionstart line emitted"
elif echo "$LINE" | grep -q '^hooks-sessionstart|ok|'; then
  pass "status=ok against the real hooks.json (H1 regression guard)"
else
  fail "status is NOT ok — H1 regressed"
  echo "    output line: $LINE"
fi
if echo "$LINE" | grep -q 'sf-wake-up\.py'; then
  pass "value names sf-wake-up.py (not .js)"
else
  fail "value does not name sf-wake-up.py"
  echo "    output line: $LINE"
fi

# ──────────────────────────────────────────────────────────────────────
# Test 2 — secondary detection: description sentinel present, command wrong
# → degraded warn "command path is wrong" (points at the .py file now).
# ──────────────────────────────────────────────────────────────────────
echo
echo "▶ Test 2 — description sentinel but wrong command → warn (command path is wrong)"
FX2="$TMPROOT/fx2"
make_plugin_with_hooks "$FX2" '{
  "hooks": {
    "SessionStart": [
      { "matcher": "startup",
        "hooks": [
          { "type": "command",
            "command": "python3 \"$CLAUDE_PLUGIN_ROOT/hooks/wake-up/wrong-name.py\"",
            "description": "sf-wake-up: SessionStart context injection" } ] }
    ]
  }
}'
LINE="$(run_check "$FX2")"
if echo "$LINE" | grep -q '^hooks-sessionstart|warn|.*command path is wrong'; then
  pass "secondary-detection degraded warn fires"
else
  fail "expected 'command path is wrong' warn did not fire"
  echo "    output line: $LINE"
fi
if echo "$LINE" | grep -q 'sf-wake-up\.py exists'; then
  pass "hint points at sf-wake-up.py (not .js)"
else
  fail "hint does not point at sf-wake-up.py"
  echo "    output line: $LINE"
fi

# ──────────────────────────────────────────────────────────────────────
# Test 3 — no wake-up hook at all → warn "missing"
# ──────────────────────────────────────────────────────────────────────
echo
echo "▶ Test 3 — hooks.json without any wake-up entry → warn (missing)"
FX3="$TMPROOT/fx3"
make_plugin_with_hooks "$FX3" '{
  "hooks": {
    "SessionStart": [
      { "matcher": "startup",
        "hooks": [
          { "type": "command", "command": "python3 something-else.py",
            "description": "unrelated hook" } ] }
    ]
  }
}'
LINE="$(run_check "$FX3")"
if echo "$LINE" | grep -q '^hooks-sessionstart|warn|.*missing'; then
  pass "missing-hook warn fires"
else
  fail "expected 'missing' warn did not fire"
  echo "    output line: $LINE"
fi

# ──────────────────────────────────────────────────────────────────────
# Test 4 — correct command but compact-only matcher → warn (won't fire fresh)
# ──────────────────────────────────────────────────────────────────────
echo
echo "▶ Test 4 — sf-wake-up.py present but matcher=compact only → warn (won't fire on fresh sessions)"
FX4="$TMPROOT/fx4"
make_plugin_with_hooks "$FX4" '{
  "hooks": {
    "SessionStart": [
      { "matcher": "compact",
        "hooks": [
          { "type": "command",
            "command": "python3 \"$CLAUDE_PLUGIN_ROOT/hooks/wake-up/sf-wake-up.py\"",
            "description": "sf-wake-up: re-inject after compaction" } ] }
    ]
  }
}'
LINE="$(run_check "$FX4")"
if echo "$LINE" | grep -q "^hooks-sessionstart|warn|.*will not fire on fresh sessions"; then
  pass "compact-only matcher warn fires"
else
  fail "expected 'will not fire' warn did not fire"
  echo "    output line: $LINE"
fi

# ──────────────────────────────────────────────────────────────────────
# Test 5 — source-regression guard: the script must grep .py, never .js
# ──────────────────────────────────────────────────────────────────────
echo
echo "▶ Test 5 — check-plugins.sh source greps sf-wake-up.py, not .js"
if grep -q 'sf-wake-up\\\.py' "$CHECK_SCRIPT"; then
  pass "check-plugins.sh contains the sf-wake-up\\.py grep"
else
  fail "check-plugins.sh missing the sf-wake-up\\.py grep"
fi
if grep -q 'sf-wake-up\\\.js' "$CHECK_SCRIPT"; then
  fail "check-plugins.sh STILL references sf-wake-up.js (H1 not fully fixed)"
else
  pass "no residual sf-wake-up.js reference in check-plugins.sh"
fi

# ──────────────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────────────
echo
echo "═══════════════════════════════════════════════════════════════"
if (( FAIL_COUNT == 0 )); then
  printf '\033[32m  H1 fix pin tests: %d/%d PASS\033[0m\n' "$PASS_COUNT" "$((PASS_COUNT+FAIL_COUNT))"
  exit 0
else
  printf '\033[31m  H1 fix pin tests: %d FAIL / %d total\033[0m\n' "$FAIL_COUNT" "$((PASS_COUNT+FAIL_COUNT))"
  exit 1
fi
