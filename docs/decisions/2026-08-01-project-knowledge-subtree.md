# Decision — `projects/<slug>/knowledge/` is the durable project subtree (issue #20)

- **Date:** 2026-08-01
- **Status:** accepted
- **Scope:** `skills/wiki-migration/schemas.json`, `wiki-skeleton/manifest.yaml`,
  `skills/ingest-project`, `skills/bootstrap-project`, `skills/wiki-health`,
  `skills/doctor`, `hooks/wake-up`, `migrations/project-knowledge-1`
- **Builds on** `docs/decisions/2026-08-01-global-tier-promotion-gate.md`
  (issue #18). Supersedes nothing.

> Dated-filename convention, same as the #18 record — this repo has no
> numbered ADR series.

## Context

RenOS advertises a hierarchical memory. The per-project taxonomy actually
defined exactly three things: `projects/<slug>/map.md` (L2),
`projects/<slug>/overview.md`, and `projects/<slug>/l1/session-*.md`. Nothing
else had a sanctioned home.

Dogfooding the Flux ingest (2026-07-31) showed the consequence: distilled
durable pages landed as flat loose `.md` files directly under
`projects/flux/` — no registered page type, no `schema_version`, silently
skipped by `/ren:doctor`'s `check_schema_versions` (which ignores any page
without a version), indistinguishable at a glance from the framework's own
`map.md`/`overview.md`. Flat files, not a hierarchy.

The neighbouring exit was just closed: issue #18 made root-level `decisions/`
· `patterns/` · `research/` the **instruction plane**, promotion-gated for
every producer. That is correct — those directories are for practices general
enough to apply across projects — but it means a project's own durable pages
now have nowhere legitimate to go at all. This decision gives them one.

## Founder ruling

**Project-specific durable knowledge lives in a real, sanctioned,
hierarchical subtree under the project: `projects/<slug>/knowledge/`. Pointers
must target pages that exist. Nothing gets a "dangling by design" pass.**

## Decision

1. **`projects/<slug>/knowledge/` is the durable project subtree.** Pages
   there carry frontmatter `type: project-knowledge`, `schema_version: 1`,
   `project: <slug>`. `project-knowledge` is registered in
   `skills/wiki-migration/schemas.json` (`current: 1`, no migrations yet), so
   from now on these pages are versioned page types like any other and
   `check_schema_versions` sees them. The directory is stamped by
   `/ren:bootstrap-project` via the skeleton manifest's `project` profile
   (`create_if_missing`, `min_framework_version: 0.6.2`).

2. **Root-tier is not for project pages — and the reverse is not a loophole.**
   Per the #18 record, `decisions/`·`patterns/`·`research/` are the
   instruction plane: general practice only, human-promoted only. A page that
   is *about one project* belongs under that project. `knowledge/` is data
   plane, so ingest can write it without a human gate — which is exactly why
   the *content* stays quarantined until reviewed (point 5). Promotion out of
   `knowledge/` into the root tier remains the one and only path upward, and
   `wiki-health`'s `single_project_global_pages` check still catches
   project-specific pages that reached the root tier by hand.

3. **`l2-map` now stamps `schema_version: 1`.** Found while registering the
   new type: `assemble_l2` emitted `type: l2-map` with no version, and
   `check_schema_versions` skips any page lacking one — so every project map
   ever written was invisible to the check despite `l2-map` being a
   registered type since 0.2. One line, and the check starts doing its job.

4. **Pointer existence rule.** A Decision-map pointer must target something
   real: either an in-wiki page that exists (or is being created in the same
   batch), or an external repository reference written `repo:<name>:<path>`.
   **Inventing a future filename is prohibited** — that is what produced the
   dangling pointers this ruling exists to stop.
   - `repo:` refs are *skipped* by both dangling-pointer implementations
     (`skills/wiki-health/lib::_dangling_pointers` and
     `skills/doctor/lib::check_dangling_pointers`): they are not resolvable
     in-wiki by construction, so calling them dangling would be a lie.
     Missing **in-wiki** targets are still flagged, exactly as before.
   - No "slot" mechanism, no dangling-by-design allowance — the founder
     rejected it explicitly. A pointer with no target is a bug, not a state.
   - The two implementations are deliberately separate walks (wiki-health's
     module docstring explains why); a drift test now asserts their
     `_REPO_REF_PREFIX` constants agree.
   - `assemble_l2` needed no change to render either shape — the existing
     `path` field carries both, and `_POINTER_RE` matches `repo:` targets.

5. **Wake-up trust: a narrow exemption, honestly bounded.** Ingest stamps its
   writes `ren_trust: foreign`, and `_is_foreign_stamped` excludes foreign
   pages from the wake-up extras channel — so knowledge pages would never
   inject. Two options were on the table; the choice taken is the smaller and
   more honest of the two:

   Pages under **the session's own detected project**'s
   `knowledge/` directory are exempt from the *foreign-stamp* exclusion
   (`_is_own_project_knowledge`, a pure prefix predicate). The user ingested
   their own repository; a durable stamp should not exile their own project's
   knowledge from their own project's sessions forever.

   The **quarantine banner exclusion is untouched.** An unreviewed knowledge
   page still carries its banner and still stays out of context until a human
   clears it (`wiki-health`'s `release_page`, the human-act exit from quarantine). So in practice: knowledge
   pages inject *after* human review releases the banner, and the durable
   `foreign` stamp no longer permanently blocks them afterwards. That closes
   the "released banner, still invisible forever" gap without weakening the
   review gate by one inch.

   Scope is one prefix: not other projects, not the project's own flat files,
   not the map or overview, and nothing at all when no project is detected.
   Four tests pin each of those negatives.

## Migration

`migrations/project-knowledge-1/` (standalone script, same shape as
`trust-backfill-1` — see its README for why the `schemas.json` chain
machinery does not fit). It relocates every flat `.md` under
`projects/<slug>/` except `map.md`/`overview.md` into `knowledge/`,
normalizes the frontmatter to the three fields above (body and `ren_*`
provenance preserved byte-for-byte), and rewrites L2 Decision-map pointers
that referenced the old paths.

Dry run by default; `--apply` writes; never overwrites an existing
`knowledge/<name>.md` (reports a collision and leaves the flat file alone —
`docs/audits/2026-07-destructive-writes.md` bug class); idempotent; every
move journaled to `state_dir()/migrations/project-knowledge-1.jsonl`.

## Consequences

- Ingest now has somewhere real to put what it distills, and the L2 map's
  pointers resolve — the map becomes a working index instead of a wish list.
- `/ren:doctor` gains real coverage it always claimed: project maps are
  schema-checked, and knowledge pages are typed and versioned from day one.
- The friction is deliberate on the other side: a project page cannot slip
  into the instruction plane, and a pointer cannot name a file that does not
  exist.
