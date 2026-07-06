#!/bin/sh
# scripts/codex_read_proof.sh — Codex read proof (Task 7.2, spec §3.9 A-9,
# exit criterion 5).
#
# "0.2 ships one working proof: Codex reads the project context from the same
# files [AGENTS.md]." This script drives that proof: if the `codex` CLI is on
# PATH, it asks Codex to read AGENTS.md (and the files it links) and answer a
# grounding question, capturing the raw output to
# docs/codex-read-proof-output.txt for a human to review. If `codex` is NOT
# installed, this exits 3 — a distinct, non-zero, non-1 code — so CI treats
# the run as PENDING-HUMAN rather than a failure. The proof needs a real
# Codex install; it cannot be faked, mocked, or silently skipped as a pass.
#
# Usage: scripts/codex_read_proof.sh [target-repo-dir]   (default: .)

set -eu

TARGET_DIR="${1:-.}"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT_FILE="$SCRIPT_DIR/docs/codex-read-proof-output.txt"

if ! command -v codex >/dev/null 2>&1; then
  echo "PENDING-HUMAN: codex CLI not installed — run this script on a machine with Codex; the proof procedure is documented in docs/codex-read-proof.md"
  exit 3
fi

cd "$TARGET_DIR"

if [ ! -f "AGENTS.md" ]; then
  echo "FAIL: no AGENTS.md found in $TARGET_DIR — run lib.portability.agents_surface.write_agents_md first."
  exit 1
fi

PROMPT="Read AGENTS.md and the files it links; then answer: what is this project, and what are its three most important decisions? Cite which linked file each point came from."

codex exec "$PROMPT" >"$OUTPUT_FILE" 2>&1 || true

if [ ! -s "$OUTPUT_FILE" ]; then
  echo "FAIL: codex produced no output — see $OUTPUT_FILE"
  exit 1
fi

# Extract the markdown-link targets AGENTS.md points at, and check whether
# Codex's answer cites at least one of them — the mechanical proxy for "Codex
# actually followed the links" rather than hallucinating an answer.
LINKED_PATHS=$(grep -oE '\([^)]+\)' AGENTS.md 2>/dev/null | tr -d '()' || true)
MATCHED=0
for p in $LINKED_PATHS; do
  BASENAME=$(basename "$p")
  if grep -qF "$BASENAME" "$OUTPUT_FILE"; then
    MATCHED=1
    break
  fi
done

if [ "$MATCHED" -eq 1 ]; then
  echo "PASS: codex output is non-empty and cites at least one file linked from AGENTS.md."
  exit 0
fi

echo "FAIL: codex output is non-empty but cites none of AGENTS.md's linked files — see $OUTPUT_FILE"
exit 1
