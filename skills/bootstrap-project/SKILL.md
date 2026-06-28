---
name: bootstrap-project
description: |
  Use when the friend wants to start a new project sub-wiki under
  ~/.startup-framework/wiki/projects/<project-name>/. Triggers on the
  /ren:bootstrap-project slash command. Creates the full ADR-014 taxonomy
  (PROJECT.md, REQUIREMENTS.md, ROADMAP.md, STATE.md, CONTEXT.md, index.md,
  log.md + research/decisions/patterns/ subdirs) as empty placeholders,
  then hands off to either manual fill or Superpowers brainstorming.
version: 0.1.0
license: MIT

contract:
  required_outputs:
    - "A complete project sub-wiki at wiki/projects/<project-name>/ matching ADR-014 taxonomy"
    - "A one-line init entry appended to the project's log.md"
    - "Optional: an entry added to the master wiki index pointing at the new sub-wiki"
  budgets:
    turns: 4
    files_written: 12
    duration_seconds: 60
  permissions:
    read:
      - "~/.startup-framework/wiki/**"
      - "skills/bootstrap-project/templates/**"
      - "skills/bootstrap-project/references/**"
    write:
      - "~/.startup-framework/wiki/projects/<project-name>/**"
      - "~/.startup-framework/wiki/index.md"
    execute: []
  completion_conditions:
    - "All 7 top-level taxonomy files exist at the target path"
    - "All 3 subdirectories (research, decisions, patterns) exist with .gitkeep markers"
    - "log.md contains the init entry with today's date"
    - "User has been prompted to fill PROJECT.md or invoke brainstorming"
  output_paths:
    - "~/.startup-framework/wiki/projects/<project-name>/"

tags: [onboarding, project, wiki, bootstrap]
related_skills: [install, interview, brainstorming]
references_required:
  - "references/template-loader.md"
  - "references/taxonomy-templates.md"
references_on_demand:
  - "references/brainstorm-handoff.md"
---

# bootstrap-project

Stamps the ADR-014 per-project sub-wiki taxonomy under the friend's local wiki at `~/.startup-framework/wiki/projects/<project-name>/`. Per ADR-015 §"`/ren:bootstrap-project <name>` command".

## When to use this skill

- Friend invokes `/ren:bootstrap-project <project-name>` (the canonical trigger)
- A friend says "I want to start a new project called X" — confirm with them, then run this skill
- During `/ren:install` Stage 7 walkthrough, when introducing the daily-loop commands and the friend wants to see one work end-to-end

## When NOT to use this skill

- The target project sub-wiki already exists at `wiki/projects/<project-name>/`. Refuse with a clear message and (if the friend confirms) offer to add only missing files via additive diff. Never overwrite.
- The master wiki at `~/.startup-framework/wiki/` doesn't yet exist. That's `/ren:install` Stage 5's job, not this skill's. Tell the friend to run `/ren:install` first.
- The project name isn't kebab-case (`^[a-z][a-z0-9-]*$`). Re-prompt for a valid name.

## How to use this skill

### 1. Parse arguments

Slash command: `/ren:bootstrap-project <project-name> [--description "<text>"] [--title "<text>"]`

- `<project-name>` (positional, required): kebab-case identifier. Becomes the directory name.
- `--description "<text>"` (optional): one-paragraph blurb prepopulating PROJECT.md's intro. Default: blank placeholder.
- `--title "<text>"` (optional): human-readable title. Default: kebab-name expanded with spaces and capitalized (e.g. `sidecar-v2` → `Sidecar V2`).

### 2. Pre-flight checks

- Verify `~/.startup-framework/wiki/` exists and contains `index.md` + `log.md`. If not, refuse and recommend `/ren:install`.
- Verify `~/.startup-framework/wiki/projects/<project-name>/` does NOT exist. If it does, switch to additive-diff mode (load `references/template-loader.md` § "Additive-diff mode" and follow it).
- Verify the project name matches the kebab-case regex.

### 3. Load the friend's handle

Read `~/.startup-framework/wiki/identity.md` frontmatter. Extract `handle:` (kebab-case string). Used for log attribution and authorship metadata.

If `identity.md` doesn't exist (e.g. friend skipped `/ren:interview`): fall back to handle = "unknown" and emit a warning suggesting they run `/ren:interview` to populate it.

### 4. Run the template loader

Load `references/template-loader.md` and follow its procedure with:

- Template root: `skills/bootstrap-project/templates/`
- Target root: `~/.startup-framework/wiki/projects/<project-name>/`
- Placeholder bindings:
  - `{{project_name}}` ← kebab-case name from argv
  - `{{project_title}}` ← `--title` or derived
  - `{{project_description}}` ← `--description` or "_TBD — fill in PROJECT.md._"
  - `{{handle}}` ← from identity.md (or "unknown")
  - `{{today}}` ← ISO YYYY-MM-DD
  - `{{framework_version}}` ← from the plugin registry

All template files use `write_rule: copy_if_missing`. Subdirectories use `create_if_missing`.

### 5. Update master wiki

Append a single line to `~/.startup-framework/wiki/index.md` under the `## Projects` section:

```
- [<project_title>](projects/<project_name>/index.md) — <one-line summary or "Bootstrapped {{today}}; first session pending">
```

Append a single line to `~/.startup-framework/wiki/log.md`:

```
## [{{today}}] init | Project sub-wiki bootstrapped for <project_name>
```

Both are additive; neither overwrites existing content. If the `## Projects` section header doesn't exist in `index.md`, refuse to guess — surface the issue, recommend re-running `/ren:install --redo-stage 5`.

### 6. Hand off

After all writes complete, prompt the friend with the choice documented in `references/brainstorm-handoff.md`:

- Option A: open `PROJECT.md` in their editor and fill in purpose / users / success criteria by hand.
- Option B: invoke Superpowers' `brainstorming` skill to interview them about the project — the AI populates PROJECT.md + REQUIREMENTS.md draft based on the conversation.
- Option C: defer; come back later. Print the file paths so they can find them.

Print the four paths the friend will most likely want first: `PROJECT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `CONTEXT.md`.

## Anti-patterns

- **Don't ask the friend to confirm every file write.** The skill is a stamp, not an interview. One confirm at the end is enough. The interview is `/ren:interview` (a different skill).
- **Don't seed templates with framework-development examples.** Per ADR-017 the friend's wiki starts EMPTY. PROJECT.md gets a placeholder paragraph, not a citation of a real project we (the framework devs) shipped.
- **Don't extend the taxonomy.** ADR-014 fixed the 5 + 2 + 3 taxonomy (5 top-level pages, 2 log/index, 3 subdirs). Adding more here drifts from the standard. If a new page is genuinely needed, file an ADR amendment first.

## Eval expectations (see `eval/eval.json`)

- All 7 files + 3 dirs present at target path after a successful run
- `log.md` contains init entry with today's date
- Re-running on existing project name does NOT overwrite; offers additive diff
- Kebab-case name validation rejects invalid input
- No template file contains forbidden dev-wiki strings (cross-check with `wiki-skeleton/tests/forbidden-substrings.txt`)
