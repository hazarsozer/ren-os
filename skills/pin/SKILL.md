---
name: pin
description: |
  Use when the friend wants to reactively pin or correct memory mid-session:
  "remember it like THIS" or "that's wrong, drop it." Triggers on the
  /ren:pin slash command. The simplest producer in the system — one
  invocation, one proposal, queued through the single write-queue like
  every other producer. Not a pipeline.
version: 0.2.0
license: MIT

framework_version: "0.2.0"
schema_version: 1
type: skill

contract:
  required_outputs:
    - "One Proposal submitted to lib.memory.queue (op ADD/UPDATE/DELETE per the invocation), pending approval"
    - "Confirmation line printed to user including the queue id and the page it targets"
  budgets:
    turns: 1
    files_written: 0
    duration_seconds: 5
  permissions:
    read:
      - "~/.renos/wiki/**"
    write: []
    execute: []
  completion_conditions:
    - "A QueueEntry exists at state_dir()/queue/<qid>.json with status=pending"
  output_paths: []

tags: [producer, mid-session, pin, correction, queue]
related_skills: [recall, wrap]
references_required: []
references_on_demand: []
---

# pin

Reactive memory control, mid-session. The friend says "remember it like THIS" or "that's wrong, drop it" — this skill turns that into exactly one `Proposal` at the single write-queue (Task 2.1). It never writes a wiki page directly; it queues, and the normal approve/apply flow (or an auto-apply policy configured elsewhere) takes it from there.

## When to use this skill

- Friend invokes `/ren:pin "<text>" [--page <path>]` — pin new or updated content to a page. If `--page` is omitted, the caller resolves a sensible default (e.g. the active project's current-context page) before calling `pin()`.
- Friend invokes `/ren:pin --wrong <page> [--instead "<text>"]` — a correction. With `--instead`, the page is replaced with the given text (UPDATE). Without it, the page is proposed for deletion (DELETE) — "that's wrong, just drop it."
- Friend says: "remember this exactly", "no, that's wrong", "pin this", "correct that page" — confirm the target page once if ambiguous, then call the lib function.

## When NOT to use this skill

- Friend wants to look something up → `/ren:recall <query>`, not `/ren:pin`
- Friend wants the whole session consolidated → `/ren:wrap`
- No page and no clear target can be resolved → ask which page before proposing anything (never guess and DELETE)

## Behavior

1. Resolve the target `page` (wiki-relative path) and the active `session` id.
2. Call `skills.pin.lib.pin(text, page, session)` or `skills.pin.lib.correct(page, replacement, session)`:
   - `pin` proposes `ADD` if the page doesn't exist yet, `UPDATE` if it does.
   - `correct` proposes `DELETE` when no replacement text is given, else `UPDATE`.
   - Both always set `producer="pin"`, `writer="human"`, `salience=True`.
3. Both calls go through `lib.memory.queue.propose`, which scrubs secrets, dedups against existing pending entries, and runs conflict detection exactly like any other producer — pin gets no special exemption.
4. Confirm to the user: `Queued <qid> — <op> <page> (pin)` or `... (correction)`.

## Why `salience=True`

Per spec §3.2, a pinned or corrected page is something the friend explicitly cared enough about to interrupt flow for. `salience` is carried through the `Proposal` into the `QueueEntry` so wake-up's relevance ranking (Phase 5) can boost it — a pin is a strong, direct signal, stronger than anything inferred.

## What this skill does NOT do

- Write to a wiki page directly. Every pin/correction is a `Proposal` at the queue door (Task 2.1) — approve/apply is a separate step owned by the queue, not this skill.
- Run any pipeline, retry loop, or multi-step flow. One invocation → one proposal. If that proposal conflicts with something, `queue.propose` attaches the conflict for a human to resolve later; this skill doesn't try to resolve it.
- Maintain its own state file, hot tier, or session-notes equivalent. There is no `--instinct` mode in 0.2 (donor `skills/note`'s instincts hot tier is out of scope here — see the harvest map).
- Decide auto-apply policy. Whether a pin's queue entry gets auto-approved or waits for a human `approve()` call is governed elsewhere (the wrap gate / risk-tier policy), not by this skill.

## Failure-degradation modes

| Failure | Behavior | User-visible |
|---|---|---|
| Empty text on `/ren:pin` | Refuse, prompt for text | "What should I pin? Usage: /ren:pin \"<text>\"" |
| `--wrong` with no resolvable page | Refuse; nothing proposed | "Which page is wrong? Usage: /ren:pin --wrong <page>" |
| Content contains a detected secret | `propose()` raises `SecretsFound`; nothing queued | "Refused: that text looks like it contains a secret." |
| Duplicate pending pin (same page + same content) | `propose()` returns the existing entry (idempotent) | "Already queued as <qid>." |

## References

- Task 2.1 (`lib/memory/queue.py`) — the single write-queue this skill's only consumer
- Spec §3.1 producer 3 — pin/correction verb definition
- Spec §3.2 — salience and wake-up ranking
- `skills/note/` (donor, `~/Dev/startup-framework`) — the pre-0.2 shape this skill shrinks from
