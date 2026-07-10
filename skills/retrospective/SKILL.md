---
name: retrospective
description: |
  Use when the friend (or a scheduled routine) wants a retrospective pass:
  mine instrumentation + journal + recent session history for repeated
  corrections, wrap-gate failures, and repeated task shapes that aren't
  skills yet — propose each as a queue diff. Triggers on /ren:retrospective
  [--since <date>]. NOT an eval-scored iteration loop — one deterministic
  pass, optionally judgment-enriched by the live session before proposing.
version: 0.5.0
license: MIT
type: skill
execution_tier: worker
schema_version: 1
framework_version: "0.5.0"

contract:
  required_outputs:
    - "Zero or more Proposals queued at retrospective/<date>-<kind>-<slug>.md and applied for lesson/instruction-tweak findings; skill-candidate findings recorded as pending suggestions in the suggestion store"
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
    - "Every finding from analyze() (as enriched by the live session) has a corresponding record — an applied QueueEntry for lesson/instruction-tweak, a pending suggestion-store entry for skill-candidate (unless its fingerprint is already pending/decided)"
  output_paths: []

tags: [retrospective, self-improvement, skill-candidate, queue]
related_skills: [wrap]
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
| `skill-candidate` (D-2) | A task-shape phrase recurs across ≥3 distinct sessions | `{task, frequency, proposed_shape, proposed_scaffold}` — a repeated pattern that isn't a skill yet, with an executable script scaffold (SKILL.md layout + `lib/run.py` stub) so the reviewer sees exactly what would be built |

All three are pure, deterministic functions over `gather()`'s output — no LLM call inside `lib.analyze`. The judgment layer belongs to the LIVE SESSION running this skill, not the library: read each finding, optionally enrich it (a sharper lesson statement, a more concrete proposed skill shape) before calling `propose_all`.

## When to use this skill

- Friend invokes `/ren:retrospective` for a fresh pass
- Friend invokes `/ren:retrospective --since 2026-01-01` to scope the metrics window
- A scheduled routine invokes it periodically (via `skills/routine-init`'s allowlist mechanism, `capabilities: ["retrospective"]`)

## Behavior

1. Call `skills.retrospective.lib.gather(since=...)`.
2. Call `analyze(gathered)` — get the deterministic findings list.
3. **Enrich each finding — in a worker subagent when possible** (`execution_tier: worker`): findings are self-contained, so spawn a cheap worker-model subagent (Sonnet/Haiku-class) to sharpen messages and refine proposed skill shapes, and take its output back. Parse its returned JSON with `lib.adapter.worker.parse_worker_json` — it tolerates a ```json fence or leading prose despite raw-JSON-only instructions, and raises `WorkerOutputError` (carrying the raw text) if the output still isn't valid JSON. Fall back to enriching inline only when subagents aren't available; the lib layer stays mechanical either way.
4. Call `propose_all(findings, session)` → `(entries, suggestions)`. `lesson`/`instruction-tweak` findings are data-plane (descriptive): each queues an `ADD` proposal (`producer="retrospective"`, `writer="retrospective"`) through `propose_and_apply` and lands `applied` immediately (`entries`). `skill-candidate` findings are instruction-plane suggestions by intent (Task 16, 0.4.2): each is recorded into the durable suggestion store (`lib.suggestions.record`, kind `page_write`) instead of the queue — fingerprinted, so re-running never re-nags a pending or already-decided candidate (`suggestions`).
5. Render the result to the friend: what auto-applied (already saved — say "undo \<write_id>" to revert), and which skill-candidate suggestions were newly recorded for review later (via the suggestion surface).

## Why `writer="retrospective"` is not quarantined

`lib.memory.queue.apply`/`apply_auto`'s auto-quarantine (Task 2.4) only fires for `writer="llm-auto"`. Retrospective findings are their OWN provenance class — a deterministic mining pass, judgment-enriched by a live session, is a different trust shape than raw unreviewed LLM output. Whether a finding auto-applies or waits `pending` is governed by the v2.2 two-plane intent split (data vs. instruction), not by quarantine — see the Behavior section above.

## What this skill does NOT do

- Auto-apply a skill-candidate finding. That's an instruction-plane suggestion by intent — it always stays `pending` for a human's OK, regardless of which page it targets.
- Iterate against an eval score. That's explicitly out of scope per spec §3.7 — this is one pass, not a tuning loop.
- Scan transcripts unboundedly. `gather()` caps at the last 10 transcripts for the current project (`MAX_SESSIONS_SCANNED`).

## References

- Task 3.1 (`lib/instrument/collect.py`) — the metrics surface + the transcript family this reads (same files `harvest_session_usage` reads, mined here for task phrases instead of token counts)
- Task 2.1 (`lib/memory/queue.py`) — the single write-queue every finding proposes through
- Task 2.4 (queue's auto-quarantine) — why `writer="retrospective"` bypasses it, see above
- `skills/insights/scripts/collect.py` (donor, `~/Dev/startup-framework`) — the topic-extraction pieces (STOPWORDS, word regex, secret guard) adapted here
- `lib/memory/revert.py` — the one-step undo a friend uses on what this skill auto-applies, invoked conversationally ("undo \<write_id>"), not through a queue skill
