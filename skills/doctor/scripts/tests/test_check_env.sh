#!/usr/bin/env bash
# test_check_env.sh — hermetic pin tests for the /sf:doctor ENVIRONMENT section.
# SECURITY guarantee: when OTEL_EXPORTER_OTLP_ENDPOINT is set, the raw endpoint
# URL (which can embed basic-auth or a token) is NEVER printed; the otel line
# reports presence ("configured"), mirroring ANTHROPIC_API_KEY's "set".

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK_SCRIPT="$(cd "$SCRIPT_DIR/.." && pwd)/check-env.sh"

PASS_COUNT=0
FAIL_COUNT=0
pass() { printf '\033[32m  ✓ PASS\033[0m  %s\n' "$1"; PASS_COUNT=$((PASS_COUNT+1)); }
fail() { printf '\033[31m  ✗ FAIL\033[0m  %s\n' "$1"; FAIL_COUNT=$((FAIL_COUNT+1)); }

OTEL_SECRET_URL="https://u5er:sk-FAKE-OTEL-TOKEN-9999@otlp.example.com/v1/traces?token=FAKE-OTEL-TOKEN-9999"

echo "▶ Scenario A — OTLP endpoint set: 'configured' shown, raw URL never printed"
OUT_A="$(OTEL_EXPORTER_OTLP_ENDPOINT="$OTEL_SECRET_URL" bash "$CHECK_SCRIPT" 2>&1)"; RC_A=$?
[[ $RC_A -eq 0 ]] && pass "exits 0" || fail "expected exit 0, got $RC_A"
echo "$OUT_A" | grep -q '^otel|ok|configured|' \
  && pass "otel reported as 'configured' when endpoint is set" \
  || fail "expected line 'otel|ok|configured|'"
if echo "$OUT_A" | grep -Fq "$OTEL_SECRET_URL"; then
  fail "SECRET LEAK — raw OTLP endpoint URL appeared in output"
else
  pass "raw OTLP endpoint URL absent from output"
fi
if echo "$OUT_A" | grep -Fq "FAKE-OTEL-TOKEN-9999"; then
  fail "SECRET LEAK — embedded OTLP token appeared in output"
else
  pass "embedded OTLP token absent from output"
fi

echo
echo "▶ Scenario B — OTLP endpoint unset: skip status"
OUT_B="$(env -u OTEL_EXPORTER_OTLP_ENDPOINT bash "$CHECK_SCRIPT" 2>&1)"; RC_B=$?
[[ $RC_B -eq 0 ]] && pass "exits 0" || fail "expected exit 0, got $RC_B"
echo "$OUT_B" | grep -q '^otel|skip|' \
  && pass "otel reported as skip when endpoint unset" \
  || fail "expected 'otel|skip|' line"

echo
echo "═══════════════════════════════════════════════════════════════"
if (( FAIL_COUNT == 0 )); then
  printf '\033[32m  check-env pin tests: %d/%d PASS\033[0m\n' "$PASS_COUNT" "$((PASS_COUNT+FAIL_COUNT))"
  exit 0
else
  printf '\033[31m  check-env pin tests: %d FAIL / %d total\033[0m\n' "$FAIL_COUNT" "$((PASS_COUNT+FAIL_COUNT))"
  exit 1
fi
