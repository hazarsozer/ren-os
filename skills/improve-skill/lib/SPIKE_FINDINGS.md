# C5a Phase-0 Spike — Findings

> **Date:** 2026-06-18. **Verdict: GO (bounded proof-of-life).** Probed the real `claude`
> binary (v2.1.181) in-session. The eval mechanic is viable but **costlier than the spec assumed**;
> the maintainer chose a bounded, cost-controlled proof-of-life. This file is authoritative where it
> contradicts the spec/plan (which were written pre-spike) — see "Superseded assumptions" below.

## Probes run

| Probe | Command (essence) | Result |
|-------|-------------------|--------|
| Bare auth | `claude --bare --print --output-format json "Reply OK"` | `is_error:true`, `result:"Not logged in · Please run /login"`, exit 1 |
| Non-bare auth | `claude --print --output-format json "Reply OK"` | `is_error:false`, `result:"OK"`, exit 0, **`total_cost_usd:0.36167`**, model `claude-opus-4-8[1m]` |
| Credential store | `ls ~/.claude/.credentials.json` | present (mode 600, refreshed today) |
| Sandboxed Haiku cost | `env -C tmp … claude --print --model haiku …` | **NOT measured** (command denied) — reasoned-only below |

## Findings

1. **Nested `claude --print` works in-session and returns the JSON shape the wrapper assumes.**
   Keys confirmed: `result` (assistant text), `usage{input_tokens,output_tokens,cache_creation_input_tokens,cache_read_input_tokens}`, `is_error`, `total_cost_usd`, `modelUsage` (model id = its keys), `stop_reason`, `session_id`. → `claude_cli.py`'s `result`/`usage` parsing is correct; **also parse `is_error`** (treat `true` as a failed run).

2. **Auth: non-bare authenticates via `~/.claude/.credentials.json` with ZERO user action. `--bare` does NOT** (it skips the credential store → "Not logged in"). **Implication (load-bearing):** the judge and change-proposer — planned as `--bare` for cheapness — must run **non-bare** to authenticate. `setup-token` / API key are *not* required for the proof-of-life.

3. **Cost is the gate.** A trivial non-bare call cost **$0.36** because it loaded the full global `~/.claude/CLAUDE.md` + the installed plugin + wiki injection on **Opus 4.8** (~22K input + 24K cache-creation + 16K cache-read tokens). Every eval call (skill-run + N judges per assertion, per iteration) pays this unless mitigated. The **skill-run must be non-bare** (to load the target skill), so it cannot escape the context cost via `--bare`.

4. **Activation detection (stream-json Skill tool-use events) — NOT yet verified.** Deferred to the proof-of-life run (Task 9): confirm the exact event shape that proves "skill `<name>` activated" before trusting `trigger_test`/`non_trigger` scoring. If undetectable, those assertions degrade to a documented limitation (don't silently pass them).

## Cost controls for the bounded proof-of-life (the contract)

- **Model:** judge → `--model haiku` (cheap; the judge only needs yes/no). Skill-run → configurable; default a cheaper tier (Sonnet) for the proof, noting it may not perfectly mirror the user's default-model behavior.
- **Empty-wiki sandbox:** run every eval call with `SF_WIKI_ROOT`/`CLAUDE_PLUGIN_DATA` → empty tmp dirs (the `sandbox.py` design) and a tmp CWD, cutting the wiki injection + project `CLAUDE.md` chain. (The global `~/.claude/CLAUDE.md` still loads in non-bare — unavoidable without `--bare`.)
- **Hard budget cap:** the proof runs with `--max-budget-usd` ≈ **$2** and `--max-iterations` ≈ **3** on a **small-eval target skill** (few assertions).
- **Measure + record:** capture the real per-call and per-run cost during the proof; append it here and to the ADR-036 supervised-run log. **If the measured per-run cost is prohibitive for regular use → fall back to the lighter-eval re-architecture (spec option B).**

## Superseded assumptions (spec/plan written pre-spike)

- **`--bare` for judge/proposer → use non-bare** (auth). The `bare` param in `claude_cli.run_print` is retained but defaults effectively to non-bare for any authenticated call; document that `bare=True` will NOT authenticate. (Plan Task 6 / spec §4.2 / `eval-runner.md` inner-sub-run note.)
- **Cost-control (model + empty-wiki sandbox + budget cap) is now first-class**, not an afterthought (spec §8 expanded).

## Open follow-ups (post-proof, not blocking)

- **Cheap authed `--bare`:** test whether `ANTHROPIC_API_KEY` (or an explicit `CLAUDE_CODE_OAUTH_TOKEN`) lets `--bare` authenticate — that would make the *judge* calls cheap (no skill needed). The skill-run still needs non-bare.
- **Skip global `CLAUDE.md` while keeping skills + auth:** investigate a flag/setting; would cut the dominant context cost.

## Live proof outcome (2026-06-19)

Ran a bounded live proof (real `claude`, sonnet, 2 sandboxed activation probes):

1. **Activation-detection parser bug — FOUND + FIXED (`c3712b2`).** The real `--output-format stream-json`
   shape nests the `Skill` tool_use inside an `assistant` message's `content[]`
   (`{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Skill","input":{"skill":"<n>"}}]}}`),
   not at the top level. `_activated_from_stream` parsed only top-level `tool_use`, so it returned `()` even
   when a Skill activated. Fixed + unit-tested against the recorded real event. Activation detection (which
   `run_evals`'s trigger/non-trigger scoring depends on) now works.
2. **Skill-loading limitation (FOLLOW-UP — keeps the loop EXPERIMENTAL).** A nested `claude --print` from the
   empty `/tmp` sandbox CWD loads **no plugin skills** ("no recall skill available"), so `run_evals` cannot
   exercise the target skill there. From a **plugin-active CWD** (the worktree) skills DO load (a `Skill`
   tool_use fired). So the eval sandbox must run skill-runs from a plugin-active CWD (or install/point at the
   target skill) before the end-to-end loop can score a real skill. Until solved, the live loop cannot improve
   a real skill — the bike-method EXPERIMENTAL gate stays, now with a concrete reason.
3. **Cost/behavior note.** Even with an empty-wiki sandbox, non-bare nested calls carry heavy context (global
   `~/.claude/CLAUDE.md` + installed plugin: ~105K cache-read + ~30K cache-create per call), and a single
   skill-run can fan out into sub-agents — real eval-loop cost is non-trivial.

**Verdict:** the eval-runner MECHANISM is now correct (parser fixed, verified offline). The end-to-end live
loop is gated on the skill-loading follow-up. Merge C5a (wiring + fixes); the supervised proof + the
skill-loading fix are the next step before any autonomy.
