# project-knowledge-1 — flat project pages → `projects/<slug>/knowledge/`

Issue #20 (RenOS 0.6.2). Before 0.6.2 the per-project taxonomy defined only
`map.md`, `overview.md` and `l1/session-*.md`. Anything else a session
distilled about a project had nowhere sanctioned to go, so a real
`/ren:ingest-project` run dropped loose `.md` files directly under
`projects/<slug>/` — no registered page type, no `schema_version`, skipped by
`/ren:doctor`'s `check_schema_versions`, and (being flat siblings of the map)
easy to mistake for framework-owned files.

0.6.2 sanctions `projects/<slug>/knowledge/` as the durable subtree, with
page type `project-knowledge` (`schema_version: 1`, `project: <slug>`)
registered in `skills/wiki-migration/schemas.json`. This migration relocates
the pages already on disk.

See `docs/decisions/2026-08-01-project-knowledge-subtree.md` for the founder
ruling and the design.

## Shape decision: standalone script, not the wiki-migration chain

Same reasoning as `migrations/trust-backfill-1/` and
`migrations/queue-governance-2-to-3/`. The chain machinery (`schemas.json`
page-type registry + `migrate.sh <page_path>` invoked once per matching page)
transforms frontmatter on a page whose type and path are already known. Here
the type is *missing* and the path is *wrong* — that is the whole defect —
and one run must see a whole `projects/<slug>/` directory at once to know
what is flat and to rewrite the map's pointers to what moved. So this is a
standalone `migrate.py`, listed in `schemas.json`'s `global_migrations` for
discoverability only, never dispatched by `migration_chain()`.

## What it does

For each `projects/<slug>/` directory:

- **Moves** every `*.md` *directly* under it except `map.md` and
  `overview.md` to `projects/<slug>/knowledge/<name>.md`. `l1/` is a
  subdirectory and is never walked; nested directories are left alone.
- **Normalizes frontmatter** on the moved page: `type: project-knowledge`,
  `schema_version: 1`, `project: <slug>`. Every other frontmatter line —
  including `ren_writer` / `ren_trust` / `ren_write_id` provenance stamps —
  and the entire body are preserved byte-for-byte. A page with no
  frontmatter gets a block; the body still does not change.
- **Rewrites pointers**: `## Decision map` lines in any `type: l2-map` page
  whose target was the old path now point at the new one. Targets that are
  not moved paths (including `repo:<name>:<path>` external references) are
  untouched.

## Safety

- **Dry run by default.** No argument = report only, zero writes. `--apply`
  performs the moves.
- **Never overwrites.** If `knowledge/<name>.md` already exists, the flat
  file stays exactly where it is and the run reports a `COLLISION`. Resolve
  by hand. (`docs/audits/2026-07-destructive-writes.md` — "a template or
  generated write meets an existing file" is the bug class this repo keeps
  paying for.)
- **Idempotent.** A second run finds nothing flat left to move and rewrites
  no pointers.
- **Journaled.** Each move appends one JSON line
  (`{ts, slug, from, to}`) to
  `state_dir()/migrations/project-knowledge-1.jsonl`. The framework write
  journal (`lib.memory.journal`) is deliberately NOT used: nothing here goes
  through the write queue, and minting `write_id`s for a relocation would
  make that journal lie about provenance.

## Running it

```
# see what would happen
uv run python migrations/project-knowledge-1/migrate.py

# do it
uv run python migrations/project-knowledge-1/migrate.py --apply
```

Honors whatever `lib.ren_paths.wiki_root()` resolves (`REN_WIKI_ROOT` /
`CLAUDE_PLUGIN_OPTION_WIKIROOT` / `REN_FRAMEWORK_ROOT`).

Exit code is always 0 — anything the script cannot classify is left in place,
which is always the safe outcome.

Each move is journaled to `state_dir()/migrations/project-knowledge-1.jsonl`
immediately after it happens, so a mid-run failure never loses the record of
files already moved.

## Documented limitation

Only `## Decision map` pointer lines in `type: l2-map` pages are rewritten to
the new `knowledge/` paths. Any OTHER page that references an old flat path
(prose links, non-map pointers) is **not** rewritten — those references go
stale and must be fixed by hand (or surfaced by a wiki-health sweep). This is
deliberate scope: rewriting arbitrary prose links safely is not this
migration's job.

## Tests

`tests/migrations/test_project_knowledge_1.py`.
