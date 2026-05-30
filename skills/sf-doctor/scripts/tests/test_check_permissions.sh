#!/usr/bin/env bash
# test_check_permissions.sh — hermetic pin tests for the /sf:doctor --permissions audit.
#
# check-permissions.sh reads ~/.claude.json + ~/.claude/settings.json(.local) and emits a
# "KEYS ON YOUR RING" report. These tests seed crafted config via the script's explicit
# input overrides (SF_CLAUDE_JSON / SF_SETTINGS_JSON / SF_SETTINGS_LOCAL_JSON) so nothing
# touches the real $HOME, the network, or any real secret.
#
# Guarantees pinned here:
#   A) seeded MCP server names are listed, with transport (stdio/http) + grant notes;
#      enabled plugins, hooks, per-project servers, and the allow tally all render;
#      broad grants (bare `Bash`, `mcp__*`) are flagged; and — critically — SEEDED FAKE
#      TOKENS NEVER appear in the output (the script reads structure, not values).
#   B) without a wildcard, explicit per-server tool-key counts are reported and no broad
#      grant is flagged.
#   C) every input absent -> exits 0 and renders a clean empty report (full tolerance).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
CHECK_SCRIPT="$REPO_ROOT/skills/sf-doctor/scripts/check-permissions.sh"

PASS_COUNT=0
FAIL_COUNT=0

pass() { printf '\033[32m  ✓ PASS\033[0m  %s\n' "$1"; PASS_COUNT=$((PASS_COUNT+1)); }
fail() { printf '\033[31m  ✗ FAIL\033[0m  %s\n' "$1"; FAIL_COUNT=$((FAIL_COUNT+1)); }

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# Fake secrets that MUST NEVER be echoed by the audit.
TOK_ENV="sk-FAKETOKEN-NEVER-PRINT-9999"
TOK_HDR="FAKE-HEADER-TOKEN-7777"
TOK_PROJ="FAKE-PROJ-SECRET-5555"

# ── Seed fixtures ─────────────────────────────────────────────────────
cat > "$TMP/claude.json" <<EOF
{
  "mcpServers": {
    "resend-test": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "resend-mcp"],
      "env": { "RESEND_API_KEY": "${TOK_ENV}" }
    },
    "remote-test": {
      "type": "http",
      "url": "https://example.com/mcp",
      "headers": { "Authorization": "Bearer ${TOK_HDR}" }
    }
  },
  "projects": {
    "/home/tester/Dev/proj-a": {
      "mcpServers": {
        "proj-mcp": {
          "type": "stdio",
          "command": "node",
          "args": ["server.js"],
          "env": { "PROJ_SECRET": "${TOK_PROJ}" }
        }
      },
      "allowedTools": ["mcp__proj-mcp__do-thing"]
    },
    "/home/tester/Dev/proj-b": {
      "mcpServers": {},
      "allowedTools": []
    }
  }
}
EOF

cat > "$TMP/settings_A.json" <<'EOF'
{
  "permissions": {
    "allow": ["Bash", "mcp__*", "mcp__resend-test__send-email", "Read(/home/**)", "mcp__resend-test__list-emails"],
    "deny": ["Bash(rm *)"],
    "ask": []
  },
  "enabledPlugins": { "foo-plugin@test-mkt": true, "bar-plugin@test-mkt": true },
  "hooks": { "SessionStart": [{"x": 1}], "PreToolUse": [{"x": 1}] }
}
EOF

cat > "$TMP/settings_B.json" <<'EOF'
{
  "permissions": {
    "allow": ["mcp__resend-test__send-email", "mcp__resend-test__list-emails"],
    "deny": [],
    "ask": []
  }
}
EOF

NOPE="$TMP/does-not-exist.json"

# ── Scenario A — full fixture (wildcard + bare Bash + secrets) ────────
echo "▶ Scenario A — full config: names, transports, tally, broad grants, secret-safety"
OUT_A="$(SF_CLAUDE_JSON="$TMP/claude.json" SF_SETTINGS_JSON="$TMP/settings_A.json" \
         SF_SETTINGS_LOCAL_JSON="$NOPE" bash "$CHECK_SCRIPT" 2>&1)"; RC_A=$?

[[ $RC_A -eq 0 ]] && pass "exits 0" || fail "expected exit 0, got $RC_A"

echo "$OUT_A" | grep -q "KEYS ON YOUR RING" \
  && pass "report header 'KEYS ON YOUR RING' present" \
  || fail "missing 'KEYS ON YOUR RING' header"

echo "$OUT_A" | grep -iq "keys != instructions" \
  && pass "framing copy 'keys != instructions' present" \
  || fail "missing 'keys != instructions' framing"

for srv in resend-test remote-test proj-mcp; do
  echo "$OUT_A" | grep -q "$srv" \
    && pass "MCP server '$srv' listed" \
    || fail "MCP server '$srv' NOT listed"
done

echo "$OUT_A" | grep -q "stdio" && pass "transport 'stdio' shown" || fail "transport 'stdio' missing"
echo "$OUT_A" | grep -q "http"  && pass "transport 'http' shown"  || fail "transport 'http' missing"

echo "$OUT_A" | grep -q "allow: 5 rule(s)" \
  && pass "allow rules tallied (5)" \
  || fail "allow tally wrong (expected 'allow: 5 rule(s)')"

echo "$OUT_A" | grep -q "BROAD GRANT" \
  && pass "broad grants section flags something" \
  || fail "no BROAD GRANT flagged"
echo "$OUT_A" | grep -Fq 'bare `Bash`' \
  && pass "bare \`Bash\` flagged as broad" \
  || fail "bare Bash not flagged"
echo "$OUT_A" | grep -Fq 'mcp__*' \
  && pass "wildcard 'mcp__*' flagged as broad" \
  || fail "mcp__* not flagged"

echo "$OUT_A" | grep -Fq 'ALL tools (via mcp__* wildcard)' \
  && pass "global mcp__* wildcard collapses per-server grant notes" \
  || fail "expected 'ALL tools (via mcp__* wildcard)' note"

echo "$OUT_A" | grep -q "foo-plugin@test-mkt" \
  && pass "enabled plugin (dict key) listed" \
  || fail "enabled plugin not listed"

echo "$OUT_A" | grep -q "SessionStart" \
  && pass "hooks event (SessionStart) listed" \
  || fail "hooks event not listed"

echo "$OUT_A" | grep -q "proj-a" \
  && pass "per-project label (proj-a) shown" \
  || fail "per-project label not shown"

# CRITICAL: no seeded secret may ever appear in the output.
SECRET_LEAK=0
for tok in "$TOK_ENV" "$TOK_HDR" "$TOK_PROJ"; do
  if echo "$OUT_A" | grep -Fq "$tok"; then
    fail "SECRET LEAK — token '$tok' appeared in output"
    SECRET_LEAK=1
  fi
done
[[ $SECRET_LEAK -eq 0 ]] && pass "no seeded secret/token printed (env + header + project secrets all absent)"

# ── Scenario B — no wildcard: explicit per-server counts, no broad grant ─
echo
echo "▶ Scenario B — no wildcard: explicit tool-key count + clean broad-grants"
OUT_B="$(SF_CLAUDE_JSON="$TMP/claude.json" SF_SETTINGS_JSON="$TMP/settings_B.json" \
         SF_SETTINGS_LOCAL_JSON="$NOPE" bash "$CHECK_SCRIPT" 2>&1)"; RC_B=$?

[[ $RC_B -eq 0 ]] && pass "exits 0" || fail "expected exit 0, got $RC_B"

echo "$OUT_B" | grep -q "2 tool-key(s) granted" \
  && pass "explicit per-server count reported (resend-test: 2)" \
  || fail "expected '2 tool-key(s) granted' for resend-test"

echo "$OUT_B" | grep -q "none found" \
  && pass "no broad grants flagged when none exist" \
  || fail "expected '(none found ...)' in broad grants"

echo "$OUT_B" | grep -Fq "$TOK_ENV" \
  && fail "SECRET LEAK in scenario B" \
  || pass "no secret printed in scenario B"

# ── Scenario C — all inputs absent: full tolerance ───────────────────
echo
echo "▶ Scenario C — every input absent: exits 0, renders empty report"
OUT_C="$(SF_CLAUDE_JSON="$NOPE" SF_SETTINGS_JSON="$NOPE" SF_SETTINGS_LOCAL_JSON="$NOPE" \
         bash "$CHECK_SCRIPT" 2>&1)"; RC_C=$?

[[ $RC_C -eq 0 ]] && pass "exits 0 with no config at all" || fail "expected exit 0, got $RC_C"
echo "$OUT_C" | grep -q "KEYS ON YOUR RING"        && pass "header still renders" || fail "header missing on empty"
echo "$OUT_C" | grep -q "(none configured globally)" && pass "empty MCP handled" || fail "empty MCP not handled"
echo "$OUT_C" | grep -q "(none enabled)"            && pass "empty plugins handled" || fail "empty plugins not handled"
echo "$OUT_C" | grep -q "(no hooks configured)"     && pass "empty hooks handled" || fail "empty hooks not handled"

# ── Summary ──────────────────────────────────────────────────────────
echo
echo "═══════════════════════════════════════════════════════════════"
if (( FAIL_COUNT == 0 )); then
  printf '\033[32m  permission-audit pin tests: %d/%d PASS\033[0m\n' "$PASS_COUNT" "$((PASS_COUNT+FAIL_COUNT))"
  exit 0
else
  printf '\033[31m  permission-audit pin tests: %d FAIL / %d total\033[0m\n' "$FAIL_COUNT" "$((PASS_COUNT+FAIL_COUNT))"
  exit 1
fi
