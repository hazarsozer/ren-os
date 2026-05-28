#!/usr/bin/env bash
# check-env.sh — sf-doctor ENVIRONMENT section
#
# Output: lines of the form `KEY|STATUS|VALUE|HINT` where:
#   KEY    = stable identifier (claude-code, node, git, gh, claude-auth, os, anthropic-key, upstash-key, otel, snapshot-retain)
#   STATUS = ok | warn | error | skip
#   VALUE  = human-readable value or empty
#   HINT   = remediation text or empty (used only when STATUS != ok)
#
# Side effects: NONE. Read-only checks of installed binaries + env vars + plugin userConfig.
# Timeout: 10s (enforced by SKILL.md orchestrator).

set -uo pipefail

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────
emit() {
  # KEY|STATUS|VALUE|HINT
  printf '%s|%s|%s|%s\n' "$1" "$2" "${3:-}" "${4:-}"
}

# version_ge a b → returns 0 if a >= b in strict semver order, else 1
version_ge() {
  # Trim leading 'v' if present
  local a="${1#v}" b="${2#v}"
  printf '%s\n%s\n' "$b" "$a" | sort -V -C 2>/dev/null
}

# ──────────────────────────────────────────────────────────────────────
# Claude Code
# ──────────────────────────────────────────────────────────────────────
if command -v claude >/dev/null 2>&1; then
  # `claude --version` outputs "X.Y.Z (Claude Code)" — extract the semver triple
  CC_VER="$(claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
  CC_VER="${CC_VER:-unknown}"

  # Surface ~/.claude/ symlink target if it's a symlink (per lifecycle-2's heads-up about
  # dotfiles-managed configs). Helps friends debug "my hook isn't where I expected".
  if [[ -L "$HOME/.claude" ]]; then
    CLAUDE_TARGET="$(readlink -f "$HOME/.claude" 2>/dev/null)"
    emit "claude-config" "ok" "~/.claude → ${CLAUDE_TARGET} (symlinked)" ""
  elif [[ -d "$HOME/.claude" ]]; then
    emit "claude-config" "ok" "~/.claude (regular directory)" ""
  fi
  CC_MIN="1.0.33"
  if version_ge "$CC_VER" "$CC_MIN"; then
    emit "claude-code" "ok" "v${CC_VER} (≥ ${CC_MIN} required)" ""
  else
    emit "claude-code" "error" "v${CC_VER} (≥ ${CC_MIN} required)" "→ Update Claude Code: https://docs.claude.com/en/docs/claude-code"
  fi
else
  emit "claude-code" "error" "not found" "→ Install: https://docs.claude.com/en/docs/claude-code"
fi

# ──────────────────────────────────────────────────────────────────────
# Node.js
# ──────────────────────────────────────────────────────────────────────
if command -v node >/dev/null 2>&1; then
  NODE_VER="$(node --version 2>/dev/null | sed 's/^v//')"
  NODE_MIN="22.5.0"
  if version_ge "$NODE_VER" "$NODE_MIN"; then
    emit "node" "ok" "v${NODE_VER} (≥ ${NODE_MIN} required)" ""
  else
    emit "node" "error" "v${NODE_VER} (≥ ${NODE_MIN} required)" "→ Install Node ${NODE_MIN}+: https://nodejs.org/ or use nvm/fnm/volta"
  fi
else
  emit "node" "error" "not found" "→ Install Node ≥ 22.5: https://nodejs.org/"
fi

# ──────────────────────────────────────────────────────────────────────
# git
# ──────────────────────────────────────────────────────────────────────
if command -v git >/dev/null 2>&1; then
  GIT_VER="$(git --version 2>/dev/null | awk '{print $3}')"
  emit "git" "ok" "v${GIT_VER}" ""
else
  emit "git" "error" "not found" "→ Install git: https://git-scm.com/downloads"
fi

# ──────────────────────────────────────────────────────────────────────
# gh CLI
# ──────────────────────────────────────────────────────────────────────
if command -v gh >/dev/null 2>&1; then
  GH_VER="$(gh --version 2>/dev/null | head -1 | awk '{print $3}')"
  if gh auth status >/dev/null 2>&1; then
    GH_USER="$(gh api user --jq .login 2>/dev/null || echo 'unknown')"
    emit "gh" "ok" "v${GH_VER} (authenticated as ${GH_USER})" ""
  else
    emit "gh" "warn" "v${GH_VER} (NOT authenticated)" "→ Run: gh auth login"
  fi
else
  emit "gh" "error" "not found" "→ Install: https://cli.github.com/  |  apt install gh  |  brew install gh"
fi

# ──────────────────────────────────────────────────────────────────────
# claude auth
# ──────────────────────────────────────────────────────────────────────
if command -v claude >/dev/null 2>&1; then
  if claude auth status >/dev/null 2>&1; then
    CC_AUTH_EMAIL="$(claude auth status 2>/dev/null | grep -oE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]+' | head -1)"
    emit "claude-auth" "ok" "logged in${CC_AUTH_EMAIL:+ (}${CC_AUTH_EMAIL}${CC_AUTH_EMAIL:+)}" ""
  else
    emit "claude-auth" "error" "NOT logged in" "→ Run: claude auth login"
  fi
else
  emit "claude-auth" "skip" "" "(claude-code not found; checked above)"
fi

# ──────────────────────────────────────────────────────────────────────
# OS
# ──────────────────────────────────────────────────────────────────────
OS_KERNEL="$(uname -s 2>/dev/null || echo unknown)"
OS_VER="$(uname -r 2>/dev/null || echo unknown)"
OS_DISTRO=""
if [[ -f /etc/os-release ]]; then
  OS_DISTRO="$(. /etc/os-release && echo "${PRETTY_NAME:-}")"
fi
emit "os" "ok" "${OS_KERNEL} ${OS_VER}${OS_DISTRO:+ (${OS_DISTRO})}" ""

# ──────────────────────────────────────────────────────────────────────
# ANTHROPIC_API_KEY
# ──────────────────────────────────────────────────────────────────────
if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  emit "anthropic-key" "ok" "set" ""
else
  emit "anthropic-key" "error" "not set" "→ export ANTHROPIC_API_KEY=sk-ant-... in your shell rc (see console.anthropic.com/settings/keys)"
fi

# ──────────────────────────────────────────────────────────────────────
# Upstash (context7) API key
# ──────────────────────────────────────────────────────────────────────
# context7 expects UPSTASH_CONTEXT7_API_KEY (per ADR-015 amendment)
if [[ -n "${UPSTASH_CONTEXT7_API_KEY:-}" ]]; then
  emit "upstash-key" "ok" "set" ""
else
  emit "upstash-key" "warn" "not set" "→ context7 plugin will not work without it. /sf:install Stage 1 OAuth flow can generate it."
fi

# ──────────────────────────────────────────────────────────────────────
# OpenTelemetry (optional per ADR-015 Stage 6)
# ──────────────────────────────────────────────────────────────────────
if [[ -n "${OTEL_EXPORTER_OTLP_ENDPOINT:-}" ]]; then
  emit "otel" "ok" "${OTEL_EXPORTER_OTLP_ENDPOINT}" ""
else
  emit "otel" "skip" "" "no OTLP endpoint configured (optional)"
fi

# ──────────────────────────────────────────────────────────────────────
# Snapshot retain (from userConfig — passed as env var by CC)
# ──────────────────────────────────────────────────────────────────────
SNAP_RETAIN="${CLAUDE_PLUGIN_OPTION_SNAPSHOTRETAIN:-3}"
emit "snapshot-retain" "ok" "${SNAP_RETAIN}" "(configurable via userConfig.snapshotRetain)"

exit 0
