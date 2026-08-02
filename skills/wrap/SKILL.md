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
version: 0.6.4
license: MIT

framework_version: "0.6.4"
schema_version: 1
type: skill
execution_tier: judgment

contract:
  required_outputs:
    - "One L1 narrative page queued, approved, and applied (writer=llm-auto), auto-quarantined by the queue"
    - "Zero or more durable-candidate Proposals queued through the data-plane door — auto-applied to 'Saved this session' unless held for a contradiction or surfaced as a 'Suggestion' (instruction-plane global/ target)"
    - "A gated_out list explaining why each non-durable candidate was turned away"
    - "A refused list for any durable candidate the queue itself rejected (e.g. a planted secret)"
    - "A fail_closed flag, accurate for this run, surfaced to the user when true"
    - "An end screen with 'What I learned', 'Saved this session (revertible)', 'Held — contradictions to resolve' (omitted when empty), 'Possible connections (unverified)' (judged, informational, omitted when empty), and 'Suggestions' sections — no slash-command hints anywhere; suggestions are resolved conversationally in chat"
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

1. **Compose the L1 narrative.** The live session writes this ITSELF — never a subagent (`execution_tier: judgment`; the exception to worker delegation: only the main model holds the conversation being summarized in context). A short narrative markdown summary of what happened this session — what was done, what's open, what changed. Lead with outcomes. Target ≤1,000 tokens. This is data, not doctrine; it always gets quarantined on write (queue Task 2.4 wiring), so nothing here needs to hedge its own confidence.
2. **Extract candidate durable items.** The live session identifies zero or more candidate strings that MIGHT be worth durable, cross-session memory (a decision, a lesson, a reusable pattern). When in doubt, extract fewer, not more — the classifier gate is the second line of defense, not the first.
3. **Call `skills.wrap.lib.wrap_session(narrative_md, durable_items, session, llm_call=...)`.**
   - `session` is just a LABEL for this session's records — you are not expected to know Claude Code's real `session_id`, and nothing depends on you guessing it. (The 0.6.1 estimator-calibration harvest resolves the transcript from the id the wake-up hook itself recorded, never from this label.)
   - `llm_call` is injectable — point it at a CHEAP model (classifier-class) when one is reachable; the gate is a strict yes/no/discard question that doesn't need main-model reasoning. Otherwise it's the live session's own way of asking itself that question (see `lib/classifier.py`'s prompt). If no such mechanism is wired up yet, omit `llm_call` — the deterministic fallback (`session-only`/`discard` only, never `durable`) keeps memory safe by construction rather than guessing.
   - Do NOT pass `project=` yourself — leave it unset. `wrap_session` derives the current project from `cwd` (defaulting to the live session's real process cwd) via the same `lib.ren_paths.detect_project` helper the wake-up hook's read path uses, so the L1 page lands exactly where the NEXT wake-up for this project will read it (codex D4 wiring). Non-project cwds (or a cwd that doesn't match any `wiki/projects/<slug>/`) fall through to the original global `l1/` path unchanged.
   - When a durable candidate is project-specific, it belongs under that project's `projects/<slug>/knowledge/` tree — read `projects/<slug>/schema.md` (the project's own SCHEMA document: taxonomy + conventions, issue #20 amendment) first and place the page where the taxonomy says it goes, updating the relevant hub `index.md`. Never a root-tier page for one project's fact.
   - The SAME `llm_call` also drives the judge (Task 4/0.5.0) over this session's applied writes (Task 11/0.5.2's `shortlist_pairs`, restricted via `focus_pages` to the pages `wrap_session` just applied) — no separate wiring needed. `llm_call=None` or a judge failure both degrade to `semantic_findings: []`, same fail-closed discipline as the classifier; this never blocks or delays a write.
4. **Present results to the friend:**
   - L1: "session summary saved (quarantined, unreviewed)."
   - Durable candidates: qids + pages, saved this session (revertible) unless held for a contradiction or surfaced as a promotion suggestion.
   - Gated out: verdict + one-line reason each.
   - Refused: any candidate the queue itself rejected (e.g. a planted secret) — surfaced explicitly, not silently dropped.
   - If `fail_closed` is true: tell the friend the classifier fell back to the deterministic path this run (LLM path errored) — nothing was silently promoted to durable as a result.

5. **Harvest instruction suggestions.** Call `skills.wrap.lib.harvest_suggestions(session)`. This runs the wrap-time suggestion producers (promotion candidates, doctrine shaping, wiki-health critical contradictions — the retrospective producer runs inside `/ren:retrospective`, not here) and records any new ones into `lib.suggestions`. Never raises; nothing in the end screen below depends on its return value — pending suggestions surface to the friend at the NEXT wake-up (`suggestion_line()`'s store pointer) or via `/ren:suggestions`, not on this screen.
6. **Session journal.** `wrap_session` appends one append-only summary line to the journal (pages touched, counts) — automatic, no action needed. `ren-wiki-lint` uses these lines to lint incrementally.

## End screen

After `wrap_session()` returns (and `harvest_suggestions()` has run), call `skills.wrap.lib.render_wrap_screen(wrap_result, session)` and print its output VERBATIM as the close-out — do not re-summarize or re-format it. The screen is pure presentation (spec §3.8's unified wrap surface): "What I learned" (the L1 summary's status), "Saved this session (revertible)" (this session's auto-applied entries — `auto-tier` or `model-resolved` — each with a spoken one-step revert hint, e.g. `say "undo <write_id>" to revert` — plus, when `wrap_session()`'s `decayed` list is non-empty, an "N stale page(s) archived — revertible" line for Task 17's 90-day decay sweep: up to `DECAY_MAX_PER_WRAP` stale, unrecalled, non-salient data-plane pages moved to `archive/` this wrap, never deleted), "Held — contradictions to resolve" (still-pending entries with a detected `contradicts` conflict, omitted entirely when there are none), "Possible connections (unverified)" (Task 12: judged semantic findings — `{page, with, verdict, confidence, reason}` — over this session's applied writes; purely informational, omitted entirely when empty, no apply/consolidation action attached — that's 0.5.3's job), "Live pins" (issue #25: every applied `producer="pin"` page still on disk and unarchived, ANY session, each with a one-line preview — omitted entirely when there are none; the follow-up ask is below), and "Suggestions" (pending entries targeting an instruction-plane `global/` page, or any other pending residue, rendering `- (none)` when empty), plus a refused note when the classifier gate or the secrets scan turned something away — even though risk tiers fragment the underlying writes across auto-applied and pending state, the friend sees one legible screen with **no slash-command hints anywhere**.

**Then, ask about Live pins in chat (issue #25).** If the rendered screen's "Live pins" section is present, review each listed pin against what happened this session (and what its own text says). For any pin that looks acted-on — its task done, its plan executed, its "next session" already here and past — ask the friend conversationally: "this pin looks acted-on — delete it, or keep?" On "delete", call `skills.pin.lib.correct(<page>, None, session, approved_by=<friend's handle>)` — the normal correction path (`producer="pin"`, `writer="human"`), proposed through the queue like any other write, with `approved_by` carrying the approval the friend just gave in chat: for a pin under an instruction-plane prefix (`global/`, `decisions/`, `patterns/`, `research/`) the plain DELETE would hold pending at the data-plane door and the confirmed delete would be silently swallowed; `approved_by` completes it via `queue.approve_and_apply`. Then report status honestly from the returned entry: `applied` → confirm the delete (with the `undo <write_id>` revert hint); still `pending` (a `contradicts` conflict — deliberately not auto-completed) → NEVER say deleted; report `Queued as <qid> — held` and the resolution path, mirroring `skills/pin/SKILL.md`'s held-case copy. Never delete without asking; no answer means keep. A pin that still looks live is simply left alone — this gate exists to close the loop on finished task-pins, not to nag about every pin.

**Then, ask about Suggestions in chat.** If the rendered screen's Suggestions section is non-empty, ask the friend about each one conversationally — e.g. "Suggest promoting X because \<reason + evidence> — yes/no?" Never auto-answer a suggestion. On "yes", call `queue.approve_and_apply(qid, who=<friend's handle>)`; on "no", call `queue.reject(qid, why=<their words>)`. Skipping is fine — a skipped suggestion just persists to the next session's screen.

**On request, list ALL pending suggestions.** If the friend asks to see the full pending list (e.g. after wake-up's "ask me to list them"), call `skills.wrap.lib.render_pending_list()` and print its output VERBATIM — every pending entry across all sessions, not just this one.

## Design notes

- Adapted from donor `skills/wrap/lib/classifier.py`'s KEY 0.1 finding: an LLM prompt/parse path was built but never wired in, while a deterministic heuristic quietly did all the real work. 0.2 swaps the roles on purpose — see `lib/classifier.py`'s module docstring.
- Every write here goes through `lib.memory.queue` — no direct wiki writes, no donor-style `CONTEXT.md` rewrite machinery.
