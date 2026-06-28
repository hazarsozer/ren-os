# routine-spec v1 → v2

The framework's **first real schema migration** (ADR-027). Until C2 every page-type sat at `current: 1` with
an empty `migrations: []`; this is the one that exercises the whole machinery — registry entry, migration dir,
`verify.json`, the chain computer, and `/ren:doctor` drift — end to end.

## What changes
- Adds `verification_strategy` (enum: `visual | test-run | lint | llm-judge | manual`) — how a routine's
  output is confirmed. **Default on migration: `manual`** (the friend verifies; no behavioural claim is made
  until they review and set the real strategy).
- Adds `verification_tools` (YAML list; default `[]`) — optional tool names backing the strategy (e.g.
  `[pytest]` for `test-run`, `[ruff]` for `lint`).
- Bumps `schema_version` 1 → 2.

Purely **additive** optional fields with defaults → **MINOR** per ADR-019/027. Body content is untouched.

## Mode: scripted
Mechanical — a schema bump plus two deterministic default-field insertions, frontmatter-bounded. No semantic
judgment, so there is no `migrate.md`. Values are written **without inline `#` comments**: the framework's
frontmatter parsers don't strip them, and a commented value would fail `verify.json`'s `yaml.in` enum check.
The "please review" guidance lives here and in the diff the friend approves.

## Compatibility
- Framework versions shipping schema v2 write the new fields; older versions read v1 pages fine (additive).
- N+3 deprecation (ADR-027): v1 routine-specs stay auto-migrate-able through the window. `supported_from`
  stays `1`; `deprecated_below` stays `null`.

## Rollback
- Snapshot at runtime: `${CLAUDE_PLUGIN_DATA}/wiki-snapshots/v1-pre-update-<ts>/`
- Manual restore: `cp -a $CLAUDE_PLUGIN_DATA/wiki-snapshots/<latest>/. $SF_WIKI_ROOT/`
