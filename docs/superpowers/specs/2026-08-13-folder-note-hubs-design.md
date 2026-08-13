# Folder-note hubs + graph legibility (#56, #59, #55 residue) — design

**Date:** 2026-08-13 · **Issues:** [#56](https://github.com/hazarsozer/ren-os/issues/56),
[#59](https://github.com/hazarsozer/ren-os/issues/59),
[#55](https://github.com/hazarsozer/ren-os/issues/55) (repair residue) ·
**Target:** next minor after the #58 hotfix (MAJOR-classified migration)

## Problem

The wiki's spine (root `index.md` → project `map.md` → knowledge hubs → leaves)
is fully connected — verified 2026-08-13: Obsidian resolves the maps'
wiki-root-relative markdown links — but illegible in graph view:

1. Every knowledge hub is `index.md`. Graph view labels nodes by filename, so
   the entire hub tier renders as twelve identical anonymous "index" dots.
2. By-design-unlinked tiers (`raw/`, `archive/`) plus not-yet-repaired orphans
   ring the graph as noise.

Also settled here: the rendering target is **Obsidian only**. The GitHub backup
remote is storage, not a reading surface, so wiki-root-relative link paths
stay. #59 shrinks from "switch to file-relative" to recording that decision.

## Decisions already made (with Hazar)

- Target surface: Obsidian only. No link re-pathing; root-relative paths stay.
- Hub naming: folder-note convention — `knowledge/<topic>/index.md` becomes
  `knowledge/<topic>/<topic>.md`. Root `index.md` is untouched (unique at root,
  the vault entry point).
- Orphan-by-design tiers are hidden by a default graph filter, not linked in.
- Hierarchy contract: root `index.md` → project `map.md` → hub folder notes →
  leaf pages, with operational satellites (`schema.md`, `open-work.md`, L1
  sessions) hanging one hop off the map directly.

## 1 — Hub rename migration

A new schema version for knowledge trees, driven by the existing
`wiki-migration` machinery (`/ren:update`: snapshot → migrate → verify →
approve → apply):

- **Rename:** every `hub: true` page named `index.md` below a project's
  `knowledge/` root moves to `<parent-folder-name>.md` in place. Applies to all
  live projects (ren-os's seven subtree hubs, flux's design/research/
  interventions/mechanisms hubs, and any other tree the scan finds). The scan
  keys on filename: **any** `index.md` below a `knowledge/` root renames,
  hub-flagged or not (matching verify's zero-remaining assertion); a renamed
  page missing `hub: true` gets the flag stamped in the same write.
- **Link rewrite, same pass:** every markdown link and decision-map pointer in
  the wiki whose target is a renamed path is rewritten to the new path — map
  Decision-map lines, child→hub relatives (`../wiki-structure/index.md` →
  `../wiki-structure/wiki-structure.md`), hub→hub cross-references, and L1
  narrative links. Pointer lines keep their write_id parenthetical untouched.
- **Schema text rewrite:** per-project `schema.md` pages that state the old
  convention ("hub files are always named `index.md`") are rewritten to state
  the folder-note convention, through the queue like every migration write.
- **verify.json:** (a) zero `index.md` files remain below any `knowledge/`
  root; (b) every rewritten link resolves to an existing file; (c) every
  `hub: true` page's filename equals its parent folder's name; (d) pointer
  lines still parse under the pointer regex.
- Renames and rewrites are journaled queue writes over snapshotted pages —
  revertible like the 0.7.0 train; hand-converting ahead of the version is
  unsupported and doctor flags mixed-convention trees until migrated.

## 2 — Producer and parser lockstep

Same release, atomic with the migration:

- **Emitters:** `ingest-project` (hub scaffolding), `bootstrap-project`
  (skeleton — verify it stamps no `knowledge/` hubs today; update if it does),
  wrap's D4 auto-pointer path (no format change, but its "already referenced"
  dedup must match post-rename paths).
- **Parsers/checks:** wiki-health dangling-pointer + orphan detection, doctor's
  pointer scan, remember's map renderer. Each accepts only the new convention
  post-migration; doctor warns on any surviving `knowledge/**/index.md`.
- **Docs:** SKILL.md examples in bootstrap/ingest/remember/wiki-health that
  show `index.md` hub paths.

## 3 — Default graph config

`.obsidian/graph.json` shipped at install and update time, **only when the file
is absent** — an existing user-tuned config is never overwritten:

- Filter excludes `raw/` and `archive/` paths.
- Path-based color groups per tier — root+maps, hubs+knowledge leaves, `l1/`,
  quarantine-flagged — using the Okabe-Ito palette (colour-vision-safe;
  the folder-note naming itself is the second signal, per accessibility
  doctrine: colour never carries meaning alone).

## 4 — One-time repair session (post-migration)

Previously blocked on the naming decision, unblocked by this train; executed as
a `/ren:wiki-health`-guided session after the migration lands, not as
migration code:

- Repair the four live orphan pages (link each from its owning hub or map).
- Repair the six genshin-calculator dangling pointers (worker-invented
  targets) under the now-settled convention.

## Issue bookkeeping

- #56 closes with the migration.
- #59 closes re-scoped: "Obsidian-only decided 2026-08-13; root-relative paths
  stay; GitHub browsability is a non-goal."
- #54 stays open only for the repair session above (its D1–D4 duties shipped
  in 0.7.0; the D4 production bug is #57, Cluster B).

## Testing

- Migration unit tests on a fixture wiki: hub with children renames; nested
  hub (`research/interventions/`) renames; inbound links across all four link
  classes rewritten; non-hub `index.md` outside `knowledge/` untouched; root
  `index.md` untouched; verify.json catches a seeded dangling rewrite.
- Idempotence: running the migration on an already-migrated tree is a no-op.
- Parser tests: wiki-health/doctor/remember against a migrated fixture; doctor
  flags a mixed-convention tree.
- graph.json: written when absent, skipped when present (byte-identical file
  untouched).
- Existing 0.7.0 migration tests stay green (this is a new version atop v2,
  not an edit of the 1→2 migration).

## Out of scope

- Cluster B entirely: #60 distiller, #57 D4 production bug, #39 freshness,
  quarantine-exit trio (#46/#51/#52).
- #58 install-clobber (standalone hotfix, ships first).
- Any link re-pathing (root-relative stays), any `l1`/`raw`/`archive` layout
  change, log.md backfill.
