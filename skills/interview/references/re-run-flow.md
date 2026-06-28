# Re-Run Flow — `/ren:interview` on an existing identity.md

When the friend invokes `/ren:interview` and `~/.startup-framework/wiki/identity.md` already exists, the skill switches into refresh mode. Per ADR-022 § "Re-running the interview" and the user direction "knows if there's an earlier interview file or not when the skill runs."

## Step 1: Detect + parse

Read `~/.startup-framework/wiki/identity.md`. Parse the YAML frontmatter.

If parsing fails (malformed YAML), surface the error to the friend with the offending line; offer to back up the broken file (`identity.md.bak.<today>`) and re-run from scratch. Don't silently overwrite.

If `schema_version` is older than the current framework's expected schema, load the migration rules from sf-distribution's `migrations/` set first; apply additive defaults, surface diff, require approval. Then proceed to step 2 with the migrated structure.

## Step 2: Summarize current state

Print a one-screen summary so the friend remembers what's on file:

```
Current identity at ~/.startup-framework/wiki/identity.md:

  handle:               <handle>
  name:                 <name>
  phase:                <phase>
  working_style:        <working_style>
  communication_style:  <communication_style>
  languages:            <list>
  clouds:               <list>
  databases:            <list>
  strong_skills:        <list>
  growth_areas:         <list>
  tdd_attitude:         <tdd_attitude>
  contact.timezone:     <timezone>
  updated:              <date>
  schema_version:       <n>

Markdown body sections present:
  ✓ About <name>
  ✓ Background & current role
  ✓ Working style
  ✓ Tech preferences
  ✓ Strong opinions + non-goals
  ✓ What I contribute
```

(Use `—` for empty / `[]` lists.)

## Step 3: Branch — full refresh or specific fields?

Ask the friend (4-option native AskUserQuestion):

```
What would you like to refresh?

  full       — re-run all 18 questions; current values pre-filled as defaults
  sections   — pick specific sections (A: About / B: Working style /
               C: Tech / D: Opinions / E: Contribution); only those questions run
  fields     — pick specific YAML fields by name; targeted edit
  cancel     — exit without changes
```

### Branch 3a — full refresh

Run the entire question template from `question-template.md`. For each question, pre-fill the current YAML value as the default. Friend can accept defaults via "enter to keep" affordances. This is the closest to a true re-interview but lowest friction for friends who want to validate everything is still current.

### Branch 3b — sections

Show a multi-select choice (sections A/B/C/D/E — 5 options exceeds the cap, so use **category cascade** with one stage):

- Stage 1: pick first sections via 4-option set (`A | B | C | D-or-E`)
- Stage 2 (only if `D-or-E`): pick `D | E | both`
- Final = union

Run only questions in the chosen sections. Pre-fill current values.

### Branch 3c — fields

Show a text input prompt: "Which YAML fields? Comma-separated list." Examples shown: `phase, languages, tdd_attitude`. The skill maps each field name to its source question (from `question-template.md`'s `field` mapping) and runs only those questions.

If a field name doesn't map to a known question, warn and continue with the recognized ones. Don't refuse the whole run.

### Branch 3d — cancel

Exit cleanly. No changes. No diff. No file writes.

## Step 4: Defaults policy

Per ADR-022 open question #3: when re-running, the new answers DEFAULT to current values (low-friction refresh) rather than blank (forced re-affirmation).

Rationale: friends who re-run are usually adjusting one or two things, not re-evaluating everything. Defaults-to-current respects that. The full-refresh branch (3a) gives the conscientious friend the same surface but lower friction.

## Step 5: Render + diff + approve

Render the new identity.md per `output-format.md`.

Show a unified diff (file-level, not just YAML) of the proposed change vs current. Use a colored diff format if the terminal supports it; plain `---` / `+++` otherwise.

Prompt: `Apply these changes? [y/N]` — default NO.

- Yes → write the new file. Update `updated` date.
- No → exit, no change.

Mirrors the `/revise-claude-md` approval pattern. The friend always has a chance to bail before any write.

## Edge cases

- **schema_version older than current** → step 1 handles migration first; user sees migration diff separately from the refresh diff.
- **schema_version newer than current** → refuse to overwrite (the current framework version can't safely round-trip a newer schema). Recommend the friend update the framework first (`/ren:update`).
- **identity.md exists but is empty** → treat as no identity; run fresh interview (skip the refresh branch entirely).

## What the re-run flow deliberately does NOT do

- It doesn't ask the friend to confirm every defaulted answer. That's what full-refresh (branch 3a) is for; non-full refresh trusts the friend's intent.
- It doesn't auto-bump `framework_version` in the YAML. Only `updated` changes. `framework_version` is rewritten by `/ren:install` Stage 5 (it tracks the wiki skeleton's version, not per-file edits).

## Cross-references

- ADR-022 § "Re-running the interview" — source spec
- `output-format.md` — what gets rendered
- `/ren:install` Stage 4 — first-time invocation path (skips this whole flow)
