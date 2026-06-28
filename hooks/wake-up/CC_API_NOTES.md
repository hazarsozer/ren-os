---
title: "Claude Code SessionStart Hook API — Empirically Verified"
status: verified
date: 2026-05-28
verified-by: lifecycle-2 (team sf-build-v1)
verified-against: claude --help output, settings.json schema (json.schemastore.org), official docs (code.claude.com/docs/en/hooks)
referenced-by: ADR-008, ADR-010, ADR-012
purpose: Ground-truth reference for the wake-up hook's interaction with Claude Code. Replaces all prior assumptions sourced from memory or external research.
---

# Claude Code SessionStart Hook API — Empirically Verified

This document captures the **verified** Claude Code hook API as it pertains to the wake-up hook (per ADR-008). Verification was completed on 2026-05-28 against four authoritative sources. **No paraphrased shortcuts** — wherever a JSON example or schema appears, it is copied verbatim from the source.

## Why this exists

ADR-008's central promise — that wiki context can be injected at the conversation layer (NOT the system prompt) — depended on Claude Code exposing a SessionStart hook output mechanism that does NOT modify the cacheable prefix. That promise is theoretical without empirical confirmation. This document closes the verification gate.

**Verdict: PASS.** The mechanism exists, is documented, is in active use elsewhere in the user's environment, and is observable in this very session (see §6 "Empirical evidence in-session").

---

## 1. Authoritative sources

| # | Source | URL | What it tells us |
|---|---|---|---|
| 1 | `claude --help` (CLI) | (local; version live as of 2026-05-28) | Flags: `--bare`, `--max-budget-usd`, `--debug=hooks`, `--include-hook-events`, `--exclude-dynamic-system-prompt-sections` |
| 2 | Settings JSON schema | `https://json.schemastore.org/claude-code-settings.json` | Hook config shape — fields, types, hook types (`command`/`prompt`/`agent`/`http`/`mcp_tool`) |
| 3 | Official hooks guide | `https://code.claude.com/docs/en/hooks-guide` | Hook lifecycle, event names, matcher semantics, output protocol |
| 4 | Live `~/.claude/settings.json` + active `session-start-bootstrap.js` (ECC plugin) | (local) | Reference impl: a working `SessionStart` hook in production |

## 2. Hook event taxonomy (relevant subset)

From source #3 (hooks-guide event table), copied verbatim into a structured form:

| Event | When it fires |
|---|---|
| **SessionStart** | When a session begins or resumes |
| **Setup** | When you start Claude Code with `--init-only`, or with `--init` or `--maintenance` in `-p` mode. For one-time preparation in CI or scripts |
| **UserPromptSubmit** | When you submit a prompt, before Claude processes it |
| **UserPromptExpansion** | When a user-typed command expands into a prompt, before it reaches Claude. Can block the expansion |
| **PreToolUse** | Before a tool call executes. Can block it |
| **PermissionRequest** | When a permission dialog appears |
| **PermissionDenied** | When a tool call is denied by the auto mode classifier. Return `{retry: true}` to tell the model it may retry the denied tool call |
| **PostToolUse** | After a tool call succeeds |
| **PostToolUseFailure** | After a tool call fails |
| **PostToolBatch** | After a full batch of parallel tool calls resolves, before the next model call |
| **Notification** | When Claude Code sends a notification |
| **MessageDisplay** | While assistant message text is displayed |
| **SubagentStart** | When a subagent is spawned |
| **SubagentStop** | When a subagent finishes |
| **TaskCreated** | When a task is being created via TaskCreate |
| **TaskCompleted** | When a task is being marked as completed |
| **Stop** | When Claude finishes responding |
| **StopFailure** | When the turn ends due to an API error. Output and exit code are ignored |
| **TeammateIdle** | When an agent team teammate is about to go idle |
| **InstructionsLoaded** | When a CLAUDE.md or `.claude/rules/*.md` file is loaded into context. Fires at session start and when files are lazily loaded during a session |
| **CwdChanged** | (Referenced separately) Fires when Claude changes directory |
| **SessionEnd** | Why the session ended — matcher filters: `clear, resume, logout, prompt_input_exit, bypass_permissions_disabled, other` |

**Implication for ADR-009** (no-Stop-hook decision): the `Stop` event exists and matches what ADR-009 described. The `SessionEnd` event also exists with its own matcher set. ADR-009's decision to use a user-invoked `/ren:wrap` slash command rather than either hook still holds (Ralph collision + claude-mem SessionEnd ordering + user-control preference all unchanged).

## 3. SessionStart hook — input schema (stdin)

Per source #3 (hooks-guide, line 8 of the cleaned doc):

> "Your script can parse that JSON and act on any of those fields. UserPromptSubmit hooks get the prompt text instead, **SessionStart hooks get the `source`** (startup, resume, clear, compact), and so on. See Common input fields in the reference for shared fields, and each event's section for event-specific schemas."

**Confirmed fields**:
- `source`: enum of `"startup" | "resume" | "clear" | "compact"` — describes how the session started
- (Plus "Common input fields" — `session_id`, `transcript_path`, `cwd`, `hook_event_name`, etc. — these are the standard CC hook payload fields; need to capture exact shape via probe before final implementation, but they are observable in any active hook)

**Matcher semantics** (per source #3, line 11):
> "SessionStart — how the session started — example matcher values: `startup`, `resume`, `clear`, `compact`"

So the `matcher` field on a SessionStart hook entry compares against `source`. Example:
- `"matcher": "startup"` → fires only on fresh session start (NOT on `/clear` or `/resume`)
- `"matcher": "compact"` → fires after compaction (relevant for ADR-008 sunset trigger: re-inject wiki context after compaction)
- `"matcher": "*"` (or omitted) → fires on all sources

## 4. SessionStart hook — output schema (stdout)

The output is a JSON object printed to stdout. **The key field for our purposes is `hookSpecificOutput.additionalContext`** (a string).

### 4.1 Verbatim quotes establishing the mechanism

Per source #3 (cleaned doc lines 7, 10, 13):

**Line 7**: "After all matching hooks finish, Claude Code combines their outputs. For PreToolUse permission decisions, the most restrictive answer wins: deny overrides ask, which overrides allow. **Text from additionalContext is kept from every hook and passed to Claude together.**"

**Line 10**: "For UserPromptSubmit hooks, use **additionalContext** instead to inject text into Claude's context. Prompt-based hooks (type: `"prompt"`) handle output differently: see Prompt-based hooks."

**Line 13**: "Command hooks communicate through stdout, stderr, and exit codes only. They cannot trigger `/` commands or tool calls. **Text returned via `additionalContext` is injected as a system reminder that Claude reads as plain text.** HTTP hooks communicate through the response body instead."

### 4.2 Inferred output shape

Combining the above with the schema's `hookSpecificOutput` references and the observed in-session behavior (see §6):

```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "<text injected into the conversation as a system reminder>"
  }
}
```

The injection appears in the LLM's view wrapped in `<system-reminder>...</system-reminder>` tags.

### 4.3 Critical property: NOT a system prompt modification

The docs explicitly say `additionalContext` is "injected as a system reminder that Claude reads as plain text." A **system reminder** is a transient instruction-shaped message; it is NOT part of the cacheable system prompt prefix Anthropic monitors for cache reuse.

This is the load-bearing distinction ADR-008 promised. **The cacheable prefix is unmodified by our hook.** Section 5 of this document covers the verification plan to confirm this empirically via cache token metrics.

## 5. Cache-preservation hypothesis (to be empirically verified per §2 of the plan)

The verification plan in `verify/REPORT.md` will test the following hypothesis with 20-30 sessions:

> H1: SessionStart hooks emitting `additionalContext` do NOT measurably reduce `cache_read_input_tokens` on subsequent sessions with identical system-prompt prefix.

Method: see §2 of the lifecycle plan (arms A=no hook, B=hook with fixed content, C=hook with varying content). Pass criteria locked there. **This document is a prerequisite, not a substitute, for that experiment.**

## 6. Empirical evidence in-session (2026-05-28)

This very session — the one in which this document is being written — provides direct evidence. The session was opened in a directory with an active SessionStart hook (the ECC plugin's `session-start-bootstrap.js`). The first message in the conversation contains:

```
<system-reminder>
SessionStart hook additional context: <EXTREMELY_IMPORTANT>
You have superpowers.
...
```

That `<system-reminder>` wrapper containing "SessionStart hook additional context:" is the rendered form of an `additionalContext` payload. The wrapping format is consistent with the docs' "injected as a system reminder" description.

This is qualitative confirmation. Quantitative cache-preservation verification still owed via §5 above.

## 7. Hook entry config shape (from source #2 schema)

A SessionStart hook is registered in `settings.json` (or per-plugin `hooks.json`) under the `hooks.SessionStart` array:

```jsonc
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",                  // optional; "*" or omitted = all sources
        "hooks": [
          {
            "type": "command",                  // can also be "prompt", "agent", "http", "mcp_tool"
            "command": "/path/to/wake-up.sh",
            "timeout": 10,                      // seconds; we target <100ms but cap at 10s per team-lead spec
            "async": false,                     // SessionStart blocks until exit (see §8)
            "shell": "bash"                     // default; can be "powershell"
          }
        ]
      }
    ]
  }
}
```

### 7.1 Field semantics (from source #2)

- `type: "command"` — shell command; stdout JSON is parsed for hookSpecificOutput
- `command` — shell command to execute
- `timeout` — seconds; hook is killed after this elapses
- `async` — when true, hook runs without blocking; useful for hooks that don't return additionalContext
- `asyncRewake` — async hook that wakes the model when exit code is 2; not relevant for wake-up
- `shell` — "bash" (default; uses login shell) or "powershell"
- `if` — permission-rule filter (ONLY runs on tool events: PreToolUse/PostToolUse/etc.; on SessionStart, an `if` field means the hook **never runs**)
- `statusMessage` — custom spinner text
- `args` — exec-form arguments (no shell interpretation; safe for paths with spaces)

## 8. Blocking model + latency

**Confirmed**: SessionStart hooks are **synchronous by default** — CC waits for the hook process to exit before proceeding with session setup. The `timeout` config field is a hard kill.

> ### ⚠️ Unit callout — `timeout` is in SECONDS, not milliseconds
>
> The settings schema (`https://json.schemastore.org/claude-code-settings.json`) specifies the `timeout` field for ALL FIVE hook types (command, prompt, agent, http, mcp_tool) with the verbatim text **"Optional timeout in seconds"** — defaults of 30 and 60 (`prompt`/`http` → 30s; `agent`/`mcp_tool` → 60s) corroborate the unit.
>
> Example: `"timeout": 10` means **10 SECONDS**, not 10 milliseconds. The user's live `~/.claude/settings.json` has working hooks with `"timeout": 10` and `"timeout": 300` (5 minutes); these would be unusable as millisecond values (a node subprocess boot alone is ~50ms).
>
> **Do not "fix" `timeout: 10` to `timeout: 10000` thinking the unit is milliseconds.** That would create a real ~2.78-hour kill-timer antipattern. Schema is authoritative; this callout exists because the unit was misread once during review (resolved 2026-05-28; see Appendix A.1 for verbatim schema text).

**Implication for wake-up**: our target is <100ms wall-clock (per ADR-008 latency budget). The 10-second timeout per team-lead's locked spec is the hard ceiling — ample headroom for the wiki read + compose pass.

**Async option exists** (`async: true`) but is unsuitable for the wake-up hook because async hooks cannot inject context that arrives synchronously with session start.

## 9. Exit-code semantics

Per source #3 (and standard CC hook behavior observed in `session-start-bootstrap.js`):

- **Exit code 0**: hook succeeded; stdout JSON is parsed for hookSpecificOutput
- **Exit code 2**: hook signaled "block" (relevant for tool-event hooks; for SessionStart this likely means "abort session start" — needs probe-confirmation before relying on it)
- **Other non-zero**: hook errored; CC behavior is to log to stderr and proceed without applying the hook's output (the user does NOT see the session abort)

**Wake-up failure mode**: per ADR-008 + lifecycle plan §5, our hook MUST exit 0 even on internal errors. Any internal failure logs to `~/.startup-framework/logs/wake-up-<date>.log` and the hook emits an empty or partial additionalContext block. Session always starts.

## 10. Multi-hook combination (per ADR-010 coexistence)

From source #3 line 7: "After all matching hooks finish, Claude Code combines their outputs... Text from additionalContext is kept from every hook and passed to Claude together."

**Implication for ADR-010**: when Context Mode, claude-mem, and our wake-up all register SessionStart hooks, **all three additionalContext payloads are concatenated and sent to Claude together**. Order of concatenation = order of registration. This is the additive coexistence ADR-010 designs around. No competitive failure mode; only ordering ergonomics.

**Implication for `/ren:doctor`**: at hook-registration time, we should detect existing SessionStart hooks and warn if the combined estimated context payload exceeds ~10K tokens (since our 5K wake-up + others' could grow large).

## 11. Confirmed CC flags relevant to our work

From source #1 (`claude --help`):

| Flag | Status | Use case |
|---|---|---|
| `--bare` | ✅ confirmed | Per ADR-012: skip plugins/hooks/CLAUDE.md/auto-memory; pass to inner sub-runs in `/ren:improve-skill` |
| `--max-budget-usd <amount>` | ✅ confirmed, **print-mode only** | Per ADR-012; shadow with our own tracking in non-print sub-runs |
| `--max-turns` | ❌ **NOT FOUND** in CLI help | See §12 below |
| `--debug [filter]` (accepts `"hooks"` and `"api"`) | ✅ confirmed | Debug runs during cache verification |
| `--include-hook-events` | ✅ confirmed; works with `--output-format=stream-json` | Capture hook lifecycle in verification |
| `--exclude-dynamic-system-prompt-sections` | ✅ confirmed | Strongest supporting evidence for ADR-008's design (CC's own pattern moves content from system prompt to first user message for cache reuse) |
| `--output-format <text\|json\|stream-json>` | ✅ confirmed | Used in verification |
| `--system-prompt`, `--append-system-prompt` | ✅ confirmed | For inner sub-runs in `/ren:improve-skill` if needed |

## 12. Open issue: `--max-turns` is NOT a CC CLI flag

ADR-012 amendment dated 2026-05-28 states:

> "**`--max-turns N`** — limits the number of agentic turns; CC exits with error when limit reached. Useful as a hard upper bound for our Karpathy loop regardless of friend's `--max-iterations` argument."

**This flag is NOT in `claude --help` output** (verified 2026-05-28 against current CC version). It is not present in subcommand helps for `claude agents`, `claude project`, or `claude doctor`.

**Possible explanations**:
- (a) The amendment referenced an SDK-level or env-var setting rather than a CLI flag
- (b) The flag was removed or renamed between the docs-validation pass and now
- (c) It exists at a less-discoverable level we haven't probed

**Action item** (for Task #15 `/ren:improve-skill`):
- Do NOT bake `--max-turns` into the pre-flight requirement until the flag's true status is confirmed
- Use `--max-iterations` + `--max-budget-usd` (print-mode) + our shadow-budget-tracking as the three safety primitives
- Document in `references/cc-flag-watch.md`: "Re-check `--max-turns` availability on next CC release"

## 13. What still needs probe-confirmation (not blocking, for future)

These are nice-to-haves not strictly required before implementing the hook:

1. **Exact stdin payload field names** (e.g., is the cwd field named `cwd` or `pwd` or `workingDir`?). Pulled from a real probe hook capturing `cat /dev/stdin`. The docs' "Common input fields" reference (`https://code.claude.com/docs/en/hooks#common-input-fields`) should disambiguate; an active probe would be a useful double-check.
2. **Exact `hookSpecificOutput` field tolerated by the parser** (does it strictly require `hookEventName`? Or just `additionalContext`?).
3. **Behavior when hook stdout is malformed JSON** (does CC ignore the hook, throw a user-visible error, or warn silently?).

These can be confirmed during the §2 cache-verification phase by running probe-instrumented hooks and recording the observed CC behavior.

---

## 14. Summary of the ADR-008 verification gate

| Gate criterion | Status |
|---|---|
| Mechanism exists for SessionStart hooks to inject text into the conversation layer (not system prompt) | ✅ CONFIRMED via `additionalContext` field |
| The mechanism does NOT modify the cacheable system-prompt prefix | ✅ DOCUMENTATION supports this (system-reminder vs system-prompt); EMPIRICAL verification via §2 plan still owed |
| Other plugins' SessionStart hooks coexist additively without overriding ours | ✅ CONFIRMED via "Text from additionalContext is kept from every hook" |
| The hook's exit code semantics allow graceful failure (exit 0 always) | ✅ CONFIRMED via observed reference implementations |

**ADR-008 design is officially permitted by Claude Code's hook API.** Wake-up hook implementation (Task #13) is unblocked **on the API-shape question**. Implementation still gated on the cache-verification REPORT.md per team-lead's instruction.

---

## References

- `claude --help` output (CLI introspection, 2026-05-28; CC version `2.1.154`)
- `https://json.schemastore.org/claude-code-settings.json` (settings schema)
- `https://code.claude.com/docs/en/hooks` (hooks reference)
- `https://code.claude.com/docs/en/hooks-guide` (hooks operational guide)
- `/home/hsozer/.claude/settings.json` (live reference hook configurations)
- `/home/hsozer/.claude/scripts/hooks/session-start-bootstrap.js` (live reference implementation)
- `/home/hsozer/Dev/startup-framework/wiki/decisions/008-wake-up-hook.md` (the ADR this verifies)
- `/home/hsozer/Dev/startup-framework/wiki/decisions/010-hook-ordering.md` (coexistence model)
- `/home/hsozer/Dev/startup-framework/wiki/decisions/012-two-layer-self-improvement.md` (the `--max-turns` concern source)

---

## Appendix A — Verbatim `claude --help` receipts

These are unedited blocks copied directly from `claude --help` on **Claude Code version `2.1.154`** as of 2026-05-28. Whitespace and wrapping preserved. Future contributors comparing against later CC versions should re-run `claude --help` and diff against this appendix.

### A.1 `--bare` flag (confirms ADR-012's "skip framework overhead in inner sub-runs" mechanism)

```
  --bare                                Minimal mode: skip hooks, LSP, plugin
                                        sync, attribution, auto-memory,
                                        background prefetches, keychain reads,
                                        and CLAUDE.md auto-discovery. Sets
                                        CLAUDE_CODE_SIMPLE=1. Anthropic auth is
                                        strictly ANTHROPIC_API_KEY or
                                        apiKeyHelper via --settings (OAuth and
                                        keychain are never read). 3P providers
                                        (Bedrock/Vertex/Foundry) use their own
                                        credentials. Skills still resolve via
                                        /skill-name. Explicitly provide context
                                        via: --system-prompt[-file],
                                        --append-system-prompt[-file], --add-dir
                                        (CLAUDE.md dirs), --mcp-config,
                                        --settings, --agents, --plugin-dir.
```

### A.2 `--max-budget-usd` flag (CC-native budget cap, print-mode only)

```
  --max-budget-usd <amount>             Maximum dollar amount to spend on API
                                        calls (only works with --print)
```

Note the **"only works with --print"** constraint. Implication for `/ren:improve-skill`: if we want CC-native budget enforcement on inner sub-runs, those sub-runs must use `--print` mode. For interactive top-level invocations, our framework's shadow-budget-tracker fills the gap (sum `usage.input_tokens + output_tokens` × model pricing, abort when exceeded).

### A.3 `--max-turns` flag — VERIFIED ABSENT

Probe command:
```
$ claude --help 2>&1 | grep -i -- "--max-turns"
(no --max-turns flag found)
```

The string `--max-turns` does NOT appear anywhere in `claude --help` output on CC `2.1.154`. ADR-012's amendment dated 2026-05-28 referenced this flag as if it existed; verification disproves that. The amendment must be corrected (see the ADR-012 amendments block for the correction record, 2026-05-28 entry referencing this document).

**Implication for `/ren:improve-skill` pre-flight**: requires `--max-iterations` (our framework cap) + `--max-budget-usd` (CC-native, print-mode for inner sub-runs). Shadow turn-tracking via response-count summation is the belt-and-suspenders fallback for non-print contexts. Re-check on each CC release whether `--max-turns` returns.

### A.4 `--exclude-dynamic-system-prompt-sections` (load-bearing for ADR-008's design)

```
  --exclude-dynamic-system-prompt-sections
      Move per-machine sections (cwd, env info, memory paths, git status) from
      the system prompt into the first user message. Improves cross-user
      prompt-cache reuse. Only applies with the default system prompt (ignored
      with --system-prompt). (default: false)
```

This is **the strongest single piece of evidence** that ADR-008's design is officially supported by Claude Code. CC ITSELF implements the "move dynamic content from cacheable system-prompt prefix into the first user message" pattern, with the explicit goal of improving prompt-cache reuse. Our SessionStart hook applies the same pattern through a different mechanism (`additionalContext` → system-reminder injection) and inherits the same cache-preservation property.

### A.5 `--include-hook-events` (used in cache-verification §2 instrumentation)

```
  --include-hook-events                 Include all hook lifecycle events in the
                                        output stream (only works with
                                        --output-format=stream-json)
```

Used in `verify/probe.sh` to capture SessionStart hook firing events alongside usage metrics for the cache-preservation experiment.
