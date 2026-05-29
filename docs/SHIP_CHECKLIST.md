# Ship Checklist — v1.0.0

Maintainer-only. Single-page gate Hazar runs through before tagging + publishing. Every item must be ☑ before the orphan snapshot is pushed to `sf-marketplace`. Skip nothing.

The verification commands assume you're at the **dev repo** root (`~/Dev/startup-framework`).

> **Publishing model (per ADR-019, orphan-publish).** This dev repo is PRIVATE and keeps
> everything — full history, `wiki/`, `raw/`, `REVIEW*.md`, maintainer docs, tags. Friends
> NEVER see it. Releases are published by `scripts/publish.sh`, which builds a **fresh
> single-commit orphan snapshot containing only the shippable allowlist** and force-pushes
> THAT to `sf-marketplace`. Friends get one commit, zero history, zero wiki. See
> `docs/RELEASING.md` for the full flow.

---

## §1 — Code green

### 1.1 — All test suites pass

Run each module's pytest suite **from its own directory** — root-level `pytest` intentionally
collides on duplicate test-module import names, so always run per-module:

```bash
for m in feed hooks/wake-up scripts \
         skills/sf-backup skills/sf-catch-up skills/sf-improve-skill \
         skills/sf-install skills/sf-note skills/sf-recall skills/sf-wrap; do
  ( cd "$m" && python3 -m pytest -q ) || echo "FAIL: $m"
done
```

Then the distribution shell suites + the version-compare self-test:

```bash
bash skills/sf-doctor/scripts/tests/test_check_schemas.sh
bash skills/sf-doctor/scripts/tests/test_check_plugins.sh
bash skills/sf-update/scripts/tests/test_snapshot_inode_safety.sh
bash skills/sf-update/scripts/version-compare.sh --self-test
```

Expected: every command exits 0; final lines report `N passed` or `N/N PASS`.

> **Not pytest modules** (don't run `pytest` on these — it exits 4 "no tests collected"):
> `skills/sf-bootstrap-project` and `skills/sf-interview` are validated by their
> `eval/eval.json` fixtures, and `wiki-skeleton/` is a standalone lint, not a pytest suite.

- ☐ all module pytest suites green
- ☐ all distribution shell suites + version-compare self-test green

### 1.2 — Cross-team review findings closed

Track from `REVIEW.md` + `REVIEW-v1.0-preship.md` at repo root.

```bash
grep -c '^- \[ \]' REVIEW.md  # should be 0 (zero unchecked findings)
```

- ☐ all CRITICAL + HIGH findings from `REVIEW-v1.0-preship.md` closed
- ☐ MEDIUM/LOW sweep complete (or explicitly deferred with a note)

### 1.3 — `claude plugin validate --strict` clean

With the Crucible one-repo layout, a single command validates the marketplace manifest (which
resolves `source: "./"` to the root plugin):

```bash
claude plugin validate ./ --strict
```

Expected: `✔ Validation passed` (no errors, no warnings). For belt-and-suspenders you can also
validate the plugin manifest directly: `claude plugin validate ./.claude-plugin/plugin.json --strict`.

- ☐ validates clean with `--strict`

### 1.4 — Schema-conformance harness: 0 strict blockers

```bash
python3 tests/integration/schema-conformance/conformance.py
```

Expected: `BLOCKERS (strict mode): 0`. Informational fails are non-blocking (research files predating ADR-027).

- ☐ 0 strict blockers

### 1.5 — End-to-end migration dogfood: 17/17 PASS

```bash
bash tests/integration/migration-dogfood.sh
```

Expected: `END-TO-END MIGRATION DOGFOOD: 17/17 PASS`.

- ☐ full pipeline composes correctly

### 1.6 — Installed-runtime acceptance (ADR-030)

The one gate that proves the *installed-plugin* runtime actually works — materializes a fake
`$CLAUDE_PLUGIN_ROOT` (no env vars set, friend's own layout) and asserts wiki-context + feed both
load. This is the test that would have caught C1 + C2 together.

```bash
python3 -m pytest tests/integration/installed_runtime/ -q
```

Expected: `5 passed`.

- ☐ installed-runtime acceptance green

---

## §2 — Docs in place + freshly dated

These are the **friend-facing** docs that ship in the snapshot:

```bash
for f in README.md CHANGELOG.md LICENSES.md docs/ACTIVITY_FEED.md docs/RECOVERY.md; do
  if [[ -f "$f" ]]; then
    printf "  ✅ %s — last mod: %s\n" "$f" "$(stat -c %y "$f" | cut -d. -f1)"
  else
    printf "  ❌ %s — MISSING\n" "$f"
  fi
done
```

- ☐ `README.md` exists (friend entry point: install walkthrough + per-friend-wiki principle)
- ☐ `CHANGELOG.md` has a `[1.0.0] — <ship-date>` entry
- ☐ `LICENSES.md` lists every plugin's SPDX license + Context Mode's ELv2 SaaS caveat surfaced
- ☐ `docs/RECOVERY.md` covers the 8 scenarios per ADR-026 + ADR-027
- ☐ `docs/ACTIVITY_FEED.md` present

Maintainer-only docs (`SHIP_CHECKLIST.md`, `RELEASING.md`, `RELEASE_v1.0.0.md`) stay in the dev
repo and are **excluded from the snapshot by `publish.sh`'s allowlist** — verified in §5.

### CHANGELOG entry check

```bash
grep -E '^## \[1\.0\.0\]' CHANGELOG.md
```

Expected: one line with the version + date in `[1.0.0] — YYYY-MM-DD` format.

---

## §3 — CI / local validation

CI workflows (`validate.yml`, `verify-migrations.yml`) live in `.github/` and run on the **dev
repo** (they are excluded from the shipped snapshot). If you've pushed the dev repo to a private
GitHub remote, confirm the latest runs on the default branch are green:

```bash
# Only if the dev repo has a GitHub remote:
gh run list --workflow validate.yml --limit 1 --json conclusion -q '.[]|.conclusion'
gh run list --workflow verify-migrations.yml --limit 1 --json conclusion -q '.[]|.conclusion'
```

If the dev repo has **no remote**, §1.3 (local `claude plugin validate ./ --strict`) is the
authoritative gate — CI is a convenience layer, not a substitute.

- ☐ local `claude plugin validate ./ --strict` green (authoritative, §1.3)
- ☐ CI green on the dev repo (if a remote exists)

---

## §4 — Schema registry frozen

```bash
# Confirm no real migrations shipped at v1.0
ls skills/wiki-migration/migrations/ | grep -v '_template'
```

Expected: no output (only `_template/` exists).

```bash
# All page-types at v1
python3 -c "
import json
r = json.load(open('skills/wiki-migration/schemas.json'))
for pt, m in r['page_types'].items():
    assert m['current'] == 1, f'{pt} current != 1'
    assert m['supported_from'] == 1, f'{pt} supported_from != 1'
    assert m['migrations'] == [], f'{pt} has migrations'
print(f'  ✅ all {len(r[\"page_types\"])} page-types at v1, no migrations')
"
```

- ☐ all page-types at `current: 1, supported_from: 1, migrations: []`
- ☐ no real migration directories present (only `_template/`)

---

## §5 — Build + verify the publish snapshot

The orphan snapshot is the ONLY thing friends receive. Build + verify it BEFORE tagging.

### 5.1 — Dry-run gate (must pass green)

```bash
scripts/publish.sh --dry-run
```

This builds the allowlisted snapshot and runs all four guards:
1. no `PLACEHOLDER-ORG` anywhere in the snapshot,
2. **assert-absent** — NO maintainer-only content (`wiki/`, `raw/`, `REVIEW*.md`, maintainer docs, `.github/`, `tests/`, etc.) leaked in (this is the load-bearing ADR-019 boundary),
3. `claude plugin validate <snapshot> --strict` green,
4. both manifests present at root `.claude-plugin/` with marketplace `source: "./"`.

Expected: `✅ DRY-RUN PASSED`.

- ☐ `publish.sh --dry-run` passes all guards

### 5.2 — Marketplace repo exists + friends are read collaborators

```bash
gh repo view hazarsozer/sf-marketplace --json visibility,defaultBranchRef -q '.'
gh api repos/hazarsozer/sf-marketplace/collaborators -q '.[]|.login'
```

Expected: `"visibility":"PRIVATE"`, default branch `main`, every friend's handle listed with `read`.

- ☐ `sf-marketplace` exists + is private
- ☐ each friend added as a `read` collaborator
- ☐ (optional, RC users) `sf-marketplace-rc` exists, private, same collaborators

---

## §6 — First-friend dogfood (Hazar's own machine)

Before any other friend sees this:

### 6.1 — Publish, then fresh install

```bash
# Build the real snapshot (prints push commands; does NOT push):
scripts/publish.sh
# Inspect, then run the printed push commands by hand.

# In a fresh directory or on the secondary device:
/plugin marketplace add hazarsozer/sf-marketplace
/plugin install startup-framework@sf-marketplace
/reload-plugins
/sf:install
```

- ☐ install completes within 10 minutes (design target per ADR-015)
- ☐ all 7 stages of `/sf:install` complete green
- ☐ `/sf:doctor` post-install shows all sections ✅ (or known-acceptable ⏭️)

### 6.2 — `${HOME}` userConfig expansion verification

The `userConfig` defaults are literal `${HOME}/...` strings. CC's docs don't guarantee whether CC
expands them before exposing `CLAUDE_PLUGIN_OPTION_*`. The Python hook + the shell resolvers are
strip+expand-guarded, but verify on a real install:

```bash
/sf:doctor   # check the reported wiki path
```

- ☐ `/sf:doctor`'s wiki path is an **absolute** path (e.g. `/home/you/.startup-framework/wiki`), NOT a literal `${HOME}/.startup-framework/wiki`
- ☐ project detection works (open a project under your `devRoot`; wake-up injects its context)

If a literal `${HOME}` shows up: CC is passing the unexpanded default → confirm the shell scripts
`eval`/`expandvars`-guard it (lifecycle's resolvers do; file a bug if any path slips through).

### 6.3 — Real session: the daily loop

- ☐ wake-up hook injects sensible context at session start
- ☐ `/sf:wrap` writes an Activity Feed entry that pushes to the friend-group repo
- ☐ Hazar's `<handle>.log.md` shows the entry on GitHub
- ☐ `/sf:bootstrap-project test-project` creates the project sub-wiki
- ☐ `/sf:catch-up <project>` returns useful summaries

### 6.4 — Recovery dry-run (in a tmpdir, NOT your real wiki)

```bash
SF_WIKI_ROOT=/tmp/test-wiki bash tests/integration/migration-dogfood.sh
```

- ☐ migration pipeline + snapshot/restore semantics work in isolation

---

## §7 — Tag (dev repo) + publish (snapshot)

Only after every box above is ☑.

### 7.1 — Tag in the PRIVATE dev repo

```bash
git status                      # working tree clean
git tag v1.0.0                  # tags live ONLY in the private dev repo
PJ_VER=$(python3 -c "import json; print(json.load(open('.claude-plugin/plugin.json'))['version'])")
[[ "$PJ_VER" == "1.0.0" ]] || { echo "ABORT: plugin.json#version is $PJ_VER, not 1.0.0"; exit 1; }
# If the dev repo has a remote: git push origin v1.0.0   (NEVER push tags to sf-marketplace)
```

### 7.2 — Publish the orphan snapshot

```bash
scripts/publish.sh             # builds + verifies; prints the exact push commands
# Inspect the snapshot, then run the printed:
#   git -C <snapshot> remote add origin git@github.com:hazarsozer/sf-marketplace.git
#   git -C <snapshot> push --force origin HEAD:main
```

- ☐ snapshot built + all guards green
- ☐ orphan commit force-pushed to `sf-marketplace` (single commit, no tags)
- ☐ `/plugin marketplace update sf-marketplace` on a friend machine surfaces v1.0.0
- ☐ Activity Feed announcement posted (template in `docs/RELEASE_v1.0.0.md`)
- ☐ Friends notified out-of-band

> **Never** `git push --tags` to `sf-marketplace`. Tags carry no value to friends and the
> marketplace is meant to hold exactly one orphan commit per release.

---

## §8 — Post-publish verification

Within 24h:

- ☐ One friend other than Hazar runs `/plugin marketplace add` + `/plugin install` + `/reload-plugins` + `/sf:install` end-to-end
- ☐ That friend reports a green `/sf:doctor`
- ☐ Their `<handle>.log.md` appears in the Activity Feed
- ☐ Their `/sf:bootstrap-project` works

---

## When something fails

- **Test suite fails** → fix on a branch; rerun from §1.
- **`claude plugin validate` errors** → consult `tests/integration/plugin-validate-known-issues.md`.
- **`publish.sh` guard fails** → the message names the problem (placeholder / leaked path / validation). Fix it; the guard is doing its job — never bypass it.
- **Schema-conformance blockers** → patch the offending template; rerun.
- **`/sf:install` fails on first-friend dogfood** → triage with the failing teammate (likely sf-onboarding); do NOT publish.
- **First friend (post-publish) reports failure** → triage; ship a v1.0.1 PATCH per `docs/RELEASING.md` § Recovery from a bad release.

---

## What this checklist is NOT

- Not a substitute for code review (per `REVIEW*.md`).
- Not a substitute for test coverage (per each module's suite).
- Not a substitute for hands-on dogfood (§6 is the real gate).

The checklist is the **last sanity pass** before friends get the framework. Skipping items is how friends get a broken framework.
