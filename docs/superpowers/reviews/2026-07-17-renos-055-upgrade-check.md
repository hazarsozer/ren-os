# RenOS 0.5.4 → 0.5.5 — Live Upgrade Check (scratch-only)

**Date:** 2026-07-17
**Repo under test:** `~/Dev/renos` @ `b70e312` (`release: 0.5.5 — orientation & real usage`), tag `v0.5.5`
**Scenario:** an existing friend on 0.5.4 upgrades to 0.5.5. Does a pre-existing wiki (built before 0.5.5, no `overview.md` page type, no usage-aware decay signals) upgrade cleanly, and do the new 0.5.5 features (`overview.md`, structural-artifact quarantine exemption widening, usage-aware decay) light up without breaking anything?

**Overall result: FAIL — 29/30 assertions PASS, 1 FAIL, one CRITICAL upgrade-breaking finding (F1).**

All read-side / compose-side / doctor / trust / decay / read-tracker behavior is clean. The one failure is a real, reproducible data-loss bug in `/ren:bootstrap-project`'s forward-compatibility path: re-running it against an **existing, already-populated** project (exactly what 0.5.5 gives a friend a first-time reason to do, to pick up the new `overview.md` page) silently wipes the friend's real L2 map content back to an empty bootstrap-day template.

---

## 0. Environment (scratch-only, verified)

```
/tmp/claude-1000/-home-hsozer-Dev-startup-framework/472e8209-b369-45d4-bd67-294ae12f09a5/scratchpad/upgrade-055/
├── wiki/                 ← REN_WIKI_ROOT
├── claude-dir/           ← REN_CLAUDE_DIR
├── claude-config-dir/    ← CLAUDE_CONFIG_DIR
├── 01_setup.py           ← builds the simulated pre-0.5.5 wiki
├── 02_check1_and_4.py    ← check 1 (no-crash) + check 4 (decay), run before check 2's wrap call
├── 03_check2.py          ← check 2 (bootstrap forward path + wrap-with-stub)
├── 03b_repair_map_after_finding.py  ← repairs map.md after F1, so checks 3/5/6 run on realistic state
├── 04_check3_doctor.py   ← check 3 (doctor/schema)
├── 05_check5_trust.py    ← check 5 (trust/quarantine)
└── 06_check6_read_tracker.py  ← check 6 (read_tracker subprocess)
```

Every script imports the real modules directly (`lib.ren_paths`, `lib.memory.*`, `lib.instrument.*`, `hooks.wake-up.wakeup`, `skills.bootstrap-project.lib`, `skills.wrap.lib`, `skills.doctor.lib`) — no mocks. `hooks/observers/read_tracker.py` is invoked as a real subprocess via `sys.executable`, matching `tests/hooks/test_read_tracker.py`'s own invocation contract.

Invocation pattern used for every step:

```bash
cd ~/Dev/renos
SCRATCH=/tmp/claude-1000/-home-hsozer-Dev-startup-framework/472e8209-b369-45d4-bd67-294ae12f09a5/scratchpad/upgrade-055
REN_WIKI_ROOT="$SCRATCH/wiki" REN_CLAUDE_DIR="$SCRATCH/claude-dir" CLAUDE_CONFIG_DIR="$SCRATCH/claude-config-dir" \
  uv run python "$SCRATCH/<script>.py"
```

**`~/.claude/CLAUDE.md` untouched check:**

| | md5 |
|---|---|
| Before | `dba88348a1885e9f467415c480fa20b2` |
| After | `dba88348a1885e9f467415c480fa20b2` |

Identical. Also confirmed via `find ~/.claude -newer <first-script>` (empty result — no new/modified files under `~/.claude`) and by inspecting `~/.renos` (pre-existing, unrelated real install; its `wiki/` mtime predates this session's start, confirming it was never touched — `REN_WIKI_ROOT` fully overrides `wiki_root()` resolution, so nothing in this run ever resolved a path under the real `~/.renos` or `~/.claude`).

---

## Per-check results

| Check | Result | Assertions |
|---|---|---|
| 1. No crash on missing overview | **PASS** | 5/5 |
| 2. Bootstrap/interview forward path | **FAIL (F1)** | 7/8 |
| 3. Schema/doctor clean | **PASS** | 5/5 (2 informational warnings, both explained, neither a 0.5.5 regression) |
| 4. Usage-aware decay on a pre-existing page | **PASS** | 2/2 |
| 5. Trust/quarantine intact | **PASS** | 7/7 |
| 6. read_tracker hook | **PASS** | 3/3 |

Execution order in the scripts differs slightly from the numbering above: check 4 was run **before** check 1's `compose_wake_up_context` call, because that call's own extras-ranking surfaces (and thus mechanically "touches") the old backdated page — running check 4's "before" assertion after check 1 would have found the page already spared by check 1's own side effect, not by check 4's deliberate touch. This is itself a minor confirmation that the extras-ranking → `KIND_WAKEUP_SURFACE` → decay-sparing pipeline is live and working, not a problem.

---

## Setup — simulated 0.5.4-era wiki

`skills.bootstrap-project.lib.bootstrap("demo-project", session=..., repo_root=None)` stamps the `master` profile (identity.md, index.md, log.md, LICENSES.md, dirs) and the `project` profile (overview.md — the 0.5.5-only page) in one call, then queues an empty L2 map. To simulate a wiki that predates 0.5.5:

1. **Deleted `projects/demo-project/overview.md`** — mimics a wiki where this page type never existed.
2. **Confirmed `identity.md` is present-but-skeleton** (`handle: friend`, never interviewed) — matches a friend who bootstrapped but hasn't run `/ren:interview`.
3. **Overwrote `map.md`** with real, human-authored L2 content (Knowledge/Decision-map/Log, real facts and cross-links) — simulates months of real accumulated project knowledge pre-upgrade.
4. **Added two real content pages** (`research/topic-widget-caching.md`, `patterns/pattern-error-envelope.md`) — real prose, not placeholder-shaped, so they're extras-eligible.
5. **Added a real L1 session page** (`projects/demo-project/l1/session-old-1.md`, `writer=llm-auto`, `trust=model`, quarantine-banner intact) — mirrors exactly what `skills.wrap.lib.wrap_session` produces, giving wake-up's L1 section real substance from a prior session.
6. **Added one OLD data-plane page** (`research/deprecated-webhook-retry.md`) with its journal write manually backdated 120 days (`ren_ts`/journal `ts` both set via a `dataclasses.replace`d `Provenance`, written through the real `write_apply.apply_write` door) — to exercise usage-aware decay.

---

## Check 1 — No crash on missing overview (PASS, 5/5)

`wakeup.compose_wake_up_context(...)` run against the wiki with no `overview.md` present anywhere.

- `check1_no_crash` — composed 4148 chars without raising. **PASS**
- `check1_overview_section_omitted` — `"## What is this project"` absent from the payload (simply omitted, not an error, not a placeholder, not a crash). **PASS**
- `check1_l1_present` — `"## What happened last session"` present (the real prior-session L1 page injected correctly). **PASS**
- `check1_l2_present` — `"## Where to find project knowledge"` present (the real map.md injected correctly). **PASS**
- `check1_identity_correctly_omitted_skeleton` — `"## Who am I working with"` absent (identity.md still skeleton, correctly suppressed — pre-existing 0.5.4 behavior, unaffected by the upgrade). **PASS**

Full composed payload captured at `check1_composed.txt`; every present section (L1, L2, extras) renders real content cleanly, with `overview.md`'s absence causing nothing worse than that one section not existing.

---

## Check 2 — Bootstrap/interview forward path (FAIL — Finding F1, 7/8)

### (a) Idempotent re-stamp

Re-ran `bootstrap_lib.bootstrap("demo-project", session=..., repo_root=None)` against the now-existing project dir.

- `check2a_bootstrap_idempotent_no_crash` — `status="applied"`, no exception. **PASS**
- `check2a_overview_added` — `overview.md` now exists (the 0.5.5 skeleton was correctly additive-stamped onto the pre-0.5.5 project). **PASS**
- `check2a_overview_is_skeleton_shape` — content matches the shipped skeleton template exactly. **PASS**
- `check2a_identity_untouched` — `identity.md` byte-identical before/after. **PASS**
- **`check2a_map_untouched` — FAIL.** `map.md` was NOT byte-identical: the real, human-authored content (Knowledge/Decision-map/Log with real facts and links) was silently overwritten with an empty `"## Knowledge\n## Decision map\n_All pointer paths are relative to the wiki root, not this file._\n## Log\n- 2026-07-17: project bootstrapped"` template. **See Finding F1 below.**

### (b) Wrap with an LLM stub (material_change=true)

After F1 was found, `map.md` was repaired back to its real content (`03b_repair_map_after_finding.py`) so the rest of the drill runs against a realistic wiki. `skills.wrap.lib.wrap_session(narrative_md=..., durable_items=[], session=..., llm_call=<stub returning {"material_change": true, "overview": "<real prose>"}>, project="demo-project")` was then run.

- `check2b_wrap_overview_status_created` — `wrap_result["overview"] == "created"` (page existed but was still skeleton). **PASS**
- `check2b_overview_has_real_content` — `overview.md` body now contains the stub's replacement prose (807 chars). **PASS**
- `check2b_next_wakeup_injects_overview_section` — a fresh `compose_wake_up_context` call after the wrap now includes `"## What is this project"` with the real content. **PASS**

The wrap → maintain_overview → wake-up loop itself is solid: material-change detection, the queue auto-apply door, and the next-session injection all work exactly as designed.

---

## FINDING F1 (CRITICAL, upgrade-breaking): re-running `/ren:bootstrap-project` on an existing populated project silently destroys the L2 map

**Severity: CRITICAL — must fix before recommending 0.5.5 to friends with existing projects who want the new overview.md feature.**

**Root cause.** `skills/bootstrap-project/lib/__init__.py::bootstrap()` unconditionally builds an EMPTY L2 map on every call:

```python
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
content = assemble_l2(project_slug, [], [], f"{today}: project bootstrapped")   # always [] / []
page = _map_page(project_slug)
page_abs = ren_paths.safe_join(ren_paths.wiki_root(), page)
op = "UPDATE" if page_abs.exists() else "ADD"
entry, _ = propose_and_apply(Proposal(op=op, page=page, content=content, ...))
```

This is unlike the `overview.md` stamp, which goes through `lib.skeleton.stamp_skeleton`'s `copy_if_missing` rule (never touches an existing file — confirmed clean in check 2a). The L2 map instead goes through `lib.memory.queue.propose_and_apply`, whose only protection against clobbering real content is **applied-page dedup**: if the proposed (empty) content, once normalized, byte-matches what's already on the page, it's a no-op. A project's map that has grown ANY real content since bootstrap will never match the empty template again — so the dedup never fires, and the empty UPDATE lands for real.

The existing test suite has a blind spot here: `tests/skills/bootstrap_project/test_bootstrap.py::test_bootstrap_on_existing_map_auto_applies_update` only exercises a **same-day re-bootstrap with the map still empty** (so the dedup happens to catch it as `noop-duplicate`) — it never tests the realistic case of re-bootstrapping a project whose map has organically grown real content via wrap/ingest/hand-edit, which is exactly this drill's scenario.

**Why this is an upgrade-specific risk, not just a pre-existing quirk.** This code path has existed unchanged since 0.2 (`skills/bootstrap-project/lib/__init__.py`'s `assemble_l2([], [], ...)` call), but before 0.5.5 there was essentially no reason for a friend to re-run `/ren:bootstrap-project <existing-slug>` on a project that already has a populated map — nothing new to gain. **0.5.5 changes that**: it's the first version where re-running bootstrap-project on an existing project has a real, attractive payoff (picking up the new `overview.md` orientation page). A friend upgrading from 0.5.4 who reads the 0.5.5 changelog and thinks "let me re-run bootstrap on my existing projects to get the new overview page" will, on any project with real map content, silently lose that content back to an empty template — with `check_apply_integrity` in doctor never flagging it either (the UPDATE goes through the queue normally, so there's a matching applied entry — nothing looks broken from doctor's point of view).

**Live reproduction (this drill):**

Before re-bootstrap, `map.md` contained:
```
## Knowledge
- The demo project is a small internal tool for tracking widget inventory.
- Backend is FastAPI + Postgres; frontend is a thin HTMX layer.
- Deploys via a single systemd unit on a home server (no k8s).
## Decision map
- [[research/topic-widget-caching.md]] — why we cache widget counts in Redis (unstamped)
- [[patterns/pattern-error-envelope.md]] — the API error envelope every route follows (unstamped)
## Log
- 2026-04-01: project bootstrapped
- 2026-05-15: added Redis caching layer for widget counts
- 2026-07-10: settled on the error-envelope pattern for all routes
```

After `bootstrap("demo-project", session=..., repo_root=None)`:
```
## Knowledge
## Decision map
_All pointer paths are relative to the wiki root, not this file._
## Log
- 2026-07-17: project bootstrapped
```

All real Knowledge/Decision-map/Log content is gone. The page is archive-recoverable (every write in this framework is journaled + snapshotted, and a friend could `revert` the specific `write_id` if they knew to look — but nothing in the UI/doctor surface tells them their map was just emptied).

**Suggested fix direction (not implemented by this drill — read-only verification task):** `bootstrap()` should either (a) skip the L2-map proposal entirely when `map.md` already exists and has real (non-skeleton) content — mirroring the `copy_if_missing`/never-overwrite discipline `overview.md` and the master skeleton already get — or (b) gate the empty-map UPDATE the same way `maintain_overview` gates overview updates (only write when there's an actual reason to, never blind-clobber). Given `bootstrap-project`'s own SKILL.md already documents "A map already exists for this slug → Proposes UPDATE (queued, not silently skipped)" as accepted behavior, this may be a known-but-underestimated tradeoff rather than a pure oversight — but the 0.5.5 upgrade context materially raises the odds of a friend triggering it.

**Post-finding repair (this drill only):** `03b_repair_map_after_finding.py` restored `map.md` to its real content via a direct `write_apply.apply_write` call, so checks 3/5/6 below exercise a realistic post-upgrade wiki rather than F1's wreckage. This is a scratch-only repair; the underlying bug is reported as-is, not patched.

---

## Check 3 — Schema/doctor clean (PASS, 5/5)

- `check3_overview_registered_in_schemas_json` — `skills/wiki-migration/schemas.json` → `page_types.overview = {"current": 1, "migrations": []}`. **PASS**
- `check3_schema_versions_clean` — `check_schema_versions` → `status=ok`, `"all typed pages at current schema"`. **PASS**
- `check3_archive_integrity_clean` — `check_archive_integrity` → `status=ok`, `"no archive tier yet"`. **PASS**
- `check3_wiki_structure_clean` — `status=ok`. **PASS**
- `check3_no_unexpected_errors_across_all_checks` — zero `error`-status checks. **PASS**

Full `doctor.run_checks()` output (17 checks):

```
[ok   ] env
[ok   ] wiki_structure
[ok   ] frontmatter
[ok   ] schema_versions
[skip ] budget_lint          — no capability_tokens data yet (expected, scratch wiki)
[ok   ] dangling_pointers
[info ] graphify_status      — graphify not installed (expected, dev machine)
[info ] companions           — companions not yet decided (expected, no real ~/.claude)
[warn ] backup_configured    — no backup remote/tarball (expected, scratch wiki — not a 0.5.5 regression)
[ok   ] execution_tiers
[ok   ] global_drift
[ok   ] harness_neutrality
[ok   ] guard_health
[ok   ] suggestion_store
[warn ] apply_integrity      — see note below (test-harness artifact, not a 0.5.5 regression)
[ok   ] judge_health
[ok   ] archive_integrity
```

Two warnings, both explained and neither attributable to 0.5.5:

1. **`backup_configured`** — expected for any fresh scratch wiki with no git remote/tarball; unrelated to the 0.5.5 upgrade.
2. **`apply_integrity`** — flags 6 journal `write_id`s with no matching applied queue entry. This is a **drill-methodology artifact**: several setup/repair steps in this drill wrote directly via `write_apply.apply_write` (mirroring how `lib/skeleton.py` itself legitimately writes founding pages) rather than through `queue.propose_and_apply`, and used non-`"install"` session names — `check_apply_integrity`'s own docstring explicitly carves out `session="install"` writes as an expected, by-design exclusion for exactly this direct-write pattern; my drill's synthetic setup writes just weren't tagged that way. In a real upgrade, every write goes through a real command surface (`bootstrap`, `wrap`, `pin`, `ingest`) which all route through the queue — this warning would not fire.

---

## Check 4 — Usage-aware decay on the old page (PASS, 2/2)

- `check4_old_page_is_decay_candidate_before_touch` — `lifecycle.decay_candidates(now)` returns `['research/deprecated-webhook-retry.md']` before any touch. **PASS**
- `check4_old_page_spared_after_wakeup_surface_touch` — after `miss_log.log_surface(['research/deprecated-webhook-retry.md'], session)` (simulating a wake-up compose that surfaced it), `decay_candidates(now)` returns `[]` — the page is spared. **PASS**

Confirms the new 0.5.5 usage-touch signal (`KIND_WAKEUP_SURFACE`/`KIND_L3_FETCH`/`KIND_PAGE_READ`) correctly protects a page that predates the feature — a pre-0.5.5 page with only an old journal write (no usage-metric history at all, since that log didn't exist yet) is treated as a normal decay candidate on its journal age alone, and becomes protected the moment any of the three new usage signals name it. No special-casing needed for old pages; the mechanism is retroactive by construction (it only ever adds protection, never removes it).

---

## Check 5 — Trust/quarantine intact (PASS, 7/7)

**(a) Foreign-stamped page still excluded from extras (no regression):**
- `check5a_foreign_page_excluded_from_extras` — a `trust=foreign` page's sentinel content absent from the composed payload. **PASS**
- `check5a_held_count_line_present` — the "N quarantined page(s) held out" line present, confirming it was counted. **PASS**

**(b) Foreign-stamped overview/L2 still excluded from their dedicated sections (the FOREIGN check is explicitly NOT lifted by the 0.5.5 exemption-widening amendment — only quarantine-withhold was):**
- `check5b_foreign_overview_excluded` — sentinel absent, `"## What is this project"` absent. **PASS**
- `check5b_foreign_l2_map_excluded` — sentinel absent, `"## Where to find project knowledge"` absent. **PASS**
- `check5b_held_count_reflects_two_foreign_structural_pages` — held-count line present. **PASS**

**(c) Quarantined-but-NOT-foreign (`trust=model`) overview/L2 inject WITH their banner intact — the NEW 0.5.5 behavior:**
- `check5c_quarantined_model_overview_injects_with_banner` — `"## What is this project"` present, sentinel present, quarantine banner text present in the payload. **PASS**
- `check5c_quarantined_model_l2_injects_with_banner` — `"## Where to find project knowledge"` present, sentinel present. **PASS**

All synthetic sentinel content was written and then restored to the real pre-check content (`overview.md`/`map.md`) at the end of the script — confirmed clean by grepping for the sentinel markers post-restore.

---

## Check 6 — read_tracker hook (PASS, 3/3)

`hooks/observers/read_tracker.py` invoked as a real subprocess (`sys.executable`) with a synthetic PostToolUse `Read` event naming `projects/demo-project/overview.md`, matching `tests/hooks/test_read_tracker.py`'s own invocation contract.

- `check6_exit_code_0` — exit code 0. **PASS**
- `check6_no_stdout` — empty stdout (observer contract: must never surface output to the user). **PASS**
- `check6_kind_page_read_logged` — a new `KIND_PAGE_READ` entry naming `projects/demo-project/overview.md` appended to the metrics log. **PASS**

---

## Summary

| | |
|---|---|
| **Overall** | **FAIL** — 29/30 assertions PASS, 1 CRITICAL finding |
| Wake-up composition (missing overview) | Clean, no crash, correct omission |
| Bootstrap forward-compat (skeleton stamps) | Clean — overview.md and identity.md both correctly additive |
| Bootstrap forward-compat (L2 map) | **BROKEN — Finding F1, data loss on re-run against a populated project** |
| Wrap → overview material-change → next wake-up | Clean |
| Doctor/schema | Clean (overview registered, schema_versions ok, archive_integrity ok) |
| Usage-aware decay retroactivity | Clean |
| Trust/quarantine (foreign exclusion + new banner-intact injection) | Clean |
| read_tracker hook | Clean |
| Real-file safety (`~/.claude/CLAUDE.md`, `~/.renos`) | Confirmed untouched |
