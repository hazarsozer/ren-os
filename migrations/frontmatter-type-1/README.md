# frontmatter-type-1

Backfills the derived frontmatter `type:` onto pages created before the write
door derived one (GitHub #74).

## Shape decision

Like `trust-backfill-1` and `folder-note-hubs-1`, this walks the wiki tree
directly rather than following `skills/wiki-migration`'s per-page-type
`migrate.sh` chain. The chain is keyed by page type — and the whole point of
this migration is that these pages have no type yet, so there is no chain to
walk.

Direct writes plus an append-only journal at
`state_dir()/migrations/frontmatter-type-1.jsonl`; revert is the whole-wiki
pre-update snapshot, same as its two siblings — but that snapshot is taken
only by `/ren:update`. The journal records `{migration, page, ts}` for each
page touched; it is a record of *which* pages this migration wrote, not a
content backup, so it cannot itself revert anything. Run outside
`/ren:update` (a bare `uv run python migrations/frontmatter-type-1/migrate.py`)
has no revert substrate at all — see Running below.

## When it runs

`/ren:update` invokes this as a post-update step when
`skills.update.lib.should_run_frontmatter_type_1(<old>, <new>)` is `True` —
i.e. when the update crosses the 0.8.1 boundary. See `skills/update/SKILL.md`'s
"0.8.1 update notes".

Being listed in `skills/wiki-migration/schemas.json`'s `global_migrations` is
**discoverability only** and runs nothing on its own (issue #77); that gate
function is what actually invokes this migration.

## Invariants

- **I1** — a page that already declares a `type:` is never touched.
- **I2** — a page whose path no rule recognizes is never touched; it stays
  untyped so the lint keeps flagging it as a judgment call.
- Idempotent: running twice is a no-op the second time.

## Running

Running this outside `/ren:update` gets no pre-update snapshot — that
snapshot exists only inside `/ren:update`'s own flow, and the journal below
is not a substitute for it. Run `/ren:backup` first if invoking manually.

```bash
uv run python migrations/frontmatter-type-1/migrate.py --check   # dry run
uv run python migrations/frontmatter-type-1/migrate.py           # apply
```

## Table

The path→type table lives in `lib/memory/page_types.py` and has two
consumers: `queue.propose()` and this migration. The wiki-health lint is
NOT a consumer — its `missing-frontmatter-type` rule checks only that a
`type:` is present, never what it should be (spec 2026-08-21 §2.2). It
would become a third consumer if a rule ever validated the value. This
migration never carries its own copy of the table.
