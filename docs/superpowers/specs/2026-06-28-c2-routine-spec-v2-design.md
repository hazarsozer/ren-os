# C2 — `routine-spec` v2 `verification_strategy` (First Real Schema Migration) — Design Spec

> **Status:** Approved design (2026-06-28). Brainstormed via `superpowers:brainstorming`; scope + the field
> shape are determined by ADR-037's recorded plan + ADR-027's additive-MINOR rules (no genuine fork), resolved
> under the maintainer's standing "use your own reasoning" directive. The contract for the TDD build.
>
> **Roadmap slice:** C2 — the `routine-spec` v1→v2 bump forward-recorded in C3a's page-type batch (ADR-037 §6
> + ADR-027 amendment 2026-06-28). The sibling B1 (`experiment-log` writer) shipped 2026-06-28 (`168b3d0`).
> This is the **framework's first real schema migration** — everything is `current:1, migrations:[]` today.
> **Amends:** ADR-027 (records the first concrete migration), ADR-034 (`routine-spec` gains v2).
> **Constrained by:** ADR-027 (migration mechanics, N+3 deprecation, additive-MINOR), ADR-019 (semver: additive
> = MINOR), ADR-034 (`routine-spec` owner = sf-cadence).

---

## 1. Purpose

C4 shipped the `routine-spec` page-type (one page per live cadence routine). It records *what* a routine does
and *how it fails*, but not **how you know it worked**. C2 adds `verification_strategy` — the routine's
success signal (`visual | test-run | lint | llm-judge | manual`) + an optional `verification_tools` list — so
`/ren:doctor` and the wake-up hook can surface not just "this routine is live" but "and here's how its output
is checked."

It is an **additive** change (a new optional field with a default) → a **MINOR** schema bump (ADR-027/019).
But it is the framework's **first real migration**, so the whole ADR-027 machinery — registry bump, a
`migrations/<type>-1-to-2/` dir, a fixture, the discovery/verify scripts — runs end-to-end for the first time.
Two latent gaps surface and must be fixed for the migration to be visible at all (§4).

## 2. Locked decisions (determined, 2026-06-28)

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | **Field** | `verification_strategy` (enum `visual\|test-run\|lint\|llm-judge\|manual`) + optional `verification_tools` (YAML list, default `[]`). | ADR-037 §6's recorded plan. Both added in ONE v1→v2 bump (avoids a later bump just for `tools`). |
| 2 | **Bump kind** | Additive **MINOR**; scripted migration. | New optional fields with defaults — ADR-027 §"schema change scope" + MIGRATION_PATTERN's additive row. |
| 3 | **Migration default** | `verification_strategy: manual`, `verification_tools: []`. | Conservative: a migrated v1 page makes no behavioural claim until the friend edits it (`# default — please review`). |
| 4 | **Discovery gap** | Add `routine-spec` to **both** `compute-migration-chain.sh` and `doctor/check-schemas.sh`. | Both hardcode page-type → glob and were written pre-C4; neither lists `routine-spec`, so the migration would be invisible. `instincts`/`experiment-log` are also absent but harmless at `current:1` → noted, deferred. |
| 5 | **Writer + migration ship together** | One slice. | The bump requires new pages to be written at v2 (template) AND old pages migrated (migrate.sh); shipping either alone is incoherent (fresh pages would instantly read as "migration available"). |

## 3. The migration — `migrations/routine-spec-1-to-2/` (scripted)

Authored per MIGRATION_PATTERN.md (copy `_template`, mode **scripted**, delete `migrate.md`):

- **`README.md`** — `## Mode: scripted`; what changes (adds `verification_strategy` + `verification_tools`,
  bumps `schema_version`); compatibility (v1 readable through the N+3 window; v2 written from now);
  rollback (snapshot path).
- **`migrate.sh`** — contract per `_template` (`$1` = page path, in-place; `SF_WIKI_ROOT`/`SF_SNAPSHOT_DIR`
  env; stdout `OK`/`SKIP`; exit 0/1/2). Idempotency guard (`grep -q '^schema_version: 2'` → SKIP). Transforms,
  frontmatter-bounded: `sed` bump `schema_version: 1`→`2`; insert `verification_strategy: manual  # default —
  please review` after the schema line if absent; insert `verification_tools: []` after that if absent. Body
  untouched. GNU-sed style (matches `_template`).
- **`verify.json`** (conforms to `verify.schema.json`): `yaml.valid`; `yaml.equals schema_version 2`;
  `yaml.equals type routine-spec`; `yaml.present framework_version`; `yaml.in verification_strategy
  [visual,test-run,lint,llm-judge,manual]`; `yaml.present verification_tools`; `snapshot.body-identical`
  (additive frontmatter only → body must match).

## 4. Discovery fixes (required) + registry

- **`schemas.json`:** `routine-spec` `current: 1 → 2`, `migrations: ["1-to-2"]`. `supported_from` stays `1`,
  `deprecated_below` stays `null` (v1 still in-window).
- **`scripts/compute-migration-chain.sh` `files_for()`** and **`doctor/scripts/check-schemas.sh`
  `globs_for()`:** add `routine-spec → glob(wiki_root/"routines"/"*.md")`. Without both, `/ren:update` computes
  no chain and `/ren:doctor` shows `skip (no files)` even when v1 routine-specs exist. (Deferred, noted:
  `instincts`/`experiment-log` are likewise absent from both; harmless while `current:1`, to be added when they
  first migrate.)

## 5. Writer side — `routine-init`

- **`templates/wiki/routine-spec.md.tmpl`:** `schema_version: 1 → 2`; add `verification_strategy:
  "{{verification_strategy}}"` and `verification_tools: {{verification_tools}}` to frontmatter; a short
  "## Verification" body section.
- **`lib/__init__.py`:** `routine_init(...)` gains `verification_strategy: str = "manual"` (validated against
  `VALID_VERIFICATION_STRATEGIES = {visual, test-run, lint, llm-judge, manual}`) + `verification_tools:
  tuple[str, ...] = ()` (rendered as a YAML flow list `[a, b]` / `[]`); both added to `placeholders`. Invalid
  strategy → refuse with no writes (mirrors the trigger/tier validation).
- **`SKILL.md`:** elicit `verification_strategy` (+ optional tools) in the interview; note new pages are v2.
- **`eval/eval.json`:** add an assertion that the spec page carries `verification_strategy`.

## 6. Testing (TDD)

- **Migration (new `skills/wiki-migration/tests/test_routine_spec_migration.py`, pytest driving the bash):**
  copy `fixtures/routine-spec-v1/sample-1.md` → run `migrate.sh` → assert `schema_version: 2`,
  `verification_strategy: manual` + `verification_tools: []` present, body byte-identical, stdout `OK`; run
  `verify-page.sh verify.json migrated snapshot` → exit 0; re-run `migrate.sh` → stdout `SKIP`, file unchanged
  (idempotent). A page already carrying a `verification_strategy` is not double-inserted.
- **Discovery:** `compute-migration-chain.sh` over a tmp wiki with a v1 routine-spec emits a `routine-spec`
  chain `["1-to-2"]`; `check-schemas.sh` reports `routine-spec` `warn / migration available` (not `skip`).
- **Writer (`routine-init/lib/tests`):** update `test_writes_routine_spec_page` to `schema_version: 2`; new
  pages carry `verification_strategy` (default `manual`) + `verification_tools`; an explicit strategy renders;
  an invalid strategy refuses with no writes; tools render as a YAML list.

## 7. Governance — amendments (this IS a schema change)

- **ADR-027 amendment (2026-06-28):** the framework's first real migration ships — `routine-spec` 1→2,
  scripted, additive `verification_strategy`/`verification_tools`. Records the discovery-function fix and the
  `instincts`/`experiment-log` deferral.
- **ADR-034 amendment:** `routine-spec` gains v2 `verification_strategy`; `/ren:routine-init` elicits it.
- **CHANGELOG:** `[Unreleased]` Added bullet **and** a `### Schema` entry (`routine-spec` 1 → 2: added
  `verification_strategy` (default manual) + `verification_tools` (default []). Migration: scripted.).
- **roadmap** C3-batch row (C2 done) + **`wiki/log.md`** + project memory.

## 8. Slice

`feat/c2-routine-spec-v2` off `feat/project-ingest`; `--no-ff` merge. Touches `skills/wiki-migration/`
(schemas.json + migrations/routine-spec-1-to-2/ + tests/ + fixtures/ + compute-migration-chain.sh),
`skills/doctor/scripts/check-schemas.sh`, `skills/routine-init/` (template + lib + SKILL.md + eval.json +
tests), ADR-027 + ADR-034 amendments, CHANGELOG, roadmap, `wiki/log.md`. **This is a MINOR schema bump** — the
first to exercise `migrations[]`, the migration dir, and the verify/chain scripts end-to-end.
