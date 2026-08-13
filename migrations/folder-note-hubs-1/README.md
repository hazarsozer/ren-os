# folder-note-hubs-1 — knowledge hubs become folder notes

Issue #56 (RenOS 0.7.0). Before 0.7.0 every knowledge hub was named
`index.md` under a `projects/<slug>/knowledge/<topic>/` directory. 0.7.0
renames them to folder notes named after their folder (`<topic>/<topic>.md`),
stamps `hub: true` in frontmatter, and rewrites all inbound links wiki-wide.

See `docs/superpowers/specs/2026-08-13-folder-note-hubs-design.md` for the
founder ruling and the design.

## Shape decision: standalone script, global migration

Like `migrations/project-knowledge-1/`, this is a tree-wide global migration
that applies across ALL page types — not driven by `migration_chain()`, which
is page-type-keyed. The transformation renames files, rewrites links wiki-wide,
and stamps frontmatter. Listed in `schemas.json`'s `global_migrations` for
discoverability only; each is run directly as documented in its own README.

## What it does

For each `projects/<slug>/knowledge/<topic>/index.md` file:

- **Renames** it to `projects/<slug>/knowledge/<topic>/<topic>.md` (a folder note
  named after its folder).
- **Stamps frontmatter** with `hub: true` if not already present (other
  frontmatter preserved byte-for-byte).
- **Rewrites all inbound links** wiki-wide: every `[text](path/to/index.md)` link
  that resolves to a renamed hub is rewritten to the new folder-note name.
  Targets that don't resolve, or that don't land in a `knowledge/` tree, are
  untouched (no false positives on pre-existing danglers).
- **Updates the schema documentation** in `schema.md` files to reflect the new
  naming convention (if schema.md exists and names the old convention).
- **Journaled** — each rename appends one JSON line to
  `state_dir()/migrations/folder-note-hubs-1.jsonl` for auditing and rollback.

## Contract

**Exit code:** Always 0. Files that cannot be safely processed (e.g. due to
collision with an existing folder note) are left in place and reported to
stderr.

**SKIP:** If no `index.md` files exist under any `projects/*/knowledge/`
directory, prints `SKIP: no knowledge hubs named index.md` and exits 0.

**Output:** Either `OK` (success, some files moved + links rewritten) or `SKIP`
(nothing to do).

## Safety

- **Idempotent.** A second run finds nothing to rename and rewrites no links.
- **Collision handling.** If `<topic>/<topic>.md` already exists, the original
  `index.md` is left untouched, and a `WARN` is printed to stderr. Resolve by
  hand.
- **Journaled for audit.** Moves are logged immediately to
  `state_dir()/migrations/folder-note-hubs-1.jsonl` so mid-run failures do not
  lose the record of files already moved.

## Running it

```
# Perform the migration
uv run python migrations/folder-note-hubs-1/migrate.py

# Verify the result
uv run python migrations/folder-note-hubs-1/verify.py
```

Honors whatever `lib.ren_paths.wiki_root()` resolves (`REN_WIKI_ROOT` /
`CLAUDE_PLUGIN_OPTION_WIKIROOT` / `REN_FRAMEWORK_ROOT`).

## Rollback

The migration writes directly to disk, revertible via the whole-wiki
pre-update snapshot at `skills/update/scripts/restore.sh`. No
framework-managed write queue is used, so `ren_write_id` provenance is not
minted; the journal exists for audit only.

## Verification

`verify.py` checks that the migration is complete and consistent:

- No leftover `index.md` files under any `knowledge/` tree.
- No stale links pointing to `index.md` in a `knowledge/` tree (catches missed
  rewrites).
- Every `hub: true` page under a `knowledge/` tree is named after its folder.
- All pointer lines in `type: l2-map` pages parse correctly.

Exit 0 pass, 1 fail; failures printed one per line as `FAIL <check>: <detail>`.

## Journal

Entries written to `state_dir()/migrations/folder-note-hubs-1.jsonl`:

```json
{
  "ts": "2026-08-13T15:30:45Z",
  "from": "projects/demo/knowledge/research/index.md",
  "to": "projects/demo/knowledge/research/research.md"
}
```

And a summary entry after all renames:

```json
{
  "ts": "2026-08-13T15:30:46Z",
  "rewrites": 7
}
```

## Tests

`tests/migrations/test_folder_note_hubs_1_verify.py`.
