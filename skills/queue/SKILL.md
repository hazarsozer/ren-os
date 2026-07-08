---
name: queue
description: |
  Use when the friend wants to review, approve, reject, or revert queue
  entries — the verbs the wrap screen (Task 8.2) already tells them to use
  ("/ren:approve <qid>") but that didn't exist as a skill until now.
  Triggers on /ren:queue (review), /ren:approve <qid>, /ren:reject <qid>
  <why>, /ren:revert <write_id>. Thin presentation over lib.memory.queue and
  lib.memory.revert — no new logic.
version: 0.2.0
license: MIT
type: skill
execution_tier: judgment
schema_version: 1
framework_version: "0.2.0"

contract:
  required_outputs:
    - "/ren:queue: a rendered list of pending entries (or 'No pending queue entries.')"
    - "/ren:approve <qid>: the entry applied, confirmation with write_id + revert hint"
    - "/ren:reject <qid> <why>: the entry rejected, confirmation with the reason"
    - "/ren:revert <write_id>: the write reverted, confirmation with any citing pages"
  budgets:
    turns: 1
    files_written: 0
    duration_seconds: 5
  permissions:
    read:
      - "~/.renos/wiki/.ren/queue/**"
      - "~/.renos/wiki/.ren/journal.jsonl"
    write:
      - "~/.renos/wiki/**"
    execute: []
  completion_conditions:
    - "Unknown qid/write_id always renders a friendly one-line error string, never a raw exception"
  output_paths: []

tags: [queue, approve, reject, revert, presentation]
related_skills: [retrospective, pin, wrap]
references_required: []
references_on_demand: []
---

# queue

Every producer in the framework (pin, wrap, retrospective, routine, promotion) proposes through `lib.memory.queue` — this skill is how a friend actually acts on what's pending. Deliberately thin: every function here is a render-friendly wrapper over existing lib logic, nothing new.

## When to use this skill

- Friend invokes `/ren:queue` to see what's pending
- Friend invokes `/ren:approve <qid>` (exactly what the wrap screen tells them to run)
- Friend invokes `/ren:reject <qid> <why>`
- Friend invokes `/ren:revert <write_id>` to undo an already-applied write

## Behavior

### `/ren:queue`

Calls `review()` — renders every pending entry: qid, op, page, producer, writer, salience flag, and any attached conflicts (supersedes/contradicts/duplicate) indented underneath.

### `/ren:approve <qid>`

Calls `approve_and_apply(qid, who, session)` — approves then applies in one step (no separate apply step after `/ren:approve`; per spec, approval IS the trigger to write). Returns the resulting `write_id` and a one-line revert hint.

### `/ren:reject <qid> <why>`

Calls `reject_with_reason(qid, why)` — rejects with the given reason recorded on the entry.

### `/ren:revert <write_id>`

Calls `revert_write(write_id)` — reverts via `lib.memory.revert.revert` and reports any citing pages the friend should re-check.

## Error handling (load-bearing)

Every function here catches the underlying lib's `KeyError`/`QueueStateError` and returns a friendly one-line string instead of letting it propagate — a friend typing a stale or mistyped qid should see "No such queue entry: q-abc123", never a Python traceback.

## What this skill does NOT do

- Implement approval policy. The risk-tier gate (Task 6.1) decides what CAN auto-apply (`apply_auto`); this skill's `/ren:approve` is always the explicit human-approval path (`approve()` then `apply()`), never the auto-tier shortcut.
- Detect conflicts. `review()` only renders what `lib.memory.queue.propose` already attached (via `lib.memory.semantics`) — no new conflict logic here.
- Decide what to propose. That's every OTHER skill's job (pin, wrap, retrospective, ...); this skill only acts on what's already queued.

## References

- Task 2.1 (`lib/memory/queue.py`) — `pending`, `approve`, `apply`, `reject` — everything this skill wraps
- Task 2.3 (`lib/memory/revert.py`) — the revert primitive `revert_write` wraps
- Task 6.1 (`lib/governance/tiers.py`) — `apply_auto`, the OTHER apply path this skill deliberately does not expose
- Task 8.2 (wrap screen) — the caller that tells friends to run `/ren:approve <qid>`
