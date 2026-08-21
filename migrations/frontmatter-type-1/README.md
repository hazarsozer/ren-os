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
pre-update snapshot, same as its two siblings.

## Invariants

- **I1** — a page that already declares a `type:` is never touched.
- **I2** — a page whose path no rule recognizes is never touched; it stays
  untyped so the lint keeps flagging it as a judgment call.
- Idempotent: running twice is a no-op the second time.

## Running

```bash
uv run python migrations/frontmatter-type-1/migrate.py --check   # dry run
uv run python migrations/frontmatter-type-1/migrate.py           # apply
```

## Table

The path→type table lives in `lib/memory/page_types.py` and is shared with
`queue.propose()` and the wiki-health lint. This migration never carries its
own copy.
