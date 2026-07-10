---
name: suggestions
description: |
  Use when the friend wants to review pending suggestions: rare, high-stakes
  items a producer (retrospective, promotion, doctrine, wiki-health) has
  raised for explicit approve/reject — never auto-applied. Triggers on the
  /ren:suggestions slash command. The single interactive decide surface over
  lib.suggestions' durable store (Task 14); this is where an accepted
  decision actually becomes a write.
version: 0.4.2
license: MIT

framework_version: "0.4.2"
schema_version: 1
type: skill
execution_tier: judgment

contract:
  required_outputs:
    - "Every pending suggestion shown to the friend one at a time, each with an explicit accept/decline answer recorded"
    - "Each accepted suggestion applied by kind (page_write/promote_to_global/refresh_claude_md) or, for review_contradiction, evidence surfaced for conversational reconciliation"
  budgets:
    turns: 20
    files_written: 0
    duration_seconds: 120
  permissions:
    read:
      - "~/.renos/wiki/**"
    write:
      - "~/.renos/wiki/**"
      - "~/.claude/CLAUDE.md"
    execute: []
  completion_conditions:
    - "Every suggestion returned by render_list() at invocation time has a recorded accepted/declined decision"
  output_paths:
    - "~/.renos/wiki/"

tags: [judgment, suggestions, approve-reject, decide, gate]
related_skills: [wiki-health, retrospective, recall]
references_required: []
references_on_demand: []
---

# suggestions

The single interactive approve/reject surface over `lib.suggestions`'
durable store (Task 14). Suggestions are RARE AND HIGH-STAKES by design
(spec §1.2) — this is the only place a suggestion's payload actually gets
applied. `lib.suggestions.decide` itself is a pure state transition; this
skill's `accept()` is what turns an "accepted" decision into a real write.

## When to use this skill

- Friend invokes `/ren:suggestions` — review whatever's pending
- A producer (retrospective, promotion, doctrine, wiki-health) just raised a
  new suggestion and the friend wants to act on it now rather than later

## When NOT to use this skill

- The friend wants to record something new mid-session → `/ren:pin`
- The friend wants a coherence sweep, not a decision queue → `/ren:wiki-health`

## Behavior

1. Call `skills.suggestions.lib.render_list()`.
2. If it returns `"No pending suggestions."`, say so and stop — nothing else
   to do.
3. Otherwise walk the pending suggestions **ONE AT A TIME**, in the order
   `render_list()` returned them (oldest first):
   - Show `render_suggestion(s)` for the current suggestion — title,
     rationale, producer, and (for `page_write` suggestions) a content
     preview.
   - Ask the friend to Approve or Reject (AskUserQuestion, or plain chat if
     unavailable). Get an **explicit per-item answer** — never assume, never
     infer from silence.
   - On approve: call `skills.suggestions.lib.accept(sid, session)`. Report
     what happened from the returned `{"sid", "applied", "detail"}` — if
     `applied` is `False`, say so and show `detail` (e.g. a duplicate-content
     no-op, or the two pages + evidence for a `review_contradiction`
     suggestion the friend now reconciles conversationally).
   - On reject: call `skills.suggestions.lib.decline(sid)` — durable, this
     suggestion is never re-offered.
   - Move to the next suggestion.
4. **Never batch-apply.** Never apply a suggestion without an explicit
   per-item answer from the friend.

## Apply routes (by suggestion kind / payload action)

- `page_write` → `lib.memory.queue.propose` then
  `queue.approve_and_apply(qid, who="suggestions")`. Instruction-plane
  (`global/`) pages go through the SAME human-gated door as ever — the
  recorded suggestion decision IS the human approval. If `propose` returns a
  synthetic `noop-duplicate` entry (content already matches the live page),
  `accept()` treats it as `applied=False` with a `"content already on page"`
  detail and still records the accept decision — never a half-applied state.
- `promote_to_global` → `lib.memory.promotion.promote_to_global(source_page,
  session)` then `approve_and_apply`.
- `refresh_claude_md` → `lib.adapter.claude_md.write_global_claude_md()`.
- `review_contradiction` → applies nothing; returns the two page paths and
  evidence so the session can reconcile them conversationally.

Any apply failure is caught inside `accept()` and surfaced in `detail` —
the decision stays recorded either way.
