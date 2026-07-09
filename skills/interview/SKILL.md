---
name: interview
description: |
  Use to build or update the friend's identity + working-style profile.
  Triggers on the /ren:interview slash command, or delegated to from
  /ren:install's onboarding flow. Asks ONLY from a capped, skippable question
  list — every question is optional, the whole interview can be skipped, and
  every unanswered field gets a sane default. No venture/founder questions in
  this default path.
version: 0.3.5
license: MIT

framework_version: "0.3.5"
schema_version: 1
type: skill
execution_tier: judgment

contract:
  required_outputs:
    - "One Proposal submitted to lib.memory.queue (ADD or UPDATE identity.md), auto-applied through the data-plane door"
    - "Confirmation line naming the queue id and which fields were answered vs. defaulted"
  budgets:
    turns: 1
    files_written: 0
    duration_seconds: 60
  permissions:
    read:
      - "~/.renos/wiki/**"
    write: []
    execute: []
  completion_conditions:
    - "A QueueEntry exists at state_dir()/queue/<qid>.json with status=applied, page=identity.md"
    - "Fewer than or equal to skills.install.lib.QUESTION_BUDGET questions were asked"
  output_paths: []

tags: [producer, onboarding, interview, identity, queue]
related_skills: [install, pin]
references_required: []
references_on_demand: []
---

# interview

Builds or updates the friend's identity page. Asks from `skills.interview.lib.QUESTIONS` — a fixed, capped list (≤ `skills.install.lib.QUESTION_BUDGET`, currently 10) — in order, and stops. Nothing here is a pipeline or a branching questionnaire; it's a flat list, every entry independently skippable, with the whole thing skippable too.

## When to use this skill

- Friend invokes `/ren:interview` directly, any time — first run or a re-run to update answers.
- `/ren:install`'s onboarding flow delegates to this skill at its interview stage.

## When NOT to use this skill

- Friend wants the founder/venture arc — **not offered by this skill.** Say so in one line: "a founder/venture profile is an optional later module, not part of this interview" — and stop there. Do not ask venture questions, do not offer to enable the module from here.
- Friend just wants to pin one fact → `/ren:pin`, not a full interview.

## Behavior

1. State up front, plainly: every question below is optional, and the friend can say "skip to coding" (or equivalent) at any point to stop the whole interview — whatever wasn't answered gets a sane default, no exceptions.
2. Ask each entry in `skills.interview.lib.QUESTIONS`, in order, using its `options` (if any) to offer a small closed set — free text otherwise. Never exceed the list; never invent additional questions beyond it.
3. Collect a `dict` of `{key: answer}` for whatever was actually answered (skipped keys simply absent, or `None`).
4. Call `skills.interview.lib.save_identity(answers, session)`. This queues an `ADD` (fresh identity) or `UPDATE` (re-run) of `identity.md`, `writer="human"` — the interview is the friend's own input, always human-provenance — and auto-applies immediately through the data-plane door (`identity.md` is a non-global page, v2.2 pivot).
5. Confirm: the queue id, and a one-line breakdown of which fields were answered vs. defaulted (mirrors what `render_identity`'s `skipped_questions` field records).

## Design notes

- Donor's 18-question + 5-question-venture-arc template is the field-set donor; RenOS 0.2 keeps 10 of those fields as actual questions (name, handle, languages, working_style, communication_style, plans_before_code, tdd_attitude, strong_skills, growth_areas, contact) and lets the rest (package_managers, clouds, databases) default silently — the zero-doctrine guarantee only requires that everything unasked still gets a sane default, not that everything gets asked.
- The venture module's templates still ship under `wiki-skeleton/modules/venture/` for a friend who explicitly wants that arc later — this skill just never routes there on its own.
