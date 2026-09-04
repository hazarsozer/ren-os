#!/usr/bin/env bash
# run-hook.sh — resolve a Python interpreter and exec a RenOS hook script.
#
# hooks.json's `command` strings run under Git Bash on native Windows (Claude
# Code shells out to bash there too), but they hardcoded `python3`, which is
# usually `python` or `py -3` on a stock Windows PATH. This launcher tries,
# in order: $REN_HOOK_PYTHON (if set and executable), python3, python, `py
# -3` (only if `py` exists). If none is found it fails OPEN — a missing
# interpreter must never block tool use — by printing `{}` (a harmless
# response for any hook type) to stdout, a one-line diagnostic to stderr,
# and exiting 0.
#
# Must run on macOS bash 3.2 and Git Bash: no bash-4-only features
# (mapfile/readarray, associative arrays, etc.) — see
# scripts/lint-shell-portability.py.
#
# Usage: run-hook.sh <absolute-path-to-hook.py>
set -eu

script_path="$1"

if [ -n "${REN_HOOK_PYTHON:-}" ] && [ -x "${REN_HOOK_PYTHON}" ]; then
  exec "${REN_HOOK_PYTHON}" "$script_path"
fi

if command -v python3 >/dev/null 2>&1; then
  exec python3 "$script_path"
fi

if command -v python >/dev/null 2>&1; then
  exec python "$script_path"
fi

if command -v py >/dev/null 2>&1; then
  exec py -3 "$script_path"
fi

echo '{}'
echo "ren-hook: no python interpreter on PATH (python3/python/py)" 1>&2
exit 0
