# Ship Checklist — v1.0.0

Single-page gate Hazar runs through before tagging `v1.0.0`. Every item must be ☑ before the tag is pushed. Skip nothing.

The verification commands assume you're at the repo root.

---

## §1 — Code green

### 1.1 — All teammate test suites pass

```bash
# sf-onboarding
( cd wiki-skeleton && python3 -m pytest tests/ -q )
( cd skills/sf-bootstrap-project && python3 -m pytest tests/ -q )
( cd skills/sf-interview && python3 -m pytest tests/ -q )
( cd skills/sf-install && python3 -m pytest tests/ -q )

# sf-lifecycle
( cd skills/sf-wrap && python3 -m pytest tests/ -q )
( cd skills/sf-improve-skill && python3 -m pytest tests/ -q )

# sf-feed
( cd feed && python3 -m pytest tests/ -q )
( cd skills/sf-catch-up && python3 -m pytest tests/ -q )

# sf-distribution
bash skills/sf-update/scripts/version-compare.sh --self-test
bash skills/sf-doctor/scripts/tests/test_check_schemas.sh
bash skills/sf-update/scripts/tests/test_snapshot_inode_safety.sh
```

Expected: every command exits 0; final lines report `N passed` or `N/N PASS`.

- ☐ all four teammates' tests green

### 1.2 — Cross-team review findings closed

Track from `REVIEW.md` at repo root. Status as of writing:

- ☐ 1 critical issue addressed (was: lifecycle-2's `sf-improve-skill` YAML — resolved 2026-05-28)
- ☐ 1 high issue addressed
- ☐ 4 medium issues addressed (D1 sf-distribution check-schemas false-positive — resolved 2026-05-28)
- ☐ 3 low issues addressed (D2 sf-distribution snapshot inode-sharing — resolved 2026-05-28)

```bash
grep -c '^- \[ \]' REVIEW.md  # should be 0 (zero unchecked findings)
```

### 1.3 — `claude plugin validate --strict` clean

```bash
claude plugin validate ./plugins/startup-framework --strict
claude plugin validate .
```

Expected for both: `✔ Validation passed` (no errors, no warnings).

- ☐ plugin manifest validates
- ☐ marketplace manifest validates

### 1.4 — Schema-conformance harness: 0 strict blockers

```bash
python3 tests/integration/schema-conformance/conformance.py
```

Expected: `BLOCKERS (strict mode): 0`. Informational fails are non-blocking (research files predating ADR-027).

- ☐ 0 strict blockers
- ☐ 12+ of 16 page-types have conformant examples (rest are documented TODOs)

### 1.5 — End-to-end migration dogfood: 17/17 PASS

```bash
bash tests/integration/migration-dogfood.sh
```

Expected: `END-TO-END MIGRATION DOGFOOD: 17/17 PASS`.

- ☐ full pipeline composes correctly

---

## §2 — Docs in place + freshly dated

Every doc must exist + have a last-mod date ≥ the v1.0 cutoff date.

```bash
for f in CHANGELOG.md LICENSES.md README.md docs/RECOVERY.md docs/RELEASING.md docs/SHIP_CHECKLIST.md; do
  if [[ -f "$f" ]]; then
    printf "  ✅ %s — last mod: %s\n" "$f" "$(stat -c %y "$f" | cut -d. -f1)"
  else
    printf "  ❌ %s — MISSING\n" "$f"
  fi
done
```

- ☐ `CHANGELOG.md` has a `[1.0.0] — <ship-date>` entry
- ☐ `LICENSES.md` lists every plugin's SPDX license + Context Mode's ELv2 SaaS caveat surfaced
- ☐ `README.md` includes the 10-minute install walkthrough + per-friend wiki principle
- ☐ `docs/RECOVERY.md` covers the 8 scenarios per ADR-026 + ADR-027
- ☐ `docs/RELEASING.md` documents stable + RC + promote-rc procedures
- ☐ `docs/SHIP_CHECKLIST.md` (this file) is referenced from `docs/RELEASING.md`

### CHANGELOG entry check

```bash
grep -E '^## \[1\.0\.0\]' CHANGELOG.md
```

Expected: one line with the version + date in `[1.0.0] — YYYY-MM-DD` format.

---

## §3 — CI green on main

```bash
gh run list --workflow validate.yml --limit 1 --json conclusion,headBranch -q '.[]|.conclusion'
gh run list --workflow verify-migrations.yml --limit 1 --json conclusion,headBranch -q '.[]|.conclusion'
```

Both should print `success` for the latest run on `main`.

- ☐ `validate.yml` last run on main = success
- ☐ `verify-migrations.yml` last run on main = success
- ☐ `release.yml` has NEVER been run yet (will trigger on this tag)

---

## §4 — Schema registry frozen

```bash
# Confirm no real migrations shipped at v1.0
ls skills/wiki-migration/migrations/ | grep -v '_template'
```

Expected: no output (only `_template/` exists).

```bash
# All 16 page-types at v1
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

- ☐ all 16 page-types at `current: 1, supported_from: 1, migrations: []`
- ☐ no real migration directories present (only `_template/`)

---

## §5 — Marketplace repo preparation

Create the marketplace repo BEFORE tagging.

### 5.1 — Repo exists

```bash
gh repo view <org>/sf-marketplace --json visibility,defaultBranchRef -q '.'
```

Expected: `{"visibility":"PRIVATE","defaultBranchRef":{"name":"main"}}` (or `master`).

- ☐ `sf-marketplace` repo exists + is private
- ☐ default branch is `main` or `master`

### 5.2 — Friends added as read collaborators

```bash
gh api repos/<org>/sf-marketplace/collaborators -q '.[]|.login'
```

Expected: every friend's GitHub handle listed.

- ☐ each friend added as collaborator with `read` permission

### 5.3 — `sf-marketplace-rc` (optional, only if you'll use the RC channel)

If yes:
- ☐ `sf-marketplace-rc` repo exists, private
- ☐ same friends added as read collaborators

---

## §6 — First-friend dogfood (Hazar's own machine)

Before any other friend sees this:

### 6.1 — Fresh install on Hazar's secondary device (or in a clean dir)

```bash
# In a fresh directory or a new machine
/plugin marketplace add <org>/sf-marketplace
/plugin install startup-framework@sf-marketplace
/sf:install
```

- ☐ install completes within 10 minutes (the design target per ADR-015)
- ☐ all 7 stages of `/sf:install` complete green
- ☐ `/sf:doctor` post-install shows all sections ✅ (or known-acceptable ⏭️)

### 6.2 — Real session: open a project, run the daily loop

- ☐ `/sf:wake-up` produces a sensible context for a project
- ☐ `/sf:wrap` writes an Activity Feed entry that gets pushed to the friend-group repo
- ☐ Hazar's `<handle>.log.md` shows the entry on GitHub
- ☐ `/sf:bootstrap-project test-project` creates the project sub-wiki correctly
- ☐ `/sf:catch-up <project>` returns useful summaries

### 6.3 — Recovery dry-run

In a tmpdir (NOT your real wiki):

```bash
# Simulate /sf:update on a fresh wiki
SF_WIKI_ROOT=/tmp/test-wiki bash tests/integration/migration-dogfood.sh
```

- ☐ migration pipeline works in isolation
- ☐ snapshot + restore semantics work cleanly

---

## §7 — Tag the release

Only after every box above is ☑.

```bash
# Confirm working tree is clean
git status

# Tag locally
git tag v1.0.0

# Verify the tag matches plugin.json version
PJ_VER=$(python3 -c "import json; print(json.load(open('plugins/startup-framework/.claude-plugin/plugin.json'))['version'])")
[[ "$PJ_VER" == "1.0.0" ]] || { echo "ABORT: plugin.json#version is $PJ_VER, not 1.0.0"; exit 1; }

# Push the tag
git push origin v1.0.0
```

After push:
- ☐ `release.yml` workflow runs + creates the GitHub Release
- ☐ Activity Feed announcement posted in Hazar's `<handle>.log.md` (template in `docs/RELEASE_v1.0.0.md`)
- ☐ Friends notified out-of-band (WhatsApp / Discord / wherever)

---

## §8 — Post-tag verification

Within 24h of the tag:

- ☐ One friend other than Hazar runs `/plugin marketplace add` + `/plugin install` + `/sf:install` end-to-end
- ☐ That friend reports a green `/sf:doctor` output
- ☐ Their `<handle>.log.md` appears in the Activity Feed
- ☐ Their `/sf:bootstrap-project` works

---

## When something fails

- **Test suite fails** → fix on a branch; rerun this checklist from §1
- **`claude plugin validate` errors** → consult `tests/integration/plugin-validate-known-issues.md`
- **Schema-conformance harness blockers** → patch the offending template; rerun
- **`/sf:install` fails on first-friend dogfood** → triage with the failing teammate (likely sf-onboarding); do NOT ship
- **First friend (post-tag) reports failure** → triage; ship a v1.0.1 PATCH per `docs/RELEASING.md` § Recovery from a bad release

---

## What this checklist is NOT

- Not a substitute for code review (per `REVIEW.md`)
- Not a substitute for test coverage (per each teammate's pytest suite)
- Not a substitute for hands-on dogfood (§6 is the real ship gate)

The checklist is the **last sanity pass** before the tag goes public. Skipping items is how friends get a broken framework.
