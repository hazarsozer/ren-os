#!/usr/bin/env bash
# test_check_context.sh — hermetic tests for the /ren:doctor CONTEXT & TOKEN ECONOMICS section.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK="$(cd "$SCRIPT_DIR/.." && pwd)/check-context.sh"
PASS=0; FAIL=0
pass() { printf '\033[32m  ✓ PASS\033[0m  %s\n' "$1"; PASS=$((PASS+1)); }
fail() { printf '\033[31m  ✗ FAIL\033[0m  %s\n' "$1"; FAIL=$((FAIL+1)); }

# Fixture: a fake framework root with two skills — one oversized, one missing a frontmatter field.
FX="$(mktemp -d)"; trap 'rm -rf "$FX"' EXIT
mkdir -p "$FX/skills/big/" "$FX/skills/small/"
{ echo "---"; echo "name: big"; echo "description: x"; echo "version: 0.1.0"; echo "---"; \
  for i in $(seq 1 600); do echo "line $i"; done; } > "$FX/skills/big/SKILL.md"
{ echo "---"; echo "name: small"; echo "description: y"; echo "---"; echo body; } > "$FX/skills/small/SKILL.md"   # missing version
mkdir -p "$FX/home/.claude"
printf '%s\n' '{"mcpServers":{"resend":{},"canva":{}},"enabledPlugins":{"superpowers@x":true}}' > "$FX/home/.claude.json"
{ for i in $(seq 1 250); do echo "claude md line $i"; done; } > "$FX/home/.claude/CLAUDE.md"   # > 200 → token-heavy
printf '%s\n' '{"permissions":{"defaultMode":"bypassPermissions"}}' > "$FX/home/.claude/settings.json"

echo "▶ Scenario A — counts, lint, sizes, auto-mode"
OUT="$(SF_PLUGIN_DIR="$FX" HOME="$FX/home" CLAUDE_PROJECT_CLAUDE_MD="$FX/none/CLAUDE.md" bash "$CHECK" 2>&1)"; RC=$?
[ "$RC" = "0" ] && pass "exits 0" || fail "exit was $RC"
grep -q '^mcp_servers|ok|2' <<<"$OUT" && pass "counts 2 MCP servers" || fail "mcp_servers: $(grep '^mcp_servers' <<<"$OUT")"
grep -q '^framework_skills|ok|2' <<<"$OUT" && pass "counts 2 skills" || fail "framework_skills"
grep -Eq '^skill_size_lint\|warn\|' <<<"$OUT" && pass "lint warns (oversized + missing field)" || fail "skill_size_lint"
grep -q 'big' <<<"$OUT" && pass "names the oversized skill" || fail "no oversized skill name"
grep -Eq '^claude_md_global\|warn\|' <<<"$OUT" && pass "flags token-heavy global CLAUDE.md" || fail "claude_md_global"
grep -q '^claude_md_project|skip' <<<"$OUT" && pass "absent project CLAUDE.md → skip" || fail "claude_md_project"
grep -Eq '^auto_mode\|warn\|' <<<"$OUT" && pass "warns bypassPermissions default" || fail "auto_mode"

echo "▶ Scenario B — all absent → clean, exit 0"
EMPTY="$(mktemp -d)"; trap 'rm -rf "$FX" "$EMPTY" "${BAD:-}"' EXIT
OUT2="$(SF_PLUGIN_DIR="$EMPTY" HOME="$EMPTY" CLAUDE_PROJECT_CLAUDE_MD="$EMPTY/none" bash "$CHECK" 2>&1)"; RC2=$?
[ "$RC2" = "0" ] && pass "exits 0 with empty env" || fail "empty exit $RC2"
grep -q '^auto_mode|ok' <<<"$OUT2" && pass "no settings → auto_mode ok (safe default)" || fail "auto_mode empty"

echo "▶ Scenario C — non-UTF-8 byte in SKILL.md frontmatter → still exits 0"
BAD="$(mktemp -d)"; trap 'rm -rf "$FX" "$EMPTY" "$BAD"' EXIT
mkdir -p "$BAD/skills/garbled/"
# Frontmatter delimiters present, but a raw 0xFF byte inside breaks strict UTF-8 decoding.
{ printf '%s\n' '---' 'name: garbled'; printf 'description: \xff bad byte\n'; printf '%s\n' 'version: 0.1.0' '---' body; } > "$BAD/skills/garbled/SKILL.md"
OUT3="$(SF_PLUGIN_DIR="$BAD" HOME="$BAD" CLAUDE_PROJECT_CLAUDE_MD="$BAD/none" bash "$CHECK" 2>&1)"; RC3=$?
[ "$RC3" = "0" ] && pass "exits 0 despite non-UTF-8 SKILL.md" || fail "non-utf8 exit $RC3"
grep -q '^framework_skills|ok|1' <<<"$OUT3" && pass "still counts the garbled skill" || fail "framework_skills non-utf8"

echo ""; echo "context: $PASS passed, $FAIL failed"; [ "$FAIL" = "0" ]
