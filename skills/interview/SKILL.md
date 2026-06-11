---
name: interview
description: |
  Use when the friend invokes /sf:interview, or when /sf:install Stage 4
  needs to run the identity bootstrap. Conducts an AI-driven, ~17-18
  question interview across 5 sections (About you / Working style / Tech
  preferences / Opinions+non-goals / Contribution) and writes
  ~/.startup-framework/wiki/identity.md (hybrid YAML frontmatter + markdown
  body). Detects existing identity.md and offers full-refresh vs
  specific-field updates.
version: 0.1.0
license: MIT

contract:
  required_outputs:
    - "~/.startup-framework/wiki/identity.md (hybrid YAML+markdown matching the friend-profile schema)"
  budgets:
    turns: 36                  # ~2 per question (ask + capture); generous slack
    files_written: 1           # identity.md
    duration_seconds: 900      # ~15 minutes; target is 10
  permissions:
    read:
      - "~/.startup-framework/wiki/identity.md"
      - "skills/sf-interview/references/**"
    write:
      - "~/.startup-framework/wiki/identity.md"
    execute: []
  completion_conditions:
    - "identity.md exists with frontmatter matching the friend-profile schema"
    - "All 18 required fields are present OR explicitly listed in skipped_questions"
    - "Handle is kebab-case (^[a-z][a-z0-9-]*$)"
    - "phase is one of: ideation | building | shipping | other"
    - "If communication_style == emoji-free, no emoji in the markdown body"
  output_paths:
    - "~/.startup-framework/wiki/identity.md"

tags: [onboarding, identity, interview]
related_skills: [sf-install, sf-bootstrap-project]
references_required:
  - "references/question-template.md"
  - "references/output-format.md"
  - "references/ask-user-question-pagination.md"
references_on_demand:
  - "references/re-run-flow.md"
---

# sf-interview

Friend's identity-bootstrap interview. Runs once at install, re-runnable anytime via `/sf:interview`. Per ADR-022.

## When to use this skill

- Friend invokes `/sf:interview` (canonical trigger).
- `/sf:install` Stage 4 invokes this skill as a sub-step.
- Friend says "let's update my identity" or "I want to refresh my preferences" — confirm and run.

## When NOT to use this skill

- The friend's wiki at `~/.startup-framework/wiki/` doesn't exist yet. Refuse and direct to `/sf:install` (Stage 5 creates the wiki skeleton; this skill writes inside it).
- The friend wants to edit ONE field. Suggest direct YAML edit of `~/.startup-framework/wiki/identity.md` — the interview is for full passes or section-by-section refreshes, not single-field churn.

## How to use this skill

### 1. Detect existing identity

Check whether `~/.startup-framework/wiki/identity.md` exists.

- **Absent** → run the full interview from scratch. Load `references/question-template.md` and go to step 2.
- **Present** → load `references/re-run-flow.md` and follow the refresh branch (skip step 2; jump to step 3 with refreshed defaults).

### 2. Run the 18-question template

Load `references/question-template.md` for the full question list. Five sections, A–E:

| Section | Topic | Questions |
|---|---|---|
| A | About you | 1–5 |
| B | Working style | 6–9 |
| C | Tech preferences | 10–14 |
| D | Opinions + non-goals | 15–17 |
| E | Contribution | 18 |

Per question, use the input strategy noted in `references/ask-user-question-pagination.md`. The strategies are: native AskUserQuestion (≤4 options), pagination (split into two prompts), category cascade (two-stage drill), combine (collapse two semantic axes into one), open-ended fallback (always-offered escape hatch on multi-select).

**Handle prepopulation (Stage-4 invocation case):** when `/sf:install` Stage 4 runs this skill, the orchestrator has already collected a tentative handle in its Stage 3 mini-prompt. The install-state checkpoint surfaces it via `proposed_handle`. The interview pre-fills Q1's handle answer with that value and asks the friend to confirm or change.

**Skipping:** any question may be skipped. Record the question ID in the `skipped_questions` frontmatter list. Don't push skipped-question reminders; trust the friend.

### 3. Render output

Load `references/output-format.md` for the canonical hybrid YAML+markdown structure.

Write `~/.startup-framework/wiki/identity.md`. Schema MUST match the friend-profile schema (v1). On re-run, show a diff and require approval before write (mirrors `/revise-claude-md`'s pattern).

### 4. Confirm + exit

Print a one-screen summary:

```
✓ identity.md written at ~/.startup-framework/wiki/identity.md

Run /sf:interview anytime to refresh. Edit ~/.startup-framework/wiki/identity.md
directly for one-off field changes.
```

## Anti-patterns

- **Don't push opinions during the interview.** Ask, capture, move on. The friend's choice — even an unconventional one — is recorded as-is.
- **Don't ask the same question twice in a session.** If a multi-stage cascade lands the friend on a sub-question they've already implicitly answered, skip it.
- **Don't write the local file partway through.** Interview to completion in memory, then write once at step 3. A crash mid-interview leaves the old file intact, not a half-written one.
- **Don't seed defaults from the framework developer's own profile.** Defaults come from sensible neutral choices (e.g., `working_style: balanced`, `tdd_attitude: case-by-case`) — never from the founder's settings.

## Eval expectations (see `eval/eval.json`)

- Fresh-interview test: all 18 frontmatter fields present after a clean run
- Refresh-existing test: re-running on a populated identity.md shows diff and requires approval
- Emoji-free-respect test: setting `communication_style: emoji-free` results in zero emoji in the markdown body
- Handle-validation test: rejecting non-kebab-case handles
