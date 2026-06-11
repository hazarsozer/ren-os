#!/usr/bin/env bash
# check-update.sh — sf-doctor FRAMEWORK UPDATE section
#
# Output: `KEY|STATUS|VALUE|HINT`
# Keys: installed, latest-stable, latest-rc, channel, changelog
#
# Side effects: NETWORK READ ONLY. `gh api` calls to fetch marketplace plugin.json from upstream.
# Timeout: 8s (must be < parent orchestrator's 10s).

set -uo pipefail

emit() { printf '%s|%s|%s|%s\n' "$1" "$2" "${3:-}" "${4:-}"; }

# Flag parsing
INSTALL_MODE=0
POST_UPDATE=0
for arg in "$@"; do
  case "$arg" in
    --install-mode) INSTALL_MODE=1 ;;
    --post-update) POST_UPDATE=1 ;;
  esac
done

# Locate installed plugin version (source of truth: ${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json)
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-}"
if [[ -z "$PLUGIN_ROOT" ]]; then
  # Fallback for testing outside CC: try to find via cache
  if [[ -d "$HOME/.claude/plugins/cache" ]]; then
    PLUGIN_ROOT="$(find "$HOME/.claude/plugins/cache" -name "plugin.json" -path "*/startup-framework/*" 2>/dev/null | head -1 | xargs -r dirname | xargs -r dirname)"
  fi
fi

INSTALLED_VER="unknown"
REPO_URL=""
if [[ -n "$PLUGIN_ROOT" && -f "$PLUGIN_ROOT/.claude-plugin/plugin.json" ]]; then
  INSTALLED_VER="$(grep -oE '"version"\s*:\s*"[^"]+"' "$PLUGIN_ROOT/.claude-plugin/plugin.json" | head -1 | sed 's/.*"\([^"]*\)"$/\1/')"
  REPO_URL="$(grep -oE '"repository"\s*:\s*"[^"]+"' "$PLUGIN_ROOT/.claude-plugin/plugin.json" | head -1 | sed 's/.*"\([^"]*\)"$/\1/')"
fi

emit "installed" "ok" "v${INSTALLED_VER}" ""

# Install mode → skip update lookup entirely
if [[ $INSTALL_MODE -eq 1 ]]; then
  emit "latest-stable" "skip" "" "(install mode — skipped)"
  emit "latest-rc" "skip" "" ""
  emit "channel" "ok" "stable" ""
  exit 0
fi

# Post-update mode → don't fetch; trust we're at latest
if [[ $POST_UPDATE -eq 1 ]]; then
  emit "latest-stable" "ok" "v${INSTALLED_VER}" "(just updated)"
  emit "latest-rc" "skip" "" ""
  emit "channel" "ok" "stable" ""
  exit 0
fi

# Parse org from repository URL: https://github.com/<org>/ren-os → "<org>"
ORG=""
if [[ "$REPO_URL" =~ github\.com/([^/]+)/([^/]+) ]]; then
  ORG="${BASH_REMATCH[1]}"
fi

# Bail if the org is empty or still an unreplaced placeholder. We match the generic
# `*PLACEHOLDER*` pattern (not the exact placeholder literal) so this defensive sentinel
# does not itself trip the publish-time leftover-placeholder guard in scripts/publish.sh
# — that publish guard is the real gate against shipping an unconfigured manifest.
if [[ -z "$ORG" || "$ORG" == *PLACEHOLDER* ]]; then
  emit "latest-stable" "warn" "cannot determine marketplace repo" "→ Set the repository field in plugin.json or wait for first-ship"
  emit "latest-rc" "skip" "" ""
  emit "channel" "ok" "stable" ""
  exit 0
fi

# Determine channel
RC_CHANNEL="${CLAUDE_PLUGIN_OPTION_RCCHANNEL:-false}"

# Fetch stable marketplace plugin.json
LATEST_STABLE=""
STABLE_REPO="${ORG}/ren-os"
if STABLE_PJ="$(timeout 8 gh api "repos/${STABLE_REPO}/contents/.claude-plugin/plugin.json" --jq '.content' 2>/dev/null)"; then
  if [[ -n "$STABLE_PJ" ]]; then
    LATEST_STABLE="$(echo "$STABLE_PJ" | base64 -d 2>/dev/null | grep -oE '"version"\s*:\s*"[^"]+"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')"
  fi
fi

if [[ -z "$LATEST_STABLE" ]]; then
  emit "latest-stable" "warn" "network failure" "→ gh api unreachable; check 'gh auth status' + connectivity. Existing install unaffected."
else
  # Compare via sort -V (semver-aware enough for non-prerelease tags; for full semver use scripts/version-compare.sh)
  cmp="$(printf '%s\n%s\n' "$INSTALLED_VER" "$LATEST_STABLE" | sort -V | tail -1)"
  if [[ "$cmp" == "$INSTALLED_VER" && "$INSTALLED_VER" == "$LATEST_STABLE" ]]; then
    emit "latest-stable" "ok" "v${LATEST_STABLE}" "(up to date)"
  elif [[ "$cmp" == "$LATEST_STABLE" ]]; then
    emit "latest-stable" "warn" "v${LATEST_STABLE}" "→ Run /ren:update to install. See CHANGELOG for what's new."
  else
    emit "latest-stable" "warn" "v${LATEST_STABLE} (installed is ahead)" "→ Local version exceeds latest published — likely dogfood / RC. Run /ren:doctor --post-update if you just updated."
  fi
fi

# Fetch RC if user is on RC channel
if [[ "$RC_CHANNEL" == "true" ]]; then
  RC_REPO="${ORG}/ren-os-rc"
  LATEST_RC=""
  if RC_PJ="$(timeout 8 gh api "repos/${RC_REPO}/contents/.claude-plugin/plugin.json" --jq '.content' 2>/dev/null)"; then
    if [[ -n "$RC_PJ" ]]; then
      LATEST_RC="$(echo "$RC_PJ" | base64 -d 2>/dev/null | grep -oE '"version"\s*:\s*"[^"]+"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')"
    fi
  fi
  if [[ -n "$LATEST_RC" ]]; then
    emit "latest-rc" "ok" "v${LATEST_RC}" "(subscribed via ren-os-rc)"
  else
    emit "latest-rc" "skip" "" "(no RC published or unreachable)"
  fi
  emit "channel" "ok" "rc (subscribed)" ""
else
  emit "latest-rc" "skip" "" "(subscribe to ren-os-rc to receive release candidates)"
  emit "channel" "ok" "stable" ""
fi

exit 0
