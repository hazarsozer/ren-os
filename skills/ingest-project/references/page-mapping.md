# Page mapping — turning facts into a populated ADR-014 sub-wiki

You (the LLM) have the `scan.py` facts JSON in context. Draft the 7 ADR-014
pages from it. This doc is the mapping + the drafting rules. The page *shapes*
match `skills/bootstrap-project/templates/*.tmpl` exactly (same frontmatter,
same section headers) — you fill the bodies with real content instead of
placeholders.

---

## Frontmatter (per-page table)

Match the bootstrap templates' frontmatter exactly. The `type:` value differs
per page; all other fields are shared.

### Shared bindings (every page)

```yaml
title: "<project_title> — <Page>"
schema_version: 1
framework_version: "<facts.framework_version>"
project_name: <facts.name_candidates.chosen>   # kebab-case
created: <today>                               # ISO YYYY-MM-DD
updated: <today>
```

`project_title` is the display form of `name_candidates.chosen`: replace `-`
with spaces and title-case each word (e.g. `demo-api` → `Demo Api`).

The `title:` frontmatter above is `<project_title> — <Page>` for all 7 pages
(e.g. PROJECT.md → `— Project`, index.md → `— Index`). The H1 heading is
**not** uniformly `— <Page>` — two pages diverge. Use this verified per-page
H1 table (matched against `*.tmpl`):

| Page | H1 (verified) |
|---|---|
| `PROJECT.md` | `# <project_title>` — **no suffix** |
| `REQUIREMENTS.md` | `# <project_title> — Requirements` |
| `ROADMAP.md` | `# <project_title> — Roadmap` |
| `STATE.md` | `# <project_title> — State` |
| `CONTEXT.md` | `# <project_title> — Context` |
| `index.md` | `# <project_title> — Wiki Index` — **"Wiki Index", not "Index"** |
| `log.md` | `# <project_title> — Log` |

For `index.md` the H1 (`— Wiki Index`) and the `title:` frontmatter (`— Index`)
legitimately differ — keep both as shown; this is not a typo to reconcile.

### Per-page `type:` and extras

| Page | `type:` | Extra frontmatter |
|---|---|---|
| `PROJECT.md` | `project-main` | `status: ingested` |
| `REQUIREMENTS.md` | `project-requirements` | — |
| `ROADMAP.md` | `project-roadmap` | — |
| `STATE.md` | `project-state` | — |
| `CONTEXT.md` | `project-context` | — |
| `index.md` | `project-index` | — |
| `log.md` | `project-log-entry` | — |

`PROJECT.md` uses `status: ingested` (not `bootstrapped`) to record
provenance: this sub-wiki was generated from an existing project, not a new
blank slate.

---

## The mapping

| Page | Draw from | If evidence is thin |
|---|---|---|
| `PROJECT.md` | `name_candidates`, `stack`, README purpose/users from `doc_inventory` (kind `readme`), `doc_inventory` links | Keep the template's placeholder prose for any section with no evidence |
| `REQUIREMENTS.md` | README "features"/usage sections + `entry_points` | Leave `- _TBD_` bullets (often light) |
| `ROADMAP.md` | `git.tags` as completed milestones; "we are here" marker (see deterministic form below) | `## Phase 1: TBD` if no tags |
| `STATE.md` | `git.recent` (active work list), `git.branch`, `git.dirty` | `- _TBD_` bullets for all sections |
| `CONTEXT.md` | Most recent commit subject/date cluster; `git.branch` as current focus | "Ingested from existing project; first session pending." |
| `index.md` | Catalog of the 7 pages you wrote (match bootstrap's index shape exactly) | n/a — index is always complete |
| `log.md` | `git.timeline` → terse monthly entries (cap ~20) + the `init` entry | `init` entry only, if non-repo or zero-commit repo |

### ROADMAP.md "we are here" marker (deterministic)

The template ships a `> **We are here:** Phase 1` blockquote. Rewrite it to this
exact form so every run is reproducible:

```
> **We are here:** <git.branch> branch (latest: <git.recent[0].subject>)
```

`git.recent[0]` is the most recent commit (the list is newest-first). If
`git.recent` is empty (non-repo or zero-commit), leave the template's
`> **We are here:** Phase 1` line unchanged.

### index.md headers (authoritative)

The `index.md` template uses exactly these section headers — no "States"
section exists:

1. `## Core taxonomy`
2. `## Research`
3. `## Decisions`
4. `## Patterns`
5. `## See also`

List all 7 pages under their correct sections. `PROJECT.md`, `REQUIREMENTS.md`,
`ROADMAP.md`, `STATE.md`, `CONTEXT.md` go under **Core taxonomy**. `log.md`
goes under **See also**. `Research` and `Decisions` begin as italic
placeholders that `--depth deep` may fill (kind `doc` → Research, kind `adr` →
Decisions — see below). `## Patterns` is NEVER populated by ingest at any
depth — it always retains its template placeholder text (ingest extracts no
patterns; those accrue later from `/ren:wrap`).

---

## Timeline → log.md (single algorithm)

For each `git.timeline` entry (monthly bucket, already sorted oldest-first),
emit one terse log line using event type `backfill`:

```
## [<YYYY-MM>] backfill | <count> commits — <annotation>
```

Annotation rules:
- If any `git.tags` entry has a date in that month, append `— shipped <tag_name> (tag)`.
- Otherwise, **only when there is no condensation line** (≤20 months total),
  annotate the first month with `— project history begins`. When a condensation
  line is emitted (see below), omit this annotation entirely — the first kept
  month is not the project's actual start, so "project history begins" would be
  wrong; the condensation line already anchors the start.
- All other months need no annotation suffix (bare count is enough).

Cap at ~20 `backfill` lines. If `git.timeline` has more than 20 entries,
collapse the oldest excess into a single summary line *before* the first kept
entry (and drop the `— project history begins` annotation per the rule above):

```
## [<oldest-kept-month>] backfill | N earlier months condensed (<total-count> commits)
```

After all `backfill` lines, append the `init` entry — always present,
regardless of whether a git history exists. When the repo is non-repo or a
zero-commit repo (`git.no_commits: true`, empty `git.timeline`), there are no
`backfill` lines and the log collapses to this `init` entry alone:

```
## [<today>] init | Project sub-wiki ingested for <name>
```

Use `<name>` = `name_candidates.chosen` (kebab form).

Full example (4-month project with one tag):

```
## [2025-01] backfill | 40 commits — project history begins
## [2025-06] backfill | 22 commits — shipped v1.0 (tag)
## [2025-07] backfill | 18 commits
## [2025-08] backfill | 15 commits
## [2026-06-12] init | Project sub-wiki ingested for demo-api
```

Use event type `backfill` for reconstructed history and `init` for the ingest
event, so they're distinguishable from live `/ren:wrap` entries.

---

## `--depth deep` docs → summarize + backlink (never copy)

When `--depth deep` and `doc_inventory` contains ADRs or design docs
(kind `adr` or `doc`): for each document, add a one-paragraph **summary** to
the sub-wiki's `decisions/` (for kind `adr`) or `research/` (for kind `doc`)
subdirectory, with a **backlink** to the in-project source path. Build the
backlink by joining `facts.scanned_path` (absolute) with the inventory entry's
`path`:

```
See original: <facts.scanned_path>/<doc_inventory[i].path>
```

(e.g. `See original: /home/me/code/myapp/docs/adr/0001.md`.) This is a
local-machine absolute path: the scanner cannot know where the wiki lives
relative to the project, so a relative backlink isn't computable from the
facts JSON. Kind `doc` covers design docs; only kinds `adr` and `doc` are
summarised (no other inventory kind triggers a `decisions/`/`research/` write).

Never copy the full document into the wiki — that bloats it and drifts as the
source evolves (design §7; ADR-002/004).

For `standard` / `light` depth, just list the docs under `index.md`'s
`## Research` / `## Decisions` sections with their path and `bytes` from the
inventory; don't summarise.

---

## Hard drafting rules

1. **No invention.** Every concrete claim (stack, dates, milestones, features)
   must trace to a fact in the JSON. If a section has no evidence, keep the
   template's existing placeholder prose — a `- _TBD_` bullet or italic
   `_..._` paragraph — rather than guessing. "No invention" means no concrete
   claim absent from the facts JSON; it does not mean a literal grep for
   evidence tokens. A grep for `{{` or `_TBD_` should reveal every unfilled
   hole.

2. **Never echo secrets.** Do not copy any token-, key-, or password-looking
   string into a page, even if it somehow appears in a scanned file snippet.

3. **Honesty about confidence.** `stack.frameworks` entries are best-effort
   detection hints with NO per-entry confidence (`frameworks` is a bare
   `string[]`; only `stack.languages[]` entries carry a `confidence` field).
   Entry points are likewise hints. Always phrase a framework as "appears to
   use X" — its only evidence is a manifest substring.

4. **Stay in the sub-wiki + 2 master lines.** Write nothing into the user's
   project directory. The only master-wiki writes are the registration lines
   described below.

5. **Thin-evidence sections retain markers verbatim.** Keep the template's
   existing `- _TBD_` bullets and italic `_..._` prose exactly as they appear
   in the template. Do not rephrase them or add a reason suffix unless you have
   concrete evidence — a `_TBD_` marker is already informative enough.

---

## Master-wiki registration (registration-only footprint)

Append, idempotently (skip if an equivalent line already exists):

**`wiki/index.md`** under `## Projects`:

```
- [<project_title>](projects/<name>/index.md) — Ingested <today> from existing project (<primary language/stack>).
```

`<primary language/stack>` = `stack.languages[0].name` (the first detected
language), or `stack.frameworks[0]` if languages list is empty, or `"unknown
stack"` if both are empty.

If the `## Projects` header is absent from `wiki/index.md`, refuse to guess
— surface the issue and recommend `/ren:install --redo-stage 5` (mirrors the
`bootstrap-project` behaviour).

**`wiki/log.md`**:

```
## [<today>] init | Project sub-wiki ingested for <name>
```

`<name>` = `name_candidates.chosen` (kebab form, same as used in the log
entries above).

This is the same line text that ends the project's own `projects/<name>/log.md`
(see "Timeline → log.md" above), but the two are deliberately separate writes:
the one in `projects/<name>/log.md` is the **project-local** log entry; this one
in master `wiki/log.md` is the **master-wiki registration** that records the
ingest at the framework level. Not a copy-paste error — both are intended.

Do NOT write to master `patterns/`, `research/`, or `identity.md`. All
extracted knowledge lives in the project sub-wiki (design §6).
