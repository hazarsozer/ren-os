---
title: LLM Wiki Pattern (Karpathy)
type: research
source: raw/karpathy-llm-wiki.md
ingested: 2026-05-28
tags: [memory, knowledge-base, markdown, wiki, foundational]
status: ingested
---

# LLM Wiki Pattern (Karpathy)

## TL;DR

A memory pattern where the LLM incrementally builds and maintains a structured, interlinked markdown wiki between the user and raw sources. The wiki is a **persistent, compounding artifact** — knowledge is compiled once and kept current, not re-derived on every query. Replaces RAG-style chunk retrieval with **index-driven recall** over LLM-maintained markdown pages.

## Key insights

1. **Persistence vs. re-derivation.** RAG rediscovers knowledge on every query. The wiki accumulates it. The synthesis, contradictions, and cross-references already exist BEFORE the query is asked.

2. **Three architectural layers**:
   - **Raw sources** — immutable, source of truth, LLM never modifies
   - **Wiki** — LLM-owned markdown, the artifact
   - **Schema** — config document (CLAUDE.md / AGENTS.md) that tells the LLM how to maintain the wiki

3. **Three operations**:
   - **Ingest** — drop source → LLM reads → updates 10–15 wiki pages + log + index
   - **Query** — LLM searches the wiki, drills into pages, synthesizes answer with citations. **Good answers get filed BACK into the wiki** — explorations compound, not just sources.
   - **Lint** — periodic health check (orphans, contradictions, stale claims, missing cross-refs)

4. **Two special files**:
   - `index.md` — content-oriented catalog (every page with one-line summary, organized by category)
   - `log.md` — chronological append-only record, format `## [YYYY-MM-DD] <type> | <description>`, grep-parseable

5. **Scale envelope**: ~100 sources / ~hundreds of pages without needing search infrastructure. Index file alone is sufficient at that scale. Beyond that, hybrid search (e.g., `qmd`) becomes worth adding.

6. **Why it works** (Karpathy's framing): humans abandon wikis because maintenance burden grows faster than value. LLMs don't get bored, don't forget cross-references, can touch 15 files in one pass. Maintenance cost → zero. **Human's job: source curation, direction, questions. LLM's job: bookkeeping.**

7. **Memex lineage**: Vannevar Bush's 1945 personal knowledge store with associative trails. The pattern was always right; only the maintenance problem was unsolved. LLMs solve maintenance.

8. **Modular by design.** Karpathy explicitly says the pattern is abstract and the implementation depends on domain. Page formats, directory structure, schema conventions are up to the implementer.

## How this informs the framework

- **Memory layer == wiki.** Confirmed. Not vector embeddings, not pure RAG, not session-as-unit memory.
- **The schema lives in the plugin's CLAUDE.md.** This is the framework's curation surface for the wiki itself. We co-evolve the schema as we learn.
- **Index-first retrieval** directly serves our token-efficiency north star: read small index → drill into specific pages → never load the whole wiki.
- **Ingest is a first-class operation.** Needs explicit support in the plugin: a slash command, an agent (likely `source-ingester` adapted), workflow conventions.
- **Log discipline matters.** Chronological invariant, grep-parseable prefix. Our `log.md` design inherits this exactly.
- **Filed answers.** Queries producing valuable insight should be saved back into the wiki. This is a design consideration for `/recall` (mid-session) and `/wrap` (consolidate) skills.
- **No prescribed editor.** Karpathy uses Obsidian himself but acknowledges the wiki is just markdown — friend group can use whatever editor each prefers. The framework should not assume Obsidian.

## Open questions / gaps the pattern doesn't address

- **Session-start token budget.** What's loaded by default at the beginning of a session? The pattern assumes the user prompts the LLM to "ingest" or "query" — but in Claude Code, the session starts with auto-loaded memories. We need our own answer (the CWD-aware wake-up hook).
- **Hierarchical wikis (multi-project).** The pattern describes one wiki. Our master + project sub-wiki design is an extension. No prior art in this text for how the master/project relationship works.
- **Page format conventions.** Frontmatter schema, link discipline, when to create a new page vs. extend an existing one — all unspecified. We'll codify these in our schema as we learn.
- **Conflict resolution.** When two ingests contradict each other, what's the protocol? The text mentions "noting where new data contradicts old claims" but doesn't specify how the LLM resolves vs. flags.
- **Sharding / splitting.** When does a wiki page get too big and need to be split? No guidance.
- **Multi-author wikis.** Friend group implies multiple humans interacting with the same wiki via different Claude Code sessions. Merge conflict / locking concerns not addressed.
- **Editor-agnostic vs. Obsidian-specific tricks.** Karpathy lists Obsidian-specific features (Web Clipper, Dataview, Marp plugin, graph view). We need to decide which patterns we adopt in editor-agnostic form vs. which we drop.

## Implications for design decisions still open

| Decision | What this source says | Status |
|---|---|---|
| Memory layer is a wiki | YES | Confirmed |
| Index + log are special files | YES | Adopted |
| Schema lives in CLAUDE.md | YES | Adopted |
| Hierarchical (master + projects) | Not addressed | Our extension |
| Session-start wake-up | Not addressed | Our extension |
| Session consolidation skill | Not addressed | Our extension |
| Editor lock-in | Karpathy uses Obsidian; pattern is editor-agnostic | We stay editor-agnostic |

## Reference

- Raw source: `raw/karpathy-llm-wiki.md`
- Captured: 2026-05-28
- Attribution: text shared by user, attributed to Andrej Karpathy
