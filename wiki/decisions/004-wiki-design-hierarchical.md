---
title: "ADR-004: Wiki Design — Hierarchical Master + Project Sub-Wikis"
status: accepted
date: 2026-05-28
sunset-review: 2026-11-28
references-pages: [llm-wiki-pattern, simon-scrapes-agentic-os, prompt-engineering-agent-harness, ben-fellows-anchor-tags, gsd-redux]
affects-components: [memory, wiki, wake-up-hook, consolidate, install, onboarding]
relates-to: [002-token-efficiency-stack, 005-wiki-retrieval-evolution, 014-project-sub-wiki-taxonomy]
amendments:
  - "2026-05-28: scope clarification — the wiki is local to each friend's machine, not shared across the friend group. 'Master + project sub-wikis' refers to THIS friend's master + THIS friend's project sub-wikis. Friend-to-friend communication, if desired, happens via MCP Agent Mail messages (ADR-018), not by shared wiki state."
---

# ADR-004: Wiki Design — Hierarchical Master + Project Sub-Wikis

## Context

ADR-002 placed our team-level synthesis layer (the wiki) as the third tier of the memory architecture, complementing Context Mode (within-session) and claude-mem (cross-session individual). This ADR settles **what the wiki actually looks like** — its shape, scope, and conventions.

The research surfaced three competing wiki shapes:
- **Flat wiki**: one master `index.md` linking to all pages directly
- **Hierarchical wiki**: master + project sub-wikis with separate indexes
- **Flat-but-categorized**: idea-generator's pattern (sections by knowledge type)

Karpathy's LLM Wiki text notes the flat pattern works at "~100 sources, ~hundreds of pages" — beyond that, search becomes necessary (covered in ADR-005). For the friend-group case, the user explicitly identified the question of isolation vs. intertwining of projects, and we agreed the friend group's projects are mostly **isolated with a thin shared layer** (different verticals like Sidecar / Restore / Era share studio-level patterns but most facts are project-specific).

GSD Redux's persistent-artifacts pattern (PROJECT.md / REQUIREMENTS.md / STATE.md / CONTEXT.md per project) offers a useful taxonomy for the per-project layer. Anchor Tags' manifest pattern validates the master-index-first retrieval approach for any structured wiki, regardless of shape.

## Decision

The wiki is **hierarchical** AND **local to each friend's machine**. There is one master wiki per friend (containing their personal studio knowledge — patterns, decisions, lessons relevant to their work), plus one project sub-wiki per active project (a startup attempt the friend is involved in, a tool they're building, etc.).

**Scope correction (added 2026-05-28)**: the wiki is **not shared across the friend group**. Each friend has their own. Friend-to-friend communication, if desired, happens via Agent Mail messages (per ADR-018), not via shared wiki state. Below references to "studio knowledge" or "team-level" mean THIS friend's view of the friend group's shared work — captured locally on this friend's machine. Each friend may evolve their own framing of the same shared topics.

**Directory shape:**

```
wiki/
├── research/                       ← ingested external sources (LLM Wiki pattern)
├── decisions/                      ← ADRs (this directory)
├── alternatives/                   ← rejected options with reasoning
├── patterns/                       ← reusable team patterns
├── people/                         ← founders, key customers, collaborators
├── projects/                       ← project sub-wikis
│   ├── <project-name>/
│   │   ├── PROJECT.md              ← spec, scope, current state
│   │   ├── REQUIREMENTS.md         ← what needs to be true
│   │   ├── ROADMAP.md              ← phases / milestones
│   │   ├── STATE.md                ← right-now state
│   │   ├── CONTEXT.md              ← active work context
│   │   ├── research/               ← project-specific source ingestion
│   │   ├── decisions/              ← project-specific ADRs
│   │   ├── patterns/               ← project-specific patterns
│   │   ├── index.md
│   │   └── log.md
│   └── ...
├── index.md                        ← master catalog
└── log.md                          ← master chronological event log
```

(The specifics of the per-project layer — PROJECT.md / STATE.md / CONTEXT.md fields and conventions — are detailed in ADR-014.)

**Loading discipline at session start** (formalized in ADR-008):

1. Hook reads `pwd` to determine context
2. Master `wiki/index.md` always loads (small, slow growth)
3. If `pwd` is inside `Dev/<project>/`, load `wiki/projects/<project>/index.md` + recent `log.md` tail + session pointer
4. If not in a project directory, master alone is sufficient
5. Specific pages drill in on demand via the LLM's judgment (not auto-load)

Target session-start context: **3–5K tokens of relevant material**, never the whole wiki.

**Page format conventions (every page):**

```markdown
---
title: <Title>
type: research | decision | alternative | pattern | people | project-state | ...
date: YYYY-MM-DD
tags: [...]
status: ingested | accepted | proposed | superseded | deprecated
references-pages: [...]  ← for cross-linking
related: [...]
---

# <Title>

<short summary or TL;DR>

<sections per type>

## References
<links to source material or other wiki pages>
```

**Cross-references** use relative markdown links. Link liberally — orphan pages are an anti-pattern caught by future lint passes.

**Log discipline**: every wiki event appends to `log.md` with the chronological-invariant prefix format `## [YYYY-MM-DD] <type> | <description>`. Master `log.md` covers studio-level events; project `log.md`s cover project-specific events. Chronological order is the invariant — same-day reordering OK, cross-day rewrites forbidden once the next day's first entry lands.

## Consequences

**Easier:**
- Two-step traversal (master → project) is small token cost for the win of CWD-aware loading
- Master stays tiny forever — studio-level knowledge grows slowly; only project-level entries add bulk to per-project indexes
- Adding / archiving / sunsetting projects is clean — drop a project sub-directory in/out without touching master beyond an index update
- The structure handles both the current pre-product phase (when there are zero projects beyond the framework itself) and the future post-product phase (when there are 1–5+ active projects)
- Maps directly onto Claude Code's native CLAUDE.md inheritance (parent + per-subdirectory overrides)

**Harder:**
- Cross-project synthesis queries ("what auth patterns have we used across all projects?") require reading multiple project indexes — slower path for a rare query. Accept this trade.
- A page that belongs partly in master + partly in a project needs a clear home decision — convention: lean toward master for synthesis ("the auth pattern"), project for instance ("Sidecar's auth implementation")
- Multi-author concerns (friends writing to the same wiki across machines) need to be addressed by git workflow + later ADR or guideline. Not a v1 blocker but log it.

**Now impossible:**
- A single-flat wiki — not without restructuring. Worth committing to hierarchy now so we don't drift into accidental flatness.

**Sunset review trigger conditions:**
- If projects stay deeply intertwined (cross-cutting concerns dominate), reconsider whether flat-but-categorized would have served better
- If a single project's sub-wiki grows past ~200 pages and search performance suffers — trigger qmd adoption per ADR-005
- If multi-author conflicts become recurring pain (rather than rare and resolvable in git)

## Alternatives considered

### A) Flat wiki (no hierarchy)

**Considered shape**: One master `index.md` linking to all pages directly. Pages either at `wiki/<type>/` (research, decisions, patterns, etc.) or `wiki/<topic>/` regardless of project.

**Why rejected**: At scale, the master index becomes unwieldy (Karpathy's "~100 sources" envelope). More importantly, the friend group's projects are mostly isolated (Sidecar/Restore/Era are different verticals) — putting them in one flat namespace would blur boundaries that should stay clear. Cross-project synthesis is rare; project-specific work is common — optimize for the common case.

### B) Flat-but-categorized (idea-generator's pattern)

**Considered shape**: Categorized sections at the top level (`wiki/psychology/`, `wiki/businesses/`, `wiki/gaps/`, etc.) without per-project sub-wikis.

**Why rejected**: This works for idea-generator because its scope IS the studio's product research — all categories are inherently cross-cutting. For a configuration that needs to hold project-specific code patterns, project decisions, and project history, per-project isolation matters more than category isolation.

### C) Per-project wikis with no master

**Considered shape**: Each project has its own wiki; no overarching master.

**Why rejected**: Loses cross-project synthesis entirely. Studio-level decisions ("we never use free trials", "we adopt token-efficient patterns") have no home. Patterns developed in one project can't propagate. The framework's own decisions (this ADR) need somewhere to live — and they're not project-scoped.

### D) Hierarchical with shared "everything" plus minimal per-project leaves

**Considered shape**: Master holds 90% of content; per-project sub-wikis are nearly empty stubs.

**Why rejected**: Forces premature decisions about what's studio-level vs. project-specific. The per-project layer earns its existence as projects accumulate genuine project-level material; it doesn't need to start empty just because we're nervous about boundaries.

## References

- `wiki/research/llm-wiki-pattern.md` — Karpathy's foundational pattern; scale envelope ~100 sources
- `wiki/research/simon-scrapes-agentic-os.md` — hierarchical CLAUDE.md inheritance; Claude Code native support for the pattern
- `wiki/research/prompt-engineering-agent-harness.md` — system prompt assembly walks ancestor directories (mechanical basis for hierarchical context)
- `wiki/research/ben-fellows-anchor-tags.md` — manifest-first retrieval validates `index.md`-first approach
- `wiki/research/gsd-redux.md` — persistent artifact taxonomy (PROJECT.md / STATE.md / CONTEXT.md) borrowed for project sub-wiki shape — full details in ADR-014
- ADR-002 (Token-Efficiency Stack) — places the wiki as the team-synthesis layer
- ADR-005 (Wiki Retrieval Evolution) — defines when/how we transition from `index.md` to qmd
- ADR-014 (Project Sub-Wiki Taxonomy) — settles per-project layer conventions in detail
