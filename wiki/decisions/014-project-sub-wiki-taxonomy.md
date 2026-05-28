---
title: "ADR-014: Project Sub-Wiki Taxonomy — PROJECT.md / REQUIREMENTS.md / STATE.md / CONTEXT.md"
status: accepted
date: 2026-05-28
sunset-review: 2026-11-28
references-pages: [gsd-redux, llm-wiki-pattern, simon-scrapes-agentic-os, py-harness-engineering]
affects-components: [wiki, projects, wake-up, consolidate, install]
relates-to: [004-wiki-design-hierarchical, 008-wake-up-hook, 009-consolidate-via-wrap]
amendments:
  - "2026-05-28: clarified that the project sub-wiki is THIS friend's view of the project, not a shared artifact across friends. Each friend's PROJECT.md / STATE.md / CONTEXT.md captures their own work + understanding of the shared project. Friends communicate updates via Agent Mail (ADR-018) when desired, not by writing to each other's project sub-wikis."
---

# ADR-014: Project Sub-Wiki Taxonomy — PROJECT.md / REQUIREMENTS.md / STATE.md / CONTEXT.md

## Context

ADR-004 established that each active project (a friend group's startup attempt, a tool we're building, etc.) gets its own sub-wiki under `wiki/projects/<project-name>/`. The sub-wiki's research / decisions / patterns directories mirror the master wiki's pattern (per ADR-004).

What was deferred to this ADR: **what specific top-level pages live at the root of each project sub-wiki**, beyond the directories.

GSD Redux's persistent-artifacts pattern surfaced four pages that GSD treats as core per-project documents:

- `PROJECT.md` — high-level project description
- `REQUIREMENTS.md` — what needs to be true
- `ROADMAP.md` — phases / milestones
- `STATE.md` — right-now state
- `CONTEXT.md` — active context for current work

ADR-004 borrowed this taxonomy. This ADR settles **what each of those pages actually contains, who writes them, when they update, and how they feed the wake-up + consolidate loop**.

The structure must serve:
1. **Wake-up hook (ADR-008)** — when a developer is in `Dev/<project>/`, the wake-up reads index + log + session-pointer; we need to know what else (if anything) feeds the wake-up
2. **Consolidate (ADR-009)** — when `/wrap` promotes signal from a session, which of these pages get updated and how
3. **Friend-group readability** — the project sub-wiki should be skimmable by a friend who's about to take ownership of (or look at) the project

## Decision

Each project sub-wiki at `wiki/projects/<project-name>/` has these top-level pages (and the directories from ADR-004):

```
wiki/projects/<project-name>/
├── PROJECT.md          ← high-level description (rarely changes)
├── REQUIREMENTS.md     ← what must be true (changes as scope evolves)
├── ROADMAP.md          ← phases + milestones (updates per milestone shift)
├── STATE.md            ← right-now state (updates frequently, per session)
├── CONTEXT.md          ← current work focus (updates per session start; ephemeral)
├── index.md            ← catalog of all pages in this sub-wiki (per ADR-004)
├── log.md              ← chronological event log (per ADR-004)
├── research/           ← project-specific source ingestion (per ADR-004)
├── decisions/          ← project-specific ADRs (per ADR-004)
└── patterns/           ← project-specific patterns (per ADR-004)
```

### Page contents and update cadence

**PROJECT.md** — the "what is this and why does it exist" doc

- One-paragraph description of the project's purpose
- Target users (who is this for?)
- Success criteria (how do we know it worked?)
- Constraints (technical, scope, ethical)
- Links to source material (PRDs, customer interviews, wikis it references)

**Update cadence**: rare. Major scope shifts only. Most sessions don't touch this.

**Author**: human (initial creation at project kickoff) + LLM via consolidate when a session establishes a new purpose-shaping decision.

**REQUIREMENTS.md** — what must be true at "done"

- Functional requirements (the system does X)
- Non-functional requirements (performance, security, scale, accessibility)
- Out-of-scope items (deliberate exclusions)

**Update cadence**: per-milestone or major scope event. Touched a few times per project lifecycle.

**Author**: human-driven initially; LLM via consolidate when a session results in scope changes.

**ROADMAP.md** — phases and milestones

- Phase 1 / Phase 2 / etc., each with a checklist of milestones
- Boxes check off as work completes
- Marker for "we are here" pointing at the current active phase

**Update cadence**: as milestones complete or move. Multiple touches per project lifecycle.

**Author**: LLM via consolidate when milestones tick; human can edit directly.

**STATE.md** — right-now snapshot of the project

- Active work (what's being touched in the past week)
- Open threads (things in progress)
- Recent decisions (links to project's `decisions/*.md`)
- Recent learnings (links to project's `research/*.md` or `patterns/*.md`)
- Recent blockers + their status

**Update cadence**: per session that has signal. The consolidate skill (ADR-009) updates this when sessions promote items to the wiki.

**Author**: LLM via consolidate; human can edit directly.

**CONTEXT.md** — current work focus

- One-paragraph "what we're working on right now"
- The session pointer that the next wake-up reads (ADR-008's session pointer is conceptually identical to CONTEXT.md's first paragraph)
- Open questions blocking forward progress

**Update cadence**: per session. Effectively ephemeral — refreshed each wrap.

**Author**: LLM via consolidate.

**Note on session pointer vs. CONTEXT.md**: ADR-008's session pointer is the one-paragraph "where I left off" that wake-up reads. Implementation choice: **CONTEXT.md IS the session pointer's home.** Wake-up reads `CONTEXT.md`; consolidate rewrites `CONTEXT.md`. Same file, two views. This avoids the file proliferation of separate session-pointer artifacts.

### Reading order for wake-up

When a developer is in `Dev/<project>/`, the wake-up hook (ADR-008) reads:

1. Master `wiki/index.md` (always)
2. Master `wiki/log.md` tail (last 5 entries)
3. Project `wiki/projects/<project>/index.md` (always when in project dir)
4. Project `wiki/projects/<project>/CONTEXT.md` (the session pointer + active focus)
5. Project `wiki/projects/<project>/log.md` tail (last 10 entries)
6. **NOT** PROJECT.md / REQUIREMENTS.md / ROADMAP.md / STATE.md unless the conversation indicates need. These are full-page reads, drilled into on demand.

Total target: 3–5K tokens per ADR-004.

### Updating during consolidate

When `/sf:wrap` runs (ADR-009), the consolidate skill checks each of these against the session's signal:

| Page | When to update |
|---|---|
| PROJECT.md | Major purpose-shaping decision (rare) |
| REQUIREMENTS.md | Scope change (in/out, success criteria shift) |
| ROADMAP.md | Milestone completed; phase transition; new phase added |
| STATE.md | Session had signal; reflect what changed |
| CONTEXT.md | Always rewritten by consolidate (it's the next wake-up's pointer) |
| log.md | Always append a one-line entry |
| index.md | If any new pages added to research/decisions/patterns |

### Initial project sub-wiki bootstrap

When a new project starts, the framework provides a `/sf:bootstrap-project <name>` command (filed under ADR-015 onboarding) that creates the sub-wiki skeleton with sensible defaults:

- `PROJECT.md` with placeholder sections (purpose, users, success criteria)
- `REQUIREMENTS.md` with empty Functional / Non-functional / Out-of-scope sections
- `ROADMAP.md` with a single "Phase 1: TBD" marker
- `STATE.md` with empty Active Work / Open Threads sections
- `CONTEXT.md` with "Just bootstrapped; first session pending"
- Empty `index.md` and `log.md` with one entry: `## [YYYY-MM-DD] init | <project-name> sub-wiki bootstrapped`

The user fills in PROJECT.md / REQUIREMENTS.md at kickoff (or invokes Skill Creator / Superpowers' brainstorming to interview them — connects to ADR-015's identity-bootstrap pattern).

## Consequences

**Easier:**
- **Predictable structure.** Friends can navigate any project sub-wiki because they all look the same.
- **Wake-up has a defined contract.** It reads CONTEXT.md + log tail; everything else is on-demand. Predictable token cost.
- **Consolidate has a clear update map.** Each session's signal goes to the right page(s).
- **GSD's hard-won taxonomy is borrowed without adopting GSD itself.** Best of both worlds (per ADR-006's reasoning).

**Harder:**
- **Five required pages per project is a lot for tiny projects.** Mitigation: bootstrap command creates them with placeholders; they can stay nearly empty if the project is small.
- **Consolidate logic gets a bit more complex** (it has to decide which pages to update). But the decision tree is fairly mechanical.
- **Pages may drift out of sync** (e.g., ROADMAP says Phase 2 is "in progress" but STATE shows nothing happening). Mitigation: wiki-maintainer agent's lint pass (future) cross-checks for consistency.

**Now impossible:**
- Project sub-wikis without these pages — every active project has the taxonomy.
- Treating CONTEXT.md as a "real" persistent doc (it's deliberately ephemeral and rewritten each session).

**Sunset review trigger conditions:**
- The taxonomy proves to be too heavy for the friend group's actual project shapes → consolidate to fewer pages
- New page categories emerge consistently (e.g., RISKS.md, KPIs.md) → add to standard taxonomy
- A given page sees zero updates in 3+ months across all projects → consider removing it from required set

## Alternatives considered

### A) Match GSD Redux exactly (PROJECT.md, REQUIREMENTS.md, ROADMAP.md, STATE.md, CONTEXT.md)

**Considered shape**: Adopt GSD's taxonomy verbatim, including its assumed update semantics.

**Why partially accepted**: We DO adopt the page names. We deviate on **semantics + update cadence + relationship to wake-up/consolidate** because GSD's are tied to its 3-phase workflow which we don't fully adopt.

### B) Minimalist: only STATE.md and log.md

**Considered shape**: Drop PROJECT.md, REQUIREMENTS.md, ROADMAP.md, CONTEXT.md as required pages; let projects add them ad-hoc.

**Why rejected**: Loses the "skim the sub-wiki and understand the project in 2 minutes" property. Friends switching between projects (or onboarding a new friend to a project) need PROJECT.md to exist as a known entry point.

### C) Free-form: no required pages; let each project organize itself

**Considered shape**: Project sub-wikis just have `index.md` + `log.md`; everything else is project-specific.

**Why rejected**: Inconsistency across projects makes navigation friction. The taxonomy is light enough to be standard. Bootstrap command + sensible placeholders mean the cost is "near zero."

### D) Treat the session pointer as a separate file from CONTEXT.md

**Considered shape**: Have a dedicated `wiki/projects/<name>/.session-pointer.md` (hidden, ephemeral) distinct from CONTEXT.md (longer-lived "active focus").

**Why rejected**: File proliferation for no real benefit. CONTEXT.md is already ephemeral by design. Merging the concepts simplifies the model.

## References

- `wiki/research/gsd-redux.md` — source of the PROJECT.md / REQUIREMENTS.md / STATE.md / CONTEXT.md taxonomy
- `wiki/research/llm-wiki-pattern.md` — Karpathy's index.md + log.md core (which we extend per-project)
- `wiki/research/simon-scrapes-agentic-os.md` — projects-vs-clients hierarchical structure pattern
- `wiki/research/py-harness-engineering.md` — file-backed state survives truncation (the principle this taxonomy implements)
- ADR-004 (Wiki Design Hierarchical) — defines the directory shape this taxonomy fills in
- ADR-008 (Wake-Up Hook) — defines which of these pages wake-up reads
- ADR-009 (Consolidate via /wrap) — defines which pages get updated during consolidate
- ADR-015 (Onboarding) — defines `/sf:bootstrap-project` for sub-wiki initialization
