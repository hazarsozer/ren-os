---
name: update
description: |
  Use when the user runs /ren:update to upgrade the framework. Drives the
  migration state machine — fetches latest version, classifies the bump,
  snapshots the wiki, runs migrations, verifies via verify.json, shows diffs
  for approval, applies, and re-verifies. Snapshot/rollback is built in.
  Never silent on MAJOR bumps.
version: 0.3.0
license: MIT
type: skill
execution_tier: deterministic
schema_version: 1
framework_version: "0.3.0"

contract:
  required_outputs:
    - "A printed migration plan (per-page-type ordered migration chain) before any write"
    - "A pre-migration wiki snapshot under ${CLAUDE_PLUGIN_DATA}/wiki-snapshots/v<from>-pre-update-<ISO8601>/"
    - "Migrated wiki pages written to disk only after per-page verify.json PASS + diff approval, with frontmatter schema_version/framework_version bumped"
    - "An appended migration entry in wiki/log.md (snapshot path + update record)"
    - "On --dry-run: the plan only, with zero writes to wiki, snapshot dir, or marketplace"
  budgets:
    turns: 30
    files_written: 200
    duration_seconds: 600
  permissions:
    read:
      - "skills/wiki-migration/**"
      - "migrations/**"
      - "~/.renos/wiki/**"
      - "${CLAUDE_PLUGIN_DATA}/wiki-snapshots/**"
    write:
      - "~/.renos/wiki/**"
      - "${CLAUDE_PLUGIN_DATA}/wiki-snapshots/**"
    execute:
      - "scripts/snapshot.sh"
      - "scripts/restore.sh"
      - "scripts/prune-snapshots.sh"
      - "scripts/version-compare.sh"
  completion_conditions:
    - "Equal version → exits without snapshotting"
    - "A snapshot exists before any page is migrated"
    - "Failed/crashed pages were reverted from snapshot while other pages continued; snapshot retained"
  output_paths:
    - "${CLAUDE_PLUGIN_DATA}/wiki-snapshots/"

tags: [update, migration, snapshot, rollback]
related_skills: [wiki-migration, backup, doctor]
references_required: []
references_on_demand: []
---

# update

Carried near-verbatim from donor `skills/update/` (Task 7.3) — the migration state machine's snapshot/restore/version-compare substrate. Renamed identifiers only: `SF_WIKI_ROOT` → `REN_WIKI_ROOT`, `SF_SNAPSHOT_MODE` → `REN_SNAPSHOT_MODE`, `~/.startup-framework/` → `~/.renos/`.

## Scripts (carried, unchanged behavior)

- `scripts/snapshot.sh <from-version>` — copies the wiki to `${CLAUDE_PLUGIN_DATA}/wiki-snapshots/v\<from\>-pre-update-\<ISO8601\>/`, prunes beyond `CLAUDE_PLUGIN_OPTION_SNAPSHOTRETAIN` (default 3), logs the snapshot to `wiki/log.md`.
- `scripts/restore.sh {--list|--whole <snap>|--page <snap> <rel>}` — lists snapshots, restores the whole wiki (stashing the pre-restore state first), or restores a single page.
- `scripts/prune-snapshots.sh [<N>] [--dry-run]` — retention enforcement for both normal snapshots and `STASH-broken-*` dirs (created by `restore.sh --whole`).
- `scripts/version-compare.sh <A> <B>` / `--bump <A> <B>` — strict semver comparison + bump classification (patch/minor/major/downgrade/equal/prerelease). No CC-marketplace dependency; the framework owns semver semantics since the marketplace treats `version` as an opaque string.

## When to use this skill

- Friend invokes `/ren:update` to check for and apply a framework version bump
- Friend invokes `/ren:update --dry-run` to preview the migration plan with zero writes
- Friend invokes `/ren:update --restore-snapshot` to interactively restore from a prior snapshot

## What this skill does NOT do

- Decide WHICH migrations exist or their chain order — that's `skills/wiki-migration`'s registry (this skill calls into it, doesn't own it).
- Auto-rollback on new post-update doctor issues. The snapshot is retained and named; the human decides whether to restore.
- Force-push or touch the backup remote. That's `skills/backup`'s scope entirely.

## 0.3 update notes

- **queue-governance 2→3 (Task 10):** a friend upgrading past 0.3 has queue
  entries left `pending` for the OLD reason (0.2 gated every write) rather
  than the new one (v2.2's instruction-plane/contradiction holds only). Run
  `migrations/queue-governance-2-to-3/migrate.py` once as a post-update step
  after the version bump lands — it is NOT part of the `skills/wiki-migration`
  page-type chain (it walks queue state under `state_dir()/queue/`, not wiki
  pages), so `/ren:doctor`'s schema-drift check does not surface it; invoke it
  directly. `--check` previews what would be released with zero writes.
  Idempotent — safe to (re-)run even if a friend already updated once without
  it. See that migration's README.md for the shape-decision rationale.

## Overlap note: snapshot substrate vs. Task 1.2's per-write snapshots

`lib/memory/snapshot.py` (Task 1.2, G9) is a DIFFERENT snapshot mechanism: per-write-id, page-granularity snapshots for the write-safety substrate (revert a single memory write in one step). `scripts/snapshot.sh` here is whole-wiki, version-bump-granularity, for migration rollback. They serve genuinely different purposes at different granularities — this skill's carried snapshot logic is NOT rewritten to unify with Task 1.2's substrate; that unification (if it's ever worth doing) is a 0.3-scoped ADR decision, not something to improvise here. Noted per the task brief's explicit instruction not to rewrite working carried code.

## References

- `skills/wiki-migration/` — the migration registry + verify/apply primitive this skill drives
- `migrations/queue-governance-2-to-3/` — the standalone (non-chain) queue-state migration named in the 0.3 update notes above
- `lib/memory/snapshot.py` (Task 1.2) — the OTHER snapshot mechanism (per-write, not whole-wiki); see overlap note above
- `skills/doctor/` — the post-update health check this skill's flow ends with
