# Releasing the Startup Framework

Maintainer-facing. Skip if you're a friend just using the framework.

Per ADR-019. Cadence: **monthly stable**. Out-of-cycle PATCH releases for security / broken-hook fixes only.

---

## The repos (ADR-019 distinction, orphan-publish model)

| Repo | Purpose | Contents | Who has access |
|---|---|---|---|
| **dev repo** (this one, `~/Dev/startup-framework`) | Design history, ADRs, research, the source of truth | EVERYTHING — full git history, `wiki/`, `raw/`, `REVIEW*.md`, maintainer docs, **release tags** | Maintainers only; **PRIVATE, never pushed to the marketplace** |
| `sf-marketplace` (stable) | Distribution to friends | ONE orphan commit per release — only the shippable allowlist | Maintainers write (via `publish.sh`); friends read |
| `sf-marketplace-rc` (RC channel) | Pre-release dogfood | Same, RC versions | Maintainers write; subscribed friends read |
| `activity-feed` (separate repo, ADR-018) | Cross-friend session reports | Friends' `<handle>.log.md` | All friends write |

**The boundary.** The dev repo holds the product brain (wiki, research, internal reviews). Friends
must never see it. We do **not** `git push` the dev repo to the marketplace — that would leak the
whole history. Instead, `scripts/publish.sh` builds a **fresh single-commit orphan snapshot** of
only the shippable allowlist and force-pushes THAT. Friends get one commit, zero history, zero wiki.

**Tags live only in the dev repo.** The marketplace carries no tags — it's a rolling single orphan
commit. Friends pick up changes with `/plugin marketplace update sf-marketplace`; `/sf:doctor`
reads the published `plugin.json#version` to notify them.

---

## Pre-release checklist

Run through this before bumping the version:

- [ ] All ADRs touching this release's changes are filed in the dev wiki.
- [ ] If schema changed for any page-type: the corresponding `skills/wiki-migration/migrations/<page-type>-<from>-to-<to>/` directory exists with `README.md` + `migrate.sh` and/or `migrate.md` + `verify.json`.
- [ ] If schema changed: `skills/wiki-migration/schemas.json` updated — `current` bumped, migration basename appended to `migrations`, `supported_from` advanced per the N+3 deprecation window (ADR-027).
- [ ] Version bump classified correctly:
  - **PATCH** (`1.2.3 → 1.2.4`): bug fixes only. NO schema changes, NO hook changes, NO new commands.
  - **MINOR** (`1.2.x → 1.3.0`): additive only. New optional fields with defaults; new commands/skills/page-types. NO renames, NO removals.
  - **MAJOR** (`1.x.x → 2.0.0`): anything else. Goes through the RC pipeline (below).
- [ ] `scripts/publish.sh --dry-run` is green (validates the snapshot would be clean).
- [ ] Migrations CI green: synthetic-wiki fixtures pass every new migration's `verify.json`.
- [ ] `CHANGELOG.md` entry written (this drives `/sf:doctor`'s update-notification text).
- [ ] You dogfooded the migration: ran `/sf:update` against your own wiki from the previous version, approved the diffs, confirmed `/sf:doctor` green afterward.

---

## Stable release process

### Step 1 — bump the version (dev repo)

```bash
# plugin.json#version is THE source of truth (CC docs warn against duplicating in marketplace.json)
$EDITOR .claude-plugin/plugin.json
# → set "version" to the new value (e.g. 1.3.0)

# marketplace.json#version is independent — bump ONLY if the marketplace's own shape changed.
$EDITOR .claude-plugin/marketplace.json
```

### Step 2 — write the CHANGELOG entry

```markdown
## [1.3.0] — 2026-08-15

### Added
- new optional field `phase` in identity.md frontmatter (default: ideation)

### Schema
- `identity.md` schema 1 → 2: scripted migration adds `phase`

### Fixed
- /sf:doctor's plugin-version check no longer crashes when claude-mem worker is offline

### Deprecated / Removed / Security
- (none)
```

Keep-a-Changelog conventions. The `### Schema` section is custom — `/sf:doctor` summarises it in update notifications.

### Step 3 — commit + tag in the DEV repo

```bash
git add -A
git commit -m "release: v1.3.0"
git tag v1.3.0
# If the dev repo has a private remote: git push origin main --tags
# (This pushes to the PRIVATE dev remote ONLY — NEVER to sf-marketplace.)
```

### Step 4 — publish the orphan snapshot

```bash
scripts/publish.sh            # --channel stable is the default
```

`publish.sh`:
1. reads the version from `plugin.json`,
2. copies only the shippable allowlist into a temp snapshot,
3. runs the guards (no `PLACEHOLDER-ORG`; assert-absent of all maintainer-only paths; `claude plugin validate --strict`; manifests + `source:"./"`),
4. makes a single orphan commit `Release v1.3.0`,
5. **prints** the exact push commands and the snapshot path — it does NOT push.

Inspect the snapshot, then run the printed commands:

```bash
git -C <snapshot> remote add origin git@github.com:hazarsozer/sf-marketplace.git
git -C <snapshot> push --force origin HEAD:main
```

The force-push replaces the marketplace's single orphan commit with the new release. **Never push
tags to the marketplace.**

### Step 5 — announce in the Activity Feed

In your own `<handle>.log.md` in the activity-feed repo:

```markdown
## [2026-08-15 09:30] release | hazar | framework v1.3.0 shipped — see CHANGELOG
```

### Step 6 — friends pick it up on their own time

`/sf:doctor` shows `⚠️ Framework update available: v1.3.0` (it reads the published `plugin.json#version`).
Friends run `/plugin marketplace update sf-marketplace` then `/sf:update` when convenient — snapshot,
migrate, diff-review, apply. Opt-in only; no nagging beyond the doctor message (ADR-019).

> **Why not GitHub Releases on `sf-marketplace`?** The marketplace carries no tags, so tag-triggered
> GitHub Releases don't apply there. `release.yml` is **dev-repo CI** (it validates on dev-repo tag
> pushes if you've given the dev repo a private remote). Friends get "what changed" from `CHANGELOG.md`
> (which ships) + `/sf:doctor`, not from a GitHub Release page.

---

## RC (release-candidate) process

For MAJOR releases or anything risky enough to want a dogfood week first.

### Why two repos, not two branches

CC requires a unique `marketplace.json#name` per marketplace. Two branches of one repo would collide
on that. So we use two physical repos with distinct names (`sf-marketplace`, `sf-marketplace-rc`),
both private, both with the same read-only friend collaborators.

### Step 1 — set an RC version + publish to the RC channel

```bash
$EDITOR .claude-plugin/plugin.json     # "version": "1.3.0-rc.1"
git commit -am "rc: v1.3.0-rc.1" && git tag v1.3.0-rc.1   # dev repo
scripts/publish.sh --channel rc        # builds + verifies the RC snapshot
# run the printed push → git@github.com:hazarsozer/sf-marketplace-rc.git
```

> **Semver note:** CC does NOT parse semver — it treats `version` as an opaque string and only checks
> "did it change?". We own semver ourselves; `skills/sf-update/scripts/version-compare.sh` implements
> strict comparison incl. pre-release order: `1.3.0-rc.1 < 1.3.0-rc.2 < 1.3.0-rc.10 < 1.3.0`.
> `publish.sh` enforces that `--channel rc` carries an `-rc.N` suffix and `--channel stable` does not.

### Step 2 — dogfood ~1 week

Maintainer runs `/sf:update --rc` on their own wiki. Watch for unexpected migration diffs, new
`/sf:doctor` warnings, or peer-plugin incompatibilities. Fix on the dev repo, bump `-rc.N`, re-publish.

### Step 3 — friends opt in to RC

```text
/plugin marketplace add hazarsozer/sf-marketplace-rc
/sf:update --rc
```

This sets `userConfig.rcChannel = true`. They cannot run BOTH stable and RC (same plugin name); the
`--rc` flow swaps the installed source under the covers.

### Step 4 — promote RC → stable

There is **no PR/rsync promotion** under orphan-publish. Promotion is just a stable publish of the
de-suffixed version:

```bash
$EDITOR .claude-plugin/plugin.json     # "1.3.0-rc.5" → "1.3.0"
git commit -am "release: v1.3.0 (promoted from rc.5)" && git tag v1.3.0   # dev repo
scripts/publish.sh --channel stable    # → sf-marketplace
# run the printed force-push
```

**Activity Feed announcement:**

```markdown
## [2026-08-22 10:00] release | hazar | framework v1.3.0 stable — RC dogfood 08-15→08-22 found no blockers
```

> `.github/workflows/promote-rc-draft.yml.template` is a **deprecated stub** under this model — the
> old rsync-PR promotion no longer applies. See the stub's header; promotion is the `publish.sh` step above.

---

## Recovery from a bad release

### A migration silently corrupted some friends' wikis

1. Triage via friend reports + pasted `/sf:doctor` output.
2. Identify the broken migration; read its `verify.json` — was an assertion too lax?
3. Ship a PATCH (`v1.3.1`) with a corrective migration `<page-type>-3-to-4` (forward fix, never reverse) + a reproducing fixture.
4. Announce: `release | hazar | framework v1.3.1 PATCH — fixes identity.md migration; run /sf:update`.
5. Affected friends roll back via snapshot (`RECOVERY.md` Scenario 3) and re-`/sf:update` once the patch is out.

### A snapshot was published with the wrong contents

Under orphan-publish this is **easy to correct** — there are no tags on the marketplace to confuse `gh`
clients:

1. Fix the issue in the dev repo, bump to the next PATCH (e.g. `v1.3.1`), add a CHANGELOG note ("v1.3.0 was faulty; do not stay on it").
2. Re-run `scripts/publish.sh` → force-push the corrected orphan commit. It cleanly replaces the bad one.
3. Post a strong Activity Feed warning + ping friends out-of-band so they `/plugin marketplace update` + `/sf:update`.

(Dev-repo **tags** still follow the never-delete-and-re-push rule — but the marketplace has none, so the rolling force-push is the normal mechanism, not a hazard.)

### A friend reports breakage we can't reproduce

1. Ask them to paste `/sf:doctor` output, `${CLAUDE_PLUGIN_DATA}/wiki-snapshots/` listing, and the first 50 lines of the file claimed broken.
2. One-off corruption → walk them through `RECOVERY.md` Scenario 3.
3. Pattern across friends → file an ADR amendment under ADR-019's sunset-review triggers.

---

## Onboarding a co-maintainer

Per ADR-019 § sunset-review-triggers ("Hazar-bottleneck on releases"):

1. Add them as a write collaborator on `sf-marketplace` AND `sf-marketplace-rc` (and the private dev remote, if any).
2. Add their GitHub username to `wiki/maintainers.md`.
3. Walk them through this document + `publish.sh`.
4. Both maintainers admin on the GitHub repos (bus factor).

The process is intentionally manual + auditable. Don't add automation that bypasses the human checklist (or `publish.sh`'s guards) without a strong reason.

---

## What to NOT do

- **Don't `git push` the dev repo to `sf-marketplace`.** That leaks the wiki + history. Always publish via `scripts/publish.sh`.
- **Don't push tags to `sf-marketplace`.** Tags live only in the private dev repo.
- **Don't bypass `publish.sh`'s guards.** The assert-absent guard is the ADR-019 boundary; if it fails, fix the leak — don't work around it.
- Don't push directly to friends' wikis — the per-friend-wiki principle (ADR-017) is load-bearing.
- Don't auto-update. Opt-in (ADR-019) is the safety net.
- Don't skip the CHANGELOG — `/sf:doctor` consumes it.
- Don't combine PATCH + MINOR in one release. Pick one; the semver classification is the schema-change contract.
- Don't ship a MAJOR without RC. The dogfood week is the safety net.
