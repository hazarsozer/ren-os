#!/usr/bin/env bash
# experimental-hook.sh — Probe-only SessionStart hook for cache-verification arms B + C.
#
# Per the lifecycle plan §2 experiment design:
#   - Arm A: NO hook registered (use --bare or empty probe-settings)
#   - Arm B: this hook with SF_PROBE_ARM=B → emits FIXED ~3K-char additionalContext
#   - Arm C: this hook with SF_PROBE_ARM=C → emits VARYING content per session
#
# Hooks emit JSON to stdout matching the SessionStart contract documented in
# hooks/wake-up/CC_API_NOTES.md §4. The `additionalContext` field gets injected
# into the conversation as a system-reminder, which is what ADR-008 needs to
# verify preserves the cacheable system-prompt prefix.
#
# NOT a production hook. Lives under verify/ to make that clear.

set -euo pipefail

ARM="${SF_PROBE_ARM:-}"

# Fixed 3K-char payload for arm B — deterministic so any cache differences vs
# arm A must come from the hook MECHANISM itself, not from content variance.
# (~3000 chars chosen to mirror the realistic v1 wiki-context size we expect
# the production hook to emit.)
FIXED_BLOCK_3K="\
[wake-up-verify arm B fixed content]
This is a deterministic 3KB additionalContext block emitted by the
experimental cache-verification hook. The content is identical across every
session of arm B so the only variable between A and B is hook PRESENCE.

If ADR-008's design is correct, the prompt-cache prefix should be preserved
regardless of this content's presence — i.e., cache_read_input_tokens at
turn 2 should be statistically indistinguishable between arm A (no hook)
and arm B (this hook firing with fixed content).

We pad to ~3K characters with deterministic lorem-ipsum-style text below to
realistically mirror v1 wiki-context payload sizes:

Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod
tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam,
quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo
consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse
cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat
non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.

Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium
doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore
veritatis et quasi architecto beatae vitae dicta sunt explicabo. Nemo enim
ipsam voluptatem quia voluptas sit aspernatur aut odit aut fugit, sed quia
consequuntur magni dolores eos qui ratione voluptatem sequi nesciunt.

Neque porro quisquam est, qui dolorem ipsum quia dolor sit amet, consectetur,
adipisci velit, sed quia non numquam eius modi tempora incidunt ut labore
et dolore magnam aliquam quaerat voluptatem. Ut enim ad minima veniam, quis
nostrum exercitationem ullam corporis suscipit laboriosam, nisi ut aliquid
ex ea commodi consequatur.

Quis autem vel eum iure reprehenderit qui in ea voluptate velit esse quam
nihil molestiae consequatur, vel illum qui dolorem eum fugiat quo voluptas
nulla pariatur. At vero eos et accusamus et iusto odio dignissimos ducimus
qui blanditiis praesentium voluptatum deleniti atque corrupti quos dolores
et quas molestias excepturi sint occaecati cupiditate non provident.

[end wake-up-verify arm B fixed content]"

# Varying payload for arm C — same length as B but per-session unique content.
# Tests whether content VARIANCE (the realistic production condition where
# each session's wake-up payload differs) still preserves cache.
VARYING_PREFIX="[wake-up-verify arm C varying content — session epoch ${EPOCHSECONDS:-$(date +%s)}]"

emit_json() {
    # Properly JSON-escape the content via python (stdlib only)
    python3 -c "
import json, sys
content = sys.argv[1]
print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'SessionStart',
        'additionalContext': content,
    }
}))
" "$1"
}

case "$ARM" in
    B)
        emit_json "$FIXED_BLOCK_3K"
        ;;
    C)
        # Append varying prefix to the fixed body so total length matches arm B
        emit_json "${VARYING_PREFIX}
${FIXED_BLOCK_3K}"
        ;;
    A|"")
        # Arm A or unset arm — emit nothing (no additionalContext injection).
        # Returning exit 0 with no JSON output means CC sees no hook output =
        # equivalent to no hook firing.
        :
        ;;
    *)
        echo "experimental-hook.sh: unknown SF_PROBE_ARM=$ARM" >&2
        exit 1
        ;;
esac
