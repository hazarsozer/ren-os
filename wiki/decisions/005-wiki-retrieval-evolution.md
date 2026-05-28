---
title: "ADR-005: Wiki Retrieval Evolution — index.md Now, qmd at Scale"
status: accepted
date: 2026-05-28
sunset-review: 2027-05-28
references-pages: [llm-wiki-pattern, qmd, nate-herk-give-me-10-mins, claude-mem]
affects-components: [wiki, wake-up-hook, install, future-v2]
relates-to: [002-token-efficiency-stack, 003-no-daemon-rule, 004-wiki-design-hierarchical]
---

# ADR-005: Wiki Retrieval Evolution — index.md Now, qmd at Scale

## Context

ADR-004 established the wiki's structure (hierarchical, master + project sub-wikis) and the master `index.md` as the catalog read first at session start. The retrieval mechanism — *how* the LLM finds relevant pages — needs its own ADR because two factors make it the most likely component to evolve:

1. **Scale**: Karpathy's pattern works at "~100 sources, ~hundreds of pages" with `index.md` alone. Beyond that, retrieval quality degrades — too many entries to read sensibly per session, too easy to miss relevant pages.

2. **Tool maturity**: qmd (Tobi Lütke) is the named v2 upgrade path from Karpathy himself — hybrid BM25 + vector + LLM re-rank, all on-device, with both CLI and MCP interfaces. MIT-licensed. Ready to drop in when needed.

The risk if we don't think through this now: we lock in an `index.md`-only design that ages badly. The wiki grows past the envelope, retrieval quality drops, and adding qmd later becomes a costly rewrite because some part of our v1 design assumed flat catalog reads.

The opportunity: design v1 so qmd can slot in later **without restructuring** the wiki itself.

## Decision

**v1 retrieval: `index.md`-driven, no search infrastructure.** Sufficient for current scale and the foreseeable v1 envelope.

**v2 retrieval: qmd as drop-in upgrade**, triggered when wiki scale or query quality drops below useful threshold.

**The pre-conditions for keeping the v1→v2 transition cheap** (all enforced at our layer):

| Pre-condition | Rationale |
|---|---|
| Wiki content stays as plain markdown | qmd reads markdown directly; no conversion needed |
| Frontmatter conventions stay stable (per ADR-004) | qmd can index frontmatter as metadata |
| Wiki is git-versioned | qmd indexes any directory; git gives us version safety during the migration |
| Retrieval logic in wake-up hook is abstracted from data source | A small `wiki_retrieve(query, project) → pages[]` function we can swap implementation of |
| Cross-references use relative markdown links | qmd preserves link semantics |

**Transition triggers (any of these flips us to qmd):**

1. **Master `index.md` exceeds 200 entries or 20KB** — too large to read efficiently per session
2. **Aggregate project sub-wiki `index.md`s exceed 500 total entries** — synthesizer queries become unreliable
3. **A session's wake-up hook routinely loads >8K tokens of indexes** — exceeds our 3-5K target from ADR-004
4. **Recurring "the LLM missed the relevant page" failures** — recall is breaking, not just scale

When any trigger fires, ADR-018 (a future amendment) will document the transition decision with current state and migration plan.

**qmd v2 install + integration outline** (deferred to actual transition time):

- Install: `npm install -g @tobilu/qmd`
- Configure collections: `qmd collection add wiki/ --name "framework-wiki"`
- Add qmd MCP server to Claude Code configuration
- Update wake-up hook to call `query` MCP tool instead of reading `index.md` blindly
- Wiki structure unchanged; only the retrieval mechanism swaps

**Cost at v2 transition**: ~2GB local model download per developer (one-time), node-llama-cpp dependency, ~1–2 days to integrate. Acceptable when the time comes.

**What stays the same forever:**

- `index.md` continues to exist even after qmd adoption (serves as a human-readable map + backup retrieval mechanism)
- `log.md` chronological invariant remains the source of truth for event ordering
- Page format conventions from ADR-004
- The wake-up hook's contract (returns relevant context based on cwd + question) — implementation changes; interface doesn't

## Consequences

**Easier:**
- v1 has zero retrieval infrastructure cost (no daemons, no model downloads, no new install steps)
- The decision to add qmd is deferred until evidence demands it — no premature optimization
- Future-proofing is light-touch: a few conventions (plain markdown, abstracted retrieval) are easy to honor
- We get to learn what retrieval really needs from real wiki use before committing to a search architecture

**Harder:**
- We have to actually honor the pre-conditions — easy to slip into a non-markdown extension or bake `index.md` reads into multiple places without abstraction
- v1 wake-up logic must use the abstracted retrieval function from day one, even though the implementation is naive
- When v2 transition fires, the friend group will need to coordinate model downloads — onboarding will need a sequel section

**Now impossible:**
- Using a non-markdown wiki format without breaking the v2 path
- Skipping qmd later in favor of something else without re-deciding (the door is open to other tools; qmd is just the leading candidate based on research)

**Sunset review trigger conditions:**
- Any of the four transition triggers above fires
- A meaningfully better successor to qmd emerges (e.g., a Claude-Code-native search plugin with stronger integration)
- The friend group's wiki growth pattern reveals different scale dynamics than expected

## Alternatives considered

### A) Adopt qmd at v1 (skip the index.md phase)

**Considered shape**: Install qmd as part of the standard onboarding; use it for retrieval from day one.

**Why rejected**: At v1's wiki scale (handful of pages, maybe a few dozen by the time the framework is "perfected"), qmd is significant infrastructure (~2GB models, install step, node-llama-cpp dependency) for marginal benefit. `index.md` is faster, simpler, more auditable. Karpathy's pattern explicitly works at this scale without search. Premature optimization.

### B) Build our own search system

**Considered shape**: A small SQLite + FTS5 indexer the configuration manages, possibly as a slash command (`/sf:search <query>`).

**Why rejected**: Violates ADR-003 (no-daemon at our layer) if it stays running between sessions, or duplicates qmd's substantial work if it doesn't. qmd is MIT, already built, by a credible author. Use it; don't reinvent.

### C) Use claude-mem's mem-search for the wiki layer too

**Considered shape**: Hook the wiki into claude-mem's indexing pipeline so its 3-layer disclosure retrieval works on wiki content alongside its own captured observations.

**Why rejected**: Conflates layers. claude-mem is captured per-developer; the wiki is shared per-team. Mixing them would mean each developer's claude-mem indexes the whole team's wiki — unnecessary duplication of work and storage. Also, claude-mem doesn't expose its indexing primitives for arbitrary content (would require their cooperation).

### D) Skip the retrieval evolution question entirely

**Considered shape**: Decide retrieval is `index.md`-only forever; cap wiki growth artificially or just accept degradation at scale.

**Why rejected**: The friend group's whole point is to accumulate knowledge over time. Capping wiki growth defeats the purpose. Accepting degradation defeats the token-efficiency north star. Better to plan for the upgrade explicitly.

## References

- `wiki/research/llm-wiki-pattern.md` — Karpathy's scale envelope ("~100 sources, ~hundreds of pages")
- `wiki/research/qmd.md` — qmd architecture, install path, dependencies, license
- `wiki/research/nate-herk-give-me-10-mins.md` — prompt caching mechanics that affect retrieval cost
- `wiki/research/claude-mem.md` — claude-mem's 3-layer progressive disclosure pattern (different layer, different scope)
- ADR-002 (Token-Efficiency Stack) — places this in the memory architecture
- ADR-003 (No-Daemon Rule) — qmd's optional daemon mode is at the plugin layer, OK
- ADR-004 (Wiki Design Hierarchical) — provides the wiki structure qmd will index
