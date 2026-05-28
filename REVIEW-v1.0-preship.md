# Pre-Ship Review — startup-framework V1.0

**Date:** 2026-05-29
**Reviewers:** 4 parallel Sonnet agents (install-integrity, lifecycle-logic, feed-concurrency, ship-docs-security) + main-thread synthesis and independent spot-check.
**Method:** Each reviewer read its slice, ran the relevant test suites and `claude plugin validate`, and reasoned adversarially against the "V1.0 ready" claim. The four CRITICAL findings below were then re-verified directly against the code by the synthesizer (not merely relayed).
**Scope:** This is a holistic ship-readiness review, distinct from `REVIEW.md` (onboarding-2's intra-build cross-team review, 2026-05-28, all 9 findings since fixed).

---

## ⛔ VERDICT: NO-SHIP (until the 4 CRITICAL blockers below are closed)

**The good news:** 659/659 tests pass, the plugin validates `--strict` clean, the architecture is sound, the ADR-028 split-writer contract conforms, and the ADR-011 eval-schema regression is fully fixed. None of this requires re-architecture.

**The blocker:** the framework's core feature (wiki-context injection) and its headline feature (the cross-friend Activity Feed) are **both silently dead on a real install**, the shared feed repo **corrupts on the first network hiccup**, and **there is no documented sequence that produces a working `sf-marketplace` repo**. Reviewer split was 2× NO-SHIP / 2× SHIP-WITH-FIXES; the aggregate is unambiguously NO-SHIP.

**Estimated effort to clear all CRITICAL + HIGH:** ~half a day. No code changed in this session (review was document-only by request).

---

## 🔴 CRITICAL — must fix before tag (all independently verified)

### C1 — Wake-up hook reads the wrong wiki path in production → every friend's wiki silently skipped
- **Where:** `hooks/wake-up/sf-wake-up.py:213`
- **Code:** `wiki_root = Path(os.environ.get("SF_WIKI_ROOT", "")) or (Path.home() / ".startup-framework" / "wiki")`
- **Bug:** `Path("")` is `PosixPath('.')`, which is **truthy** — so the `or` home-dir fallback **never fires**. `hooks.json` does not set `SF_WIKI_ROOT`, and the Python hook ignores `CLAUDE_PLUGIN_OPTION_WIKIROOT` (the userConfig var that every shell script *does* read via `${SF_WIKI_ROOT:-${CLAUDE_PLUGIN_OPTION_WIKIROOT:-$HOME/.startup-framework/wiki}}`). In production `wiki_root` becomes the session CWD; `index.md`/`log.md` aren't there; the hook injects only a 46-char header.
- **Verified:** `python3 -c "from pathlib import Path; print(repr(Path('')), bool(Path('')))"` → `PosixPath('.') True`. The test suite masks this via `env.setdefault("SF_WIKI_ROOT", ...)`, so no test exercises the unset path.
- **Impact:** The single most important feature — per-friend wiki memory injection — does nothing on any real install.
- **Fix:** Replace with an explicit three-way fallback matching the shell scripts (`SF_WIKI_ROOT` → `CLAUDE_PLUGIN_OPTION_WIKIROOT` → `$HOME/.startup-framework/wiki`, each `.strip()`-guarded). Add a test that *removes* `SF_WIKI_ROOT` from env and asserts the home default.

### C2 — Activity Feed is dead on every install → missing `feed/` symlink in the packaged plugin
- **Where:** `plugins/startup-framework/` (has `hooks -> ../../hooks` and `skills -> ../../skills` but **no `feed -> ../../feed`**)
- **Bug:** `sf-wake-up.py` does `from feed import …`. On an installed plugin the cache at `$CLAUDE_PLUGIN_ROOT` contains only the dereferenced `hooks/` and `skills/`; `feed/` is absent → `ImportError` → the hook's `except ImportError: return ""` guard silently degrades to no-feed. `skills/activity-feed/scripts/status.sh` has the same root-path miss.
- **Verified:** `ls -la plugins/startup-framework/` shows only the two symlinks.
- **Impact:** The cross-friend Activity Feed — a headline V1 feature — never runs once installed. `/sf:doctor`'s feed section silently zeros.
- **Fix:** Add `plugins/startup-framework/feed -> ../../feed`. CC dereferences it alongside hooks/skills, placing the package under `$CLAUDE_PLUGIN_ROOT`. (No code change needed — consistent with the existing symlink pattern.)

### C3 — Feed corrupts the shared repo on the first network hiccup → cross-friend rebase lockup
- **Where:** `feed/bootstrap.py` `_write_bootstrap_files()` never writes a `.gitignore`; `feed/io_github.py:210` commits via `git add -A`. `feed/config.py` *claims* `.queue.log` is "gitignored" — false.
- **Bug:** `.queue.log` and per-clone `.state.json` get staged by `git add -A` and pushed to the **shared** bare repo. Each friend's `.state.json` differs (own push stats) → the next cross-friend `git pull --rebase --autostash` hits an unresolvable JSON merge conflict → clone stuck in `REBASE_HEAD` → all future feed writes silently queue → recovery needs a manual `git rebase --abort` that is documented nowhere.
- **Verified:** `grep -n gitignore feed/bootstrap.py` → no match; only `feed/config.py` mentions gitignore (the false claim).
- **Impact:** Triggered by any one friend's routine transient network failure. Data-corruption / lockup of the only cross-friend channel. No test catches it (`test_scenario_3` asserts entry count, not absence of `.state.json` from the bare repo).
- **Fix:** Write a `.gitignore` (`.queue.log`, `.state.json`, `.queue.log.lock`, `*.pyc`) in `_write_bootstrap_files()` (~5 lines). Add a test asserting those files are absent from the bare repo after a failure→recovery cycle.

### C4 — No documented path to a working, correctly-scoped `sf-marketplace` repo
- **Where:** `docs/SHIP_CHECKLIST.md` (§5, §7), `docs/RELEASING.md`, `.github/workflows/promote-rc-draft.yml.template:84`
- **Three compounding gaps:**
  1. **Not a git repo.** SHIP_CHECKLIST §7 opens with `git status` → `fatal: not a git repository`. No doc says to `git init` or clarifies that shipping operates on the *separate* `sf-marketplace` repo.
  2. **Population undefined.** §5 verifies `sf-marketplace` exists + has collaborators but never says how to get the plugin content *into* it.
  3. **Symlinks dangle on copy.** `hooks`/`skills` (and the C2 `feed`) symlinks point `../../`. Copying only `plugins/` (the promote template uses `rsync -av`, no `-L`) ships dangling symlinks → broken install. Pushing the *whole* dev repo resolves the symlinks but leaks the maintainer-only `wiki/`, `raw/`, `REVIEW.md` to friends — **violates ADR-019**.
- **Also blocking ship (verified):** `README.md` missing at root (SHIP_CHECKLIST §2 gate + friend entry point); `PLACEHOLDER-ORG` still in `plugins/startup-framework/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, and `CHANGELOG.md`.
- **Fix:** Pick a packaging strategy and document it end-to-end. Recommended: a publish step that `cp -rL`'s only the shippable subset (`plugins/` content dereferenced + `README.md` + `CHANGELOG.md` + `LICENSES.md`) into `sf-marketplace`, excluding `wiki/`/`raw/`/`REVIEW*.md`/`docs/SHIP_CHECKLIST.md`. Add `git init`/remote/commit steps, a `grep -rn PLACEHOLDER-ORG` gate, a "no dangling symlinks" assertion, and write the `README.md`. (Alternative: restructure so `plugins/startup-framework/` holds real files, with a build step syncing from root.)

---

## 🟠 HIGH

- **H1 — `/sf:doctor` falsely reports the hook broken on first run.** `skills/sf-doctor/scripts/check-plugins.sh` (and `references/hook-id-registry.md`) grep for `sf-wake-up.js`; the hook is `sf-wake-up.py` (hooks.json's own `$comment` even claims doctor greps `.py`). Every friend's first `/sf:doctor` warns the hook is misconfigured and points to a nonexistent `.js` file. **Verified.** Fix: detect `sf-wake-up\.py` (or `sf-wake-up\.(js|py)`); fix the success/warn messages and the registry doc.
- **H2 — Git locale not forced to `C` → conflict misdetection on non-English systems (hits Hazar directly).** `feed/io_github.py` `_try_push`/`_try_rebase` match English git substrings ("rejected"…) without `LANG=C`/`LC_ALL=C`. On a Turkish-locale machine git messages are localized → `_looks_like_non_fast_forward` returns False → pushes queue instead of rebase-retry → concurrent-write guarantee degrades to eventually-consistent. Compounds C3. Fix: `env={**os.environ, "LANG": "C", "LC_ALL": "C"}` on those subprocess calls.
- **H3 — `README.md` missing** (see C4). Required by SHIP_CHECKLIST §2; first thing friends see.
- **H4 — `PLACEHOLDER-ORG` unreplaced** in `plugin.json`, `marketplace.json`, `CHANGELOG.md` (see C4). **Verified.** Add a pre-tag `grep -rn PLACEHOLDER-ORG` gate.

---

## 🟡 MEDIUM

- **M1 — `~/Dev/` hardcoded for project detection.** `hooks/wake-up/lib/__init__.py:99` `dev_root = Path.home() / "Dev"`. Friends who keep projects in `~/code/`, `~/work/`, etc. get no project-specific context (silent degradation). Not exposed via userConfig. Fix: add a `devRoot` userConfig field + read `CLAUDE_PLUGIN_OPTION_DEVROOT`, or document the assumption prominently. (Same "Hazar's personal convention baked in" root cause as C1/C2.)
- **M2 — Handle not validated in the Python layer.** `feed/writer.py:478` builds `local_path() / f"{handle}.log.md"`; `feed/config.handle()` does no format check. A hand-edited `identity.md` handle with `../` escapes the feed dir (path traversal). The interview validates `^[a-z][a-z0-9-]*$` at input, but nothing enforces it at use. Fix: assert the pattern in `config.handle()` (mirror `sf-note`'s session_id sanitizer).
- **M3 — Pinning gap:** `sf-backup`, `sf-note`, `sf-recall` ship real `eval.json` files but are missing from `CANONICAL_EVAL_FIXTURES` in `skills/sf-improve-skill/lib/tests/test_preflight.py`. Evals are conformant, but the pinning guarantee weakens. Fix: add the 3 paths.
- **M4 — SHIP_CHECKLIST §1.1 has wrong test paths** (`docs/SHIP_CHECKLIST.md:14-24`). `sf-wrap`/`sf-improve-skill` tests live in `lib/tests/` not `tests/`; `sf-bootstrap-project`/`sf-interview` have only eval fixtures (no pytest dir → exit 4); `wiki-skeleton` is a standalone lint, not pytest. Following the checklist literally yields misleading errors or silently-zero test runs. Fix: correct the commands.
- **M5 — No `git rebase --abort` recovery.** `feed/io_github.py` `_try_rebase`: a previously-stalled rebase ("rebase in progress…") isn't detected by `_looks_like_non_fast_forward`, so the clone stays permanently stuck. Fix: detect in-progress rebase and `--abort` before retry.
- **M6 — `catch-up.sh` documented but not shipped.** `skills/activity-feed/SKILL.md:20` lists `scripts/catch-up.sh` (only `status.sh` exists). `/sf:catch-up` works via `render.py`, so it's a dead reference, but anything shelling out per the SKILL.md description fails. Fix: remove the reference or ship the stub.
- **M7 — CI silently skips `claude plugin validate`.** `.github/workflows/validate.yml:89` skips validation when the `claude` CLI is absent (it is, on ubuntu-latest runners), printing a SKIP. SHIP_CHECKLIST §3 ("validate.yml green") therefore gives false confidence; validation only really happens locally (§1.3). Fix: install the CLI in CI or downgrade §3's claim.
- **M8 — `CHANGELOG.md` v1.0.0 dated 2026-05-28** (already past; ship hasn't happened). Fix: stamp the real tag date at ship.
- **M9 — Injection pattern in `promote-rc-draft.yml.template:103`** — direct `${{ steps.parse.outputs.rc-tag }}` in a `run:` block instead of via `env:` (the same file does it correctly at line 109). Bounded by the tag glob; template is inactive until first RC. Fix: route through `$RC_TAG`.
- **M10 — `docs/ACTIVITY_FEED.md` omits the `~/Dev/` assumption** (see M1).

---

## 🟢 LOW

- **L1 —** `skills/sf-improve-skill/SKILL.md:110` says `test_cases[]`; code (correctly) uses `tests[]`. Doc drift.
- **L2 —** `skills/sf-improve-skill/eval/` is empty → the Karpathy loop can't self-improve (philosophical gap, not a runtime bug for other skills).
- **L3 —** Chronological invariant enforced only at read time (`reader.py` sorts), not at write time. Matches the "same-day reordering OK" intent; benign.
- **L4 —** `feed/format.py` `MAX_BODY_CHARS=300` checks the full assembled body, not `task_brief` alone → confusing "too-long" messages.
- **L5 —** `wiki/index.md:83` link to `plugin-validate-baseline.txt` has wrong description path (`skills/sf-distribution/…` doesn't exist; actual is `tests/integration/`) and points at a directory.
- **L6 —** `wiki/index.md:64` says ADR-026 has "6 disaster scenarios"; `index.md:90` and `RECOVERY.md` say 8. Update line 64.
- **L7 —** `feed/writer.py:401` puts the unsanitized handle into the git commit message (no shell injection — list-form args — but malformed messages possible). Folds into the M2 fix.
- **L8 —** No `.gitignore` at repo root → pushing the whole dev repo to `sf-marketplace` would expose `wiki/`, `raw/`, `REVIEW*.md`, maintainer docs (ADR-019 violation). Folds into C4's packaging decision.

---

## 🧠 Root-cause pattern → candidate ADR-030

C1, C2, and M1 share **one root cause**: the 659 passing tests inject `SF_WIKI_ROOT`, use `FeedFake`, and run from the dev tree — so the **actual installed-plugin runtime was never exercised**: `$CLAUDE_PLUGIN_ROOT` (symlinks dereferenced, `feed/` possibly absent), no `SF_WIKI_ROOT`, a friend's own home/dir layout. This is precisely the failure mode **ADR-029 ("test against real contract instances")** targets — but it bit the wake-up hook anyway, because here the real "contract instance" is *the installed plugin environment*, which no test reproduces.

**Proposed ADR-030 (ratify when fixing):** ship an **installed-runtime integration test** that materializes a fake `$CLAUDE_PLUGIN_ROOT` (dereferenced symlinks, no env vars set, configurable home/dev-root), runs `sf-wake-up.py`, and asserts both wiki-context *and* feed load. That single test would have caught C1 + C2 together.

---

## ✅ Confirmed solid (do not re-litigate)

- **ADR-028 split-writer feed API** — `feed/__init__.py` exports `feed_write_session_start/_session_end/_release`; `_write_entry_dispatch` is private; no polymorphic public entrypoint. Conformant.
- **ADR-011 eval.json schema regression — fully fixed.** `lib/preflight.py` enforces `tests[].binary_assertions: list[str]`, explicitly rejects the old `binary: true` object form, zero residue across all 7 shipped eval files, pinned by `TestCanonicalEvalFixtureConformance`.
- **`--max-turns` correctly absent** from the improve-skill preflight (CC 2.1.154); guarded by `test_max_turns_NOT_required`. `cc-flag-watch.md` documents the watch.
- **ADR-008 cache-preservation mechanism** sound (`additionalContext`, no system-prompt mutation). Note: the 47062→47062 evidence is from the ECC hook, not our payload (framing caveat, not a bug).
- **659 tests green, 0 fail.** Append-only + terse-format invariants enforced at runtime. No `shell=True`/`eval`/`exec`/`pickle`/`yaml.load`. No hardcoded secrets. `--show-token` removed (REVIEW.md F1 confirmed fixed).

---

## 📋 Prioritized fix plan (for the next session / Codex)

1. **C1** — three-way wiki-root fallback in `sf-wake-up.py:213` + unset-env test.
2. **C2** — add `feed -> ../../feed` symlink + assert import resolves under a simulated `$CLAUDE_PLUGIN_ROOT`.
3. **C3** — write `.gitignore` in `feed/bootstrap.py` + test asserting `.state.json`/`.queue.log` absent from the bare repo.
4. **C4** — decide packaging strategy; rewrite SHIP_CHECKLIST + RELEASING end-to-end (git init, population, `cp -rL` dereference, PLACEHOLDER-ORG gate, no-dangling-symlink check); write `README.md`.
5. **H1** doctor `.py`; **H2** `LANG=C`; **H4** replace PLACEHOLDER-ORG (folds into C4).
6. **ADR-030** — author + ship the installed-runtime integration test (would have caught C1+C2).
7. MEDIUM (M1 devRoot config, M2 handle validation, M3–M10) then LOW.

---

## 🔗 Reviewer agents (resumable for deep-dives)

| Slice | Agent ID | Per-slice verdict |
|-------|----------|-------------------|
| Install & plugin integrity | `ae199bcb653fcf96d` | SHIP-WITH-FIXES (flagged the missing `feed/` symlink = C2) |
| Daily-loop engine (hook + lifecycle skills) | `a2721cb48b08ce347` | SHIP-WITH-FIXES (found C1 wiki-root + H1 doctor) |
| Activity Feed + concurrency | `ad4d5395d3eff8a49` | NO-SHIP (found C3 `.gitignore` + H2 locale) |
| Ship-readiness + docs + security + wiki | `ad61c9ddcd10d7a36` | NO-SHIP (found C4 ship-path + git-init + symlink/copy) |

**Related ADRs:** 008 (wake-up hook), 011 (eval schema), 018 (feed repo design), 019 (maintainer-only wiki), 027 (schema versioning), 028 (locked build contracts), 029 (test against real contract instances).
