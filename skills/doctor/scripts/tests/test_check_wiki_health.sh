#!/usr/bin/env bash
# test_check_wiki_health.sh — hermetic tests for the /ren:doctor WIKI HEALTH section.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK="$(cd "$SCRIPT_DIR/.." && pwd)/check-wiki-health.sh"
PASS=0; FAIL=0
pass() { printf '\033[32m  ✓ PASS\033[0m  %s\n' "$1"; PASS=$((PASS+1)); }
fail() { printf '\033[31m  ✗ FAIL\033[0m  %s\n' "$1"; FAIL=$((FAIL+1)); }

W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
mkdir -p "$W/research"
# index links to one existing + one missing page (dead wikilink)
# Fresh pages use 2099-09-01 (> DOCTOR_TODAY=2099-06-01) so they aren't stale (< 90d old).
printf '%s\n' '---' 'title: i' 'updated: 2099-09-01' '---' 'See [[real-page]] and [[ghost-page]].' > "$W/index.md"
printf '%s\n' '---' 'title: r' 'updated: 2099-09-01' '---' 'fresh' > "$W/research/real-page.md"
# a stale page (old updated) and a heavy page (>500 lines)
printf '%s\n' '---' 'title: s' 'updated: 2000-01-01' '---' 'old' > "$W/research/stale.md"
{ echo "---"; echo "title: h"; echo "updated: 2099-09-01"; echo "---"; for i in $(seq 1 600); do echo "L$i"; done; } > "$W/research/heavy.md"

echo "▶ Scenario A — one dead link, one stale, one heavy"
OUT="$(CLAUDE_PLUGIN_OPTION_WIKIROOT="$W" DOCTOR_TODAY="2099-06-01" bash "$CHECK" 2>&1)"; RC=$?
[ "$RC" = "0" ] && pass "exits 0" || fail "exit $RC"
grep -Eq '^dead_links\|warn\|1\b' <<<"$OUT" && pass "finds 1 dead link" || fail "dead_links: $(grep '^dead_links' <<<"$OUT")"
grep -q 'ghost-page' <<<"$OUT" && pass "names the dead target" || fail "no dead target name"
grep -Eq '^stale_pages\|warn\|1\b' <<<"$OUT" && pass "finds 1 stale page" || fail "stale_pages"
grep -Eq '^heavy_pages\|warn\|1\b' <<<"$OUT" && pass "finds 1 heavy page" || fail "heavy_pages"
grep -Eq '^health_score\|(warn|error)\|' <<<"$OUT" && pass "emits a score" || fail "health_score"

echo "▶ Scenario B — no wiki → skip, exit 0"
OUT2="$(CLAUDE_PLUGIN_OPTION_WIKIROOT="$W/nonexistent" bash "$CHECK" 2>&1)"; RC2=$?
[ "$RC2" = "0" ] && pass "exits 0 without wiki" || fail "exit $RC2"
grep -Fq 'health_score|skip' <<<"$OUT2" && pass "no wiki → skip" || fail "no-wiki skip"

echo ""; echo "wiki-health: $PASS passed, $FAIL failed"; [ "$FAIL" = "0" ]
