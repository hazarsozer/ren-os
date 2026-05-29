---
title: "ADR-030: Test the Installed-Plugin Runtime — The Real Contract Instance Prior Tests Never Reproduced"
status: accepted
date: 2026-05-29
sunset-review: 2027-05-29
references-pages: []
affects-components: [testing, hooks, feed, distribution, install]
relates-to: [008-wake-up-hook, 015-onboarding, 019-framework-distribution, 028-locked-build-time-contracts, 029-test-against-real-contract-instances]
---

# ADR-030: Test the Installed-Plugin Runtime — The Real Contract Instance Prior Tests Never Reproduced

## Context

The V1.0 pre-ship review (`REVIEW-v1.0-preship.md`, 2026-05-29) returned **NO-SHIP** with four CRITICAL blockers. Two of them — **C1** (wake-up hook reads the wrong wiki path in production) and **C2** (the Activity Feed is dead on every install because `feed/` is unreachable from the packaged plugin) — shared a single root cause with the MEDIUM finding M1 (`~/Dev/` hardcoded):

> The 659 passing tests inject `SF_WIKI_ROOT`, use `FeedFake`, and run from the dev tree — so the **actual installed-plugin runtime was never exercised**: `$CLAUDE_PLUGIN_ROOT` (symlinks dereferenced, `feed/` possibly absent), no `SF_WIKI_ROOT`, a friend's own `$HOME`/dir layout.

Each bug was independently severe and each was invisible to a fully green suite:

- **C1** — `wiki_root = Path(os.environ.get("SF_WIKI_ROOT", "")) or (Path.home() / ".startup-framework" / "wiki")`. `Path("")` is `PosixPath('.')`, which is **truthy**, so the home-dir fallback never fires. In production (`SF_WIKI_ROOT` unset) `wiki_root` silently became the session CWD; the wiki was skipped; the hook injected only a 46-char header. The suite masked this with `env.setdefault("SF_WIKI_ROOT", ...)` in its subprocess helper — i.e. the test harness set the very variable whose absence was the bug.
- **C2** — `sf-wake-up.py` does `from feed import …`, but the hook only adds its own script dir (`hooks/wake-up/`) to `sys.path`; it never adds `$CLAUDE_PLUGIN_ROOT`. On an installed plugin invoked as `python3 "$CLAUDE_PLUGIN_ROOT/hooks/wake-up/sf-wake-up.py"` (with CWD = the session's project dir and no `PYTHONPATH`), `feed` is unreachable → `ImportError` → the hook's `except ImportError: return ""` guard silently degrades to no-feed. The suite masked this because pytest puts the dev-repo root on `sys.path`, so `from feed import` always resolved from the dev tree.

This is precisely the failure mode **ADR-029 ("test against real contract instances")** targets — but ADR-029's three layers (signature-drift tests, cross-team review, invariant assertions) did not catch it, because here the real "contract instance" is **the installed plugin environment itself**, and no test reproduced it. Signature-drift tests confirm a symbol's *shape*; they import the symbol from the dev tree and therefore cannot observe that the symbol is *unreachable* in the packaged layout. Unit and behavior tests that inject env vars and inject fakes cannot observe what happens when those env vars are unset and the real module must be discovered on `sys.path`.

The pattern is therefore a genuine extension of ADR-029, not a duplicate: ADR-029 says *validate against the canonical contract source*; ADR-030 says *one of those contract instances is the deployment environment, and it must be materialized and exercised end-to-end, not simulated away*.

## Decision

Ship an **installed-runtime integration test** that materializes a fake `$CLAUDE_PLUGIN_ROOT`, runs the wake-up hook the way Claude Code runs it — **as a subprocess, with a clean environment** — and asserts the framework's two load-bearing features come alive: wiki-context injection (C1) and the Activity Feed (C2). Lives at `tests/integration/installed_runtime/` (maintainer-only; `tests/` is not in the shipped set per the ADR-019 / Crucible ship boundary).

### Core principle: reproduce the deployment, do not simulate it

The test's value comes entirely from what it **refuses to do** that the masking suite did:

1. **No `SF_WIKI_ROOT`, no `CLAUDE_PLUGIN_OPTION_WIKIROOT`.** The headline case leaves both unset so the home-default tier (the one C1 broke) is the path under test.
2. **No `PYTHONPATH` to the dev tree.** The subprocess environment is built from scratch (`PATH`, `HOME`, `CLAUDE_PLUGIN_ROOT`, `LANG=C`, `LC_ALL=C`) so `from feed import` can only succeed via the hook's own plugin-root discovery — never via a pytest-injected `sys.path`.
3. **Real files in the packaged shape.** A fake plugin root is materialized by copying real files (symlinks dereferenced) into the post-Crucible layout: `.claude-plugin/plugin.json`, `hooks/wake-up/{sf-wake-up.py,lib/}`, `hooks/hooks.json`, `feed/` (the whole package), and `skills/` as a real (empty) dir for shape parity.
4. **A configurable fake `$HOME`.** The friend's wiki + Activity-Feed clone live under `<fake_home>/.startup-framework/`, so `Path.home()`-derived resolution is exercised against a real, controlled layout (`Path.home()` honors the `HOME` override on POSIX).
5. **Subprocess invocation, exit-0 invariant.** The hook is run with `subprocess.run([python, sf_wake_up], input=<SessionStart JSON>, env=<scrubbed>, cwd=<neutral dir with no wiki>)`, and stdout is parsed as the `hookSpecificOutput.additionalContext` envelope. Every case asserts `returncode == 0` (the ADR-008 never-abort invariant).

### The import/path contract (locked with the hook owner)

C2's real fix lives in the hook, not only in the packaging: before any `from feed import`, the hook inserts the plugin root at `sys.path[0]`, resolving it as `$CLAUDE_PLUGIN_ROOT` (`.strip()` + expand) if set, else `Path(__file__).resolve().parents[2]`. Post-restructure those two agree (`hooks/wake-up/sf-wake-up.py` → `parents[2]` == plugin root). The same dual-resolution is applied to `skills/activity-feed/scripts/status.sh`. The **restructure/symlink fix alone is necessary but not sufficient** — the hook must put the plugin root on `sys.path`. The test exercises the same mechanism CC uses (it sets `$CLAUDE_PLUGIN_ROOT`) and additionally proves the `parents[2]` self-locate fallback.

### Assertions (one invocation proves both bugs)

- **C1 (wiki loads from the home default):** `additionalContext` is non-empty and contains the `"Master wiki index"` section header plus a unique sentinel string seeded into `<fake_home>/.startup-framework/wiki/index.md`. Pre-fix → `wiki_root` is `.` → no index section → fails.
- **C2 (feed imports and loads):** `additionalContext` contains feed's **real rendered output** — the `"Activity Feed — recent friend activity"` header (emitted by `feed.reader._format_header`, present in both fresh and stale forms) and a seeded friend handle (`"friend-b"`). That block is emitted *only if* `from feed import` resolved; the `ImportError` branch produces nothing. Per ADR-029, the assertion rides feed's real output, not a test-only sentinel. Pre-fix → `ImportError` → no block → fails.

The C2 fixture is just loose `<fake_home>/.startup-framework/activity-feed/<handle>.log.md` files plus a valid `identity.md` (`handle:`, `schema_version: 1`); `feed_read_friends_tails(refresh=False)` does zero git (`glob` + parse only), so no `git init` is required. The hook's best-effort `pull()` / `write_session_start()` fast-fail on a non-git dir under `LANG=C` without interfering.

### Permanent negative controls ("teeth")

Two controls make the "would have caught C1+C2" claim a durable CI guarantee rather than a one-time manual check:

- **No-feed control:** materialize the plugin root **without** `feed/` → assert the friends block is **absent**, the hook log contains the graceful-degrade signal `"feed module unavailable; skipping feed integration"`, **and** `returncode == 0`. This proves the hook degrades gracefully (not swallowing a *different* error) and guards against `feed/` ever going missing from the package again.
- **No-wiki control:** point the fake home at a layout with no wiki → assert no `"Master wiki index"` section and `returncode == 0`. Proves the C1 assertion discriminates.

### Coverage variants

- **Headline** (`CLAUDE_PLUGIN_ROOT` set; both wiki-root env vars unset): asserts C1 + C2 in a single subprocess. This is the case ADR-030 ratifies.
- **Fallback variant** (`CLAUDE_PLUGIN_ROOT` unset): proves the `parents[2]` self-locate path resolves `feed`.
- **Tier-2 variant** (`CLAUDE_PLUGIN_OPTION_WIKIROOT` set, `SF_WIKI_ROOT` unset): proves the middle wiki-root fallback tier — the userConfig var the buggy Python layer ignored entirely.

## Verification

Completed 2026-05-29 against the post-fix tree (C1 `df86388`, Crucible restructure `5bf9186`, C2 import fix `8acb1b5`). Test invocation: `python3 -m pytest tests/integration/installed_runtime/ -q`.

- [x] **Headline test PASSES on post-fix code** — `test_installed_runtime_wiki_and_feed_both_live` asserts C1 (wiki sentinel + `Master wiki index`) and C2 (`recent friend activity` + `friend-b`) in one subprocess invocation. 5/5 tests pass in 0.21s.
- [x] **Headline test FAILS on pre-fix code** — proved by materializing a plugin root with the **baseline buggy hook** (`git show baseline-v1.0-full-wiki:hooks/wake-up/sf-wake-up.py`) + the current `lib`/`feed`, then running the exact same scrubbed-env subprocess. Result: `rc=0`, `additionalContext` is **46 chars** — `"## Framework wake-up context (source=startup)\n"`, the precise symptom REVIEW §C1 documented — with the wiki sentinel ABSENT (C1 assertion fails) and the feed block ABSENT with `"feed module unavailable; skipping feed integration"` logged (C2 assertion fails). Both assertions bite on pre-fix code. (One-off proof; the permanent guarantee is the two negative controls below.)
- [x] **Both negative controls PASS** — `test_no_feed_degrades_gracefully` (plugin root without `feed/` → no feed block + the graceful-degrade log line + `rc==0`, wiki still loads) and `test_no_wiki_yields_no_context` (no wiki/identity → empty context + `rc==0`). These prove the headline assertions discriminate and guard the C1/C2 conditions in CI permanently.
- [x] **Fallback + tier-2 variants PASS** — `test_feed_resolves_without_plugin_root_env` (`CLAUDE_PLUGIN_ROOT` unset → `parents[2]` self-locate resolves feed) and `test_wiki_resolves_via_plugin_option_wikiroot` (middle wiki-root tier honored).
- [x] **Adjacent + full suites green** — `tests/` tree 11 passed / 1 xfailed; `skills/sf-install` 50 passed; `feed` 181 passed / 1 skipped; `hooks/wake-up/lib/tests` 50 passed (incl. `TestWikiRootResolution` C1 unit pins). `claude plugin validate ./ --strict` → validation passed. My additions are new files only (no edits to existing code); the bare-root `pytest` collision (duplicate `lib.tests` package names across skills) is pre-existing and unrelated — suites run per-directory per `docs/SHIP_CHECKLIST.md` §1.1.

## Consequences

**Easier:**
- The single most important feature (wiki injection) and the headline feature (Activity Feed) now have an end-to-end guard against the entire class of "works in dev, dead on install" regressions.
- Future packaging changes (symlink → real dir, path moves, env-var renames) are caught by a test that runs the real artifact in the real shape.
- The "installed runtime is a contract instance" lesson is wiki-indexed doctrine, not tribal knowledge.

**Harder:**
- The test is heavier than a unit test (materialize a tree, spawn a subprocess). Kept to a small number of cases; the fake plugin root is session-scoped, the fake home per-test.
- Contributors touching the hook's import/path logic or the feed read path must keep this test's fixture faithful to the deployed layout.

**Now impossible:**
- Shipping a build where the wake-up hook silently resolves the wrong wiki path when `SF_WIKI_ROOT` is unset.
- Shipping a build where `feed/` is unreachable from the packaged plugin (missing dir, missing `sys.path` entry) without a red test.
- Treating "659 green + `inspect.signature` drift tests" as sufficient evidence that the installed plugin works.

**Sunset-review trigger conditions:**
- A future failure of the "works in dev, dead on install" class slips past this test → reframe (the materialized environment diverged from the real one).
- CC ships an official plugin-runtime test harness that materializes `$CLAUDE_PLUGIN_ROOT` for us → adopt it and retire the hand-rolled fixture.
- The hook stops importing `feed` / stops reading the wiki (architecture change) → the specific assertions become moot; revisit scope.

## Alternatives considered

### A) Rely on ADR-029's existing three layers (drift tests + review + invariant tests)

**Why rejected:** all three operated, all three were green, and C1 + C2 still shipped to the NO-SHIP gate. The layers import symbols from the dev tree and inject env/fakes; by construction they cannot observe unreachability or unset-env behavior. The deployment environment is a contract instance none of them reproduces.

### B) Just remove the env-masking (`env.setdefault("SF_WIKI_ROOT", …)`) from the existing subprocess test

**Why rejected:** necessary but insufficient. It would expose C1 but not C2 (the existing test still runs from the dev tree with the repo root on `sys.path`, so `from feed import` keeps resolving). Only a materialized `$CLAUDE_PLUGIN_ROOT` with a scrubbed `PYTHONPATH` exercises the feed-import path. We do both: this ADR's test materializes the tree, and the existing entry-point unit tests keep their fast in-process pins.

### C) Assert C2 via a test-only sentinel string emitted by the feed block

**Why rejected:** that is production scaffolding for a test. Per ADR-029 the assertion should ride the real contract instance's real output (`feed.reader`'s actual header + a real friend handle). The hook's `"feed module unavailable"` log line is retained only as a *secondary diagnostic* (and as an explicit assertion in the no-feed control), never as the load-bearing pass/fail signal.

### D) Mock `subprocess` / call `main()` in-process

**Why rejected:** in-process invocation inherits pytest's `sys.path` (the exact crutch that hid C2) and the parent process's env (the crutch that hid C1). The whole point is to run the artifact as CC runs it — a real subprocess with a clean environment.

## References

- `REVIEW-v1.0-preship.md` — the NO-SHIP review; § "Root-cause pattern → candidate ADR-030" is this ADR's origin; C1/C2/M1 findings with file:line + evidence.
- `wiki/decisions/029-test-against-real-contract-instances.md` — parent doctrine; ADR-030 extends it to the deployment environment as a contract instance.
- `wiki/decisions/008-wake-up-hook.md` — the hook this test exercises; the never-abort / graceful-degrade invariants asserted here.
- `wiki/decisions/019-framework-distribution.md` + the Crucible one-repo restructure — define the packaged layout the fake plugin root mirrors and the ship boundary (`tests/` is maintainer-only).
- `wiki/decisions/028-locked-build-time-contracts.md` — framework root path `~/.startup-framework/` + split feed-write API the fixture relies on.
- `tests/integration/installed_runtime/` — the test + fixtures this ADR ratifies: `conftest.py` (the materialize-plugin-root / seed-home / scrubbed-env subprocess factories) + `test_installed_runtime.py` (headline C1+C2 gate, two negative-control teeth, two resolution variants).
- `hooks/wake-up/lib/tests/test_entry.py` — the in-process / env-masking entry-point tests this ADR complements (`TestWikiRootResolution` unit-pins `_resolve_wiki_root`; ADR-030 is the end-to-end installed-subprocess layer).
- `skills/sf-install/tests/integration/test_daily_loop_e2e.py` — the FeedFake daily-loop harness; the `_populate_feed_fixture` pattern reused for the C2 fixture.
