---
name: ingest-project
description: |
  Use when the solo builder wants to bring an EXISTING project (one with real
  code/git history that predates the framework) into their wiki — turning it
  into a first-class citizen on par with a freshly bootstrapped project, but
  with pages populated from what's actually in the repo. Triggers on the
  /ren:ingest-project slash command (optional [path], --depth standard|light|deep,
  --name <kebab>). A read-only scanner mines the project and emits facts; the
  LLM drafts the full ADR-014 sub-wiki; one preview, one approval, then additive
  writes. NEVER modifies the user's project files. For brand-new empty projects
  use /ren:bootstrap-project instead.
version: 0.1.0
license: MIT

framework_version: "1.0.0"
schema_version: 1
type: skill

contract:
  required_outputs:
    - "A populated project sub-wiki at wiki/projects/<name>/ matching ADR-014 taxonomy, drafted from the real repo"
    - "A one-line registration in master wiki/index.md under '## Projects'"
    - "A one-line init entry in master wiki/log.md"
    - "An init + backfill entry set in the project's own log.md"
  budgets:
    turns: 8
    files_written: 10
    duration_seconds: 180
  permissions:
    read:
      - "<project-path>/**"
      - "~/.startup-framework/wiki/**"
      - "skills/ingest-project/references/**"
      # The bootstrap template shapes (frontmatter / H1 tables) are embedded in
      # references/page-mapping.md, so the templates dir is never opened at runtime.
    write:
      - "~/.startup-framework/wiki/projects/<name>/**"
      - "~/.startup-framework/wiki/index.md"
      - "~/.startup-framework/wiki/log.md"
    execute:
      - "scripts/scan.py"
  completion_conditions:
    - "All 7 top-level taxonomy files exist at the target path, populated from facts (or honest placeholders)"
    - "All 3 subdirectories (research, decisions, patterns) exist with .gitkeep markers"
    - "Master index.md has exactly one bullet under '## Projects' linking to projects/<name>/index.md (idempotent on re-run)"
    - "Master log.md has exactly one '## [<today>] init | Project sub-wiki ingested for <name>' entry (idempotent on re-run)"
    - "No file inside the user's project directory was created, modified, or deleted"
  output_paths:
    - "~/.startup-framework/wiki/projects/<name>/"

# Note: the ~/ paths above are illustrative. The real path is resolved via
# wiki_path() from lib/sf_paths.py, same as bootstrap-project.
# files_written: 7 pages + 3 .gitkeep = 10 (standard/light depth).
# --depth deep may add <=N decisions/research summary files; those are
# outside the v1 binary-eval scope.

tags: [onboarding, project, wiki, ingest, brownfield, read-only]
related_skills: [bootstrap-project, install, interview, brainstorming]
references_required:
  - "references/extraction-spec.md"
  - "references/page-mapping.md"
references_on_demand: []
---

# ingest-project

Turns an **existing** project into a first-class framework citizen. The builder
goes into an old project dir, runs `/ren:ingest-project`, and gets a populated
ADR-014 sub-wiki + master-wiki registration — drafted from the repo's real
README, stack, docs, and git history. Read-only on the project; one approval
before any write.

This is the **brownfield** counterpart to `bootstrap-project` (which stamps an
empty skeleton for a brand-new project).

## When to use this skill

- Builder invokes `/ren:ingest-project [path]` (default path = cwd)
- Builder says: "add this existing project to my wiki", "ingest my old repo",
  "bring sidecar into the framework" — confirm scope once, then run

## When NOT to use this skill

- The project is brand-new / empty → use `/ren:bootstrap-project <name>`
- The master wiki doesn't exist yet → run `/ren:install` first
- The builder wants a read-only retrospective on sessions → `/ren:insights`
- The target sub-wiki already fully exists → refuse and offer additive-diff for
  any missing pages only (never overwrite what's there)

## Flags

`--depth` is an **Interpret-stage** control, not a scan control: the scanner
performs the same full read-only scan (fixed caps) regardless of `--depth`; the
flag is consumed by Stage 3 (Interpret) to decide how aggressively to draft.

| Flag | Effect |
|---|---|
| `[path]` (positional) | Project directory to ingest. Default: current working directory. |
| `--depth standard` (default) | Full page drafting from the facts JSON. |
| `--depth light` | Leaner drafting — lean toward `_TBD_` placeholders over inference. |
| `--depth deep` | Standard + summarize existing ADRs/`docs/` into `decisions/`/`research/` with backlinks (per `references/page-mapping.md`). |
| `--name <kebab>` | Override the derived project name (must match `^[a-z][a-z0-9-]*$`) |

## Procedure

### Stage 1 — Pre-flight

Resolve the wiki via `lib/sf_paths.py` `wiki_path()`. If
`wiki_path()/index.md` is absent, refuse and recommend `/ren:install`.

Resolve the project path (default cwd). If it doesn't exist or isn't a
directory, refuse with a clear message.

Read the handle via `lib/sf_paths.py` `handle()`. On `HandleNotConfiguredError`,
fall back to `unknown` and warn (suggest `/ren:interview`).

### Stage 2 — Scan (read-only)

Run the scanner:

```
python3 scripts/scan.py "<project-path>"
```

The scanner prints the facts JSON on stdout and writes nothing — it never reads
secrets or oversized files (see `references/extraction-spec.md` for all safety
bounds). The scan is always the same full read-only pass; `--depth` does not
change scanning (it is consumed later, in Stage 3).

**After scan, handle the three conditional branches:**

- If `looks_like_project` is `false`: warn the builder ("This doesn't look like
  a project — no manifest, git repo, or README found. Ingest anyway?") and
  confirm before continuing.
- If `size_signals.recommend_subagents` is `true`: tell the builder the repo is
  large and offer two options: (a) fan out code-skim subagents (one per top dir),
  or (b) draft at `--depth light` (leaner pages, more placeholders). The scan
  itself is already bounded by fixed caps either way.
- Resolve the project name: use `--name` if given (validate kebab-case regex
  `^[a-z][a-z0-9-]*$`; re-prompt if invalid); otherwise use
  `name_candidates.chosen`.

### Stage 3 — Interpret (draft the pages)

Read `references/page-mapping.md` and draft all 7 ADR-014 pages in memory from
the facts JSON. Match the bootstrap templates' frontmatter and section headers
exactly.

**No invention:** thin evidence → keep the placeholder marker
(`- _TBD_ — <reason>; fill in.`), never fabricate content. A claim may appear
only if its evidence is present in the facts JSON. See the no-invention drafting
rules in `references/page-mapping.md` for the precise placeholder form.

### Stage 4 — Preview (ONE approval gate)

Determine the additive manifest: check which target paths already exist under
`wiki/projects/<name>/` (follow `../bootstrap-project/references/template-loader.md`
additive-diff semantics — missing pages are listed for writing, existing pages
are listed as `skipped (exists)`).

Show the builder **one** preview in this form:

```
Ingest plan for <name> (from <project-path>):
  target:  ~/.startup-framework/wiki/projects/<name>/
  pages:   PROJECT.md      (~28 lines, high confidence)
           REQUIREMENTS.md (~12 lines, placeholder — thin evidence)
           ROADMAP.md      (~9 lines, from 2 git tags)
           STATE.md        (~14 lines, from recent commits)
           CONTEXT.md      (~6 lines)
           index.md        (catalog)
           log.md          (18 backfilled monthly entries + init)
  master:  + wiki/index.md  "## Projects" registration line
           + wiki/log.md    init line
  sample:  <first ~10 lines of PROJECT.md>

Write these? [y / edit / abort]
```

- `y` → proceed to Stage 5 (Write).
- `edit` → let the builder adjust a page or the name in conversation; re-show
  the preview after each adjustment.
- `abort` → exit clean, write nothing.

This is the **only write gate** (design principle: scan → preview → one
approval).

### Stage 5 — Write (additive-only)

Reuse `../bootstrap-project/references/template-loader.md`'s **write rules
only** — `copy_if_missing` (files) / `create_if_missing` (dirs) / never-overwrite.
**Skip its placeholder-expansion step** (template-loader Step 5): the pages
arrive already fully drafted from Stage 3's facts, so there is no `{{var}}`
substitution to perform here.

1. `mkdir -p` the target sub-wiki + `research/`, `decisions/`, `patterns/`
   subdirectories, each with a `.gitkeep` marker.
2. Write each page **only if its target file does not already exist** (additive;
   never overwrite). On a re-run, only missing pages are written.
3. Append the master registration lines **idempotently**:
   - Under `## Projects` in `wiki/index.md`:
     ```
     - [<project_title>](projects/<name>/index.md) — Ingested <today>; <one-line description or "_TBD_">
     ```
     Skip if a line containing `projects/<name>/index.md` already exists under
     `## Projects` (path match — robust to a re-run where the description was
     edited). If the `## Projects` header is absent, refuse to guess — surface
     the issue and recommend re-running `/ren:install --redo-stage 5`.
   - Append to `wiki/log.md`:
     ```
     ## [<today>] init | Project sub-wiki ingested for <name>
     ```
     Skip if an identical line already exists (idempotent).
4. Print a per-file summary (`wrote` / `skipped (exists)`) for every file.

### Stage 6 — Hand off

Print the four key paths the builder will most likely want first:
`PROJECT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `CONTEXT.md`.

Suggest the builder skim `PROJECT.md` to verify the top-level description, then
run `/ren:wrap` at the end of their next session to keep `STATE.md` and
`CONTEXT.md` current.

### Code-map seeding (additive; graceful)

After the four key paths, build the project's code-map so the builder starts with
a navigation index:

- If `lean-ctx` is available, run `/ren:code-map "<project-path>" --name <name>`
  (writes only to the plugin-data cache — the project + wiki are untouched).
- If `lean-ctx` is absent, print one line: "Code-map skipped (lean-ctx not
  installed); run /ren:code-map later." Never fail ingest over this.

## Edge cases

| Situation | Behavior |
|---|---|
| Path is not a directory | Exit 2 with a clear error. Do not fall back to cwd. |
| Name collision — `wiki/projects/<name>/` already fully exists | Refuse to overwrite. Show which files exist; offer additive-diff (write only missing pages). |
| Empty repo (no commits) | Scanner returns `git.no_commits: true`. `log.md` gets the `init` entry only (no backfilled monthly entries). |
| Non-git directory | `git.is_repo: false`. Pages drafted without git-derived content; more placeholders. |
| `looks_like_project: false` | Warn and ask for confirmation before continuing (see Stage 2). |
| `size_signals.recommend_subagents: true` | Warn the builder and offer light-depth or subagent fan-out (see Stage 2). |
| `--name` override fails kebab-case validation | Re-prompt; do not proceed with an invalid name. |

## Anti-patterns

- **Never write into the user's project directory.** Read-only on the project,
  always. The scanner enforces this; the skill must too. No marker files, no
  "ingested" stamps, no `.framework` sidecar directories in the repo.
- **Never overwrite an existing sub-wiki page.** Additive-diff only, per
  `template-loader.md`. There is no `--force` mode.
- **Never invent content.** Thin evidence → placeholder marker. The framework's
  credibility depends on honest pages (see the no-invention rule in
  `references/page-mapping.md` and the analogous principle in `insights`).
- **Don't touch the master wiki beyond the 2 registration lines.** No
  `patterns/`, no `identity.md` (that belongs to `/ren:interview`).
- **Don't re-implement bootstrap's taxonomy shapes.** Match the existing template
  shapes from `skills/bootstrap-project/templates/*.tmpl` exactly; if a page
  shape needs to change, that's an ADR-014 amendment, not an ad-hoc change here.
- **Don't skip the preview.** Even if the builder says "just do it", show the
  manifest and get one approval. The one-gate design is a load-bearing invariant
  (see ADR-027).

## Eval expectations (see `eval/eval.json`)

- 7 pages + 3 `.gitkeep` subdirs present at the target after a run; pages
  populated from facts (not blank templates).
- Master `wiki/index.md` contains exactly one bullet under `## Projects` linking
  to `projects/<name>/index.md` (re-running adds no second bullet — idempotent).
- Master `wiki/log.md` contains exactly one
  `## [<today>] init | Project sub-wiki ingested for <name>` entry (idempotent).
- Re-run is additive: no pages overwritten; master lines not duplicated.
- The user's project directory is byte-identical before and after the run.
- A low-evidence project yields honest placeholders (`_TBD_`), not fabricated
  features.
- Files written = 7 pages + 3 `.gitkeep` = 10 (standard/light depth); master
  `index.md` and `log.md` are edits (appends), not new files.

## References

- `references/extraction-spec.md` — the scanner's detection rules + safety bounds
- `references/page-mapping.md` — facts → ADR-014 pages + no-invention drafting rules
- `scripts/scan.py` — the read-only scanner (emits facts JSON on stdout)
- `../bootstrap-project/references/template-loader.md` — additive/no-overwrite write discipline (reused, not forked)
- ADR-032 (Project Ingest), ADR-014 (per-project taxonomy), ADR-031 (Solo-First), ADR-027 (show-diffs/require-approval)
