# `_template` — copy this when authoring a migration

**This is NOT a real migration.** It will not be discovered by `compute-migration-chain.sh` (the discovery glob excludes directories starting with `_`). Don't try to run it.

When you need to author a new migration:

```bash
cp -a migrations/_template migrations/<page-type>-<from>-to-<to>
# e.g.
cp -a migrations/_template migrations/identity-1-to-2
```

Then edit the four files inside the copied directory + register in `schemas.json` + add a fixture under `tests/fixtures/` + add a `CHANGELOG.md` entry. The full guide is in `../../MIGRATION_PATTERN.md`.

## Files in this template

| File | What to do with it |
|---|---|
| `README.md` (this file) | Replace ENTIRELY with the new migration's description. See template content below. |
| `migrate.sh` | Edit the transformations. Keep the idempotency guard. Keep `set -euo pipefail`. Keep the exit codes. |
| `migrate.md` | If your mode is "scripted-only", delete this file. Otherwise, write the LLM prompt that handles the semantic part. |
| `verify.json` | Replace the example assertions with the assertions that confirm YOUR migration succeeded. |

## What a real README.md should look like

```markdown
# <Page-type> v<from> → v<to>

## What changes
- BULLET each change. Field added? Renamed? Removed?
- Be specific. Mechanical changes vs semantic changes.

## Mode: scripted | LLM-driven | hybrid
- Justify your choice.
- If hybrid, describe what each file does.

## Compatibility
- Which framework version reads schema v<from>? Which writes v<to>?
- N+3 deprecation timeline: which framework version will make v<from> read-only?

## Rollback
- Snapshot location at runtime: ${CLAUDE_PLUGIN_DATA}/wiki-snapshots/v<from>-pre-update-<ts>/
- Manual restore: cp -a $CLAUDE_PLUGIN_DATA/wiki-snapshots/<latest>/. $SF_WIKI_ROOT/
```

## Hard rules (recap from MIGRATION_PATTERN.md)

1. Idempotent.
2. Deterministic (within scripted; LLM is one-shot).
3. No body data loss without explicit verify.json consent.
4. Preserve untouched frontmatter keys verbatim.
5. No PATCH-version migrations.
6. No external network in `migrate.sh`.
7. No writes outside the target page.
