---
title: "Claude Code CLI flag availability watch list"
type: skill-reference
parent_skill: sf-improve-skill
version: 0.1.0
date: 2026-05-28
last-cc-version-verified: "2.1.154"
verification-source: "hooks/wake-up/CC_API_NOTES.md Appendix A (verbatim claude --help output)"
---

# CC CLI flag watch list

This document tracks Claude Code CLI flags that **`/ren:improve-skill` would like to use** but which either don't exist yet, only work in restricted contexts, or have behaviors we want to monitor across CC releases. When a flag changes status, this doc gets the update and the `/ren:improve-skill` pre-flight check follows.

**Re-verify on every CC release** by running `claude --help` and diffing against `hooks/wake-up/CC_API_NOTES.md Appendix A`. When `/ren:doctor` checks CC version drift, it should also nudge to re-verify this watch list.

## Watch list

### `--max-turns N`

**Status**: ❌ **NOT AVAILABLE** in CC `2.1.154` (verified 2026-05-28 against `claude --help`, `claude agents --help`, `claude project --help`, `claude doctor --help` — all null results).

**History**:
- ADR-012's original 2026-05-28 amendment claimed `--max-turns` existed as a CC-native safety primitive (sourced from an "official-docs-validation pass" that apparently scanned the wrong doc surface)
- lifecycle-2's §1.1 verification on 2026-05-28 disproved this empirically
- ADR-012 amendment-of-correction filed same day, dropping `--max-turns` from the autonomous-mode pre-flight requirement set
- See ADR-012 `amendments:` block + `hooks/wake-up/CC_API_NOTES.md` §12 + Appendix A.3 for the verification trail

**What we use instead**:
- `--max-iterations N` (our framework cap; canonical outer-loop bound)
- `--max-budget-usd N` (CC-native; print-mode only — bounds dollar runaway in autonomous runs)
- Shadow turn-tracking: sum responses across all inner sub-runs; abort when count exceeds an optional `--max-turns-shadow N` flag (our framework — NOT a CC flag)

**Adoption criteria when/if it returns**:
- Verify in `claude --help` on a fresh CC install
- Verify it works in non-print mode (i.e., interactive sub-runs)
- Verify behavior on hit: error exit vs graceful stop
- Update `/ren:improve-skill` pre-flight to require it in autonomous mode (alongside `--max-iterations` + `--max-budget-usd`)
- Drop the shadow turn-counter (or keep it as belt-and-suspenders — TBD)

### `--max-budget-usd N`

**Status**: ✅ **AVAILABLE** but **`--print` mode only** (verified 2026-05-28 — see `CC_API_NOTES.md` Appendix A.2).

**Verbatim help text**:
```
  --max-budget-usd <amount>             Maximum dollar amount to spend on API
                                        calls (only works with --print)
```

**Implication for `/ren:improve-skill`**:
- Inner sub-runs (the change-proposal LLM calls) ARE in print mode — `claude --bare --print --max-budget-usd $REMAINING`. ✅ Works there.
- The top-level `/ren:improve-skill` invocation may NOT be in print mode (the friend wants interactive UX). For that level, we shadow-track budget using `usage.input_tokens + usage.output_tokens` × model pricing.

**Adoption criteria when it expands to non-print mode**:
- Verify `claude --max-budget-usd $X` works in interactive mode
- Drop our shadow-budget tracker (or keep as belt-and-suspenders — TBD)
- Update `references/budget-tracking.md` to reflect the new mechanism

### `--bare`

**Status**: ✅ **AVAILABLE** (verified 2026-05-28 — see `CC_API_NOTES.md` Appendix A.1).

**Verbatim help text** (excerpt):
```
  --bare                                Minimal mode: skip hooks, LSP, plugin
                                        sync, attribution, auto-memory, ...
```

**Implication**: inner sub-runs use `--bare` to skip our own framework overhead (hooks, plugin sync, CLAUDE.md) — the change-proposal LLM shouldn't reload the entire framework's context just to suggest a one-line edit. This matches ADR-012's design intent.

**Watch for**: if `--bare`'s exclusion list changes (e.g., it starts auto-loading skills), audit our inner-sub-run prompts for assumptions. Track CHANGELOG entries that mention "bare" in CC release notes.

### `--exclude-dynamic-system-prompt-sections`

**Status**: ✅ **AVAILABLE** (verified 2026-05-28 — see `CC_API_NOTES.md` Appendix A.4).

**Relevance to `/ren:improve-skill`**: not directly used, but documented here because **it's the load-bearing evidence for ADR-008's design** (CC's own pattern of moving content from cacheable system-prompt prefix into the first user message). Any drift in this flag's behavior signals broader cache-architecture changes we'd need to react to in the wake-up hook.

**Watch for**: deprecation notices; behavior changes in cache-reuse measurements; renaming.

### `--include-hook-events`

**Status**: ✅ **AVAILABLE** with `--output-format=stream-json` (verified 2026-05-28 — see `CC_API_NOTES.md` Appendix A.5).

**Relevance**: used by lifecycle plan §2 cache-verification infrastructure (Task #11). Not directly used by `/ren:improve-skill` itself but lifecycle-2 owns both.

**Watch for**: stream-json format changes; new hook events that affect our cache-verification collector.

### `--max-runtime-seconds N` (hypothetical)

**Status**: ❌ **NOT AVAILABLE**.

**Why on the list**: a wall-clock limit would complement `--max-iterations` (counts) + `--max-budget-usd` (dollars) for autonomous runs. Currently we rely on OS-level `timeout` wrappers if friends want a wall-clock bound.

**Adoption criteria when/if added**: same pattern as `--max-turns` — verify, update pre-flight, optionally drop OS-level wrapper.

## Update protocol

When a flag's status changes:

1. Run `claude --version` and update the `last-cc-version-verified` frontmatter field
2. Capture the verbatim `claude --help` block (per the CC_API_NOTES.md Appendix A discipline)
3. Update the relevant section of this doc
4. If a status change unlocks new safety guarantees, propose an amendment to ADR-012 documenting the new pre-flight semantics
5. If a status change forces fallback to alternative safety mechanisms, this doc becomes the diagnostic for `/ren:doctor`

## How `/ren:improve-skill` consumes this

Pre-flight code:

```python
# Pseudocode
def pre_flight_autonomous(args) -> None:
    if not args.autonomous:
        return  # interactive mode has different requirements

    # The two locked requirements from this watch list:
    if not args.max_iterations:
        fail("--autonomous requires --max-iterations N. See cc-flag-watch.md.")
    if not args.max_budget_usd:
        fail("--autonomous requires --max-budget-usd N. See cc-flag-watch.md.")

    # If cc-flag-watch.md says --max-turns is now available, this fail() gets added:
    # if not args.max_turns:
    #     fail("--autonomous requires --max-turns N (CC ships this now).")
```

The pre-flight is dumb — it just reflects the current watch list. The intelligence lives in this document.
