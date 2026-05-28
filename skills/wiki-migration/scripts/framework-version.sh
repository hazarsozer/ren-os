#!/usr/bin/env bash
# framework-version.sh — print the installed framework version to stdout.
#
# Resolution chain (same as feed.config.framework_version() per feed-2 coord 2026-05-28):
#   1. $CLAUDE_PLUGIN_OPTION_FRAMEWORK_VERSION (env)         — explicit override
#   2. $CLAUDE_PLUGIN_ROOT/.claude-plugin/plugin.json#version — canonical install
#   3. Fallback "1.0.0"                                       — only if both above fail
#
# Fail-open semantics: any error falls through to the next layer; never raises.
# Stdout: exactly one line containing the version. No newlines or extra output.
# Exit: always 0 (the fallback guarantees a printable answer).
#
# Used by:
#   - /sf:doctor's check-update.sh (cross-version compare)
#   - /sf:update's state machine (current-version source of truth)
#   - any future bash consumer needing "what version am I?"
#
# Python consumers should use feed.config.framework_version() instead — same chain,
# zero shell-out cost on hot paths.

set -uo pipefail

# Layer 1: explicit env override
if [[ -n "${CLAUDE_PLUGIN_OPTION_FRAMEWORK_VERSION:-}" ]]; then
  printf '%s' "$CLAUDE_PLUGIN_OPTION_FRAMEWORK_VERSION"
  exit 0
fi

# Layer 2: parse from installed plugin.json
PJ="${CLAUDE_PLUGIN_ROOT:-}/.claude-plugin/plugin.json"
if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" && -f "$PJ" ]]; then
  # Tiny grep+sed (no jq dep, no python startup cost)
  VER="$(grep -oE '"version"[[:space:]]*:[[:space:]]*"[^"]+"' "$PJ" 2>/dev/null | head -1 | sed 's/.*"\([^"]*\)"$/\1/')"
  if [[ -n "$VER" ]]; then
    printf '%s' "$VER"
    exit 0
  fi
fi

# Layer 3: fallback
printf '1.0.0'
exit 0
