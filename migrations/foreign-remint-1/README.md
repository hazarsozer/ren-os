# foreign-remint-1 — restamp mis-minted `ren_trust: "foreign"` to `"model"` (issue #22)

## Why

Before #22, `lib.memory.provenance.trust_class` mapped `producer="ingest"`
to `ren_trust: "foreign"`. That mint was wrong for what the ingest door
actually writes: knowledge pages drafted by RenOS's **own worker subagents**
distilling the **friend's own repo**, applied through the single write
queue with quarantine banners — the same trajectory as wrap-written L1
pages, which are stamped `"model"`.

The consequence was severe: spec §4.5's structural-artifact exemption lifts
only the quarantine-withhold check for L1/overview/map — the foreign-stamp
check is never lifted — so a foreign-stamped `map.md` was held out of
wake-up **unconditionally**, even from the project's own checkout, even
after release. An ingested project could never actually reach wake-up.

As of #22, `trust_class` mints `"model"` for ingest drafts. `"foreign"`
stays in the taxonomy — reserved for genuinely external content (a future
import door, hand-stamped pages) — and every foreign check remains in force.

## What it does

Walks the whole wiki tree once and rewrites exactly the
`ren_trust: "foreign"` frontmatter line to `"model"` on pages where
`ren_writer` is a known non-human class (`llm-auto`, `retrospective`,
`routine`). That writer condition bounds the restamp to the mis-minted
population: every foreign stamp in an existing wiki was either self-minted
by the ingest door (always `writer="llm-auto"`) or backfilled by
trust-backfill-1 onto queue-written pages. A foreign page with **no**
writer stamp has genuinely unknown provenance and conservatively keeps
`"foreign"`; `ren_writer: "human"` pages are never touched.

Quarantine banners are untouched — a reminted page still stays out of
context until released via the normal review path.

Bodies and all other frontmatter are byte-for-byte preserved. Idempotent —
safe to (re-)run. `--check` previews with zero writes.

## Shape decision

Standalone global migration (not `skills/wiki-migration`'s per-page-type
chain), for the same reason as trust-backfill-1: "is this page mis-minted
foreign?" is a per-file property evaluated across the whole tree, not a
`schema_version`-keyed page-type dispatch. Listed in
`skills/wiki-migration/schemas.json`'s `global_migrations` note for
discoverability; run directly.

## Run

```sh
uv run python migrations/foreign-remint-1/migrate.py --check   # preview
uv run python migrations/foreign-remint-1/migrate.py           # apply
```

Gated in `/ren:update` by `skills.update.lib.should_run_foreign_remint_1(
<old-version>, <new-version>)` — `True` when the update crosses the 0.6.3
boundary.
