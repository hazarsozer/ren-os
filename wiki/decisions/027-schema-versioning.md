---
title: "ADR-027: Schema Versioning — Per-Page schema_version Field, Hybrid Migrations, N+3 Deprecation"
status: accepted
date: 2026-05-28
sunset-review: 2026-11-28
references-pages: [llm-wiki-pattern, skill-creator]
affects-components: [wiki, skills, install, update, migration, doctor]
relates-to: [004-wiki-design-hierarchical, 011-skill-schema, 014-project-sub-wiki-taxonomy, 015-onboarding, 017-per-friend-wiki-scope, 019-framework-distribution, 026-backups-and-recovery]
amendments:
  - "2026-05-28: snapshot location override — snapshots live at `${CLAUDE_PLUGIN_DATA}/wiki-snapshots/` (per CC's documented plugin persistent-data directory), NOT at `~/.startup-framework/wiki-snapshots/` as suggested in § Migration mechanics step 2 of this ADR. Reasoning: Claude Code's plugin reference documents `${CLAUDE_PLUGIN_DATA}` as a persistent directory that survives plugin updates — exactly the lifetime snapshots need. The original ADR-027 text was written without knowledge of this CC primitive. Path resolves to `~/.claude/plugins/data/<plugin-id>/wiki-snapshots/`. Source: https://code.claude.com/docs/en/plugins-reference § Persistent data directory. Implementation confirmed by sf-distribution Task #32 (`skills/sf-update/scripts/snapshot.sh`)."
---

# ADR-027: Schema Versioning

## Context

ADR-017 committed the framework to **backwards-compatibility**: plugin updates must not break wikis from earlier versions; breaking changes require explicit migration. ADR-019 operationalizes this in the update mechanism (semver, monthly stable releases, `/sf:update` runs migrations). What's missing: the concrete schema-versioning mechanics that make this work.

Without ADR-027, contributors writing new wiki page types or evolving existing ones have no clear rules for how schema changes propagate to friends running older framework versions. Migrations get ad-hoc; some friends end up with broken wikis on update.

## Decision

### Per-page `schema_version` field in YAML frontmatter

Every wiki page's YAML frontmatter (per ADR-004 + ADR-011 conventions) gains two version fields:

```yaml
---
title: ...
type: research | decision | identity | project-state | ...
framework_version: 1.0.0      # framework version when this file was last written
schema_version: 1              # the page's format-schema version (per page type)
date: ...
---
```

- **`framework_version`**: which framework version wrote the page. Bumps automatically on `/sf:wrap` or any framework-driven write.
- **`schema_version`**: which schema this page conforms to. Bumps only when the page TYPE's format meaningfully changes (e.g., identity.md adds a new required field; project STATE.md restructures sections).

Different page types have INDEPENDENT schema versions. `identity.md` schema 1 ≠ `project STATE.md` schema 1; they evolve independently.

The framework maintains a **canonical schema registry** in `plugin/skills/wiki-migration/schemas.json` (or similar) listing current schema versions per page type:

```json
{
  "identity": 1,
  "project-state": 1,
  "project-roadmap": 1,
  "research": 1,
  "decision": 1,
  "log-entry": 1,
  ...
}
```

When friends update the framework, `/sf:doctor` and `/sf:update` reconcile each page's `schema_version` against the registry.

### Pages without `schema_version` (legacy / pre-v1.0)

Default treatment: assume `schema_version: 1` if missing. The first migration step (1 → 2) for any page type adds the field explicitly. After framework v1.0 release, ALL new pages include `schema_version` from the start (skill templates write it).

### Migration mechanics

When `/sf:update` runs and detects a framework version bump that includes schema changes:

1. **Identify the chain of migrations needed.** E.g., if friend is on v1.0 (schema identity=1, project-state=1) and updating to v1.3 which has identity=3 and project-state=2, framework computes the migration path: identity (1→2, 2→3), project-state (1→2).

2. **Take a snapshot.** Copy the entire wiki to `~/.startup-framework/wiki-snapshots/v1.0-pre-update-<timestamp>/`. Retention: keep latest 3 snapshots (configurable).

3. **For each migration step:**
   - Apply the transformation (scripted or LLM-driven; see below)
   - Update `schema_version` field on transformed pages
   - Update `framework_version` field to the new version

4. **Show diff for user approval** (similar to `/revise-claude-md`'s pattern from ADR-009 amendment):
   ```
   Migration: identity.md  1 → 2
   - Adds new field: phase
   - Renames field: tech-preferences → tech_preferences (snake_case)

   Diff (your file):
   - tech-preferences: ...
   + tech_preferences: ...
   + phase: ideation        # default — review and confirm

   [a] approve  [s] skip  [e] edit  [r] revert
   ```

5. **If approved**: write the new file. **If rejected**: skip; framework warns that the page is stuck at the old schema (won't work with new framework features that rely on the new schema; doctor will keep flagging).

6. **If anything goes wrong mid-migration**: restore from snapshot, abort, report.

### Hybrid migrations: scripted for mechanical, LLM-driven for semantic

Migrations live in `plugin/skills/wiki-migration/migrations/<page-type>-<from>-to-<to>/`. Each directory contains:

```
migrations/identity-1-to-2/
├── README.md              # describes what changes + why
├── migrate.md             # the LLM prompt for semantic changes (if needed)
├── migrate.sh             # the script for mechanical changes (if any)
└── verify.json            # binary assertions to verify migration succeeded
```

**Decision rule** (declared in `README.md`):
- **Scripted (`migrate.sh`)**: when changes are mechanical — field renames, sed-style transformations, adding fields with deterministic defaults, file renames. Fast, deterministic, no LLM cost.
- **LLM-driven (`migrate.md`)**: when intent matters — merging two fields into one with judgment about which value wins, restructuring sections semantically, splitting one page into multiple based on content. Requires Claude reasoning.
- **Hybrid**: scripted does the mechanical 80%; LLM handles the 20% that needs judgment.

Each migration declares which mode applies. Friends always see the diff regardless.

**verify.json** holds binary assertions to confirm the migration produced valid output (per ADR-011's eval pattern):

```json
{
  "assertions": [
    "Output file has YAML frontmatter",
    "schema_version field is 2",
    "phase field exists and is one of ideation|building|shipping|other",
    "All original tech-preferences values preserved (now under tech_preferences key)"
  ]
}
```

If verify.json's assertions fail post-migration: abort that page's migration, revert from snapshot, surface error to user.

### Deprecation window: N+3 versions

Per ADR-017's commitment:

- **Schema version V is supported** for reading + writing in framework versions through V+3
- **In framework version V+4**, schema V is no longer auto-migrated; pages stuck at schema V become read-only (framework still reads them but won't write to them; `/sf:update` warns)
- **Older snapshots beyond V+4** require manual migration via documented procedure or restoration from older framework version

This gives friends 3 release cycles (~3 months at monthly cadence per ADR-019) to migrate. Plenty of time.

### Schema change scope: tied to semver per ADR-019

Per ADR-019's semver:

| Version change | Schema policy |
|---|---|
| **PATCH** (e.g., 1.2.3 → 1.2.4) | **No schema changes allowed.** Bug fixes only. |
| **MINOR** (e.g., 1.2.x → 1.3.0) | **Additive schema changes only.** New optional fields with defaults; new page types. No field renames or removals. Migration auto-runs but transparent (no user prompt needed for purely additive). |
| **MAJOR** (e.g., 1.x.x → 2.0.0) | **Breaking schema changes allowed.** Renames, removals, restructures. Migration required, user reviews diffs. RC release process per ADR-019 mitigates risk. |

### `/sf:doctor` integration

Per ADR-025's tech stack matrix doctor output, schema-versioning adds these checks:

```
Schema versions:
  identity.md:           1  (current: 1)  ✅
  project STATE.md:      1  (current: 1)  ✅
  ADR files:             1  (current: 1)  ✅
  research files:        1  (current: 1)  ✅
  log entries:           1  (current: 1)  ✅

No schema migrations pending.
```

When friend is behind:

```
Schema versions:
  identity.md:           1  (current: 2)  ⚠️  migration available
  project STATE.md:      1  (current: 1)  ✅
  ...

Run /sf:update to apply migrations (see CHANGELOG for v1.3 schema changes).
```

When friend has pages stuck at a deprecated schema (>N+3 behind):

```
Schema versions:
  identity.md:           1  (current: 4)  ❌  schema v1 is now beyond deprecation window
                                               page is READ-ONLY; manual migration required.
                                               See RECOVERY.md "Schema beyond deprecation."
```

### `RECOVERY.md` entry (added per this ADR)

Add to the disaster scenarios in `RECOVERY.md` (from ADR-026):

> **"My page is stuck at a deprecated schema (>N+3 versions behind)"**
> - This happens if a friend skipped multiple `/sf:update` runs and crossed the N+3 deprecation window
> - Options:
>   1. Restore from a snapshot in `~/.startup-framework/wiki-snapshots/`, re-migrate stepwise via intermediate framework versions
>   2. Manually update the page to match the current schema (the framework's current schema doc shows what's needed)
>   3. Discard the page if not valuable enough to migrate

## Consequences

**Easier:**
- Contributors writing new wiki page types follow a clear schema-version pattern
- Friends know exactly what version their wiki is at + what migrations exist
- Snapshots provide rollback safety
- Deprecation window (N+3) gives reasonable migration time
- Hybrid migrations (scripted + LLM) handles both mechanical and semantic changes appropriately
- `/sf:doctor` surfaces schema drift as a real concern, not hidden state

**Harder:**
- Every schema change requires authoring a migration (more work for framework maintainers)
- Snapshots take disk space (latest 3 ≈ 3× wiki size — usually small but grows with project sub-wikis)
- Friends who skip several updates may face complex chained migrations
- LLM-driven migrations have non-determinism risk; verify.json assertions are critical

**Now impossible:**
- Silent breaking changes to wiki page formats (must go through migration + diff approval)
- Friends being trapped at a schema version with no upgrade path within the deprecation window

**Sunset review trigger conditions:**
- Friends actually hit the N+3 deprecation window (suggests we're shipping too aggressively or friends are skipping updates) → reconsider window length
- LLM-driven migrations consistently produce regressions (verify.json catches them but friends find it frustrating) → revisit migration mode for affected page types
- A schema change pattern emerges that doesn't fit scripted-or-LLM cleanly → add a third migration mode

## Alternatives considered

### A) Wiki-wide single schema version

**Considered shape**: One `schema_version: N` for the whole wiki; all pages share it.

**Why rejected**: Forces all page types to evolve in lockstep. If identity.md needs a change but project STATE.md is stable, we'd bump the whole wiki's schema. Per-page granularity is the right scope.

### B) No schema versioning at all

**Considered shape**: Trust the framework to handle backwards compat without explicit version fields; let migrations be ad-hoc.

**Why rejected**: ADR-017 explicitly commits to backwards compatibility. Without versioning, migrations are guesswork; future contributors can't tell which pages need transformation.

### C) Scripted-only migrations (no LLM)

**Considered shape**: All migrations are deterministic scripts; no LLM-driven transformations.

**Why rejected**: Semantic schema changes (e.g., "we're splitting `working_style` into `response_length` + `comm_style`") need judgment to handle existing free-form content. LLM is the right tool for that subset.

### D) LLM-only migrations (no scripts)

**Considered shape**: All migrations go through Claude; no shell scripts.

**Why rejected**: Slow, expensive (tokens per page), non-deterministic. Field renames are mechanical and should be scripted. Hybrid is right.

### E) Auto-approve migrations without diff review

**Considered shape**: Just run migrations, no user prompt.

**Why rejected**: Per ADR-017's amendment commitment and ADR-021's "show diffs" pattern from `/revise-claude-md`, user approval is the safety net. Auto-apply risks data loss on semantic changes.

### F) Longer deprecation window (e.g., N+6 instead of N+3)

**Considered shape**: Give friends more time to upgrade.

**Why rejected**: At monthly stable cadence (per ADR-019), N+3 is 3 months — already generous. Longer windows mean we maintain ancient schemas longer; that's burden on us. Friends who skip updates for 3+ months can manually migrate.

## Open questions for implementation phase

1. **Snapshot retention policy** — keeping latest 3 is conservative; could be tunable per friend. Default to 3, expose `SF_SNAPSHOT_RETAIN=N`.

2. **Verify.json failure handling** — what if verify.json's assertions fail for SOME pages but pass for others during a migration? Probably: abort the failing pages (revert from snapshot), continue successful ones, report mixed result.

3. **Schema registry source-of-truth** — `plugin/skills/wiki-migration/schemas.json` is the framework's authoritative list. Friends should never edit this. Document.

4. **Pre-v1.0 framework users** — if someone installs an alpha/RC version of the framework before v1.0 stable, their wikis may have ad-hoc schema_version values. v1.0 release should include a "normalize" migration step that assumes any missing or weird values → schema_version: 1.

5. **`/sf:rollback`** — a slash command to manually restore from a snapshot? Flagged as v2 per ADR-023's V2+ list. For v1: manual `cp` from snapshots directory per RECOVERY.md.

## References

- `wiki/research/llm-wiki-pattern.md` — Karpathy's pattern; the wiki is the artifact whose schema this ADR governs
- `wiki/research/skill-creator.md` — eval pattern (verify.json mirrors)
- ADR-004 (Wiki Design Hierarchical) — page format conventions
- ADR-011 (Skill Schema) — frontmatter conventions
- ADR-014 (Project Sub-Wiki Taxonomy) — page types subject to schema versioning
- ADR-015 (Onboarding) — `/sf:doctor` checks schema versions per this ADR
- ADR-017 (Per-Friend Wiki Scope) — backwards-compat commitment this ADR operationalizes
- ADR-019 (Framework Distribution) — semver policy this ADR ties to
- ADR-026 (Backups & Recovery) — snapshot-based rollback infrastructure this ADR uses
