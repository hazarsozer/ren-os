# Decision — the `knowledge/` taxonomy is capped at two directory levels; deeper hierarchy is carried by links

- **Date:** 2026-09-04
- **Status:** accepted
- **Scope:** `lib/memory/taxonomy.py` (`MAX_DEPTH`), `skills/ingest-project`,
  `skills/wrap`, `skills/distill --seed-tree`
- **Amends** `docs/decisions/2026-08-01-hierarchical-project-wiki.md`
  ruling 2 ("arbitrary-depth subdirectories are sanctioned") and settles the
  "overridable per project … YAGNI" placeholder in
  `docs/superpowers/specs/2026-08-31-concept-tree-routing-design.md` §3.

## Context

The 2026-08-01 amendment sanctioned an arbitrary-depth `knowledge/` tree.
The 0.8.5 concept-tree routing spec shipped a parser with `MAX_DEPTH = 2`
below `knowledge/` and deferred a per-project override as YAGNI. During the
first live ingest-draft under 0.8.5 (study project, 2026-09-04) the cap was
questioned and then ruled on.

## Founder ruling

**Two directory levels below `knowledge/` is the permanent cap. Hierarchy
beyond that is carried by parental links inside pages, not by directory
nesting.** This is Karpathy's LLM-wiki pattern: the wiki's structure lives
in dense cross-references between pages; directories are a coarse shelf,
not the graph. A page that belongs "under" another says so with a link to
its parent (and the parent links back), and the folder-note hubs and the
L2 map stay a compact index.

## Consequences

1. `MAX_DEPTH` stays 2. No per-project override is built; the spec's
   "overridable later if ever needed" clause is closed as *not needed*.
2. Ingest, wrap, and seed-tree never propose a third directory level. A
   concept that feels deeper than two levels lands at depth two and links
   to its conceptual parent in its body.
3. Hub pages summarize and link children; leaf pages link siblings, their
   hub, and any conceptual parent. Lint (wiki-health) is the tool that finds
   orphans and stale links, not a deeper directory tree.
4. Ruling 2 of the 2026-08-01 amendment reads "sanctioned up to depth 2"
   from this date; nothing else there changes.
