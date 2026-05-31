# v1.0 Remediation Findings — next-session backlog

> **Status:** Filed 2026-05-31 from a multi-agent review of the SHIPPED v1.0 plugin. **No code changed** by this review. Per the maintainer's direction, these are to be tackled **next session, together with the namespace fix**, as one combined remediation effort. This doc is the plan input — sequence/scope it into a TDD plan (`superpowers:writing-plans`) at the start of that session.
>
> **Scope note:** This covers the **shipped plugin** only. The `sf-ingest-project` plan's own findings were already patched into `docs/superpowers/plans/2026-05-31-project-ingest.md` § "Review Corrections" (separate track).

Review method: 3 agents on the shipped plugin (architecture/consistency, security/privacy, Python correctness) + 1 dedicated namespace investigator. All Python claims were validated by **running** the per-module suites (483 tests pass). Findings are grounded in `file:line`.

---

## 0. THE HEADLINE — `/sf:` commands do not ship (HIGH)

**What ships:** users type **`/startup-framework:sf-wrap`**, `/startup-framework:sf-insights`, etc. — NOT `/sf:wrap`.

**Why (both compound):**
1. A plugin's command namespace **is its `plugin.json` `name`** (`startup-framework`), not a free choice. ADR-013's premise — that we can pick the `/sf:` prefix independently — is false.
2. The command verb is the **skill directory name** (`sf-wrap`), not frontmatter `name:`. So even namespace-stripped it's doubled.

**Evidence (very high confidence):**
- Official CC docs (`plugins.md`): *"The folder name becomes the skill name, prefixed with the plugin's namespace … To change the namespace prefix, update the `name` field in `plugin.json`."*
- Live proof on this machine: installed plugins register as `crucible:run` (dir `run/`), `vercel:deploy` (file `commands/deploy.md`, no frontmatter `name`). Same rule → `startup-framework` + `sf-wrap` = `/startup-framework:sf-wrap`.
- Corroborated by this session's own skill list (`crucible:run`, `vercel:deploy`, `supabase:supabase` — all `plugin:skill`).

**Blast radius:** ~175 files, 1500+ `/sf:` string occurrences (README, CHANGELOG, all SKILL.md descriptions, stage-7 walkthrough, all 28 ADRs, the ingest plan). **Nothing functional breaks** — no hook/script invokes `/sf:` programmatically (verified) — but **every documented first-run command errors**: a fresh user typing `/sf:install` from the README gets nothing.

**Fix — Option A (make reality match the docs; recommended):**
1. `.claude-plugin/plugin.json`: `"name": "startup-framework"` → `"name": "sf"`. (Update `marketplace.json` install id + README/CHANGELOG `/plugin install …@sf-marketplace` lines. `displayName` can stay "Startup Framework".)
2. Rename every skill dir to drop `sf-`: `sf-wrap`→`wrap`, `sf-insights`→`insights`, `sf-doctor`→`doctor`, `sf-bootstrap-project`→`bootstrap-project`, `sf-improve-skill`→`improve-skill`, `sf-note`→`note`, `sf-recall`→`recall`, `sf-backup`→`backup`, `sf-install`→`install`, `sf-interview`→`interview`, `sf-update`→`update`. (`wiki-migration` is invoked as `/sf:migrate-wiki` in docs — reconcile: either rename dir to `migrate-wiki` or fix the docs to `/sf:wiki-migration`. The planned `sf-ingest-project`→`ingest-project`.)
3. Lockstep-update everything that greps `skills/sf-*` paths: `lib/sf_paths.py`, `sf-doctor` check scripts, every `eval.json`/test that `cd`s into `skills/sf-*`, the ingest plan. After the renames, the existing `/sf:<verb>` docs are correct **as-is** (no doc rewrite needed) and ADR-013's intent is finally true.

**Then:** re-run all per-module tests + `claude plugin validate --strict` + `publish.sh --dry-run`, and **re-publish** the marketplace (this changes the shipped command surface). Add a CHANGELOG entry + bump version (this is a user-visible change to every command → at least MINOR; arguably MAJOR since old `/startup-framework:*` invocations change — though they never worked as documented).

**Caveat to verify first (cheap):** install the plugin, type `/sf` vs `/startup-framework` at the prompt, confirm what autocompletes. Settle empirically before the rename.

---

## 1. Python bugs (shipped; all 483 tests pass — these are untested paths)

| Sev | Finding | Location | Fix |
|---|---|---|---|
| HIGH | Rollback verify iterates only `pre_snapshot` keys → a new file created by a partial apply, not removed by `git clean`, is invisible; rollback reported clean when wiki is half-applied. `_rollback_wiki` also returns early on `git restore` failure without running `git clean`. | `skills/sf-wrap/lib/apply.py:204` (and `:128`) | Compare full symmetric diff: `for k in pre \| post.keys()`; run `git clean` even when `git restore` fails. |
| HIGH | Frontmatter parser keeps scanning into the document body when the closing `---` is absent → a `handle:` line in a truncated `identity.md`'s body is accepted as the handle (passes `HANDLE_RE`), flowing a wrong handle into paths. | `lib/sf_paths.py:263` | Track "opening fence seen"; return `None` if the loop ends without a closing `---`. |
| HIGH | `compute_usage_cost_usd` indexes `rates["cache_read"]`/`["cache_creation"]` unguarded → `KeyError` crash if a `model-pricing.json` entry omits them. | `skills/sf-improve-skill/lib/budget.py:126` | `.get(..., 0.0)`, or validate the 4 keys in `load_pricing_table`. |
| MED | New wiki pages stamped `framework_version: "1.0.0"` hardcoded instead of `framework_version()` → schema-version drift after upgrades. (Same root cause as ingest C1.) | `skills/sf-wrap/lib/diff_plan.py:150` | Import + call `lib.sf_paths.framework_version()`. |
| MED | Empty `new_content` → empty unified diff → `git apply --check` fails with a confusing "no valid patches" instead of an early guard. | `skills/sf-wrap/lib/diff_plan.py:68` | Guard blank content before diffing. |
| MED | `grep_wiki` sort key calls `path.stat()` after `rglob`; a concurrent delete → unhandled `OSError`. | `skills/sf-recall/lib/__init__.py:244` | `stat` guarded by `exists()` or precompute mtimes. |
| LOW | Dead `if False else` ternary (unreachable `--no-edit` branch). | `skills/sf-wrap/lib/apply.py:123` | Remove dead branch. |
| LOW | `decode_project_dir` lossy fallback can yield wrong project basename when record `cwd` absent. | `skills/sf-insights/scripts/collect.py:486` | Prefer encoded `dir_name` over lossy decode in fallback. |
| LOW | redundant local `import re as _re`; partial-quote frontmatter values. | `lib/sf_paths.py:74`, `:273` | Minor cleanups. |

**Top 3 Python:** apply.py rollback (data integrity), sf_paths frontmatter (wrong handle → paths/commits), budget.py KeyError (crashes improve-loop).

---

## 2. Architecture / docs / contract drift (shipped)

| Sev | Finding | Location |
|---|---|---|
| HIGH | **Page-type count disagrees 3 ways**: CHANGELOG says 11, `RELEASE_v1.0.0.md` says 16, `schemas.json` actually has **15** (missing from CHANGELOG enum: `master-index`, `project-index`, `licenses`, `project-log-entry`). CHANGELOG is `/sf:doctor`-consumed. | `CHANGELOG.md:49,74`, `docs/RELEASE_v1.0.0.md:35` vs `skills/wiki-migration/schemas.json` |
| HIGH | **3 skills ship with no `contract:` block** (violates ADR-011 "now impossible to ship without one"; contradicts `wiki/index.md:38`): `sf-doctor`, `sf-update`, `wiki-migration`. `sf-update` (full wiki write + migrations) most needs it. Also missing `license:`. | `skills/{sf-doctor,sf-update,wiki-migration}/SKILL.md` |
| MED | **Feed remnants on shipped surface** (contradict ADR-031): `sf-update/SKILL.md:174` "With sf-feed"; `sf-bootstrap-project/SKILL.md:133` activity-feed anti-pattern; `release.yml:125-138` "Activity Feed announcement" step. | as listed |
| MED | `sf-doctor` eval + SKILL assert conformance to `output-schema.json` that **does not exist** → eval assertion can never pass. | `skills/sf-doctor/SKILL.md:147`, `reference.md:202` |
| MED | `alternatives/` ships in master skeleton but has no registered page-type / no `/sf:doctor` schema coverage. | `wiki-skeleton/manifest.yaml:60` vs `schemas.json` |
| MED | CHANGELOG `[1.0.0]` date drift (CHANGELOG 05-30 vs SHIP_CHECKLIST pre-stamp 05-29; today 05-31). | `CHANGELOG.md:23`, `docs/SHIP_CHECKLIST.md:290` |
| MED | `sf-improve-skill` ships no `eval/eval.json` (documented exception, but contradicts ADR-011 absolute language). | `skills/sf-improve-skill/eval/README.md` |
| LOW | README requires CC ≥ 2.1.154 but enforced floor is 1.0.33. | `README.md:57` vs `check-env.sh:46` |
| LOW | "friend group / per-friend" framing remnants in shipped manifests vs solo-first README. | `.claude-plugin/{plugin,marketplace}.json` |
| — | **Structural:** no CI runs the binary evals (`validate.yml` only does JSON-schema + `bash -n` + version self-test). Eval-vs-reality gaps (e.g. the `output-schema.json` one) go undetected. Consider a CI step once an eval runner exists. | `.github/workflows/validate.yml` |

**Top 3 arch:** page-type count (15, fix CHANGELOG+RELEASE), add the 3 missing contracts, purge feed remnants.

---

## 3. Security / privacy (shipped)

**Confirmed safe (evidence-backed):** `collect.py` read-only + no-network; `check-permissions.sh` never prints secret values (hermetic tests); `publish.sh` snapshot provably excludes `wiki/` (Guard 0 aborts if present) and has no `eval`/injection; handle path-traversal guard enforced at every use.

| Sev | Finding | Location | Fix |
|---|---|---|---|
| MED | `check-env.sh` emits the **raw `OTEL_EXPORTER_OTLP_ENDPOINT`** into session output; Grafana/Honeycomb/Datadog embed credentials in that URL. | `skills/sf-doctor/scripts/check-env.sh:144` | Emit `"configured"` not the URL (match the ANTHROPIC_API_KEY pattern). |
| MED | `collect.py` `kickoff` field forwards the user's first message verbatim (could contain a pasted secret) into the synthesis LLM context; the prompt's "don't repeat secrets" is a soft control. | `collect.py:366,592` | Redact token-like substrings, or drop the `kickoff` field (aggregates are more useful). |
| LOW | `HANDLE_RE` has no max length → 50k-char hand-edited handle → `OSError` on path ops. | `lib/sf_paths.py:186,200` | Add `len(value) <= 50` to `validate_handle()`. |
| LOW | `check-permissions.sh` can print a full encoded project path via the `or path` fallback. | `check-permissions.sh:219` | Minor; note in docs or harden the fallback. |

**Top 3 security:** OTEL URL redaction, kickoff secret passthrough, HANDLE_RE max length.

---

## Suggested sequencing for the combined next-session effort

1. **Decide the namespace** (verify empirically → Option A). It's the largest change and gates a re-publish; do it first so the rename and the other doc fixes happen in one sweep.
2. **Python HIGH bugs** (apply.py, sf_paths frontmatter, budget.py) — TDD: reproduce → fix → test. `lib/sf_paths.py` frontmatter fix pairs naturally with the HANDLE_RE max-length (LOW).
3. **Contract + docs drift** — add the 3 contracts, fix the page-type count to 15, purge feed remnants, ship/inline the `output-schema.json`, decide `alternatives/` page-type.
4. **Security MEDIUMs** — OTEL + kickoff redaction.
5. **Re-verify + re-publish** — per-module tests, `plugin validate --strict`, `publish.sh --dry-run`, CHANGELOG + version bump, then the human-run publish.

All findings are review-only; nothing here has been actioned.
