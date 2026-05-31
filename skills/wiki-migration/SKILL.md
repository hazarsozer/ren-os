---
name: wiki-migration
description: Use when /sf:update is upgrading the framework and detected one or more schema-version bumps. Composes the migration chain per page-type, applies migrate.sh/migrate.md, runs verify.json assertions, and reports per-page PASS/FAIL to the update driver. Also invoked by /sf:doctor (read-only) to compute schema-drift status against the canonical registry.
version: 0.1.0
license: MIT
type: skill
schema_version: 1
framework_version: 1.0.0
owner_module: sf-distribution

contract:
  required_outputs:
    - "For /sf:update PLANNING: a JSON migration plan of shape {page_type: [migration_id, ...]} computed from schemas.json"
    - "For /sf:update MIGRATING: each affected page transformed via its migrate.sh (scripted), migrate.md (LLM-driven), or both (hybrid)"
    - "For /sf:update VERIFYING: per-page PASS/FAIL from verify.json assertions (exit 0 all pass, 1 any fail, 2 missing inputs)"
    - "For /sf:doctor: read-only per-page drift status (up-to-date / migration-available / read-only-beyond-N+3) with zero writes"
  budgets:
    turns: 20
    files_written: 200
    duration_seconds: 300
  permissions:
    read:
      - "schemas.json"
      - "migrations/**"
      - "~/.startup-framework/wiki/**"
      - "${CLAUDE_PLUGIN_DATA}/wiki-snapshots/**"
    write:
      - "~/.startup-framework/wiki/**"
    execute:
      - "scripts/compute-migration-chain.sh"
      - "scripts/apply-migration.sh"
      - "scripts/verify-page.sh"
  completion_conditions:
    - "Under /sf:doctor: no file is created, modified, or deleted (read-only scan only)"
    - "Under /sf:update: page writes occur only when the /sf:update-owned snapshot already exists at ${CLAUDE_PLUGIN_DATA}/wiki-snapshots/<latest>/"
    - "verify-page.sh returned a clean exit code (0/1/2) for every migrated page"
  output_paths:
    - "~/.startup-framework/wiki/"
---

# wiki-migration

The schema-versioning runtime for the startup framework. Per ADR-027.

## When to invoke

- `/sf:update` enters PLANNING → reads `schemas.json` to compute migration chains per page-type.
- `/sf:update` enters MIGRATING → applies migrations to each affected page.
- `/sf:update` enters VERIFYING → runs `verify.json` assertions against each migrated page.
- `/sf:doctor` SCHEMA VERSIONS section → reads `schemas.json` + scans wiki frontmatter to compute drift status (READ-ONLY; never writes).

## What lives in this skill

| File | Purpose |
|---|---|
| `schemas.json` | Canonical page-type registry. Owned by sf-distribution; peers PR into this. |
| `schemas.schema.json` | JSON Schema validating schemas.json shape. CI enforces. |
| `verify.schema.json` | JSON Schema validating each migration's verify.json. CI enforces. |
| `MIGRATION_PATTERN.md` | Contributor guide for authoring a new migration directory. |
| `migrations/_template/` | Copy-this scaffold for new migrations. NOT a real migration. |
| `migrations/<page-type>-<from>-to-<to>/` | A real migration. Discovered + applied by `apply-migration.sh`. |
| `scripts/compute-migration-chain.sh` | Given target framework version, computes which migrations to run per page. |
| `scripts/apply-migration.sh` | Dispatches scripted vs LLM-driven vs hybrid mode per migration README. |
| `scripts/verify-page.sh` | verify.json runner; implements the locked predicate vocabulary. |

## Contracts

### With peers (universal)

- Every page-type a peer's module writes to MUST be registered in `schemas.json` with `current: 1, supported_from: 1, migrations: []` at v1.
- Every page peers write MUST include `framework_version` + `schema_version` in YAML frontmatter (per ADR-027). The values come from this skill's `framework_version` field and `page_types[type].current`.
- Peers register new page-types via PR to `schemas.json` + matching peer module update. The CI workflow `validate.yml` enforces that any new page-type registration is accompanied by a sample-page fixture under `tests/fixtures/`.

### With /sf:update

- `compute-migration-chain.sh` outputs a JSON plan: `{page_type: [migration_id, ...]}`.
- `apply-migration.sh` is called per (page, migration) with `--snapshot-dir` so semantic transformations can reference pre-migration content.
- `verify-page.sh` returns exit 0 on all assertions PASS, exit 1 on any FAIL, exit 2 on missing inputs.

### With /sf:doctor

- Read-only scan via `scripts/scan-schemas.sh` (lives in `skills/sf-doctor/scripts/check-schemas.sh` and imports this skill's registry).
- Computes per-page status: up-to-date / migration-available / read-only (beyond N+3).

## Schema-policy reminder

Per ADR-019 + ADR-027:

| Framework bump | Allowed schema change |
|---|---|
| PATCH | None. Any migration directory ships in MINOR+. |
| MINOR | Additive only. New optional fields with defaults. New page-types. NO renames, NO removals. |
| MAJOR | Anything. RC release process per ADR-019. |

The MIGRATION_PATTERN.md document elaborates.

## What this skill does NOT do

- Author migrations. Each contributor writes their own migration directory.
- Make policy decisions. The registry + verify-vocabulary is the policy surface.
- Touch the wiki without snapshot. The /sf:update driver owns snapshotting; this skill assumes the snapshot already exists at `${CLAUDE_PLUGIN_DATA}/wiki-snapshots/<latest>/`.
