---
name: retrospective
description: |
  Use when the friend (or a scheduled routine) wants a retrospective pass:
  mine instrumentation + journal + recent session history for repeated
  corrections, wrap-gate failures, and repeated task shapes that aren't
  skills yet — propose each as a queue diff. Triggers on /ren:retrospective
  [--since <date>]. NOT an eval-scored iteration loop — one deterministic
  pass, optionally judgment-enriched by the live session before proposing.
version: 0.2.0
license: MIT
type: skill
schema_version: 1
framework_version: "0.2.0"

contract:
  required_outputs:
    - "Zero or more Proposals queued at retrospective/<date>-<kind>-<slug>.md, all pending"
    - "A rendered list of what was proposed, shown to the friend at the end"
  budgets:
    turns: 3
    files_written: 0
    duration_seconds: 30
  permissions:
    read:
      - "~/.renos/wiki/**"
      - "~/.claude/projects/**"
    write: []
    execute: []
  completion_conditions:
    - "Every finding from analyze() (as enriched by the live session) has a corresponding pending QueueEntry"
  output_paths: []

tags: [retrospective, self-improvement, skill-candidate, queue]
related_skills: [queue, wrap]
references_required: []
references_on_demand: []
---

# retrospective

Spec §3.7's minimal retrospective engine + v2.1 D-2's skill-candidate mining, in one pass: `gather` → `analyze` → (live session may enrich) → `propose_all`. No eval-scored iteration — this runs once per invocation, not a tuning loop.

## The three deterministic rules (`analyze`)

| Finding kind | Fires when | What it proposes |
|---|---|---|
| `lesson` | A page has been corrected (journaled UPDATE with `supersedes`) ≥2 times | "This page keeps being corrected — capture the stable truth" |
| `instruction-tweak` | ≥3 classifier `fail_closed` events recorded | "Wrap gate failing often — check llm_call wiring" |
| `skill-candidate` (D-2) | A task-shape phrase recurs across ≥3 distinct sessions | `{task, frequency, proposed_shape}` — a repeated pattern that isn't a skill yet |

All three are pure, deterministic functions over `gather()`'s output — no LLM call inside `lib.analyze`. The judgment layer belongs to the LIVE SESSION running this skill, not the library: read each finding, optionally enrich it (a sharper lesson statement, a more concrete proposed skill shape) before calling `propose_all`.

## When to use this skill

- Friend invokes `/ren:retrospective` for a fresh pass
- Friend invokes `/ren:retrospective --since 2026-01-01` to scope the metrics window
- A scheduled routine invokes it periodically (via `skills/routine-init`'s allowlist mechanism, `capabilities: ["retrospective"]`)

## Behavior

1. Call `skills.retrospective.lib.gather(since=...)`.
2. Call `analyze(gathered)` — get the deterministic findings list.
3. **The live session may enrich each finding** (sharpen the message, refine the proposed skill shape) — this is where judgment enters; the lib layer stays mechanical.
4. Call `propose_all(findings, session)` — queues one `ADD` proposal per finding, `producer="retrospective"`, `writer="retrospective"`.
5. Render the pending list to the friend: what was proposed, and that it's sitting in the queue awaiting `/ren:approve`.

## Why `writer="retrospective"` is not quarantined

`lib.memory.queue.apply`'s auto-quarantine (Task 2.4) only fires for `writer="llm-auto"`. Retrospective findings are their OWN provenance class — a deterministic mining pass, judgment-enriched by a live session, is a different trust shape than raw unreviewed LLM output. The queue itself (every proposal lands `pending`, diff-approved) is already the human gate here; quarantine would be a redundant, mismatched second gate for content that was never "LLM-authored and unreviewed" in the same sense `llm-auto` content is.

## What this skill does NOT do

- Auto-apply anything. Every finding is a `Proposal`, always `pending`.
- Iterate against an eval score. That's explicitly out of scope per spec §3.7 — this is one pass, not a tuning loop.
- Scan transcripts unboundedly. `gather()` caps at the last 10 transcripts for the current project (`MAX_SESSIONS_SCANNED`).

## References

- Task 3.1 (`lib/instrument/collect.py`) — the metrics surface + the transcript family this reads (same files `harvest_session_usage` reads, mined here for task phrases instead of token counts)
- Task 2.1 (`lib/memory/queue.py`) — the single write-queue every finding proposes through
- Task 2.4 (queue's auto-quarantine) — why `writer="retrospective"` bypasses it, see above
- `skills/insights/scripts/collect.py` (donor, `~/Dev/startup-framework`) — the topic-extraction pieces (STOPWORDS, word regex, secret guard) adapted here
- `skills/queue/` — the review/approve/reject/revert verbs a friend uses on what this skill proposes
