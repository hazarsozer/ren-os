#!/usr/bin/env bash
# check-plugins.sh — sf-doctor PLUGINS section
#
# Output format: same as check-env.sh — `KEY|STATUS|VALUE|HINT`.
#
# Plugins checked (per ADR-006):
#   sf, superpowers, skill-creator, claude-mem, context-mode,
#   context7, claude-md-management, frontend-design (conditional)
#
# Also:
#   hooks-sessionstart (per references/hook-id-registry.md)
#   wiki (counts entries + projects)
#
# Side effects: NONE. Reads marketplace cache + hooks.json.

set -uo pipefail

emit() { printf '%s|%s|%s|%s\n' "$1" "$2" "${3:-}" "${4:-}"; }

# ──────────────────────────────────────────────────────────────────────
# Locate the framework plugin install
# ──────────────────────────────────────────────────────────────────────
# CC plugin cache lives at ~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/
# We look for any installed sf version.
PLUGIN_CACHE_ROOT="${HOME}/.claude/plugins/cache"
# Honor a pre-set SF_PLUGIN_DIR (used by tests + power users to point the checks at a
# specific plugin tree, e.g. the dev repo root). When unset, auto-discover from the cache.
SF_PLUGIN_DIR="${SF_PLUGIN_DIR:-}"
SF_VERSION="${SF_VERSION:-}"
SF_MARKETPLACE="${SF_MARKETPLACE:-}"

if [[ -z "$SF_PLUGIN_DIR" && -d "$PLUGIN_CACHE_ROOT" ]]; then
  # Find the newest installed version (sort by version dir mtime, latest wins)
  for mkt_dir in "$PLUGIN_CACHE_ROOT"/*/; do
    [[ -d "$mkt_dir/sf" ]] || continue
    for ver_dir in "$mkt_dir/sf"/*/; do
      [[ -f "$ver_dir/.claude-plugin/plugin.json" ]] || continue
      ver_basename="$(basename "$ver_dir")"
      if [[ -z "$SF_VERSION" ]] || [[ "$ver_basename" > "$SF_VERSION" ]]; then
        SF_VERSION="$ver_basename"
        SF_PLUGIN_DIR="$ver_dir"
        SF_MARKETPLACE="$(basename "$mkt_dir")"
      fi
    done
  done
fi

if [[ -n "$SF_PLUGIN_DIR" ]]; then
  # Parse version from plugin.json (source of truth per CC docs)
  SF_PLUGIN_JSON_VER="$(grep -oE '"version"\s*:\s*"[^"]+"' "$SF_PLUGIN_DIR/.claude-plugin/plugin.json" | head -1 | sed 's/.*"\([^"]*\)"$/\1/')"
  emit "sf" "ok" "v${SF_PLUGIN_JSON_VER:-$SF_VERSION} (installed via ${SF_MARKETPLACE})" ""
else
  emit "sf" "error" "not found in plugin cache" "→ /plugin install ren@ren-os"
fi

# ──────────────────────────────────────────────────────────────────────
# Sibling required plugins
# ──────────────────────────────────────────────────────────────────────
check_sibling_plugin() {
  local key="$1" display="$2" extra_hint="$3"
  if [[ -z "$PLUGIN_CACHE_ROOT" || ! -d "$PLUGIN_CACHE_ROOT" ]]; then
    emit "$key" "skip" "" "(plugin cache not found)"
    return
  fi
  # Search all marketplaces for any version of the plugin
  local plugin_dir=""
  for mkt_dir in "$PLUGIN_CACHE_ROOT"/*/; do
    if compgen -G "$mkt_dir/$key" >/dev/null; then
      plugin_dir="$(find "$mkt_dir/$key" -maxdepth 1 -type d -mindepth 1 | sort -V | tail -1)"
      break
    fi
  done
  if [[ -n "$plugin_dir" ]]; then
    local ver=""
    if [[ -f "$plugin_dir/.claude-plugin/plugin.json" ]]; then
      ver="$(grep -oE '"version"\s*:\s*"[^"]+"' "$plugin_dir/.claude-plugin/plugin.json" | head -1 | sed 's/.*"\([^"]*\)"$/\1/')"
    fi
    emit "$key" "ok" "${ver:+v$ver }installed${extra_hint:+ ${extra_hint}}" ""
  else
    emit "$key" "error" "not installed" "→ /plugin install ${key}@<its marketplace>"
  fi
}

check_sibling_plugin "superpowers" "Superpowers" ""
check_sibling_plugin "skill-creator" "Skill Creator" ""
check_sibling_plugin "claude-mem" "claude-mem" ""
check_sibling_plugin "context-mode" "Context Mode" "(ELv2 — SaaS distribution restricted; see LICENSES.md)"
check_sibling_plugin "context7" "context7" "(Upstash API key required)"
check_sibling_plugin "claude-md-management" "claude-md-management" ""

# Frontend Design — conditional
if [[ -n "$PLUGIN_CACHE_ROOT" && -d "$PLUGIN_CACHE_ROOT" ]]; then
  fd_found=""
  for mkt_dir in "$PLUGIN_CACHE_ROOT"/*/; do
    if compgen -G "$mkt_dir/frontend-design" >/dev/null; then
      fd_found="yes"
      break
    fi
  done
  if [[ -n "$fd_found" ]]; then
    emit "frontend-design" "ok" "installed" "(conditional — UI work enabled)"
  else
    emit "frontend-design" "skip" "" "(conditional — not installed; skip if no UI work)"
  fi
fi

# ──────────────────────────────────────────────────────────────────────
# Hooks registration
# ──────────────────────────────────────────────────────────────────────
# Per references/hook-id-registry.md, two-way detection:
#   primary  : grep for 'sf-wake-up.py' in the command field (more precise than directory)
#   secondary: grep for 'sf-wake-up:' in description field (defense in depth)
if [[ -n "$SF_PLUGIN_DIR" && -f "$SF_PLUGIN_DIR/hooks/hooks.json" ]]; then
  HOOKS_JSON="$SF_PLUGIN_DIR/hooks/hooks.json"
  PRIMARY_HIT=0
  SECONDARY_HIT=0
  grep -q "sf-wake-up\.py" "$HOOKS_JSON" && PRIMARY_HIT=1
  # Description sentinel: must include "sf-wake-up:" inside a description field
  grep -qE '"description"\s*:\s*"[^"]*sf-wake-up:' "$HOOKS_JSON" && SECONDARY_HIT=1

  if (( PRIMARY_HIT )); then
    # Try to extract matcher + timeout for nicer reporting (best-effort, no full JSON parser)
    SS_MATCHER="$(grep -A1 '"SessionStart"' "$HOOKS_JSON" | grep -oE '"matcher"\s*:\s*"[^"]+"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/' || echo '*')"
    SS_TIMEOUT="$(grep -oE '"timeout"\s*:\s*[0-9]+' "$HOOKS_JSON" | head -1 | awk -F: '{print $2}' | tr -d ' ' || echo 'default')"
    if [[ "$SS_MATCHER" == "startup" || "$SS_MATCHER" == "*" || -z "$SS_MATCHER" ]]; then
      emit "hooks-sessionstart" "ok" "SessionStart (sf-wake-up.py, matcher: ${SS_MATCHER:-*}, timeout: ${SS_TIMEOUT}s)" ""
    else
      emit "hooks-sessionstart" "warn" "SessionStart hook registered but matcher='${SS_MATCHER}' — wake-up will not fire on fresh sessions" "→ Update matcher to 'startup' or '*'"
    fi
  elif (( SECONDARY_HIT )); then
    # Description sentinel found but command path didn't match. Degraded green per registry.
    emit "hooks-sessionstart" "warn" "SessionStart description matches but command path is wrong" "→ Check \${CLAUDE_PLUGIN_ROOT}/hooks/wake-up/sf-wake-up.py exists"
  else
    emit "hooks-sessionstart" "warn" "SessionStart hook missing (sf-wake-up not active)" "→ Run /ren:update which re-registers hooks, OR /reload-plugins"
  fi
else
  emit "hooks-sessionstart" "skip" "" "(plugin not installed; hooks check skipped)"
fi

# ──────────────────────────────────────────────────────────────────────
# Wiki
# ──────────────────────────────────────────────────────────────────────
WIKI_ROOT="${CLAUDE_PLUGIN_OPTION_WIKIROOT:-$HOME/.startup-framework/wiki}"
if [[ -d "$WIKI_ROOT" ]]; then
  ENTRY_COUNT="$(find "$WIKI_ROOT" -maxdepth 4 -name '*.md' -type f 2>/dev/null | wc -l)"
  PROJECT_COUNT=0
  if [[ -d "$WIKI_ROOT/projects" ]]; then
    PROJECT_COUNT="$(find "$WIKI_ROOT/projects" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l)"
  fi
  emit "wiki" "ok" "${WIKI_ROOT} (${ENTRY_COUNT} entries, ${PROJECT_COUNT} projects)" ""
else
  emit "wiki" "error" "${WIKI_ROOT} not found" "→ Run /ren:install to bootstrap; or /ren:install --restore <wiki-remote-url> to recover"
fi

exit 0
