# Decision — hierarchical project wikis: `schema.md`, nested `knowledge/` with hubs, `raw/` (issue #20 amendment)

- **Date:** 2026-08-01
- **Status:** accepted
- **Scope:** `skills/wiki-migration/schemas.json`, `wiki-skeleton/manifest.yaml`
  + `templates/projects/schema.md.tmpl`, `skills/ingest-project`,
  `skills/bootstrap-project`, `skills/wrap`, `skills/wiki-health`,
  `hooks/wake-up`, `migrations/project-knowledge-1`
- **Amends** `docs/decisions/2026-08-01-project-knowledge-subtree.md`
  (issue #20): this record extends that decision's flat `knowledge/`
  directory into a real hierarchical wiki. Nothing there is reversed;
  everything here builds on it.

> Dated-filename convention, same as the other 2026-08-01 records — this
> repo has no numbered ADR series.

## Context

The #20 decision gave project-specific durable pages a sanctioned home —
`projects/<slug>/knowledge/` — but a *flat* one: a single directory of
`<topic>.md` files, indexed by the L2 map. Dogfooding immediately showed
that flat is not a knowledge base. A real project wiki needs
project-determined depth: a genshin-calculator project wants
`knowledge/entities/characters/…` and `knowledge/mechanics/…`; a web app
wants `knowledge/api/…` and `knowledge/infra/…`. The taxonomy is a property
of the *project*, not of the framework — so the framework cannot hardcode
it, but it can require that each project declare one.

## Guide: the Karpathy LLM Wiki pattern

The design follows Andrej Karpathy's LLM Wiki pattern:

- **Three layers**: immutable raw sources; LLM-maintained wiki pages dense
  with cross-references; and a **SCHEMA document** defining the wiki's
  structure and conventions, which the LLM reads and follows on every write.
- **Ingest touches many pages** and maintains cross-references between them,
  rather than appending to one log.
- **Lint finds contradictions, stale claims, and orphan pages** — the wiki
  is audited, not trusted.
- **`index.md` + `log.md` are navigation aids**, not the knowledge itself.
- "The wiki is a persistent, compounding artifact — the cross-references
  are already there." The human curates sources; **the LLM's job is
  everything else.**

## Founder ruling

**A project's wiki has project-determined depth. Each project declares its
own taxonomy in `projects/<slug>/schema.md`; every `knowledge/` subdirectory
carries a hub `index.md`; immutable source material lives in
`projects/<slug>/raw/`.**

## Decision

1. **`projects/<slug>/schema.md` — the project's own SCHEMA document.**
   New registered page type `project-schema` (`schemas.json`, `current: 1`,
   frontmatter `type: project-schema`, `schema_version: 1`,
   `project: <slug>`). Content contract: the project's wiki conventions —
   the taxonomy tree (which `knowledge/` subdirectories exist and what
   belongs in each), naming conventions, and what `raw/` holds. The ingest
   worker drafts it **before any knowledge page** (the taxonomy is proposed
   from what the repo/domain actually contains — a migration script or
   template cannot invent it); `/ren:bootstrap-project` stamps a template
   stub (`copy_if_missing`) so the file always exists with instructions in
   it. Future sessions read and follow it; evolving it is a normal wiki
   write through the queue.

2. **`knowledge/` is a tree, not a directory.** Arbitrary-depth
   subdirectories are sanctioned. Every subdirectory MUST carry a hub page
   `index.md` — `type: project-knowledge` (no new type minted) with a
   `hub: true` frontmatter key — that summarizes and links its children.
   The L2 map's Decision-map points at **hubs and top-level pages, not deep
   leaves**: the map stays a compact index, the hubs carry the fan-out.
   Verified against the existing machinery: every prefix predicate in play
   (`_is_own_project_knowledge` in wake-up, the tier/plane prefixes, the
   dangling-pointer walks, `check_schema_versions`) is a `startswith`/
   `rglob` over wiki-relative paths and already covers nested paths — no
   code change was needed for nesting itself, only for the new checks.

3. **`projects/<slug>/raw/` — immutable source material.** Optional,
   sanctioned, `create_if_missing` in the skeleton's project profile.
   Convention: write-once — a file placed in `raw/` is never edited (fix by
   adding, not rewriting). Because it is *source, not claims*:
   - wiki-health's contradiction/duplicate/drift scans **skip `raw/`**;
   - Decision-map and hub pointers **may target `raw/`** (an existing file
     there satisfies the pointer-existence rule like any other page);
   - wake-up **never injects `raw/`** — excluded from extras discovery
     entirely (not counted as "held out": raw has no withheld trust signal,
     it was never a candidate).

4. **Ingest drafts in Karpathy order.** The `ingest-project` drafting spec
   is rewritten: the worker proposes the taxonomy → writes `schema.md` →
   hub `index.md` pages → leaf pages (nested paths) → the map points at
   hubs. Leaf pages cross-reference their siblings. The pointer-existence
   rule from the parent decision is unchanged.

5. **wiki-health grows a structural finding: `hubless_knowledge_dirs`.**
   Any `knowledge/` subdirectory without an `index.md` hub is a finding.
   The same walk cheaply covers the orphan-page angle as a second key,
   `unlinked_knowledge_pages`: a knowledge leaf (non-hub page in a
   *subdirectory* of `knowledge/`) that no hub and no map pointer links.
   Top-level `knowledge/*.md` pages are exempt — the map indexes those
   directly, as before.

6. **Migration: extend `project-knowledge-1`, don't mint a second one.**
   The migration is unreleased, so it grows in place: relocated flat pages
   still land directly under `knowledge/` (a script cannot invent a
   taxonomy), and the run now **reports** any `projects/<slug>/` missing a
   `schema.md` — reporting only, never fabricating one. Writing the schema
   is the model's (or the human's) job, in a live session that can see the
   project.

## Consequences

- A project wiki can finally mirror its domain: the taxonomy is declared
  once (`schema.md`), navigated through hubs, and audited by wiki-health —
  structure is a checked invariant, not a hope.
- The map stays small and stable: it indexes hubs, and hubs absorb growth.
- `raw/` gives sources a home that the coherence scans deliberately ignore,
  so quoting a source can never "contradict" the page that distills it.
- The cost is a real content contract on ingest: schema first, hubs always.
  wiki-health's `hubless_knowledge_dirs` is the enforcement backstop.
