#!/usr/bin/env bash
# check-backup.sh — sf-doctor BACKUP section
#
# Output: `KEY|STATUS|VALUE|HINT`
# Keys: wiki-remote, last-commit, tarball
#
# Side effects: NONE. Reads .git/config + tarballs dir.

set -uo pipefail

emit() { printf '%s|%s|%s|%s\n' "$1" "$2" "${3:-}" "${4:-}"; }

WIKI_ROOT="${CLAUDE_PLUGIN_OPTION_WIKIROOT:-$HOME/.startup-framework/wiki}"
TARBALL_DIR="${HOME}/.startup-framework/backups"

if [[ ! -d "$WIKI_ROOT" ]]; then
  emit "wiki-remote" "skip" "" "(wiki not present; check-plugins.sh already reported)"
  exit 0
fi

# ──────────────────────────────────────────────────────────────────────
# Wiki git remote
# ──────────────────────────────────────────────────────────────────────
if [[ ! -d "$WIKI_ROOT/.git" ]]; then
  emit "wiki-remote" "warn" "wiki is not a git repo" "→ /ren:backup --setup <your-private-repo-url> initialises git + adds remote"
  emit "last-commit" "skip" "" ""
else
  cd "$WIKI_ROOT" || exit 0

  REMOTE_URL="$(git config --get remote.origin.url 2>/dev/null || echo '')"
  LAST_COMMIT_TS="$(git log -1 --format=%ct 2>/dev/null || echo '0')"
  NOW_TS="$(date +%s)"
  if [[ "$LAST_COMMIT_TS" -gt 0 ]]; then
    DAYS_SINCE=$(( (NOW_TS - LAST_COMMIT_TS) / 86400 ))
  else
    DAYS_SINCE=999
  fi

  AHEAD=0
  if [[ -n "$REMOTE_URL" ]]; then
    AHEAD="$(git rev-list --count @{upstream}..HEAD 2>/dev/null || git rev-list --count HEAD 2>/dev/null || echo '?')"
  else
    AHEAD="$(git rev-list --count HEAD 2>/dev/null || echo '?')"
  fi

  if [[ -z "$REMOTE_URL" ]]; then
    if [[ "$DAYS_SINCE" -gt 7 ]]; then
      emit "wiki-remote" "error" "not configured AND >7d since last commit" "→ ⚠️⚠️ Configure a wiki backup before you lose context — it would be hard to reconstruct. /ren:backup --setup <your-private-repo-url>"
    else
      emit "wiki-remote" "warn" "not configured" "→ Recommend: /ren:backup --setup <your-private-repo-url>"
    fi
  else
    # Check if remote is reachable (last push status from cached HEAD)
    if git rev-parse @{upstream} >/dev/null 2>&1; then
      emit "wiki-remote" "ok" "$REMOTE_URL" ""
    else
      emit "wiki-remote" "warn" "$REMOTE_URL (upstream not tracked)" "→ git push -u origin main"
    fi
  fi

  if [[ "$LAST_COMMIT_TS" -gt 0 ]]; then
    # Format duration
    if [[ "$DAYS_SINCE" -eq 0 ]]; then
      HOURS=$(( (NOW_TS - LAST_COMMIT_TS) / 3600 ))
      DUR="${HOURS}h ago"
    elif [[ "$DAYS_SINCE" -lt 7 ]]; then
      DUR="${DAYS_SINCE}d ago"
    else
      WEEKS=$(( DAYS_SINCE / 7 ))
      DUR="${WEEKS}w ago"
    fi
    if [[ -n "$REMOTE_URL" ]]; then
      emit "last-commit" "ok" "${DUR}, ${AHEAD} commit(s) ahead of remote" ""
    else
      emit "last-commit" "ok" "${DUR}, ${AHEAD} commit(s) total (no remote)" ""
    fi
  else
    emit "last-commit" "warn" "no commits yet" "→ git add -A && git commit -m 'initial wiki state' (or /ren:backup)"
  fi
fi

# ──────────────────────────────────────────────────────────────────────
# Tarball backups
# ──────────────────────────────────────────────────────────────────────
if [[ -d "$TARBALL_DIR" ]]; then
  COUNT="$(find "$TARBALL_DIR" -maxdepth 1 -name 'wiki-*.tar.gz' -type f 2>/dev/null | wc -l)"
  if [[ "$COUNT" -gt 0 ]]; then
    NEWEST_FILE="$(find "$TARBALL_DIR" -maxdepth 1 -name 'wiki-*.tar.gz' -type f -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | awk '{print $2}')"
    NEWEST_TS=$(stat -c %Y "$NEWEST_FILE" 2>/dev/null || echo 0)
    NEWEST_DAYS=$(( ($(date +%s) - NEWEST_TS) / 86400 ))
    emit "tarball" "ok" "${COUNT} in ${TARBALL_DIR} (newest: ${NEWEST_DAYS}d ago)" ""
  fi
fi
# If no tarballs: emit nothing for this key (the section just omits the line)

exit 0
