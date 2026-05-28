#!/usr/bin/env bash
# probe.sh — single-session cache-verification probe runner
#
# Per the ADR-008 cache-preservation verification plan (lifecycle plan §2):
# runs ONE Claude Code session with a fixed first-prompt; captures the per-turn
# usage metrics via --include-hook-events --output-format=stream-json; writes
# the raw JSON-L stream to a per-session file for the collect.py scraper.
#
# Usage:
#   probe.sh ARM SESSION_INDEX OUTPUT_DIR [--cooldown SECONDS] [--dry-run]
#
# ARM is one of: A | B | C
#   - A: baseline. No wake-up hook registered.
#   - B: hook registered, emits a FIXED 3K-token additionalContext block.
#   - C: hook registered, emits per-session VARYING content.
#
# The actual hook registration is the caller's job (typically via a per-arm
# settings.json template + the SF_PROBE_ARM env var that the experimental
# wake-up hook reads to decide what to emit).
#
# Output: $OUTPUT_DIR/probe-<arm>-<session>-<ISO-timestamp>.jsonl
#
# Per team-lead's refinement: capture BOTH turn 1 and turn 2 metrics; cache
# benefit shows turn 2+. The probe sends a deterministic 2-turn conversation:
# the first prompt elicits one response; a fixed follow-up triggers the second.
#
# Never run more than once per 5 minutes against the same Claude Code
# subscription tier (sub-agent cache TTL is 5 minutes; subscription TTL is 1
# hour). The --cooldown flag enforces this between calls in a batch.

set -euo pipefail

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------

ARM="${1:-}"
SESSION_INDEX="${2:-}"
OUTPUT_DIR="${3:-}"
COOLDOWN_SECONDS=0
DRY_RUN=0

shift 3 2>/dev/null || true

while [[ $# -gt 0 ]]; do
    case "$1" in
        --cooldown)
            COOLDOWN_SECONDS="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        *)
            echo "Unknown flag: $1" >&2
            exit 2
            ;;
    esac
done

if [[ -z "$ARM" || -z "$SESSION_INDEX" || -z "$OUTPUT_DIR" ]]; then
    echo "Usage: $0 ARM SESSION_INDEX OUTPUT_DIR [--cooldown SECONDS] [--dry-run]" >&2
    echo "  ARM = A | B | C" >&2
    exit 2
fi

if [[ "$ARM" != "A" && "$ARM" != "B" && "$ARM" != "C" ]]; then
    echo "ARM must be one of: A, B, C (got: $ARM)" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

ISO_TS=$(date -u +"%Y-%m-%dT%H-%M-%SZ")
OUTFILE="${OUTPUT_DIR}/probe-${ARM}-${SESSION_INDEX}-${ISO_TS}.jsonl"

# The fixed first prompt — same across every session of every arm.
# Designed to be cheap (short response expected) and prompt-cacheable.
PROMPT_1="What is 2+2? Answer in one word."
# Fixed follow-up to trigger turn 2 (where cache benefit becomes observable).
PROMPT_2="And 3+3?"

# CC flags chosen for the experiment:
#   --print              : non-interactive
#   --output-format=stream-json : machine-readable per-turn usage data
#   --include-hook-events: capture SessionStart hook firing for diagnostics
CLAUDE_FLAGS=(
    "--print"
    "--output-format=stream-json"
    "--include-hook-events"
    "--verbose"
)

# Arm-specific env vars the experimental hook reads
export SF_PROBE_ARM="$ARM"

# ---------------------------------------------------------------------------
# Cooldown (only when not dry-running)
# ---------------------------------------------------------------------------

if [[ "$COOLDOWN_SECONDS" -gt 0 && "$DRY_RUN" -eq 0 ]]; then
    echo "probe: cooldown ${COOLDOWN_SECONDS}s before session ${SESSION_INDEX} (arm ${ARM})" >&2
    sleep "$COOLDOWN_SECONDS"
fi

# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------

if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "DRY-RUN: would run:"
    echo "  SF_PROBE_ARM=$ARM claude ${CLAUDE_FLAGS[*]} '${PROMPT_1}'"
    echo "  (then follow-up: '${PROMPT_2}')"
    echo "  output → $OUTFILE"
    exit 0
fi

mkdir -p "$OUTPUT_DIR"

# Run the two-turn probe. We pipe both prompts via stdin in stream-json input
# mode for a multi-turn session in a single process.
#
# The implementation here is intentionally minimal: it captures everything
# Claude Code emits on stdout to $OUTFILE; collect.py then walks the JSON-L
# to extract usage records. Stderr is captured to a sidecar file for
# diagnostics.

ERRFILE="${OUTFILE}.stderr"
echo "probe: arm=${ARM} session=${SESSION_INDEX} → ${OUTFILE}" >&2

# Two prompts in series; CC's stream-json output captures both turns.
# Use a here-doc for clean multi-prompt input.
{
    echo "$PROMPT_1"
    echo "$PROMPT_2"
} | claude "${CLAUDE_FLAGS[@]}" \
    --input-format=text \
    > "$OUTFILE" \
    2> "$ERRFILE" || {
        echo "probe: claude exited non-zero (see $ERRFILE for stderr)" >&2
        # Don't fail the script — partial captures are still analyzable;
        # collect.py will report the absence of expected fields.
    }

echo "probe: arm=${ARM} session=${SESSION_INDEX} complete" >&2
