---
name: update
description: |
  Use when the user runs /ren:update to upgrade the framework. Drives the
  migration state machine — fetches latest version, classifies the bump,
  snapshots the wiki, runs migrations, verifies via verify.json, shows diffs
  for approval, applies, and re-verifies. Snapshot/rollback is built in.
  Never silent on MAJOR bumps.
version: 0.8.2
license: MIT
type: skill
execution_tier: deterministic
schema_version: 1
framework_version: "0.8.2"

contract:
  required_outputs:
    - "A printed migration plan (per-page-type ordered migration chain) before any write"
    - "A pre-migration wiki snapshot under ~/.claude/plugins/data/renos/wiki-snapshots/v<from>-pre-update-<ISO8601>/ (root overridable via REN_SNAPSHOT_ROOT)"
    - "Migrated wiki pages written to disk only after per-page verify.json PASS + diff approval, with frontmatter schema_version/framework_version bumped"
    - "An appended migration entry in wiki/log.md (snapshot path + update record)"
    - "On --dry-run: the plan only, with zero writes to wiki, snapshot dir, or marketplace"
    - "a 'What changed in your RenOS' digest after apply (changelog_digest; empty digest degrades to a CHANGELOG.md pointer, never a failure)"
    - "companion delta offered after apply (pending_offers): only undecided-and-absent entries, choices recorded durably"
  budgets:
    turns: 30
    files_written: 200
    duration_seconds: 600
  permissions:
    read:
      - "skills/wiki-migration/**"
      - "migrations/**"
      - "~/.renos/wiki/**"
      - "~/.claude/plugins/data/renos/wiki-snapshots/**"
      - "$CLAUDE_PLUGIN_ROOT/CHANGELOG.md"
    write:
      - "~/.renos/wiki/**"
      - "~/.claude/plugins/data/renos/wiki-snapshots/**"
    execute:
      - "uv tool install *"
      - "scripts/snapshot.sh"
      - "scripts/restore.sh"
      - "scripts/prune-snapshots.sh"
      - "scripts/version-compare.sh"
  completion_conditions:
    - "Equal version → exits without snapshotting"
    - "A snapshot exists before any page is migrated"
    - "Failed/crashed pages were reverted from snapshot while other pages continued; snapshot retained"
  output_paths:
    - "~/.claude/plugins/data/renos/wiki-snapshots/"

tags: [update, migration, snapshot, rollback]
related_skills: [wiki-migration, backup, doctor]
references_required: []
references_on_demand: []
---

# update

Carried near-verbatim from donor `skills/update/` (Task 7.3) — the migration state machine's snapshot/restore/version-compare substrate. Renamed identifiers only: `SF_WIKI_ROOT` → `REN_WIKI_ROOT`, `SF_SNAPSHOT_MODE` → `REN_SNAPSHOT_MODE`, `~/.startup-framework/` → `~/.renos/`.

## Scripts (carried, unchanged behavior)

- `scripts/snapshot.sh <from-version>` — copies the wiki to `~/.claude/plugins/data/renos/wiki-snapshots/v\<from\>-pre-update-\<ISO8601\>/` (snapshot root overridable via `REN_SNAPSHOT_ROOT`; never derived from `CLAUDE_PLUGIN_DATA` — issue #34), prunes beyond `CLAUDE_PLUGIN_OPTION_SNAPSHOTRETAIN` (default 3), logs the snapshot to `wiki/log.md`.
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

## 0.5.1 update notes

- **trust-backfill-1 (Task 10a):** a friend upgrading from before 0.5.1 has
  pre-0.5.1 wiki pages with no `ren_trust` frontmatter (the trust taxonomy
  0.5.1 Task 6 started stamping at the single write door). Run
  `migrations/trust-backfill-1/migrate.py` once as a post-update step after
  the version bump lands, gated by `skills.update.lib.should_run_trust_backfill(
  <old-version>, <new-version>)` — `True` when the update crosses the 0.5.1
  boundary. Like `queue-governance-2-to-3`, this is NOT part of the
  `skills/wiki-migration` page-type chain (it walks the whole wiki tree, not
  a single page type keyed by `schema_version`) — see
  `skills/wiki-migration/schemas.json`'s `global_migrations` note and that
  migration's README.md for the shape-decision rationale. `--check` previews
  what would be stamped with zero writes. Idempotent — safe to (re-)run even
  if a friend already updated once without it.

## 0.6.2 update notes

- **project-knowledge-1 (issue #20):** a friend upgrading from before 0.6.2
  may have flat `.md` pages directly under `projects/<slug>/` (pre-0.6.2
  ingest had no sanctioned durable subtree). Run
  `migrations/project-knowledge-1/migrate.py` once as a post-update step
  after the version bump lands, gated by
  `skills.update.lib.should_run_project_knowledge_1(<old-version>,
  <new-version>)` — `True` when the update crosses the 0.6.2 boundary.
  Standalone global migration (walks whole `projects/<slug>/` directories,
  not a schema_version-keyed page type) — see
  `skills/wiki-migration/schemas.json`'s `global_migrations` note and that
  migration's README.md. Dry-run is the DEFAULT (`--apply` writes); show the
  friend the dry-run plan before applying. Idempotent — safe to (re-)run.
  It also reports any `projects/<slug>/` missing a `schema.md`; relocating
  pages is the script's job, but organizing them into a taxonomy (nested
  `knowledge/` subtrees, hubs, `schema.md`) is model-work — offer the friend
  a follow-up session per project (or a re-run of `/ren:ingest-project`,
  which now produces the hierarchical shape natively).

## 0.6.3 update notes

- **foreign-remint-1 (issue #22):** a friend upgrading from before 0.6.3 may
  have ingest-drafted knowledge pages mis-stamped `ren_trust: "foreign"`
  (pre-#22 `trust_class` minted "foreign" for every `producer="ingest"`
  write, which held the ingested project's L2 map out of wake-up
  unconditionally). Run `migrations/foreign-remint-1/migrate.py` once as a
  post-update step after the version bump lands, gated by
  `skills.update.lib.should_run_foreign_remint_1(<old-version>,
  <new-version>)` — `True` when the update crosses the 0.6.3 boundary.
  Standalone global migration (walks the whole wiki tree, restamps only
  foreign pages with a known non-human `ren_writer`; quarantine banners are
  untouched) — see `skills/wiki-migration/schemas.json`'s
  `global_migrations` note and that migration's README.md. `--check`
  previews what would be reminted with zero writes. Idempotent — safe to
  (re-)run even if a friend already updated once without it.

## 0.7.0 update notes

- **l2-map-1-to-2 (issue #53):** a friend upgrading from before 0.7.0 has L2
  pointer-maps still in schema 1 — arrow-form wiki pointers
  (`- [Topic] → path (write_id)`) instead of Obsidian-native markdown links
  (`- [Topic](path) (write_id)`). Unlike the standalone global migrations
  above, this one IS part of `skills/wiki-migration`'s ordinary page-type
  chain (`l2-map` is a registered page type in `skills/wiki-migration/schemas.json`,
  currently at schema 2), so it's driven the same way `/ren:doctor`'s
  `check_schema_versions` discovers pending work, not a one-off script
  invoked by hand. Walk it as follows, under the update flow's existing
  pre-migration snapshot (`REN_SNAPSHOT_DIR` already pointed at that run's
  `wiki-snapshots/v<from>-pre-update-<ISO8601>/`):
  1. Enumerate wiki pages via `wiki_root.rglob("*.md")`, skipping
     `projects/<slug>/raw/` (write-once source material — never a migration
     target; `lib.ren_paths.in_project_raw` is the existing predicate,
     see `skills/doctor/lib/check_schema_versions` for the same walk).
  2. Read each page's frontmatter `type`. The master `wiki/index.md` is
     `type: l2-map` too — it is NOT special-cased out of this walk, per-
     project maps (`projects/<slug>/map.md`) and the master index are
     migrated the same way.
  3. For pages whose `type` is `l2-map`, read `schema_version`; an absent
     value means the page predates schema-stamping (issue #20) — treat it
     as `1`, not as "skip me".
  4. Compute `migration_chain("l2-map", <version>)` — via
     `importlib.import_module("skills.wiki-migration.lib")`, same as
     `/ren:doctor`'s `check_schema_versions` — for that page. A non-empty
     chain today is always exactly `["l2-map-1-to-2"]`.
  5. For each pending page, run `run_migration(Path("migrations/l2-map-1-to-2"),
     <page_path>, wiki_root, snapshot_dir)` (same `skills.wiki-migration.lib`
     import) — same primitive `/ren:doctor` verifies against, same
     `SF_*`/`REN_*` env-mapping shim. Inspect the returned
     `MigrationRunResult`: `skipped=True` (stdout carried `SKIP`) means
     transform.py itself declined (wrong type, no frontmatter, or already
     at schema 2 — see `migrations/l2-map-1-to-2/README.md`); a non-zero
     `returncode` with `skipped=False` is a genuine transform failure
     (page left untouched, rolled back from the snapshot like any other
     failed page).
  6. Verify each migrated page with `verify_page(
     Path("migrations/l2-map-1-to-2/verify.json"), <page_path>)` (same
     import) before counting it as applied.
  7. Show the friend the per-page diff summary, per this skill's usual
     diff-approval contract, before the migrated content is treated as
     final.
  Idempotent — re-running is always safe: `migrate.sh` (via `transform.py`)
  `SKIP`s any page already at `schema_version: 2`, scoped to the
  frontmatter block only (a body line that happens to read
  `schema_version: 2` cannot false-SKIP a stale page). See
  `migrations/l2-map-1-to-2/README.md` for the full transform contract.

- **Global migration: folder-note-hubs-1.** Gate:
  `should_run_folder_note_hubs_1()` from `skills.update.lib`. If true — show
  the friend the pending rename list (the gate's paths), get approval (this
  is a MAJOR-classified structural change), then run
  `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/<version>" uv run python
  migrations/folder-note-hubs-1/migrate.py` followed by
  `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/<version>" uv run python
  migrations/folder-note-hubs-1/verify.py` — these also run from the
  versioned plugin cache dir, so redirect uv's project environment the same
  way (#40; `ren_paths.envs_dir()`) rather than letting a `.venv` land
  inside that immutable cache dir. On verify success, call
  `skills.install.lib.write_default_graph_config()` (the new Obsidian tier
  view written during the migration). On verify failure: stop, show the FAIL
  lines, offer whole-wiki restore via `skills/update/scripts/restore.sh --whole <snapshot>`
  (the snapshot taken at the start of this update). Never proceed to the closing
  summary with a failed verify.

## 0.8.0 update notes

- **distiller-watermark seed (spec §3.5):** a friend upgrading from before
  0.8.0 has no distiller watermark yet. Initialize the watermark as a
  post-update step after the version bump lands, gated by
  `skills.update.lib.should_run_distiller_watermark_seed(<old-version>,
  <new-version>)` — `True` when the update crosses the 0.8.0 boundary.
  Call `skills.distill.lib.write_watermark("2026-08-03T00:00:00Z")` ONLY
  if `skills.distill.lib.watermark_path()` doesn't exist yet (idempotent —
  safe to (re-)run even if a friend already updated once without it).
  See `docs/superpowers/specs/2026-08-18-knowledge-flows-train-design.md`'s
  §3.5 for the backlog-rescue acceptance run.

## 0.8.1 update notes

- **frontmatter-type-1 (issues #74, #77):** a friend upgrading from before
  0.8.1 has wiki pages created before the write door derived a frontmatter
  `type:` from the page path, so those pages carry none — and every one of
  them keeps tripping wiki-health's `missing-frontmatter-type` rule, filing a
  fresh suggestion per page per sweep. Run
  `migrations/frontmatter-type-1/migrate.py` once as a post-update step after
  the version bump lands, gated by
  `skills.update.lib.should_run_frontmatter_type_1(<old-version>,
  <new-version>)` — `True` when the update crosses the 0.8.1 boundary.
  Standalone global migration (walks the whole wiki tree calling
  `lib.memory.page_types.ensure_type`, not a `schema_version`-keyed page
  type) — see `skills/wiki-migration/schemas.json`'s `global_migrations` note
  and that migration's README.md. `--check` previews what would be stamped
  with zero writes; show the friend that preview before applying. Idempotent
  — safe to (re-)run even if a friend already updated once without it.
  It never overrides an existing `type:` (invariant I1) and leaves any path
  the derivation table doesn't recognize untouched (I2).

  **Run it before the friend's next `/ren:distill` or `/ren:wrap`.** Until a
  page is typed, a re-propose of unchanged content against it no longer
  normalizes equal — the proposal carries `type:` and the page on disk does
  not — so each untyped page costs one extra self-healing write and a
  distiller `WRITE_CAP` slot. Running the migration first avoids that burst
  entirely.

## Overlap note: snapshot substrate vs. Task 1.2's per-write snapshots

`lib/memory/snapshot.py` (Task 1.2, G9) is a DIFFERENT snapshot mechanism: per-write-id, page-granularity snapshots for the write-safety substrate (revert a single memory write in one step). `scripts/snapshot.sh` here is whole-wiki, version-bump-granularity, for migration rollback. They serve genuinely different purposes at different granularities — this skill's carried snapshot logic is NOT rewritten to unify with Task 1.2's substrate; that unification (if it's ever worth doing) is a 0.3-scoped ADR decision, not something to improvise here. Noted per the task brief's explicit instruction not to rewrite working carried code.

## Closing steps (after re-verify)

- **Re-render project CLAUDE.md blocks** — call
  `skills.update.lib.rerender_all_project_claude_md()` after migrations
  complete. The queue's post-apply hook and `revert`'s post-revert hook
  (`lib.adapter.claude_md.rerender_for_page`) each re-render only the ONE
  project touched by a single instructions.md write; an update can change
  the block's FORMAT (adapter changes, doctrine index refresh) for every
  project at once without touching instructions.md at all — this closes
  that spec §3(b) gap (#64). Best-effort per slug — the returned
  `{slug: "ok" | "error: <msg>"}` dict is informational, never a gate.

- **Re-render the global CLAUDE.md block** — call
  `lib.adapter.claude_md.write_global_claude_md()`. The global block's
  doctrine index holds absolute paths pinned to the running plugin version
  (`.../cache/ren-os/ren/<version>/doctrine/*.md`), so a version bump leaves
  every one of them naming the PREVIOUS version — live only until that cache
  dir is GC'd, then dead links in a file injected into every session. The
  project-tier call above cannot cover this: it iterates projects with an
  `instructions.md`, and the global block belongs to no project. Same shape as
  #64 one tier up. Best-effort like its project-tier sibling — report the
  returned status (`added`/`updated`/`unchanged`/`conflict`), never gate the
  update on it. A `conflict` means torn markers in the friend's own
  `CLAUDE.md`: say so and leave the file untouched.

- **Report what changed** — build the "what changed in your RenOS" digest:
  `skills.update.lib.changelog_digest(<old-version>, <new-version>,
  <plugin-root>/CHANGELOG.md)` (plugin root = `$CLAUDE_PLUGIN_ROOT`, falling
  back to the framework root). Print it verbatim under a "What changed in
  your RenOS" heading. If it returns "" (unparseable/missing), say the
  update landed and point at CHANGELOG.md instead — the digest is a
  courtesy, never a gate.

- **Offer new companions** — call `lib.companions.pending_offers()`. If
  non-empty, say: "This update recommends companions you haven't decided
  on:" and list each (title — pitch — install hint). Same rules as install
  Stage 6: accepted tools are installed for them and recorded
  (`record_choice(cid, "accepted")`); accepted plugins get the hint + a
  restart note; declines are recorded and never re-asked; no answer records
  nothing. Nothing installs without an explicit yes in chat.

- **Re-warm the fast-path interpreter** — call
  `skills.update.lib.rewarm_interpreter()`. `warm_environment()` runs at
  install and never at update, so the recorded interpreter kept naming the
  cache dir the update just superseded; the wake-up hook then falls through
  to cold `uv` every session, silently, because it fails safe. This also
  deletes the pre-0.8.3 record at `state_dir()/interpreter.json` — that
  location is inside the wiki and therefore inside `/ren:backup`'s push, so
  it carried one machine's absolute paths to every machine restoring the
  wiki. The record now lives in `ren_paths.machine_state_dir()`, which is
  never backed up; that is what retired the `platform.node()` comparison
  guarding it (macOS returns an IP-derived node name on some networks, so
  the guard rejected the machine's own valid record after any network
  change). Best-effort, never a gate — report the returned `status`.

- **GC stale uv envs** — call `skills.update.lib.gc_stale_envs()`. It
  removes `framework_root()/.envs/<v>` dirs whose version is no longer in
  the plugin cache (#40 — the versions this same update just made stale)
  and returns the removed version list; report it if non-empty, silent
  otherwise. Best-effort, never a gate.

## References

- `skills/wiki-migration/` — the migration registry + verify/apply primitive this skill drives
- `migrations/queue-governance-2-to-3/` — the standalone (non-chain) queue-state migration named in the 0.3 update notes above
- `migrations/trust-backfill-1/` — the standalone (non-chain) wiki-wide migration named in the 0.5.1 update notes above
- `migrations/l2-map-1-to-2/` — the ordinary page-type-chain migration named in the 0.7.0 update notes above
- `lib/memory/snapshot.py` (Task 1.2) — the OTHER snapshot mechanism (per-write, not whole-wiki); see overlap note above
- `skills/doctor/` — the post-update health check this skill's flow ends with
