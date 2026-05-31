---
title: "/sf:wrap signal-threshold classifier criteria"
type: skill-reference
parent_skill: sf-wrap
version: 0.1.0
date: 2026-05-28
---

# Signal-threshold classifier — the discipline that keeps the wiki clean

Per ADR-009: **most sessions produce ZERO wiki edits.** This is not a bug. It is the discipline. The wiki's value is its high signal-to-noise ratio; that ratio survives only if routine work doesn't get promoted.

This document defines the criteria the classifier evaluates against a session transcript. The classifier returns ONE of seven labels (multi-label allowed).

## The default label is `none`

When in doubt, return `none`. The bias is conservative. A wiki page never written is recoverable next session (just invoke `/sf:wrap` again and re-evaluate). A wiki page written incorrectly is hard to retract gracefully (per ADR-021's "deletion is hard" reality).

**Heuristic**: ask yourself "would the next session's wake-up be better off loading this?" If the answer is "maybe" or "not sure," return `none`. Only "yes, clearly" warrants a label.

## The seven labels

### 1. `decision`

**Triggers**: a real architectural, scope, or tooling choice was made — one that future sessions need to know to avoid re-litigating.

**Positive examples**:
- "We're choosing Postgres over MongoDB because of <reason>"
- "Dropping the OAuth flow; using magic-link only for v1"
- "Standardizing on uv for all Python projects in this app"
- "Locked the API contract for /v1/auth/login — no breaking changes pre-v2"

**Negative examples** (NOT decisions):
- "Fixed the typo in the login button" → routine
- "Refactored the auth service" → routine unless the refactor establishes a new pattern
- "Added a unit test" → routine
- "Tried X, didn't work, went back to Y" → only a decision if the team SETTLED on Y deliberately; trial-and-error is routine

**Wiki target**: `wiki/projects/<active>/decisions/<short-slug>.md` + STATE.md "Recent decisions" section update.

### 2. `pattern`

**Triggers**: a reusable solution emerged that other projects (or future sessions on this one) would benefit from.

**Positive examples**:
- "The way we structured the form-validation hook works really well — let's codify it"
- "The auth-middleware composition pattern from this session is reusable"
- "This webhook-idempotency pattern should apply across all our integrations"

**Negative examples**:
- "We use Tailwind for styling" → not a pattern; that's a stack choice (`stack_change` at best, or just CLAUDE.md territory)
- "We use git" → trivial

**Wiki target**: `wiki/projects/<active>/patterns/<short-slug>.md` (or master `wiki/patterns/` if cross-project).

### 3. `lesson`

**Triggers**: a non-obvious learning that, if forgotten, would cost time again. Often called a "gotcha."

**Positive examples**:
- "Stripe webhook payloads include a trailing whitespace in `metadata.email` — strip before lookup"
- "Next.js's `revalidate` doesn't fire on edge runtime; learned the hard way"
- "Supabase RLS policies require explicit `using` AND `with check` clauses"

**Negative examples**:
- "TypeScript caught my missing import" → routine; tools doing their job is not a lesson
- "The test failed because I forgot to mock the timer" → routine debugging

**Wiki target**: STATE.md "Recent learnings" section OR the skill's own `learnings.md` if the lesson is tooling-specific (e.g., a Claude Code interaction quirk).

### 4. `stack_change`

**Triggers**: the project's tech stack shifted in a way that affects future work.

**Positive examples**:
- "Migrating from Pages Router to App Router this session"
- "Switched from raw OpenAI calls to the Anthropic SDK"
- "Added Inngest for background jobs; removing the in-process scheduler"

**Negative examples**:
- "Updated React 18 → 18.3" → patch bump; not a stack change unless API surface differs
- "Renamed a file" → routine

**Wiki target**: STATE.md "Active work" section + possibly REQUIREMENTS.md if non-functional reqs shift (e.g., adding Inngest changes the runtime topology).

### 5. `milestone`

**Triggers**: a ROADMAP milestone is now complete, or a new phase starts.

**Positive examples**:
- "Phase 1 (MVP) is done; entering Phase 2 (beta)"
- "Auth feature shipped to staging — ROADMAP item ✓"

**Negative examples**:
- "Sub-task done within an ongoing milestone" → not a milestone-level event
- "Branch merged to main" → routine unless it represents the milestone

**Wiki target**: ROADMAP.md (check the box / move the "we are here" marker).

### 6. `purpose_shift`

**Triggers**: VERY RARE. The project's purpose, scope, or target user changed.

**Positive examples**:
- "Pivoting from B2B to B2C"
- "Scope expanded to include the dashboard; no longer just the API"
- "Target users shifted from indie developers to enterprise teams"

**Negative examples**:
- Adding a feature → not a purpose shift; the feature serves the existing purpose
- Changing pricing → not a purpose shift; that's go-to-market

**Wiki target**: PROJECT.md (the rarely-touched purpose doc).

### 7. `none`

**Default**. The session was routine: coding, debugging, exploring, fixing — but no Architectural Decision, Reusable Pattern, Non-Obvious Lesson, Stack Change, Milestone, or Purpose Shift.

**Outcome**: zero wiki edits except CONTEXT.md (which is always rewritten as the next-session pointer). Most sessions land here — that is the discipline, not a bug.

## Multi-label is allowed but rare

A session can produce e.g. `decision` + `lesson` (the decision was made AND a related gotcha was found). In practice, multi-label is uncommon — sessions usually have one dominant theme.

When multi-labeling, treat each label independently in the diff plan. Don't conflate.

## How the classifier runs

The **default** classifier (`lib/classifier.py:classify()`) is a conservative
DETERMINISTIC heuristic — **EXPERIMENTAL** (ADR-031 bike-method). It scans the
combined transcript (session log + `/sf:note` pins) for the deliberate signal
phrases that the criteria above describe, with a hard bias to `none`:

- **Pins dominate** — a friend who explicitly `/sf:note`-pinned something is
  signalling intent, so a single deliberate keyword in a pin fires its label;
  the raw session log needs a full deliberate phrase.
- It **never raises** — every failure mode degrades to `none`.
- It proposes `candidate_artifacts` only for fired `decision`/`pattern` (the
  page-creating labels); multi-label is capped at ~2.
- Limits: phrase-driven, no semantic understanding — it can miss subtly-phrased
  signal and rarely over-fire on a deliberate keyword used casually. That is the
  EXPERIMENTAL caveat; the LLM path below is the future upgrade.

## Classifier prompt template (the future LLM path)

`build_classifier_prompt()` + `parse_classifier_output()` ship as composable
primitives for a future LLM-backed classifier (not wired into the default
deterministic path). When that path is enabled, the LLM evaluates the session
against this prompt:

```
Given the session transcript below, classify the session's signal level
according to the criteria in references/signal-threshold.md.

Output JSON only:
{
  "labels": ["decision" | "pattern" | "lesson" | "stack_change" | "milestone" | "purpose_shift" | "none"],
  "reasoning": "<1-3 sentences justifying the label(s)>",
  "candidate_artifacts": [
    {
      "label": "<one of the 7>",
      "proposed_title": "<short slug, kebab-case>",
      "proposed_summary": "<one paragraph, ≤300 words>",
      "target_file": "<wiki path>"
    }
  ]
}

Bias toward "none". Only escalate if the criteria are CLEARLY met.
The transcript follows:
---
<TRANSCRIPT>
```

## Why this discipline matters

From ADR-009:
> "Default discipline: most sessions produce ZERO wiki edits. Most work is routine. Only sessions with genuine signal touch the wiki. Per ADR-004's general rule: 'would I want this loaded next session by default? If no, it doesn't go in.'"

The wake-up hook's value is its 3–5K token budget — if the wiki accumulates routine entries, the wake-up's context-load discipline collapses. Saying "no" to most sessions is how we keep the wake-up small and the wiki searchable.
