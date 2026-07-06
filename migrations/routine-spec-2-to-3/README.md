# routine-spec v2 → v3

Task 6.3 (RenOS 0.2 Phase 6). Mirrors donor's `routine-spec-1-to-2` structure exactly (`migrate.sh` + `verify.json` + this README) — see that migration for the general pattern this one follows.

## What changes

- Adds `allowlist` (nested mapping): `paths: []` (wiki-relative globs the routine may propose writes to) and `capabilities: []` (named capabilities it may invoke). **Empty after migration** — the migration can't know what a pre-existing routine should be allowed to touch; the friend fills it in. See "Validity" below.
- **Overwrites** `failure_handler` to the literal `notify-journal` — the ONLY valid value in 0.2 (spec §3.5: "failure = notify + journal"). A v1/v2 spec's old free-text value (e.g. `"email me@example.com via Resend MCP"`) described a mechanism 0.2 doesn't implement; there is no migration path that preserves that behavior, so the field is normalized rather than left inconsistent with the schema.
- Adds `exit_criterion` with a placeholder value (`"MIGRATED — declare a real exit criterion"`) if absent — a real one is required going forward.
- Bumps `schema_version` 2 → 3.

This is **not purely additive** (unlike 1-to-2) because of the `failure_handler` overwrite — it's the schema tightening around a capability the framework never actually offered a working implementation of pre-0.2. Per ADR-019/027 conventions this would be flagged for MINOR-vs-MAJOR judgment by the framework's own versioning discipline; noted here for whoever owns that call.

## Mode: scripted

Mechanical — a schema bump plus three deterministic frontmatter insertions/overwrites, frontmatter-bounded. No semantic judgment, so there is no `migrate.md`. Values are written **without inline `#` comments** (same reasoning as 1-to-2: the framework's frontmatter parsers don't strip them, and a commented value would fail a `verify.json` `yaml.in`/`yaml.equals` check).

## Validity after migration (load-bearing distinction)

An **empty** `allowlist.paths` is a **valid** v3 spec — but it means the routine can propose nothing until a human fills it in. `skills/routine-init/lib.validate_routine_spec(spec, migrated=True)` treats empty `paths` as a **warning**, not an error, for exactly this case. A **brand-new** spec authored via `/ren:routine-init` (`migrated=False`, the default) requires **non-empty** `paths` — a routine that may touch anything is invalid by schema at declaration time; a migrated routine that (for now) may touch nothing is valid but inert.

`allowlist.paths` entries must never include `global/` or `global/**` — routines can never write to the global tier. `validate_routine_spec` enforces this at declaration time; `lib.governance.tiers.tier_of` (Task 6.1) independently enforces it again at apply time (a routine `memory_write` to a `global/` page is always `diff_approved`, never `auto`) — belt and suspenders, not redundant, since a routine could theoretically declare an allowlist that (incorrectly) includes a global path and this is the schema-level backstop against that.

## Compatibility

- Framework versions shipping schema v3 write the new fields; older versions read v2 pages fine until they're migrated.
- N+3 deprecation window applies per ADR-027 convention (documented here for consistency with 1-to-2; the actual registry/doctor machinery that enforces this is out of scope for Task 6.3).

## Rollback

- Snapshot at runtime: `${CLAUDE_PLUGIN_DATA}/wiki-snapshots/v2-pre-update-<ts>/` (same convention as 1-to-2).
- Manual restore: `cp -a $CLAUDE_PLUGIN_DATA/wiki-snapshots/<latest>/. $REN_WIKI_ROOT/`
