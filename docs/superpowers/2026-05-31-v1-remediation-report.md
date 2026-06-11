# v1.0 Remediation — Implementation Report

**Date:** 2026-05-31
**Branch:** `fix/v1-remediation` (git worktree at `.claude/worktrees/fix-v1-remediation`, branched off `feat/project-ingest` @ `4ee2265`)
**Commits:** 36 (since the plan commit) · tree clean · all suites green
**Version:** **NOT bumped** — this is v1.0 polish; `plugin.json` stays `1.0.0` (maintainer decision, 2026-05-31)
**Status:** Phases 1–4 **complete**. Phase 5 (re-verify → empirical `/sf` check → re-publish) is deferred to the maintainer; no version bump.

**Source artifacts:**
- Findings (input): `docs/superpowers/specs/2026-05-31-v1-remediation-findings.md`
- Plan: `docs/superpowers/plans/2026-05-31-v1-remediation.md`
- This report (outcome): `docs/superpowers/2026-05-31-v1-remediation-report.md`

---

## TL;DR

Remediated the shipped v1.0 `startup-framework` plugin across four phases — Python correctness, doc/contract drift, security/privacy, and the command-namespace rename — executed via `superpowers:subagent-driven-development` (fresh implementer per task + two-stage spec-then-quality review). 17 of 18 planned tasks landed (one dropped as a mischaracterized non-issue), plus one in-flight expansion the security review forced. The namespace rename (`startup-framework` → `sf`, the headline fix) was completed and independently opus-audited with zero over-reach. **The only thing left is the re-publish, which is intentionally the maintainer's (it needs a live install + the `/sf` autocomplete confirmation), and per decision today carries no version bump.**

---

## Method

- **Workspace:** isolated git worktree on `fix/v1-remediation` (reversible).
- **Execution:** `superpowers:subagent-driven-development` — one implementer subagent per task; after each, a **spec-compliance** review then a **code-quality** review (independent subagents, "don't trust the report — verify the code"), with fix loops until both approve.
- **Security phase:** quality reviews routed through the **`security-reviewer`** agent (per the project's security-code review doctrine) + an adversarial re-review after fixes.
- **Namespace rename:** executed as one atomic sweep (intermediate states are deliberately red), then a two-half **opus** audit — completeness gate + over-reach audit.
- **Ordering:** namespace-**last** (changed from the findings' suggested "first") — because it's independent of the fixes, fully reversible in the worktree, and its only empirical confirmation needs an install; so Phases 1–3 ran first on the verified `skills/sf-*` paths and the rename + its install-check became the final unit.

---

## Phase 1 — Python correctness (12 commits)

The original findings' "3 Python HIGH bugs" framing was **wrong** and was corrected during implementation:

| Finding | Cited | **Actual** | Fix | Tests |
|---|---|---|---|---|
| `lib/sf_paths.py` — unterminated frontmatter accepts a body `handle:` (flows into FS paths) | HIGH | **HIGH ✓** (the only true HIGH) | Parser returns `None` if no closing `---`; handle length capped at 50 (+ error message states the cap) | 49 ✓ |
| `skills/sf-improve-skill/lib/budget.py` — `KeyError` on a pricing table missing cache-rate keys | HIGH | **MED** | `.get(..., 0.0)` for the two cache rates | 144 ✓ |
| `skills/sf-wrap/lib/diff_plan.py` — `framework_version` hardcoded `"1.0.0"` | MED | **MED** (+ caveat) | Resolve dynamically via `importlib` file-load (naive `import lib.sf_paths` fails — the skill's own `lib/` shadows it); `except`-branch now genuinely tested | 90 ✓ |
| `skills/sf-wrap/lib/diff_plan.py:68` — "empty-content guard" | MED | **NOT A BUG** | Cited function was dead code (0 callers) → deleted | — |
| `skills/sf-recall/lib/__init__.py` — unguarded `stat()` in `grep_wiki` sort key | MED | **MED ✓** | `_safe_mtime` helper (module-level) guards `OSError` | 26 ✓ |
| `skills/sf-wrap/lib/apply.py` — rollback "incomplete" diagnostic | HIGH | **LOW** (`git clean` already runs; rollback works — only the log *count* under-reported) | Extracted symmetric `_count_differing(pre, post)` helper | (in 90) |
| `skills/sf-wrap/lib/apply.py:123` — dead `is_absolute()` ternary | LOW | **LOW ✓** | Collapsed to `rel = str(wiki_root)` | — |
| `skills/sf-insights/scripts/collect.py:486` — lossy project-name fallback | LOW | **LOW ✓** (expectation corrected — `my-app` is unrecoverable) | Surface the encoded `dir_name`, not the lossy decode | 24 ✓ |

**Net:** 1 HIGH, 2 MED, the rest LOW/dead-code — not 3 HIGH.

---

## Phase 2 — Doc / contract / consistency drift (8 commits, 1 task dropped)

| Task | Result |
|---|---|
| 2.1 Page-type count | CHANGELOG + RELEASE reconciled to **15** (verified against `schemas.json`; was 11/16) |
| 2.2 Missing contracts | Added `contract:` + `license:` to `sf-doctor`, `sf-update`, `wiki-migration` SKILL.md (ADR-011); spec review verified each contract's claims against the skills' real behavior + script dirs |
| 2.3 Feed remnants | Removed 4 live Activity Feed remnants (ADR-031) incl. a **bonus** `"sf-feed"` left in the `owner_module` CI-validator enum |
| 2.4 output-schema.json | Re-pointed 3 dangling refs at the inline schema (file never existed; eval didn't assert it) |
| **2.5 Remove `alternatives/`** | **DROPPED (won't-fix).** Implementer caught that a test (`test_stage5_additive_diff.py`) + 2 eval fixtures depend on it — it's an *intentional* freeform skeleton dir, not orphan drift. The planner's "zero consumers" claim was wrong. |
| 2.6 CHANGELOG date | `[1.0.0]` + SHIP_CHECKLIST pre-stamp aligned to 2026-05-31 |
| 2.7 README CC floor | `≥ 2.1.154` → `≥ 1.0.33` (the actually-enforced floor) |
| 2.8 Solo framing | `friend-group`/`Per-friend` → `solo-builder`/`Per-builder` in both manifests (+ an `rcChannel` description the implementer caught) |

---

## Phase 3 — Security / privacy (6 commits, 1 expansion)

| Task | Result |
|---|---|
| 3.1 OTEL endpoint leak | `check-env.sh` now emits `configured`, never the raw `OTEL_EXPORTER_OTLP_ENDPOINT` (which can embed creds). Security review surveyed the whole script — **no sibling leaks** — but caught that `reference.md` still *rendered* the raw endpoint; that render-layer leak was closed too. New hermetic `test_check_env.sh`. |
| 3.2 kickoff passthrough → **+ topics leak** | Dropped the `kickoff` field (verbatim first user message → synthesis LLM). **The security review then found the same leak class survived via the `topics` field** (`_scan_topics`'s token regex captured `sk-ant-…`/`AKIA…` as single tokens) — and that the new test was a *false green* (case-sensitive vs. lowercased tokens). Expanded to add a `_looks_like_secret` filter (length + credential-prefix + AWS-shape) on both user- and assistant-text paths; corrected the test (case-insensitive, two sentinels). Adversarial re-review confirmed closed. |
| 3.3 permissions path fallback | `check-permissions.sh` label fallback no longer dumps a full project path (`(root)` instead); + a `/`-key regression pin; + removed a dead arm I'd over-specified. Security survey confirmed this was the script's only raw-path emitter. |

---

## Phase 4 — Namespace rename `startup-framework` → `sf` (10 commits)

The headline fix: `/sf:` commands never shipped — the plugin installed as `/startup-framework:sf-wrap` etc. Root cause: a plugin's command namespace **is** its `plugin.json` `name`, and the command verb is the skill **dir** name.

**Swept (one atomic transformation):**
- 11 `skills/sf-*/` dirs → bare verbs via `git mv` (`wiki-migration` kept); 11 `SKILL.md` `name:` fields flipped.
- `plugin.json` + marketplace plugin-entry `name` → `sf` (marketplace id `sf-marketplace` + repo refs untouched).
- Plugin data-dir fallbacks `startup-framework-sf-marketplace` → `sf-sf-marketplace` (3 scripts + RECOVERY.md).
- All functional refs (13 Python path literals, shell test scripts, 2 CI invocations, conformance glob, `check-plugins.sh` cache lookup), install-id doc lines (`sf@sf-marketplace`), 3 `/sf:migrate-wiki`→`/sf:wiki-migration` strings, and `sf-*` mentions in comments/docstrings.
- ~60 references across ~44 files; 139 renames (history preserved, `R099`).

**Opus audit — ✅ both halves:**
- **Completeness:** every stale-ref grep empty; **454 pytest + all bash harnesses + version-compare self-test + conformance + `claude plugin validate --strict`** green.
- **Over-reach:** all must-not-change surfaces **CONFIRMED INTACT** — `/sf:` doc strings (1046, zero malformed), `lib/sf_paths` (not a skill dir), `~/.startup-framework/` user-data root (103 refs), `wiki-migration/`, `eval.json#name` labels + `run_evals("sf-wrap")` args, marketplace id/repo.

(The SHIP_CHECKLIST runbook's stale `skills/sf-*` test commands were also fixed so the ship runbook works post-rename.)

---

## Decisions made (with rationale)

| Decision | Rationale | Who/when |
|---|---|---|
| **Namespace-last** ordering | Independent of the fixes; reversible in the worktree; empirical `/sf` check needs an install (same install Phase 5 needs). Lets Phases 1–3 run on verified paths. | You, 2026-05-31 |
| **Drop Task 2.5** (`alternatives/`) | A test + 2 fixtures depend on it → intentional freeform dir, not orphan drift; needs no page-type. | You, 2026-05-31 |
| **Expand 3.2** to close the `topics` leak | Same secret-leak class as kickoff; leaving it (and a false-green test) would make the privacy phase incoherent. | You, 2026-05-31 |
| **Keep `wiki-migration` dir** (fix 3 doc strings instead) | Renaming the dir would touch ~35 refs + `$schema` pointers for a never-typed machinery skill. | Plan default |
| **No version bump** | Polishing v1; stays `1.0.0`. | You, 2026-05-31 |

---

## What the review pipeline caught that planning missed

The two-stage (and security) reviews surfaced **4** things the upfront investigation didn't:

1. **2.5** — the planner's "zero consumers" was false (a test + 2 fixtures depend on `alternatives/`).
2. **3.1** — `reference.md` still rendered the raw OTLP endpoint (render-layer leak beyond the script fix).
3. **3.2** — the **`topics` secret-leak** (same class as kickoff) — the most significant catch.
4. **3.2** — the new test was a false green (case-sensitive assertion hiding the topics leak).

Plus the Phase 1 severity recalibration (3 HIGH → 1) and the dead-code "bug". This is the payoff of fresh-context per-task review + adversarial security re-review.

---

## Current state & verification

- **Branch:** `fix/v1-remediation`, 36 commits, tree clean.
- **Tests:** 454 pytest passing across all modules (lib 49, wrap 90, insights 24, improve-skill 144, recall 26, note 18, backup 70, install 33) + all `sf-doctor`/`sf-update` bash harnesses + version-compare self-test + conformance.
- **`claude plugin validate ./ --strict`:** ✔ passed.
- **`plugin.json`:** `name: sf`, `version: 1.0.0` (unbumped).

---

## What remains (Phase 5 — maintainer, no version bump)

The rename only takes effect for the user once **re-published** (the shipped command surface changes). Deferred to a future session:

1. **Empirical `/sf` confirmation** — add the worktree as a local marketplace → `/plugin install sf@sf-marketplace` → type `/sf` and confirm `/sf:wrap`, `/sf:doctor`, … autocomplete and `/startup-framework:*` is gone.
2. **Re-publish** (human-gated) — `bash scripts/publish.sh --dry-run`, then `bash scripts/publish.sh` → `/plugin marketplace update sf-marketplace`. **No version bump** per decision.
3. **Post-publish sanity** — `/sf:doctor` green.
4. **Branch** — merge `fix/v1-remediation` into the dev branch (`finishing-a-development-branch`).
5. **Optional** — fold the polish items into the CHANGELOG `[1.0.0]` entry (no new version section, since not bumping); a final holistic full-branch review before publish.
6. **Local one-time** — if a `~/.claude/data/startup-framework-sf-marketplace/` dir exists locally, move it to `sf-sf-marketplace/` (the data-dir name changed with the plugin name).

---

## Commit log (Phases 1–4, oldest → newest)

**Phase 1 — Python (12):**
`75e6e5f` `43da562` sf_paths · `4bfedca` `20b3811` budget · `e3f5a56` `04ca0a8` diff_plan · `ab9a61d` `fb9fe6c` recall · `6d4be93` `9ae693e` apply · `f796dc4` `0ce7fa6` collect

**Phase 2 — Doc/contract (8):**
`e1a8191` page-count · `15589b3` contracts · `532d140` feed remnants · `843f3bd` `672abb1` output-schema refs · `b9ff9ed` CHANGELOG date · `1142c94` CC floor · `e0d12ef` solo framing

**Phase 3 — Security (6):**
`b5ef84c` `9ee56af` OTEL leak (script + doc) · `7ee64b8` kickoff drop · `dce00f6` topics-token filter · `c4cd80c` `192629b` permissions fallback

**Phase 4 — Namespace (10):**
`5a19815` dirs+names · `3195379` manifests · `93a2230` data-dir · `3a239d8` check-plugins · `aa63293` python refs · `17e2be3` shell refs · `b9f9aef` CI+conformance · `21bba00` comments/docstrings · `1652356` install-id+migrate-wiki · `791cfec` SHIP_CHECKLIST runbook
