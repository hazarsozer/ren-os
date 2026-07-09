---
name: doctor
description: |
  Use when the friend wants a framework health check, or after /ren:update
  to confirm nothing broke. Triggers on /ren:doctor. Runs a battery of
  small, isolated checks (env, wiki structure, frontmatter, schema
  versions, budget lint, dangling L2 pointers, graphify status, backup
  configuration, global-tier drift, harness neutrality) — all warn-not-block.
version: 0.3.5
license: MIT
type: skill
execution_tier: deterministic
schema_version: 1
framework_version: "0.3.5"

contract:
  required_outputs:
    - "One CheckResult per registered check, printed as a report"
  budgets:
    turns: 2
    files_written: 0
    duration_seconds: 30
  permissions:
    read:
      - "~/.renos/wiki/**"
      - "skills/**/SKILL.md"
      - "skills/wiki-migration/schemas.json"
    write: []
    execute:
      - "scripts/lint-yaml-frontmatter.py"
  completion_conditions:
    - "run_checks() returns one CheckResult per registered check, even if individual checks crash"
  output_paths: []

tags: [doctor, health-check, diagnostics]
related_skills: [update, backup, wiki-migration, metric-watch]
references_required: []
references_on_demand: []
---

# doctor

Adapted from donor `skills/doctor/scripts/check-*.sh` (one bash script per section) into a single Python check-harness (`skills.doctor.lib.run_checks()`) — the new checks below need to call directly into this repo's Python lib modules (`collect`, `promotion`, `code-map`, `backup`, `portability`), so the harness itself is Python, not bash, per this task's ADAPT (not CARRY) label.

## Checks

**Carried (logic ported from donor's bash):**

| Check | What it verifies |
|---|---|
| `check_env` | git + python3 on PATH, `ANTHROPIC_API_KEY` set |
| `check_wiki_structure` | wiki root exists, `identity.md`/`log.md` present |
| `check_frontmatter` | `scripts/lint-yaml-frontmatter.py` passes over the wiki |
| `check_schema_versions` | every typed page vs. `skills.wiki-migration.lib`'s registry — behind-current pages named with their pending migration chain |

Donor's Node/gh/claude-cli checks, activity-feed/RC-channel/fleet checks, and the wikilink dead-link/stale-page/heavy-page check are all **dropped** — see the module docstring's "DROPPED entirely" note for why each one doesn't apply here.

**New (Task 7.3, all warn-not-block):**

| Check | What it verifies |
|---|---|
| `check_budget_lint` | measured `capability_tokens` (Task 3.1) vs. any SKILL.md-declared `tokens:` ceiling — `info` when nothing's declared to compare against yet, `skip` when no measured data exists |
| `check_dangling_pointers` | every l2-map page's "## Decision map" pointer targets actually exist |
| `check_graphify_status` | `skills.code-map.lib.status()` — not installed → `info` w/ companions.md pointer; version outside pin → `warn`; stale graph → `info` |
| `check_companions` | registry choices vs reality (lib/companions) — accepted-but-missing → warn; undecided-and-absent → info; consistent → ok |
| `check_backup_configured` | `skills.backup.lib.backup_configured()` |
| `check_global_drift` | `lib.memory.promotion.demote_check()` — non-doctrine/preference pages in `global/` |
| `check_harness_neutrality` | `lib.portability.agents_surface.lint_generated_surfaces` — **soft-wired**: skips cleanly if that module (Task 7.2, built in parallel) isn't present |

## Behavior

1. Call `skills.doctor.lib.run_checks()`.
2. Each check is isolated — a crashing check produces a `CheckResult(status="error", message="check crashed: ...")` rather than aborting the run; every OTHER check still executes (same isolation discipline as `skills.metric-watch.lib.watch`, Task 6.3).
3. Render the report: one line per check, `<name> | <status> | <message>`.

## Why every check is warn-not-block

Per the task brief: doctor is diagnostic, not a gate. Even the carried checks (env, wiki structure, frontmatter) report their findings as `ok`/`warn`/`skip`/`info` — none of them can fail a build or block a command. The risk-tier gate (Task 6.1) and the PreToolUse hooks (Task 6.2) are where blocking actually happens; doctor's job is visibility.

## What this skill does NOT do

- Fix anything. Every check is read-only; remediation is always a follow-up action the friend or another skill takes.
- Validate `verify.json`/schema conformance in the JSON-Schema sense. `check_schema_versions` only asks "is this page's declared `schema_version` behind the registry's current for its type" — that's `skills.wiki-migration.lib.migration_chain`'s job, reused here, not reimplemented.
- Require graphify, backup, or `lib.portability` to be present. Each of those checks degrades gracefully (info/skip) rather than erroring when its dependency is absent.

## References

- Task 3.1 (`lib/instrument/collect.py`) — `capability_tokens` data `check_budget_lint` reads
- Task 6.1 (`lib/memory/promotion.py`'s `demote_check`) — the global-tier drift this check surfaces
- Task 7.2 (`lib/portability/agents_surface.py`) — soft-wired dependency for `check_harness_neutrality`
- `skills/code-map/lib/__init__.py` — `status()`, the graphify-presence/freshness check
- `skills/backup/lib/__init__.py` — `backup_configured()`, shared with metric-watch's own backup check
- `skills/wiki-migration/lib/__init__.py` — the registry `check_schema_versions` reads
