# The graph is the hierarchy

- **Date:** 2026-09-04
- **Status:** accepted
- **Spec:** `docs/superpowers/specs/2026-09-04-graph-is-the-hierarchy-design.md`
- **Plan:** `docs/superpowers/plans/2026-09-04-graph-is-the-hierarchy.md`
- **Follows:** `docs/decisions/2026-09-04-taxonomy-depth-cap.md`

## Decision

The depth cap said directories are a shelf, not a hierarchy. This is the
mechanism that carries the hierarchy instead: links in the page body.

1. **Convention, not schema.** `Parent: [[stem]]` and a flat `## Related`
   list live in the body — never in frontmatter. Obsidian renders them and
   `_orphan_pages` already reads them; a frontmatter field would need a
   parser, a migration and a renderer to buy exactly nothing.
2. **Fan-out is bounded by its candidate count, not a second cap.** 12
   candidates, sitting inside Karpathy's observed 10-15 touches per source.
   A cap under the candidate count would only discard verdicts the
   classifier had already made.
3. **`fact` edges land only on concept-node content pages.** Lessons are
   episodic; accreting facts onto them makes them worse. A `fact` verdict on
   a `lessons/` page is downgraded to `relate`, never dropped.
4. **No migration.** Existing pages gain links lazily — when a producer
   touches them, or when the asymmetry auto-fix runs. The first sweep after
   the update reports a large backlog; that is the honest starting state.

## Consequences

- Every durable landing costs one extra classifier-class call and up to 12
  queued writes; distill's `WRITE_CAP` charges fan-out edits, so a capped
  run lands fewer items rather than more writes.
- Recall gets a graph signal for free, and wake-up inherits it (it calls
  `rank`). Any further wake-up ranking change is a separate decision.
- `_orphan_pages` and fan-out and recall share one resolver, so a future
  change to what "a link" means happens in exactly one file.
