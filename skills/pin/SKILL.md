---
name: pin
description: |
  Use when the friend wants to reactively pin or correct memory mid-session:
  "remember it like THIS" or "that's wrong, drop it." Triggers on the
  /ren:pin slash command. The simplest producer in the system — one
  invocation, one proposal, queued through the single write-queue like
  every other producer. Not a pipeline.
version: 0.7.6
license: MIT

framework_version: "0.7.6"
schema_version: 1
type: skill
execution_tier: judgment

contract:
  required_outputs:
    - "One Proposal submitted through lib.memory.queue.propose_and_apply (op ADD/UPDATE/DELETE per the invocation), auto-applied (revertible) unless an instruction-plane target (global/, decisions/, patterns/, research/) or a contradiction leaves it pending"
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
    - "A QueueEntry exists at state_dir()/queue/<qid>.json with status=applied, or status=pending if held for an instruction-plane target (global/, decisions/, patterns/, research/) or a contradiction"
  output_paths: []

tags: [producer, mid-session, pin, correction, queue]
related_skills: [recall, wrap]
references_required: []
references_on_demand: []
---

# pin

Reactive memory control, mid-session. The friend says "remember it like THIS" or "that's wrong, drop it" — this skill turns that into exactly one `Proposal` at the data-plane door (Task 2.1). A pin is the friend's own words (`writer="human"`), so it applies immediately with provenance and a one-step revert — it never writes a wiki page directly, but it doesn't wait on anyone either. Only an instruction-plane target (`global/`, `decisions/`, `patterns/`, `research/`) or a detected `contradicts` conflict leaves it pending instead of applying right away — NOTHING is on disk in that case, so never report a held pin as saved: surface the queue id and tell the friend the pin is pending their approval (`/ren` approval path: `lib.memory.queue.approve_and_apply(<qid>, who)`).

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
3. Both calls go through `lib.memory.queue.propose_and_apply`, which scrubs secrets, dedups against existing pending entries, and runs conflict detection exactly like any other producer — pin gets no special exemption. Per the v2.2 pivot, a pin/correction to a data-plane page auto-applies immediately (provenance-tagged, one-step revertible). An instruction-plane target (`global/`, `decisions/`, `patterns/`, `research/`) or a `contradicts` conflict holds the entry pending instead — nothing lands on disk.
4. Confirm to the user, honestly per outcome:
   - Applied: `Saved (write <write_id>) — <op> <page> (pin)`, or `... (correction)`, and mention saying "undo <write_id>" to revert — matching `ingest`'s conversational closing copy.
   - Held pending (instruction-plane target or contradiction): NEVER say "saved". Report `Queued as <qid> — <page> is an instruction-plane target, held for your approval` and point at the approval path (`lib.memory.queue.approve_and_apply("<qid>", who="<friend>")`, i.e. the /ren approval flow) or contradiction resolution as appropriate. Exception: when the friend has ALREADY approved the correction in conversation (e.g. wrap's "Live pins" gate asked and they said "delete"), pass `approved_by=<friend's handle>` to `correct(...)` — it completes the instruction-plane hold through `approve_and_apply` in the same call, so the confirmed correction actually lands (dogfood-2 finding H1). A `contradicts` hold is never auto-completed this way — it still comes back `pending` and must be reported as held.

## Why `salience=True`

Per spec §3.2, a pinned or corrected page is something the friend explicitly cared enough about to interrupt flow for. `salience` is carried through the `Proposal` into the `QueueEntry` so wake-up's relevance ranking (Phase 5) can boost it — a pin is a strong, direct signal, stronger than anything inferred.

## Task-shaped pins (issue #25)

A pin whose content is a TASK ("next session, do X") should carry its own disposal as its last step — end the pinned text with "…and delete this page once done." Belt-and-braces: `/ren:wrap`'s "Live pins" gate (see `skills/wrap/SKILL.md`) also lists every live pin at session end and asks the friend about ones that look acted-on, so a finished plan-pin gets caught there even when the text forgot its own delete step. Disposal is always the normal correction path (`correct(page, None, session)` → queue DELETE) — never a direct file deletion.

## Standing rules scoped to a project (#63)

When the friend asks to make something a standing rule for the CURRENT PROJECT specifically ("always do X in this repo", "make that a standing rule here") — not an ordinary page pin — the session calls `lib.memory.promotion.promote_to_project(text, slug, session)` instead of `pin()`. It proposes an `ADD`/`UPDATE` against `projects/<slug>/instructions.md` (born on first promotion — no skeleton stamping anywhere else) and, being an instruction-plane page (Task 5), always comes back `pending`. After the friend confirms verbally, complete the hold with `queue.approve_and_apply(qid, who="human:pin")` — same completion contract as `correct(..., approved_by=...)`'s `_complete_if_held`. `pin()` itself stays unchanged for ordinary page pins; this is a separate entry path, not a mode of `pin()`.

## What this skill does NOT do

- Write to a wiki page directly. Every pin/correction is a `Proposal` at the data-plane door (`propose_and_apply`) — applying (or holding on a contradiction) is owned by the queue/tier machinery, not this skill.
- Run any pipeline, retry loop, or multi-step flow. One invocation → one proposal. If that proposal conflicts with something, `queue.propose_and_apply` attaches the conflict; a `contradicts` conflict is held for the model to reason about and resolve (recording that reasoning), with the friend asked only on genuine ambiguity — this skill doesn't try to resolve it itself.
- Maintain its own state file, hot tier, or session-notes equivalent. There is no `--instinct` mode in 0.2 (donor `skills/note`'s instincts hot tier is out of scope here — see the harvest map).
- Decide apply policy. Whether a pin's entry applies immediately or is held pending (an instruction-plane target — `global/`, `decisions/`, `patterns/`, `research/` — or a detected `contradicts` conflict) is governed by the memory write path, not by this skill.

## Failure-degradation modes

| Failure | Behavior | User-visible |
|---|---|---|
| Empty text on `/ren:pin` | Refuse, prompt for text | "What should I pin? Usage: /ren:pin \"<text>\"" |
| `--wrong` with no resolvable page | Refuse; nothing proposed | "Which page is wrong? Usage: /ren:pin --wrong <page>" |
| Content contains a detected secret | `propose_and_apply()` raises `SecretsFound`; nothing queued | "Refused: that text looks like it contains a secret." |
| Duplicate pending pin (same page + same content) | `propose_and_apply()` returns the existing entry (idempotent) | "Already queued as <qid>." |

## References

- Task 2.1 (`lib/memory/queue.py`) — the single write-queue this skill's only consumer
- Spec §3.1 producer 3 — pin/correction verb definition
- Spec §3.2 — salience and wake-up ranking
- `skills/note/` (donor, `~/Dev/startup-framework`) — the pre-0.2 shape this skill shrinks from
