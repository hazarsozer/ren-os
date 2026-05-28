#!/usr/bin/env bash
# apply-migration.sh — dispatch a single migration against a single page.
#
# Usage:
#   apply-migration.sh <migration-dir> <page-path>
#     Reads migration-dir/README.md to determine mode (scripted | LLM-driven | hybrid).
#     Dispatches to migrate.sh and/or returns the migrate.md prompt for the caller
#     to invoke Claude (LLM-driven step).
#
# Env (must be set by caller):
#   SF_WIKI_ROOT       — friend's wiki root
#   SF_SNAPSHOT_DIR    — pre-migration snapshot directory
#
# Output:
#   stdout = "MODE=scripted" / "MODE=hybrid" / "MODE=llm" followed by the
#            execution result. For LLM-driven steps, output includes "PROMPT="
#            with the absolute path to migrate.md so the caller can invoke Claude.
#
# Exit:
#   0   migration applied successfully (scripted) OR LLM step required (caller proceeds)
#   1   migration script failed
#   2   bad inputs / unknown mode
#
# Important: this script does NOT invoke Claude itself. The caller (sf-update's
# MIGRATING state machine, driven by SKILL.md) handles the LLM step.

set -uo pipefail

MIG_DIR="${1:-}"
PAGE="${2:-}"

if [[ -z "$MIG_DIR" || ! -d "$MIG_DIR" ]]; then
  echo "ERROR: migration dir not found: $MIG_DIR" >&2
  exit 2
fi
if [[ -z "$PAGE" || ! -f "$PAGE" ]]; then
  echo "ERROR: page not found: $PAGE" >&2
  exit 2
fi

# Refuse to operate on the _template directory (it's not a real migration)
if [[ "$(basename "$MIG_DIR")" == "_template" ]]; then
  echo "ERROR: _template is not a real migration; do not invoke" >&2
  exit 2
fi

if [[ -z "${SF_WIKI_ROOT:-}" || -z "${SF_SNAPSHOT_DIR:-}" ]]; then
  echo "ERROR: SF_WIKI_ROOT and SF_SNAPSHOT_DIR must be set" >&2
  exit 2
fi

README="$MIG_DIR/README.md"
SCRIPT="$MIG_DIR/migrate.sh"
PROMPT="$MIG_DIR/migrate.md"

# Parse mode from README.md. We look for a line starting with "## Mode:" (case insensitive).
MODE=""
if [[ -f "$README" ]]; then
  # Match e.g. "## Mode: scripted" / "## Mode: LLM-driven" / "## Mode: hybrid"
  MODE_LINE="$(grep -iE '^## mode:' "$README" | head -1 || true)"
  case "$(echo "$MODE_LINE" | tr '[:upper:]' '[:lower:]')" in
    *scripted*) MODE="scripted" ;;
    *llm*) MODE="llm" ;;
    *hybrid*) MODE="hybrid" ;;
  esac
fi

# Fall back: if migrate.sh exists and migrate.md does not, assume scripted.
if [[ -z "$MODE" ]]; then
  if [[ -f "$SCRIPT" && ! -f "$PROMPT" ]]; then MODE="scripted"
  elif [[ ! -f "$SCRIPT" && -f "$PROMPT" ]]; then MODE="llm"
  elif [[ -f "$SCRIPT" && -f "$PROMPT" ]]; then MODE="hybrid"
  else
    echo "ERROR: no migrate.sh OR migrate.md in $MIG_DIR" >&2
    exit 2
  fi
fi

echo "MODE=$MODE"
echo "MIGRATION=$(basename "$MIG_DIR")"
echo "PAGE=$PAGE"

case "$MODE" in
  scripted)
    if [[ ! -x "$SCRIPT" ]]; then
      echo "ERROR: $SCRIPT not executable" >&2
      exit 2
    fi
    # Run the script. Pass page path as $1; env vars provide context.
    if SCRIPT_OUT="$(SF_WIKI_ROOT="$SF_WIKI_ROOT" SF_SNAPSHOT_DIR="$SF_SNAPSHOT_DIR" "$SCRIPT" "$PAGE" 2>&1)"; then
      echo "RESULT=ok"
      echo "OUTPUT=$SCRIPT_OUT"
      exit 0
    else
      RC=$?
      echo "RESULT=fail" >&2
      echo "OUTPUT=$SCRIPT_OUT" >&2
      exit 1
    fi
    ;;

  hybrid)
    # Run scripted first, then signal the caller to run the LLM prompt.
    if [[ -x "$SCRIPT" ]]; then
      if SCRIPT_OUT="$(SF_WIKI_ROOT="$SF_WIKI_ROOT" SF_SNAPSHOT_DIR="$SF_SNAPSHOT_DIR" "$SCRIPT" "$PAGE" 2>&1)"; then
        echo "RESULT=script-ok"
        echo "OUTPUT=$SCRIPT_OUT"
      else
        RC=$?
        echo "RESULT=script-fail" >&2
        echo "OUTPUT=$SCRIPT_OUT" >&2
        exit 1
      fi
    fi
    if [[ -f "$PROMPT" ]]; then
      echo "PROMPT=$PROMPT"
      echo "RESULT=needs-llm"
    else
      echo "RESULT=ok"
    fi
    exit 0
    ;;

  llm)
    if [[ ! -f "$PROMPT" ]]; then
      echo "ERROR: $PROMPT not found" >&2
      exit 2
    fi
    echo "PROMPT=$PROMPT"
    echo "RESULT=needs-llm"
    exit 0
    ;;

  *)
    echo "ERROR: unknown mode: $MODE" >&2
    exit 2
    ;;
esac
