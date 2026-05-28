# Releasing the Startup Framework

Maintainer-facing. Skip if you're a friend just using the framework.

Per ADR-019. Cadence: **monthly stable**. Out-of-cycle PATCH releases for security / broken-hook fixes only.

---

## Repos involved (the four-repo distinction per ADR-019)

| Repo | Purpose | Who has access |
|---|---|---|
| `sf-marketplace` (stable) | Distribution + version bumps for the framework | Maintainers write; friends read |
| `sf-marketplace-rc` (release candidates) | Pre-release dogfood channel | Maintainers write; subscribed friends read |
| `activity-feed` (separate repo per ADR-018) | Cross-friend session reports | All friends write |
| Framework dev wiki (this repo) | Design history, ADRs, research | Maintainers only |

The maintainer (Hazar initially) writes to `sf-marketplace`. Friends `gh` clone via the marketplace `/plugin marketplace add` flow.

---

## Pre-release checklist

Run through this before bumping the version:

- [ ] All ADRs touching this release's changes are filed in the dev wiki.
- [ ] If schema changed for any page-type: the corresponding `skills/wiki-migration/migrations/<page-type>-<from>-to-<to>/` directory exists with `README.md` + `migrate.sh` and/or `migrate.md` + `verify.json`.
- [ ] If schema changed: `skills/wiki-migration/schemas.json` was updated. The page-type's `current` was bumped, the migration basename was appended to `migrations`. Where appropriate, `supported_from` was advanced to reflect the N+3 deprecation window (per ADR-027).
- [ ] Version bump classified correctly:
  - **PATCH** (e.g. `1.2.3 → 1.2.4`): bug fixes only. NO schema changes, NO hook changes, NO new commands.
  - **MINOR** (e.g. `1.2.x → 1.3.0`): additive changes only. New optional fields with defaults; new commands; new skills; new page-types. NO renames, NO removals.
  - **MAJOR** (e.g. `1.x.x → 2.0.0`): anything else. Goes through the RC pipeline (below).
- [ ] CI green: `claude plugin validate ./plugins/startup-framework --strict`
- [ ] Migrations CI green: synthetic-wiki fixtures pass every new migration's `verify.json`
- [ ] `CHANGELOG.md` entry written (this drives `/sf:doctor`'s update-notification text)
- [ ] You dogfooded the migration: run `/sf:update` against your own wiki from the previous version. Approve the diffs. Confirm `/sf:doctor` is green afterward.

---

## Stable release process

### Step 1 — bump versions

On `main` of `sf-marketplace`:

```bash
# 1. Bump plugin version (THE source of truth — CC docs warn against duplicating in marketplace.json)
$EDITOR plugins/startup-framework/.claude-plugin/plugin.json
# → set "version" to the new value

# 2. Bump marketplace manifest version (independently bumped; tracks marketplace-schema changes, not plugin changes)
#    For a routine plugin release this stays unchanged. Only bump if the shape of marketplace.json itself changed.
$EDITOR .claude-plugin/marketplace.json
# → set "version" only if the marketplace's own schema/shape changed
```

### Step 2 — write the CHANGELOG entry

```markdown
## [1.3.0] — 2026-08-15

### Added
- new optional field `phase` in identity.md frontmatter (default: ideation)
- new command `/sf:audit-stack` for friends who want a deeper plugin-version report

### Schema
- `identity.md` schema 1 → 2: scripted migration adds `phase`, renames `tech-preferences` → `tech_preferences`

### Fixed
- /sf:doctor's plugin-version check no longer crashes when claude-mem worker is not listening

### Deprecated
- (none)

### Removed
- (none)

### Security
- (none)
```

Use Keep-a-Changelog conventions. The `### Schema` section is custom (specific to this framework) and is what `/sf:doctor` summarises in update notifications.

### Step 3 — commit, tag, push

```bash
git add -A
git commit -m "release: v1.3.0"
git tag v1.3.0
git push origin main --tags
```

### Step 4 — CI does its thing

The `release.yml` GitHub Action runs on tag push:

1. Validates the plugin manifest (`claude plugin validate --strict`)
2. Runs the migrations CI suite against synthetic fixtures
3. Asserts `CHANGELOG.md` has an entry for the tagged version
4. Asserts `plugin.json#version` equals the git tag (sans the `v` prefix)
5. Creates a GitHub Release with the CHANGELOG excerpt as the body

If any step fails: fix locally, bump to the next PATCH (`v1.3.1`), retry. **Never delete + re-push a tag** — it confuses friends whose `gh` clients cached the old SHA.

### Step 5 — announce in the Activity Feed

In your own `<handle>.log.md` in the activity-feed repo:

```markdown
## [2026-08-15 09:30] release | hazar | framework v1.3.0 shipped — see CHANGELOG
```

Friends' next `/sf:wake-up` surfaces this; their `/sf:doctor` confirms an update is available.

### Step 6 — friends pick it up on their own time

`/sf:doctor` shows `⚠️ Framework update available: v1.3.0`. They run `/sf:update` when convenient. Snapshot, migrate, diff-review, apply. No nagging beyond the doctor message — per ADR-019, opt-in only.

---

## RC (release-candidate) release process

For MAJOR releases or anything risky enough to want a dogfood week first.

### Why two repos, not two branches

CC's marketplace name must be unique per `marketplace.json#name`. Two branches of one repo would collide on that uniqueness constraint. So we use two physical repos with two distinct marketplace names. Both repos are private, both have the same set of friend collaborators (read-only).

### Step 1 — develop on `sf-marketplace-rc`

The `sf-marketplace-rc` repo mirrors `sf-marketplace`'s structure but its `marketplace.json#name` is `sf-marketplace-rc`.

Work on `main` of `sf-marketplace-rc`. Set the plugin version to a pre-release suffix:

```json
{
  "name": "startup-framework",
  "version": "1.3.0-rc.1",
  ...
}
```

> **Semver note:** CC does NOT parse semver. It treats `version` as an opaque string and checks "did it change?" — that's all. We own the semver semantics ourselves. Our `version-compare.sh` script implements strict semver comparison including pre-release suffix sort order: `1.3.0-rc.1 < 1.3.0-rc.2 < 1.3.0-rc.10 < 1.3.0`. Document any new sort-order edge cases in the script header.

### Step 2 — tag + push

```bash
git tag v1.3.0-rc.1
git push origin main --tags
```

### Step 3 — dogfood for ~1 week

Maintainer runs `/sf:update --rc` on their own wiki. Real use, real sessions. Watch for:

- Migration produces unexpected diffs
- `/sf:doctor` flags new warnings post-update
- Any peer plugin (Superpowers, claude-mem, Context Mode, context7, claude-md-management) reports incompatibility

If issues found: fix on `sf-marketplace-rc`, bump `-rc.N`, repeat. Don't promote until clean.

### Step 4 — friends can opt in to RC

Friends who want early access:

```
/plugin marketplace add <org>/sf-marketplace-rc
/sf:update --rc
```

This sets their `userConfig.rcChannel = true`. They get RC versions on `/sf:update`. `/sf:doctor` reports both stable and RC latest.

They cannot have BOTH stable and RC installed at the same time — CC treats them as the same plugin name. The `--rc` flag uninstalls from stable + reinstalls from RC under the covers.

### Step 5 — promoting RC to stable

After the dogfood week passes cleanly:

```bash
# In sf-marketplace-rc:
git tag v1.3.0-rc.final   # optional, marks the candidate that promotes

# In sf-marketplace (stable):
# 1. Copy the plugin tree from rc/plugins/startup-framework/ to stable/plugins/startup-framework/
#    (mirroring the rc's state)
# 2. Edit plugin.json: drop the "-rc.N" suffix
#    "version": "1.3.0-rc.5"  →  "version": "1.3.0"
# 3. Verify CHANGELOG.md has the stable v1.3.0 entry (you wrote this when you started the RC cycle)
git add -A
git commit -m "release: v1.3.0 (promoted from rc.5)"
git tag v1.3.0
git push origin main --tags
```

**Activity Feed announcement** in your `<handle>.log.md`:

```markdown
## [2026-08-22 10:00] release | hazar | framework v1.3.0 stable — see CHANGELOG; RC dogfood from 2026-08-15 to 2026-08-22 found no blockers
```

Friends on stable pick up the new stable on their next `/sf:update`. Friends on RC are already running it (just under the `1.3.0-rc.N` version string); they can `/sf:update` to switch back to stable channel if they no longer want RC.

### Step 6 — optional: GitHub Action draft-PR-on-tag

The `sf-marketplace-rc` repo can host a GitHub Action that fires when a `-rc.final` tag is pushed. The action opens a **draft PR** against `sf-marketplace` containing the plugin tree diff. This is convenience tooling, NOT auto-merge — the human gate is preserved. Maintainer reviews + merges manually.

This Action is in scope for v1.0 but optional; ship a stub if time is short.

---

## Recovery from a bad release

Things that can go wrong:

### A migration silently corrupted some friends' wikis

1. Triage via friend reports + `/sf:doctor` output they paste.
2. Identify the broken migration. Read `verify.json` — was an assertion too lax?
3. Ship a PATCH (`v1.3.1`) that:
   - Adds a corrective migration `<page-type>-3-to-4` (forward fix; never reverse)
   - Includes a fixture that reproduces the failure mode
4. Post Activity Feed announcement: `## [<ts>] release | hazar | framework v1.3.1 PATCH — fixes identity.md migration bug; run /sf:update immediately`
5. Friends with affected wikis can roll back via snapshot (see `RECOVERY.md` Scenario 3) and re-`/sf:update` once the patch is out.

### A friend reports breakage we can't reproduce

1. Ask them to paste:
   - `/sf:doctor` output
   - The `${CLAUDE_PLUGIN_DATA}/wiki-snapshots/` directory listing (`ls -la`)
   - The first 50 lines of the file claimed to be broken
2. If it's a one-off corruption, walk them through `RECOVERY.md` Scenario 3.
3. If it's a pattern emerging across friends, file an ADR amendment under ADR-019's sunset-review trigger list (release process needs revision).

### CI passed but a manual test would have caught the bug

This is a fixtures gap. Expand `tests/fixtures/<page-type>-v<N>/` with the missing edge case + add a test in `verify-migrations.yml` that exercises it. Commit before the next release.

### A tag was pushed with the wrong contents

DO NOT delete + re-push the tag. Friends' `gh` clients may have already cached the old SHA, leading to inconsistent installs across the group. Instead:

1. Bump to the next PATCH and re-release (e.g. tag was `v1.3.0` with bad contents → release `v1.3.1` with correct contents + a CHANGELOG note "v1.3.0 was a faulty release; do not install").
2. Post a strong Activity Feed warning + ping friends out-of-band (WhatsApp, etc.) so they skip the bad tag.

---

## Onboarding a co-maintainer

Per ADR-019 § sunset-review-triggers: "Hazar-bottleneck on releases" is a known risk. When the second maintainer arrives:

1. Add them as a write collaborator on `sf-marketplace` AND `sf-marketplace-rc`.
2. Add their GitHub username to the dev wiki's `wiki/maintainers.md`.
3. Walk them through this document.
4. Both maintainers must be admins on the GitHub repos (bus factor).
5. Document the on-call rotation if one emerges.

The release process documented here is intentionally manual + auditable. Don't add automation that bypasses the human checklist without a strong reason.

---

## What to NOT do

- Don't push directly to friends' wikis. The framework's per-friend-wiki principle (ADR-017) is load-bearing; the maintainer never touches a friend's local wiki.
- Don't auto-update. The opt-in pattern (per ADR-019) is the safety net.
- Don't skip the CHANGELOG. `/sf:doctor` consumes it. An empty CHANGELOG means friends don't know what changed.
- Don't combine PATCH + MINOR changes in one tag. Pick one. The semver classification is the contract for what schemas can change.
- Don't ship a MAJOR without RC. The dogfood week is the safety net.
- Don't skip ADR amendments for sunset-review triggers. The wiki is the framework's memory; let it grow.
