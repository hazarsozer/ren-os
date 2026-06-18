#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$(PATH="/nonexistent" /bin/bash "$DIR/check-code-map.sh" 2>&1 || true)"
echo "$OUT" | grep -qi "code-map" || { echo "FAIL: no CODE-MAP section"; exit 1; }
echo "$OUT" | grep -qiE "not installed|unavailable" || { echo "FAIL: should report absence"; exit 1; }
echo "PASS"
