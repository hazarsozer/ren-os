---
name: wrap
description: |
  Use at session end when the friend wants to consolidate what happened.
  Triggers on the /ren:wrap slash command. Writes an L1 narrative summary
  (always, auto-quarantined as unreviewed) and gates candidate durable items
  through a fail-closed classifier, auto-applying them (revertible) unless
  held for a contradiction or surfaced as a promotion suggestion.
  Most sessions produce zero durable candidates — the discipline is bias
  toward NOT durable, per spec §3.1.
version: 0.3.5
license: MIT

framework_version: "0.3.5"
schema_version: 1
type: skill
execution_tier: judgment

contract:
  required_outputs:
    - "One L1 narrative page queued, approved, and applied (writer=llm-auto), auto-quarantined by the queue"
    - "Zero or more durable-candidate Proposals queued through the data-plane door — auto-applied to 'Saved this session' unless held for a contradiction or surfaced as a 'Suggestion' (instruction-plane global/ target or a retrospective skill-candidate)"
    - "A gated_out list explaining why each non-durable candidate was turned away"
    - "A refused list for any durable candidate the queue itself rejected (e.g. a planted secret)"
    - "A fail_closed flag, accurate for this run, surfaced to the user when true"
    - "An end screen with 'What I learned', 'Saved this session (revertible)', 'Held — contradictions to resolve' (omitted when empty), and 'Suggestions' sections — no slash-command hints anywhere; suggestions are resolved conversationally in chat"
  budgets:
    turns: 3
    files_written: 1
    duration_seconds: 30
  permissions:
    read:
      - "~/.renos/wiki/**"
    write:
      - "~/.renos/wiki/**"
      - "~/.renos/wiki/.ren/metrics/**"
    execute: []
  completion_conditions:
    - "The L1 QueueEntry has status=applied and its page's frontmatter carries a valid ren_write_id"
    - "collect.read(kind=KIND_CLASSIFIER_EVENT) has one new entry per gate() call this run"
  output_paths:
    - "~/.renos/wiki/l1/"
    - "~/.renos/wiki/lessons/"
    - "~/.renos/wiki/.ren/metrics/"

tags: [producer, session-end, wrap, l1, classifier, quarantine]
related_skills: [pin, recall]
references_required: []
references_on_demand: []
---

# wrap

End-of-session consolidation. The friend runs `/ren:wrap`; this skill writes the session's L1 narrative summary (always — quarantined as unreviewed LLM-auto content, never treated as instruction) and gates any candidate durable items through the classifier, auto-applying them (revertible) unless held for a contradiction or surfaced as a promotion suggestion. Per spec §3.1's discipline, most sessions should produce **zero** durable candidates — the classifier biases hard toward "not durable."

## When to use this skill

- Friend invokes `/ren:wrap` at (or near) the end of a session.
- Friend says something like "let's wrap up", "consolidate this session", "what should we remember from today."

## When NOT to use this skill

- Friend wants to pin one specific fact mid-session → `/ren:pin`, not `/ren:wrap`.
- Friend wants to look something up → `/ren:recall`.
- No session content exists yet (this is the very first turn) → nothing to wrap.

## Behavior

1. **Compose the L1 narrative.** The live session writes this ITSELF — never a subagent (`execution_tier: judgment`; the exception to worker delegation: only the main model holds the conversation being summarized in context). A short narrative markdown summary of what happened this session — what was done, what's open, what changed. This is data, not doctrine; it always gets quarantined on write (queue Task 2.4 wiring), so nothing here needs to hedge its own confidence.
2. **Extract candidate durable items.** The live session identifies zero or more candidate strings that MIGHT be worth durable, cross-session memory (a decision, a lesson, a reusable pattern). When in doubt, extract fewer, not more — the classifier gate is the second line of defense, not the first.
3. **Call `skills.wrap.lib.wrap_session(narrative_md, durable_items, session, llm_call=...)`.**
   - `llm_call` is injectable — point it at a CHEAP model (Haiku-class) when one is reachable; the gate is a strict yes/no/discard question that doesn't need main-model reasoning. Otherwise it's the live session's own way of asking itself that question (see `lib/classifier.py`'s prompt). If no such mechanism is wired up yet, omit `llm_call` — the deterministic fallback (`session-only`/`discard` only, never `durable`) keeps memory safe by construction rather than guessing.
4. **Present results to the friend:**
   - L1: "session summary saved (quarantined, unreviewed)."
   - Durable candidates: qids + pages, saved this session (revertible) unless held for a contradiction or surfaced as a promotion suggestion.
   - Gated out: verdict + one-line reason each.
   - Refused: any candidate the queue itself rejected (e.g. a planted secret) — surfaced explicitly, not silently dropped.
   - If `fail_closed` is true: tell the friend the classifier fell back to the deterministic path this run (LLM path errored) — nothing was silently promoted to durable as a result.

## End screen

After `wrap_session()` returns, call `skills.wrap.lib.render_wrap_screen(wrap_result, session)` and print its output VERBATIM as the close-out — do not re-summarize or re-format it. The screen is pure presentation (spec §3.8's unified wrap surface): "What I learned" (the L1 summary's status), "Saved this session (revertible)" (this session's auto-applied entries — `auto-tier` or `model-resolved` — each with a spoken one-step revert hint, e.g. `say "undo <write_id>" to revert`), "Held — contradictions to resolve" (still-pending entries with a detected `contradicts` conflict, omitted entirely when there are none), and "Suggestions" (pending entries targeting an instruction-plane `global/` page or produced by the retrospective skill-candidate flow, rendering `- (none)` when empty), plus a refused note when the classifier gate or the secrets scan turned something away — even though risk tiers fragment the underlying writes across auto-applied and pending state, the friend sees one legible screen with **no slash-command hints anywhere**.

**Then, ask about Suggestions in chat.** If the rendered screen's Suggestions section is non-empty, ask the friend about each one conversationally — e.g. "Suggest promoting X because \<reason + evidence> — yes/no?" Never auto-answer a suggestion. On "yes", call `queue.approve_and_apply(qid, who=<friend's handle>)`; on "no", call `queue.reject(qid, why=<their words>)`. Skipping is fine — a skipped suggestion just persists to the next session's screen.

## Design notes

- Adapted from donor `skills/wrap/lib/classifier.py`'s KEY 0.1 finding: an LLM prompt/parse path was built but never wired in, while a deterministic heuristic quietly did all the real work. 0.2 swaps the roles on purpose — see `lib/classifier.py`'s module docstring.
- Every write here goes through `lib.memory.queue` — no direct wiki writes, no donor-style `CONTEXT.md` rewrite machinery.
