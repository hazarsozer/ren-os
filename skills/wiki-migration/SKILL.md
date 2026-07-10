---
name: wiki-migration
description: |
  Use when a wiki page's schema_version is behind the registry's current
  version for its page type. Owns the minimal schema registry
  (schemas.json) and a thin verify/apply primitive for running one
  migration directory against one page. Invoked by /ren:update, not
  directly by the friend.
version: 0.4.4
license: MIT
type: skill
execution_tier: deterministic
schema_version: 1
framework_version: "0.4.4"

contract:
  required_outputs:
    - "run_migration() returns the migrate.sh subprocess's exit code + stdout/stderr, never raising"
    - "verify_page() returns (passed, failures) against a verify.json's assertions"
  budgets:
    turns: 5
    files_written: 0
    duration_seconds: 30
  permissions:
    read:
      - "skills/wiki-migration/schemas.json"
      - "migrations/**"
      - "~/.renos/wiki/**"
    write: []
    execute:
      - "migrations/*/migrate.sh"
  completion_conditions:
    - "load_registry() returns the page_types dict without raising, even if schemas.json is malformed"
  output_paths: []

tags: [migration, schema, registry, verify]
related_skills: [update, doctor]
references_required: []
references_on_demand: []
---

# wiki-migration

The minimal registry + runner `/ren:update` (and `/ren:doctor`'s schema-version check) drive migrations through. Per spec §7.1, donor's heavy chain-computer + registry-template + JSON-schema-validated verify-page.sh machinery is **pre-excluded** for 0.2 — this is deliberately thin.

## `schemas.json`

Enumerates only the page types actually stamped by something in this repo: `identity`, `l2-map` (both still at their initial schema, no migrations yet), and `routine-spec` (schema 3, migrated via `routine-spec-1-to-2` then `routine-spec-2-to-3`). Not a speculative full taxonomy — add an entry only when a page type gets a real migration.

## The env-mapping shim (load-bearing)

`migrations/routine-spec-1-to-2/` was **carried verbatim** from donor and expects `SF_WIKI_ROOT`/`SF_SNAPSHOT_DIR`. `migrations/routine-spec-2-to-3/` was written fresh for this repo and expects `REN_WIKI_ROOT`/`REN_SNAPSHOT_DIR`. `run_migration()` sets **both** pairs of env vars to the same values on every invocation, so the same thin runner drives either migration directory without needing to know in advance which naming convention its `migrate.sh` reads. This is documented here rather than fixed at the source, because "carry verbatim" for 1-to-2 was an explicit instruction (Task 6.3) — the shim is the seam, not a bug to clean up.

## Behavior

1. `load_registry()` reads `schemas.json`.
2. `migration_chain(page_type, from_version)` returns the ordered subset of that page type's migration directories still needed to reach `current`.
3. For each directory in the chain: `run_migration(migration_dir, page_path, wiki_root, snapshot_dir)` invokes its `migrate.sh` (idempotent, in-place — see each migration's own README for what it changes).
4. `verify_page(verify_json_path, page_path)` checks the migrated page's frontmatter against that migration's `verify.json` assertions (`yaml.valid`/`yaml.equals`/`yaml.present`/`yaml.in`; `snapshot.body-identical` is not implemented here — callers that need it compare bodies directly, which both migration test suites already do).

## What this skill does NOT do

- Compute a full dependency-ordered migration chain across ALL page types with cross-references (donor's chain-computer). This is a flat per-page-type list.
- Validate `verify.json` files against a JSON Schema. `verify_page()` is a small, direct predicate interpreter for the four predicate kinds actually used by the two migrations in this repo.
- Decide WHEN to migrate. `/ren:update` (this skill's only caller) owns the snapshot-before/diff-approval/apply flow around these primitives.

## References

- `migrations/routine-spec-1-to-2/`, `migrations/routine-spec-2-to-3/` — the two migration directories this skill can run
- `skills/update/` — the only intended caller of `run_migration`/`verify_page`
- `skills/doctor/` — reads `load_registry()`/`migration_chain()` for its schema-version check
