---
name: sf-update
description: Use when the user runs /sf:update to upgrade the framework. Drives the migration state machine — fetches latest version, classifies the bump, snapshots the wiki, runs migrations, verifies via verify.json, shows diffs for approval, applies, and re-verifies. Snapshot/rollback is built in. Never silent on MAJOR bumps.
version: 0.1.0
license: MIT
type: skill
schema_version: 1
framework_version: 1.0.0
owner_module: sf-distribution

contract:
  required_outputs:
    - "A printed migration plan (per-page-type ordered migration chain) before any write"
    - "A pre-migration wiki snapshot under ${CLAUDE_PLUGIN_DATA}/wiki-snapshots/v<from>-pre-update-<ISO8601>/"
    - "Migrated wiki pages written to disk only after per-page verify.json PASS + diff approval, with frontmatter schema_version/framework_version bumped"
    - "An appended migration entry in wiki/log.md (snapshot path + update record)"
    - "A post-update /sf:doctor --post-update report; on new issues, an explicit no-auto-rollback message naming the snapshot path"
    - "On --dry-run: the plan only, with zero writes to wiki, snapshot dir, or marketplace"
  budgets:
    turns: 30
    files_written: 200
    duration_seconds: 600
  permissions:
    read:
      - "${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json"
      - "skills/wiki-migration/schemas.json"
      - "skills/wiki-migration/migrations/**"
      - "~/.startup-framework/wiki/**"
      - "${CLAUDE_PLUGIN_DATA}/wiki-snapshots/**"
    write:
      - "~/.startup-framework/wiki/**"
      - "~/.startup-framework/wiki/.git/**"
      - "${CLAUDE_PLUGIN_DATA}/wiki-snapshots/**"
    execute:
      - "scripts/version-compare.sh"
      - "scripts/snapshot.sh"
      - "scripts/restore.sh"
      - "scripts/prune-snapshots.sh"
      - "skills/wiki-migration/scripts/compute-migration-chain.sh"
      - "skills/wiki-migration/scripts/apply-migration.sh"
      - "skills/wiki-migration/scripts/verify-page.sh"
      - "git (in ~/.startup-framework/wiki/, only if a remote is configured)"
      - "gh (read-only: gh api repos/<org>/sf-marketplace/contents/.claude-plugin/plugin.json)"
  completion_conditions:
    - "Equal version → exits without snapshotting"
    - "A snapshot exists before any page is migrated"
    - "Every applied page passed verify.json and was approved (or --auto for MINOR additive only; MAJOR always prompts)"
    - "Failed/crashed pages were reverted from snapshot (ROLLBACK_PAGE) while other pages continued; snapshot retained"
    - "wiki/log.md has the appended migration entry and the post-update doctor report was printed"
    - "On --dry-run: no writes occurred anywhere"
  output_paths:
    - "~/.startup-framework/wiki/"
    - "${CLAUDE_PLUGIN_DATA}/wiki-snapshots/"
---

# sf-update

The opt-in framework upgrade command. Per ADR-019 + ADR-027.

The user runs this manually. The skill never runs on session start. The snapshot taken before any migration guarantees rollback is always possible.

## Invocations

```
/sf:update                           upgrade to latest stable (interactive)
/sf:update --rc                      upgrade to latest RC (subscribes to sf-marketplace-rc if needed)
/sf:update --to v1.2.5               specific version (downgrade if a snapshot exists)
/sf:update --dry-run                 show plan; no writes
/sf:update --auto                    auto-approve MINOR additive migrations (still prompts on MAJOR)
/sf:update --restore-snapshot        interactive picker; restore wiki from a snapshot (per ADR-023 V1 fence — flag, NOT a new /sf:rollback command)
```

## The state machine

State transitions, side effects, and failure paths:

```
   ┌─────────────┐
   │   IDLE      │  user invokes /sf:update
   └──────┬──────┘
          ▼
   ┌─────────────┐  Read installed plugin.json#version from ${CLAUDE_PLUGIN_ROOT}/.claude-plugin/.
   │  FETCHING   │  Fetch upstream version via:
   │             │    gh api repos/<org>/sf-marketplace/contents/.claude-plugin/plugin.json
   │             │  Cross-check upstream marketplace.json (info only — plugin.json wins per CC docs).
   └──────┬──────┘  Failure: report network error, exit. Local install unaffected.
          ▼
   ┌─────────────┐  scripts/version-compare.sh INSTALLED LATEST → bump category:
   │  COMPARING  │    "equal"      → exit 0 "up to date"
   │             │    "patch"      → continue (no schema work expected)
   │             │    "minor"      → continue (additive schema OK)
   │             │    "major"      → continue (require explicit user OK)
   │             │    "downgrade"  → reject unless --to was passed
   └──────┬──────┘
          ▼
   ┌─────────────┐  scripts/compute-migration-chain.sh (lives in skills/wiki-migration/scripts/)
   │  PLANNING   │  Output: per-page-type ordered chain of migration IDs.
   │             │  Classify each as scripted / LLM-driven / hybrid (from README.md mode declaration).
   │             │  Estimate: N pages × M migrations. Print plan.
   │             │  Enforce semver policy:
   │             │    PATCH + any migration → ABORT (ADR-019 violation)
   │             │    MINOR + non-additive migration → ABORT (ADR-019 violation)
   │             │    MAJOR + migrations → require user OK before continuing
   └──────┬──────┘
          ▼
   ┌─────────────┐  scripts/snapshot.sh
   │ SNAPSHOTTING│  Copy wiki to ${CLAUDE_PLUGIN_DATA}/wiki-snapshots/v<from>-pre-update-<ISO8601>/
   │             │  Use hard-links where filesystem permits (cheap).
   │             │  Prune oldest snapshots beyond CLAUDE_PLUGIN_OPTION_SNAPSHOTRETAIN (default 3).
   │             │  Log snapshot path to wiki/log.md.
   └──────┬──────┘
          ▼
   ┌─────────────┐  For each (migration_step, page) in plan:
   │  MIGRATING  │    1. Read page; parse frontmatter
   │  (loop)     │    2. Set SF_SNAPSHOT_DIR + SF_WIKI_ROOT env vars
   │             │    3. Dispatch via scripts/apply-migration.sh:
   │             │       - "scripted" → run migrate.sh
   │             │       - "LLM-driven" → invoke Claude with migrate.md
   │             │       - "hybrid" → migrate.sh first, then migrate.md
   │             │    4. Capture diff (new vs snapshot)
   │             │    5. Queue diff for review
   └──────┬──────┘  On crash mid-page: enter ROLLBACK_PAGE with reason. Other pages continue.
          ▼
   ┌─────────────┐  For each migrated page:
   │  VERIFYING  │    Load migration's verify.json
   │  (per page) │    Run scripts/verify-page.sh per assertion
   │             │    All non-optional assertions must PASS
   └──────┬──────┘  Any FAIL → ROLLBACK_PAGE for that page (restore from snapshot, mark "stuck at old schema")
          │         All PASS → continue to DIFF_REVIEW
          ▼
   ┌─────────────┐  For each page that PASSED verify:
   │ DIFF_REVIEW │    Show colorized diff (mirrors /revise-claude-md UX per ADR-009 amendment)
   │             │    Options: [a]pprove [s]kip [e]dit [r]evert
   │             │    --auto mode auto-approves MINOR additive-only migrations (NEVER MAJOR)
   └──────┬──────┘  Skipped → stays at old schema; /sf:doctor will keep flagging
          │         Reverted → restore from snapshot
          │         Approved → continue
          ▼
   ┌─────────────┐  Write approved pages to disk.
   │  APPLYING   │  Update frontmatter: schema_version (new), framework_version (new).
   │             │  If any commands/skills/hooks changed: emit "/reload-plugins required" reminder.
   └──────┬──────┘
          ▼
   ┌─────────────┐  Append migration entry to wiki/log.md:
   │ COMMITTING  │    "## [<ISO>] update | <handle> | framework v<from> → v<to> | migrations: <list>"
   │             │  If wiki has a git remote AND user previously ran /sf:backup: commit + push (best-effort, never blocks).
   └──────┬──────┘
          ▼
   ┌─────────────┐  Invoke /sf:doctor --post-update (no marketplace fetch).
   │  VERIFYING_ │  Print sf-doctor's output.
   │  FINAL      │  If all green: SUCCESS.
   │             │  If any new ❌ / ⚠️ appeared: do NOT auto-rollback.
   └──────┬──────┘  Per lead's pushback: explicit message:
          │           "Migration applied but post-update doctor shows N issues.
          │            Inspect at: <paths>.
          │            Run /sf:update --restore-snapshot if you want to revert."
          ▼
       ┌──────┐
       │ DONE │
       └──────┘
```

## Failure semantics

| Path | What happens | User-facing message |
|---|---|---|
| `ROLLBACK_PAGE` | Single page reverted from snapshot. Page stays at old schema. Other migrations continue. | "⚠️ <page>: migration failed (<reason>). Reverted to schema v<old>. Other pages continued." |
| `ROLLBACK` (full) | Entire wiki restored from snapshot. Update aborted. Snapshot retained for inspection. Exit non-zero. | "❌ Update aborted: <reason>. Wiki restored from snapshot. Snapshot preserved at <path> for inspection." |
| `ABORT_NO_ROLLBACK` | User pressed [r] at DIFF_REVIEW. Pages reverted in place (no wiki-wide restore). Snapshot still retained. | "Reverted at your request. Wiki unchanged. Snapshot at <path> retained anyway." |
| Post-update doctor issues | Migration applied; new warnings/errors surfaced. **No auto-rollback** (per lead). User decides. | "Migration applied but post-update doctor shows N issue(s). Inspect at: <paths>. Run /sf:update --restore-snapshot if you want to revert." |

## Snapshot semantics (per ADR-027, location overridden per lead approval to ${CLAUDE_PLUGIN_DATA})

- **Location:** `${CLAUDE_PLUGIN_DATA}/wiki-snapshots/v<from>-pre-update-<ISO8601>/`
  - Survives plugin updates (`CLAUDE_PLUGIN_DATA` is CC-blessed persistent storage)
  - Reasoning: `~/.startup-framework/wiki-snapshots/` (ADR-027 original suggestion) was written without knowledge of `CLAUDE_PLUGIN_DATA`; the new location is correct. See ADR-027 amendment.
- **Retention:** `CLAUDE_PLUGIN_OPTION_SNAPSHOTRETAIN` (default 3, range 1–20).
- **Form:** entire wiki copy. Hard-linked where supported. Small disk footprint.
- **Pruning:** before each new snapshot. Logged to wiki/log.md.
- **Manual restore recipe** (printed by `/sf:update --restore-snapshot`):
  ```bash
  SNAP=${CLAUDE_PLUGIN_DATA}/wiki-snapshots/<picked-one>
  rm -rf "$SF_WIKI_ROOT"
  cp -a "$SNAP" "$SF_WIKI_ROOT"
  /sf:doctor
  ```

## Idempotency

- `scripts/snapshot.sh` checks if a snapshot for the current second already exists; bumps suffix `-2`, `-3` if so.
- `scripts/apply-migration.sh` checks the page's current `schema_version` before invoking `migrate.sh`; skips if already at target.
- `scripts/verify-page.sh` is a pure function of page content + verify.json.
- Running `/sf:update` twice in a row is a no-op the second time (PLANNING reports "no migrations needed; already at v<latest>", exits).

## Semver semantics (we own these; CC doesn't parse semver)

`scripts/version-compare.sh` implements strict semver including pre-release suffix sort order:

```
1.2.5 < 1.3.0-rc.1 < 1.3.0-rc.2 < 1.3.0-rc.10 < 1.3.0 < 1.3.1 < 2.0.0-rc.1 < 2.0.0
```

Behavior with `--rc` flag:
- If user is on stable and runs `/sf:update --rc`: prompt to add `sf-marketplace-rc` marketplace (if not yet added), then install from RC. CC treats it as the same plugin name; under the hood, this swaps which marketplace the plugin is pinned to.
- If user is on RC and runs `/sf:update` (no flag): if latest stable >= installed RC, prompt to switch back to stable; otherwise stay on RC and update to latest RC.

## Contracts with peers

### With sf-distribution (self)
- `scripts/snapshot.sh`, `scripts/restore.sh`, `scripts/prune-snapshots.sh`, `scripts/version-compare.sh` are part of this skill.
- `scripts/compute-migration-chain.sh`, `scripts/apply-migration.sh`, `scripts/verify-page.sh` live in `skills/wiki-migration/scripts/` (task #33).
- `/sf:update`'s VERIFYING_FINAL state invokes `/sf:doctor --post-update`.

### With sf-onboarding (`onboarding-2`)
- After `/sf:install --restore`, the friend may need to immediately `/sf:update` if their wiki is at older schemas. Handled naturally by the state machine (PLANNING computes the chain).

### With sf-lifecycle (`lifecycle-2`)
- Wake-up hook must be **safe to re-register across `/reload-plugins`** — `/sf:update` calls `/reload-plugins` programmatically when commands/skills/hooks change.

## What this skill does NOT do

- Update sibling plugins (Superpowers, claude-mem, etc.). Use `/plugin update` for those (CC built-in).
- Touch claude-mem's SQLite or Context Mode's SQLite. Plugin-internal state is the plugin's responsibility (per ADR-026).
- Run on session start. Opt-in invocation only (per ADR-019, explicit rejection of auto-update).
- Silent MAJOR migrations. ALWAYS prompts for MAJOR bumps even with `--auto`.

## Eval (lives in `eval.json`)

Binary assertions:
- Equal version → exits without snapshotting
- PATCH + zero migrations → applies and exits with VERIFYING_FINAL green
- MINOR + additive migration → applies with auto-approval when `--auto` set
- MAJOR + breaking migration → prompts even with `--auto`, requires explicit OK
- Migration crash → ROLLBACK_PAGE for the crashing page; other pages continue
- verify.json assertion FAIL → ROLLBACK_PAGE
- User presses [r] at DIFF_REVIEW → page reverted in place; snapshot retained
- Post-update doctor has new issues → migration NOT auto-rolled-back; explicit message printed
- `--restore-snapshot` → interactive picker; restores cleanly
- `--dry-run` → no writes to wiki, snapshot dir, or marketplace
