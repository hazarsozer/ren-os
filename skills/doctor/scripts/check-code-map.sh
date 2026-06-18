#!/usr/bin/env bash
# Read-only CODE-MAP check: is the lean-ctx engine available?
set -uo pipefail

echo "CODE-MAP"
if command -v lean-ctx >/dev/null 2>&1; then
  VER="$(lean-ctx --version 2>/dev/null | head -1)"
  echo "  lean-ctx: ✅ ${VER:-present}  (/ren:code-map available)"
else
  echo "  lean-ctx: ⚠️  not installed  (/ren:code-map unavailable until installed)"
fi
exit 0
