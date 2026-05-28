# Brainstorm Handoff — post-bootstrap prompt

After the bootstrap loader finishes writing the taxonomy, the skill prompts the friend with a three-option choice. This doc spells out the prompt copy and the rationale for each option.

## When this fires

After Step 6 of `SKILL.md`. All 7 files + 3 dirs have been written; `master/index.md` and `master/log.md` have been touched; the project sub-wiki is structurally complete but the content placeholders are blank.

## The prompt

```
✓ Project sub-wiki bootstrapped at ~/.startup-framework/wiki/projects/<project_name>/

  PROJECT.md       — what this is and why it exists
  REQUIREMENTS.md  — what must be true at done
  ROADMAP.md       — phases + milestones
  STATE.md         — right-now state
  CONTEXT.md       — what you're working on next

How do you want to fill these in?

  A. Fill in PROJECT.md and REQUIREMENTS.md by hand right now.
  B. Run Superpowers' `brainstorming` skill — it'll interview you about
     the project and draft PROJECT.md + REQUIREMENTS.md from your answers.
  C. Defer. Come back to it later.
```

## Per-option behavior

### A. Manual fill

- Print the four most-likely-edited paths (absolute):
  - `~/.startup-framework/wiki/projects/<name>/PROJECT.md`
  - `~/.startup-framework/wiki/projects/<name>/REQUIREMENTS.md`
  - `~/.startup-framework/wiki/projects/<name>/ROADMAP.md`
  - `~/.startup-framework/wiki/projects/<name>/CONTEXT.md`
- Suggest the friend run `/sf:wrap` when they're done so the changes get a log entry.
- Exit cleanly.

### B. Hand off to Superpowers' `brainstorming` skill

- Confirm the brainstorming skill is installed. Per ADR-006 it's part of the Superpowers plugin and is universal (not phase-gated).
- Pass an opening context line like:
  > "Bootstrapping a new project: `<project_name>`. Help me populate PROJECT.md (purpose, users, success criteria, constraints) and a draft REQUIREMENTS.md (functional / non-functional / out-of-scope). The files exist as placeholders — they need real content."
- Let the brainstorming skill run its own interview. It will write to PROJECT.md / REQUIREMENTS.md when done.
- After it finishes, suggest `/sf:wrap` to log the consolidation.

### C. Defer

- Print the four paths (same as Option A) so the friend can find the files later.
- Suggest: "When you're ready, run `/sf:bootstrap-project <name>` again — it'll detect the existing sub-wiki and offer additive-diff for any new template files in newer framework versions, but won't overwrite your in-progress content."
- Exit cleanly.

## What this skill should NOT do

- **Do not invoke brainstorming silently.** Always present the choice. Brainstorming consumes meaningful tokens + the friend's attention; an explicit opt-in matters.
- **Do not write PROJECT.md content based on guesses.** If the friend chose Option C and the bootstrap had `--description "..."`, that description has already prepopulated PROJECT.md's intro paragraph during the loader run. Don't add more.
- **Do not refuse to exit if the friend declines all three.** "Defer" is a valid landing state. The bootstrap is structurally complete; that's the deliverable.

## Why this is a separate reference doc

The SKILL.md is at <200 lines per ADR-011 progressive disclosure. The brainstorm-handoff prompt copy and the per-option logic are loaded on demand only when the loader's Step 6 trigger fires. Most invocations of this skill will exercise Option A or C (manual / defer) and not need the brainstorming-specific guidance.
