# Per-Project Taxonomy Templates

Per ADR-014, every project sub-wiki at `~/.startup-framework/wiki/projects/<name>/` has the same fixed shape. This reference catalogs each template file the bootstrap skill stamps and the rationale for the placeholders / section headers it ships with.

The template files themselves live in `skills/sf-bootstrap-project/templates/`. This doc is the *spec* for what each template is meant to capture; it travels with the skill so reviewers can compare intent vs implementation.

## Mapping

| Template file in `templates/` | Stamped to | ADR-014 role |
|---|---|---|
| `PROJECT.md.tmpl` | `<target>/PROJECT.md` | High-level "what is this and why does it exist" |
| `REQUIREMENTS.md.tmpl` | `<target>/REQUIREMENTS.md` | What must be true at "done" |
| `ROADMAP.md.tmpl` | `<target>/ROADMAP.md` | Phases + milestones |
| `STATE.md.tmpl` | `<target>/STATE.md` | Right-now snapshot |
| `CONTEXT.md.tmpl` | `<target>/CONTEXT.md` | Current work focus; rewritten each wrap |
| `index.md.tmpl` | `<target>/index.md` | Per-project catalog |
| `log.md.tmpl` | `<target>/log.md` | Per-project chronological log |
| `research/.gitkeep` | `<target>/research/.gitkeep` | Project-specific source ingestion |
| `decisions/.gitkeep` | `<target>/decisions/.gitkeep` | Project-specific ADRs |
| `patterns/.gitkeep` | `<target>/patterns/.gitkeep` | Project-specific patterns |

Total: 7 files + 3 dirs. Matches ADR-014's required taxonomy exactly. No extras.

## Per-file spec

### PROJECT.md.tmpl

Captures the "what is this and why does it exist" doc per ADR-014. Sections:

- **Purpose** — one paragraph; what the project does
- **Target users** — who it's for
- **Success criteria** — how we know it worked
- **Constraints** — technical / scope / ethical
- **References** — links to PRDs, customer interviews, related wiki pages

Placeholders used: `{{project_title}}`, `{{project_description}}` (intro paragraph), `{{today}}`, `{{framework_version}}`.

Update cadence (per ADR-014): rare. Major scope shifts only.

### REQUIREMENTS.md.tmpl

What must be true at "done". Sections:

- **Functional requirements** — what the system does
- **Non-functional requirements** — performance, security, scale, accessibility
- **Out-of-scope** — deliberate exclusions

Placeholders: `{{project_title}}`, `{{today}}`, `{{framework_version}}`.

Update cadence: per-milestone or major scope event.

### ROADMAP.md.tmpl

Phases + milestones. Sections:

- **Phase 1: TBD** — placeholder for first phase
- A "we are here" marker pointing at the current phase

Placeholders: `{{project_title}}`, `{{today}}`, `{{framework_version}}`.

Update cadence: as milestones complete or move.

### STATE.md.tmpl

Right-now snapshot. Sections:

- **Active work** (past week)
- **Open threads** (in progress)
- **Recent decisions** (links to `decisions/*.md`)
- **Recent learnings** (links to `research/*.md` or `patterns/*.md`)
- **Recent blockers** + status

Placeholders: `{{project_title}}`, `{{today}}`, `{{framework_version}}`.

Update cadence: per session that has signal. Touched by `/sf:wrap` consolidate.

### CONTEXT.md.tmpl

Current work focus per ADR-014. Conceptually identical to ADR-008's session pointer. Sections:

- **One-paragraph "what we're working on right now"**
- **Open questions blocking forward progress**

Placeholders: `{{project_title}}`, `{{today}}`, `{{framework_version}}`.

Initial body: "Just bootstrapped; first session pending."

Update cadence: per session. Effectively ephemeral; rewritten each `/sf:wrap`.

### index.md.tmpl

Per-project catalog. Same shape as the master wiki's index per ADR-004:

- Top-level frontmatter (`title`, `type: index`, `schema_version`, `framework_version`, `created`, `updated`)
- Section headers: Research / Decisions / Patterns / States (links to PROJECT/REQUIREMENTS/ROADMAP/STATE/CONTEXT)
- "See also" pointer back to master `wiki/index.md`

Placeholders: `{{project_title}}`, `{{project_name}}`, `{{today}}`, `{{framework_version}}`.

### log.md.tmpl

Per-project chronological log. Same format as master `log.md`. Initial body: a single init entry attributing the bootstrap to `{{handle}}` and noting framework version.

Placeholders: `{{project_title}}`, `{{project_name}}`, `{{handle}}`, `{{today}}`, `{{framework_version}}`.

### research/ decisions/ patterns/

Three empty subdirectories. `.gitkeep` files (zero bytes) preserve them across `git` operations. Per ADR-014, these are where project-specific ingestion / ADRs / patterns accumulate as the project matures. They start empty per ADR-017 (no framework-developer content seeded).

## What this taxonomy deliberately does NOT include

- A `people/` directory — there's no shared people directory at any wiki scope (ADR-017 amendment).
- A `RISKS.md` or `KPIs.md` — flagged in ADR-014 as candidates for a sunset-review trigger if they emerge as patterns. Not part of v1.
- A `BUDGET.md` or financial-shape page — out of v1 scope.

If a friend or future contributor wants to add one of these, the right path is: file a project-level ADR in `decisions/`, justify it, and once stable, propose an amendment to ADR-014 that extends the taxonomy.

## Cross-references

- ADR-004 — wiki shape; project sub-wikis live under `wiki/projects/`
- ADR-014 — full taxonomy spec
- ADR-015 § "`/sf:bootstrap-project <name>` command" — onboarding-time spec for this skill
- ADR-017 — load-bearing: no framework-developer content seeded
