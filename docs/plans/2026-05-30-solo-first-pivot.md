# Solo-First Pivot + Nate AIOS Adoption — startup-framework v1.0

> **Status:** Approved 2026-05-30. Implementation not yet started.
> **Branch:** `fix/v1.0-preship-blockers` @ `28b47b3` (tree clean).
> **Safety net:** baseline tag `baseline-v1.0-full-wiki` preserves the full pre-pivot tree (including the complete Activity Feed implementation). The multi-user layer is *removed from the shipped framework*, not lost — it lives in git history + that tag.

This is the durable, self-contained spec for the v1.0 effort. It is the shared reference for the implementation team. File/line references reflect the state at `28b47b3` and may drift during execution — the builder grounds every change in the actual source.

---

## 1. Context — why this change

The startup-framework was built as a multi-user "friend group" Claude Code plugin. It failed a pre-ship review, was fixed to SHIP-READY, then an independent **Codex review** surfaced 7 findings (F1–F7, see `wiki/codex-review.md`). Separately, we ingested **Nate Herk's "AI Operating System"** talk (`wiki/research/nate-herk-ai-os.md`) and found it independently validates the framework's core bet — and offers framings plus a few capabilities we lack.

Two decisions came out of the brainstorm:

1. **Pivot to a solo-first base framework.** The builder is solo; the multi-user Activity Feed is speculative complexity (YAGNI). Removing it is the biggest available complexity cut — and it *moots* the Codex findings that were all feed-related (F3, F4, F6) and shrinks F1. Multi-user becomes a **deferred** layer, preserved in git + the baseline tag, **not rebuilt now**.
2. **Adopt Nate's value, not his complexity.** Reorganize under his **Four C's** (Context → Connections → Capabilities → Cadence); take the framings for free (they're better *words* for fixes we're already making); close the genuine gaps (`/sf:insights`, a permission audit, a working deterministic cadence).

**Net effect:** the ship gate drops from **7 findings to 4** (F1′, F2, F5, F7 — all local, deterministic, low-risk) **while** the framework gains legibility (Four C's), a session-insights skill, a permission audit, and a self-improvement loop whose default path actually works.

**Governing principle:** *add value, not complexity.* The feed removal is the one large structural change; everything else is surgical.

### Codex findings → fate under solo-first

| Finding | Summary | Fate |
|---|---|---|
| **F1** (High) | `wikiRoot`/`activityFeedLocalClone` plugin options advertised but ignored (`feed/config.py` resolves only `SF_FRAMEWORK_ROOT`) | **Shrinks** to wiki-path-only; **becomes** the config-extraction refactor (Commit 1) |
| **F2** (High) | `classify()` + `run_evals()` raise `NotImplementedError` on the default path | **Fix**: deterministic default classifier (4a) + honest fail-fast for sf-improve (9) |
| **F3** (High) | `/sf:wrap` reports wiki files as project "files touched" in the feed | **Mooted** by feed removal |
| **F4** (Med) | Handle validation incomplete across feed APIs (path-traversal trap) | **Mooted** by feed removal (no handles) |
| **F5** (Med) | `publish.sh` copies ignored artifacts into the orphan snapshot | **Fix**: `git ls-files` snapshot + guard (Commit 2) |
| **F6** (Med) | Feed privacy docs contradict implementation + ADRs | **Mooted** by feed removal |
| **F7** (Low) | Unquoted `attribution:` breaks YAML lint | **Fix**: quote it (Commit 5) |

---

## 2. Locked decisions

- **Solo-first.** Remove the Activity Feed / multi-user layer entirely. No speculative replacement plugin.
- **F2 → deterministic default classifier** for `/sf:wrap` so the default path works for real; the LLM/autonomous variants stay **experimental** (bike-method). `/sf:improve-skill`'s default = **honest fail-fast** ("requires configured backend"), not a half-real runner.
- **Cadence = "working + improved, not extreme."** Deterministic on-demand loop; autonomous scheduling deferred.
- **`/sf:insights` = full** read-only skill (mine local Claude Code session history).
- **Permission audit = in** (read-only "audit your keys"). **"Other worlds" = out** (the hierarchical wiki already does cross-project discovery — ADR-004/017). **Reverse-engineer coach = deferred** (overlaps Skill Creator).
- Time is not a constraint → build to "v1.2 quality."

## 3. The Four C's reframe (organizing spine)

| Layer | Disposition | In scope |
|---|---|---|
| **Context** | Ahead — keep & polish | Wiki + cache-preserving wake-up injection (keep); *default-shift* framing; **F7** lint fix |
| **Connections** | Was weakest; feed removed → rebuild | Drop feed; **F1′** centralize wiki-path resolution; **permission audit** (`keys ≠ instructions`) |
| **Capabilities** | Ahead on rigor — keep | `/sf:*` skills + eval hygiene |
| **Cadence** | Weak layer — strengthen | **F2** deterministic classifier + honest `sf-improve` default (*bike-method*); **`/sf:insights`** |

---

## 4. Team execution topology — spine, then parallel tail

The work is **not** four parallel lanes. Solo-first made it a **sequential refactor spine** (the feed removal touches overlapping files across every early commit) plus a **small independent tail**.

```
SPINE (sequential — one builder, verification gate between each)
  Commit 1  extract lib/sf_paths (F1) + shim
     │
  Commit 2  delete feed module; rewire consumers; publish F5
     │
  Commit 3  delete feed skills; de-feed doctor/install/interview; C1-only runtime test
     │
  Commit 4  sf-wrap: remove feed write (F3 mooted) + deterministic classifier (F2a)
     │
  Commit 5  ADR-031 + wiki index/log + maintainer docs (+ F7)
     │
     ├──────────── TAIL (parallel — 3 independent agents, disjoint dirs) ────────────┐
     │   Commit 7  permission audit  (skills/sf-doctor/scripts/check-permissions.sh)  │
     │   Commit 8  /sf:insights       (new skills/sf-insights/**)                     │
     │   Commit 9  sf-improve honest default (skills/sf-improve-skill/lib/**)         │
     └───────────────────────────────────────────────────────────────────────────────┘
     │
  Commit 6  framings / README Four C's  (LAST — references /sf:insights + --permissions,
            so it lands after the tail features exist)
```

- **Spine (1→5)** is a hard dependency chain (can't delete `feed/config.py` before its core is extracted; can't rewrite install tests before feed skills are gone). One builder, sequential, green gate between commits.
- **Tail (7/8/9)** touches disjoint directories → 3 parallel agents (worktrees optional). Only shared touch points are `wiki/index.md` and `README` command tables — resolved in the final docs pass.
- **Commit 6 (framings)** runs **after** the tail because the README/commands reference `/sf:insights` and `/sf:doctor --permissions`.

---

## 5. KEY ENGINEERING FACT: `feed/config.py` is load-bearing beyond the feed

**Verified against source.** `feed/config.py` owns **both** feed-specific helpers **and** the framework-root / wiki-path / handle / schema resolution the *whole* framework uses. Non-feed consumers of `feed.config`:
- `skills/sf-wrap/lib/feed_call.py` → `config.handle`
- `skills/sf-recall/lib/__init__.py` → `config.handle`, `HandleNotConfiguredError`, `SchemaVersionMismatchError`
- `hooks/wake-up/sf-wake-up.py` → `config.handle` + exceptions (via the feed callback)
- `tests/integration/installed_runtime/conftest.py` → references `config.handle()`
- `skills/wiki-migration/scripts/framework-version.sh` → parity with `config.framework_version()`

So we **cannot `git rm feed/` wholesale**. The sequencing is **extract-then-delete**.

**CORE → extract to new `lib/sf_paths.py`:** `FRAMEWORK_ROOT_ENV`, `DEFAULT_FRAMEWORK_ROOT`, `framework_root()`, `wiki_path()`, `framework_version()`/`FRAMEWORK_VERSION`/`FALLBACK_FRAMEWORK_VERSION`, `EXPECTED_IDENTITY_SCHEMA_VERSION`, `HANDLE_RE`, `validate_handle()`, `handle()`, `HandleNotConfiguredError`, `InvalidHandleError`, `SchemaVersionMismatchError`, the `_parse_*_frontmatter` helpers.

**FEED-ONLY → delete with feed:** `local_path()`, `state_dir()`, `queue_log_path()`, `state_json_path()`, `FEED_LOCAL_ONLY_FILES`, `EXPECTED_FEED_SCHEMA_VERSION`.

**This extraction *is* the F1 fix.** New `wiki_path()` resolves `SF_WIKI_ROOT` → `CLAUDE_PLUGIN_OPTION_WIKIROOT` → `framework_root()/wiki` (strip + expandvars + expanduser per tier), unifying the hook's already-correct `_resolve_wiki_root` with the Python `handle()` reader (which today silently reads the *default* wiki — the F1 latent split). `framework_root()` stays `SF_FRAMEWORK_ROOT → default`; `wiki_path()` is independent so `CLAUDE_PLUGIN_OPTION_WIKIROOT` alone works.

**Module location:** repo-root `lib/` (new top-level package with `__init__.py`). The plugin root is already on `sys.path` (the hook's `_ensure_plugin_root_on_path`, skills' `REPO_ROOT` inserts), so `from lib.sf_paths import ...` resolves like `from feed import ...` did, and it rides the publish allowlist where `feed/` did (swap the entry).

---

## 6. Execution — 9 scoped commits

Tests run **per-module** — root `pytest` collides on duplicate `lib.tests.*` (PRE-EXISTING; do **not** "fix"): `( cd <module> && python3 -m pytest tests/ )`. Validate with `claude plugin validate ./ --strict`. Never bypass commit hooks. Targeted `git rm` / `rm -f` only.

**Phase 0 — baseline (no commit).** Run the Final Gate (§8) as-is with feed present; record pass counts (the F7 lint fail is expected until Commit 5). This is the green reference for test-count drift (Risk 3).

### Commit 1 — Extract `lib/sf_paths.py` (F1) + wiki-root tier
*Purely additive — `feed/config.py` becomes a thin shim; nothing breaks.*
- **Create** `lib/__init__.py`; `lib/sf_paths.py` (CORE symbols moved verbatim + F1 3-tier `wiki_path()`); `lib/tests/test_sf_paths.py` (port handle-validation/schema/frontmatter tests from `feed/tests/test_handle_validation.py` + **add** F1 tier tests: WIKIROOT honored when `SF_WIKI_ROOT` unset; precedence; empty/whitespace = unset; `${HOME}`/`~` expansion).
- **Edit** `feed/config.py` → shim: `from lib.sf_paths import *` (core) + keep the feed-only symbols defined locally (they call the shimmed `framework_root()`). Feed code + feed tests stay green.
- **Verify:** `( cd lib && pytest )`, `( cd feed && pytest )`, `( cd hooks/wake-up && pytest )`, installed-runtime, `plugin validate`.
- **Commit:** `refactor(config): extract core path/handle resolution into lib/sf_paths (F1) + wiki-root tier`.

### Commit 2 — Delete feed module; rewire consumers; publish F5
- **Delete (`git rm`)** the entire `feed/` dir (core already extracted): `__init__.py`, `config.py`, `format.py`, `reader.py`, `writer.py`, `bootstrap.py`, `identity_sync.py`, `io_github.py`, `skip.py`, `README.md`, `feed/tests/**`.
- **Rewire** non-feed consumers off `feed.config`:
  - `skills/sf-recall/lib/__init__.py`: delete `fetch_feed_tail()`; drop `feed_lines`/`n_feed_entries` from `recall()` + `RecallResult` (`has_results` → `bool(wiki_hits)`); keep the wiki grep; fix `__all__`. Update `tests/test_recall.py` (drop feed-tail tests, keep grep tests).
  - `hooks/wake-up/sf-wake-up.py`: remove `_build_feed_callback`, `_render_friends_tail`, the `from feed import …`; stop passing `fetch_feed_tail` to `compose_wake_up_context`; keep `_ensure_plugin_root_on_path` (now for `lib.sf_paths`).
  - `hooks/wake-up/lib/__init__.py` (`compose_wake_up_context`): remove the `fetch_feed_tail` param, the "Friends activity" block, `FRIENDS_ACTIVITY_BUDGET`, `FetchFeedTail`; fix `__all__`. Update `lib/tests/test_compose.py` + `test_entry.py` (change the `parents[2]` sentinel from `feed/__init__.py` → `lib/sf_paths.py`; **keep** wiki-root/plugin-root resolution tests).
- **F5** `scripts/publish.sh`: allowlist `feed`→`lib`; remove `docs/ACTIVITY_FEED.md`. Replace the `cp -r --parents` loop with a `git ls-files`-driven copy filtered through the allowlist; add a dry-run guard failing on `__pycache__`, `.pytest_cache`, `*.pyc`, `wiki/`.
- **Manifests** `.claude-plugin/plugin.json`: drop "+ Activity Feed" from `description`; remove `userConfig.activityFeedUrl` + `userConfig.activityFeedLocalClone` (keep `wikiRoot`, `devRoot`, `snapshotRetain`, `rcChannel`). `.claude-plugin/marketplace.json`: de-feed descriptions.
- **Guard:** `grep -rn "from feed\|import feed" . --include=*.py | grep -v __pycache__` MUST be empty.
- **Commit:** `feat(solo-first): remove Activity Feed module; lib/sf_paths is path SoT; publish ships tracked files only (F5)`.

### Commit 3 — Delete feed skills; de-feed doctor/install/interview; C1-only runtime test
- **Delete (`git rm`)** `skills/sf-catch-up/`, `skills/sf-disable-feed/`, `skills/activity-feed/`.
- **sf-doctor:** strip the Activity Feed block from `check-plugins.sh` (keep version + hook checks); remove `feed-entry` handling from `check-schemas.sh`; update `test_check_plugins.sh`/`test_check_schemas.sh` (drop feed env/rows; **update the advertised counts from a green run, not blind** — Risk 3); de-feed `SKILL.md` + `reference.md`/`references/hook-id-registry.md`.
- **sf-install:** delete `references/stage-3-activity-feed.md`; retitle Stage 3 to conditional-plugins-only; remove `--remove-activity-feed`; drop feed from `contract.required_outputs`/`output_paths`/Stage-3 summary; Stage-4 identity writes only `wiki/identity.md` (no feed push/rename); strip feed mentions from the other stage refs (keep `gh` — Risk 2 — reword as "used by `/sf:doctor`'s update check"). Delete `tests/integration/fakes/feed_fake.py`; update `conftest.py`/`simulator.py`/`test_fresh_machine`/`test_daily_loop_e2e`; delete `test_joiner.py` + `joiner.yaml` (a no-feed joiner == a fresh install). Drop feed assertions from `eval/eval.json` + fixtures.
- **sf-interview:** keep the interview; remove the feed identity-push behavior; **keep** the `handle:` frontmatter field but reframe Q1 from "handle for the Activity Feed" → "preferred handle/short name"; delete `references/public-summary-format.md`; de-feed `output-format.md` + `eval`.
- **wake-up final polish:** unify `_resolve_wiki_root()` to delegate to `lib.sf_paths.wiki_path()`; de-feed the module docstring + `CC_API_NOTES.md` (keep the graceful-failure + resolution test guarantees).
- **Rewrite installed-runtime test** `tests/integration/installed_runtime/test_installed_runtime.py` (C1+C2 → **C1-only**): drop all C2/feed assertions + `FEED_ACTIVITY_MARKER`; keep + strengthen C1; **promote** `test_wiki_resolves_via_plugin_option_wikiroot` to the headline F1 test (set ONLY `CLAUDE_PLUGIN_OPTION_WIKIROOT`). `conftest.py`: remove `include_feed`/`with_feed_clone`/`friend-b` seeding; `make_plugin_root` materializes `lib/` not `feed/`.
- **Schema surfaces:** remove the `feed-entry` page-type from `skills/wiki-migration/schemas.json`; from `tests/integration/schema-conformance/conformance.py` + README; from `compute-migration-chain.sh`; and any feed cases in `tests/integration/migration-dogfood.sh`.
- **Commit:** `feat(solo-first): delete feed skills; de-feed doctor/install/interview; C1-only installed-runtime test`.

### Commit 4 — `sf-wrap`: remove feed write (F3 mooted) + deterministic classifier (F2a)
- **Feed-write removal:** delete `skills/sf-wrap/lib/feed_call.py` + `references/feed-call.md`; remove the `feed_write_fn` param, Step 6 feed write, and all `feed_write_*` fields from `WrapResult`/`WrapInputs` (`lib/__init__.py`, `lib/types.py`). Delete `lib/validate.py` (feed-shape guards) + `test_validate.py` + `test_feed_call.py`; drop feed-write assertions + `_FakeFeedOutcome` from `test_wrap_orchestrator.py`.
- **F2a deterministic classifier** — ground truth: `classify(transcript_text, *, project_name) -> ClassifierResult` (`classifier.py:286`, currently raises at `:315`); orchestrator catches → forces `("none",)`. The primitives `build_classifier_prompt` + `parse_classifier_output` **stay** (the future LLM path); `parse_classifier_output` enforces `labels==["none"] ⇒ candidate_artifacts empty`. `compose_diff_plan` consumes `labels` (primary label → log append) + `candidate_artifacts` (creates files only for `decision`/`pattern`).
  - Implement `classify()` as a **conservative deterministic heuristic**: valid `ClassifierResult`, biases hard to `none`, **never raises**. Signal source = combined transcript (session log + `/sf:note` pins joined under "## Pinned notes"). **Pins dominate** (lower threshold). Word-boundary, deliberate-phrase regex tables per label (`decision`/`lesson`/`stack_change`/`milestone`/`pattern`/`purpose_shift`; `purpose_shift` only on a strong exact phrase). `candidate_artifacts` only for fired `decision`/`pattern` (deterministic kebab title, ≤300-char summary, `target_file` per `signal-threshold.md`). Multi-label cap ~2. Honor `none ⇒ no artifacts`.
  - **Do NOT** add a file-change-count input — `apply_result.files_changed` is *wiki* files (the exact F3 confusion). Deferred.
  - Keep the orchestrator try/except as cheap dead-code safety. Mark **experimental** (bike-method, Commit 6).
- **Tests:** replace the "stub raises" test with deterministic-classify cases (routine → none+no artifacts; "we decided to use Postgres over Mongo" → decision+1 artifact; "gotcha: …" → lesson no artifact; pin escalation; multi-label cap; none⇒empty). **Add** an orchestrator end-to-end test using the **real** default classifier (closes F2's "default path ≠ tests"). Update `signal-threshold.md` + `SKILL.md` (remove "no-signal wrap still writes a feed entry"; describe the deterministic classifier + limits + EXPERIMENTAL).
- **Commit:** `feat(sf-wrap): remove feed write (F3 mooted); ship conservative deterministic classifier (F2, experimental)`.

### Commit 5 — ADR-031 + wiki index/log + docs (+ F7)
- **Create** `wiki/decisions/031-solo-first-pivot.md` (status accepted; `supersedes: [017, 018, 020, 021]`; `amends: 022 (drop feed identity sync), 015 (drop Stage-3 feed), 019 (4-repo→2-repo), 023 (feed no longer built-in), 028 (drop feed-write API + FEED_LOCAL_ONLY_FILES), 030 (installed-runtime C1-only)`). Decision + rationale cite Nate's Four C's + keys/bike framings; preservation via baseline tag + history; no schema migration (feed-entry page type retired, not migrated).
- **Banner** superseded ADRs 017/018/020/021 (`status: superseded`, `superseded-by: ADR-031`, top note); add `amended-by: ADR-031` notes to 022/015/019/023/028/030.
- **Wiki** `index.md`: drop `feed/`; add `lib/` + `sf-insights`; annotate superseded ADRs; fix the skills list. `log.md`: append `## [2026-05-30 HH:MM] decision | solo-first pivot …` (ADR-004 format, **append-only**).
- **Docs:** delete `docs/ACTIVITY_FEED.md`; de-feed `RECOVERY.md`/`RELEASING.md`/`RELEASE_v1.0.0.md`/`SHIP_CHECKLIST.md` (update publish-snapshot assertion to the F5 guard; assert `lib/` present, `feed/` absent). Delete maintainer `.claude/agents/sf-feed.md`; de-feed `sf-onboarding.md`/`sf-distribution.md`/`sf-lifecycle.md`.
- **F7:** quote the `attribution:` value in `wiki/research/py-harness-engineering.md:8` → `python3 scripts/lint-yaml-frontmatter.py .` exits 0.
- **Commit:** `docs(adr): ADR-031 solo-first pivot supersedes 017/018/020/021; de-feed wiki + docs (F7)`.

### Commit 7 — Permission audit (`/sf:doctor --permissions`) [tail]
Real on-disk sources (verified): `~/.claude.json` (`mcpServers` global + `projects.<path>.{mcpServers,allowedTools,…}`), `~/.claude/settings.json` (`permissions.{allow,deny,ask}`, `enabledPlugins` dict, `hooks`), `~/.claude/settings.local.json` (tolerate absent). Files are mode 0600 — **never echo `env`/secret values**.
- **Create** `skills/sf-doctor/scripts/check-permissions.sh` (+ small python). Read-only: enumerate MCP servers by **name + transport type** with tool counts; tally `allow/deny/ask` by tool prefix (flag broad grants like bare `Bash` / wildcard MCP); list enabled plugins + hooks. Output a "KEYS ON YOUR RING" report. No writes, no network.
- Wire into `sf-doctor` `SKILL.md` as `--permissions`; one-line teaser in default `/sf:doctor`; Stage-7 onboarding runs it once. Framing copy: "keys ≠ instructions."
- **Tests:** `scripts/tests/test_check_permissions.sh` — hermetic temp `HOME`; assert seeded MCP names listed, allow-rules tallied, **secrets never printed**. Update `eval.json`.
- **Commit:** `feat(sf-doctor): read-only permission audit (--permissions) — keys on your ring`.

### Commit 8 — `/sf:insights` (read-only skill) [tail]
Real on-disk sources (verified): `~/.claude/projects/<encoded-cwd>/*.jsonl` (rich heterogeneous transcripts; fields `cwd`, `gitBranch`, `timestamp`, `sessionId`, `version`) + `~/.claude/session-data/*.tmp` (narrative summaries from `save-session`).
- **Create** `skills/sf-insights/` (full ADR-011 schema; ADR-013 slash command `/sf:insights [--days N] [--project <name>]`). `scripts/collect.py`: walk both sources (mtime within `--days`, default 30); parse **tolerantly** (JSONL line-by-line; heterogeneous records; malformed lines skipped); extract per-session project/tools/topics/error-retry signals; emit a structured block on stdout. **No writes, no network.** `references/synthesis-prompt.md`: LLM owns the "what's-working / what's-hindering / quick-wins" narrative (bounded, cited). `eval/eval.json`: binary assertions (no files written; four insight sections; empty-window tolerated; `--days` respected).
- **Tests:** `scripts/tests/` hermetic — seed temp `HOME` with crafted `.jsonl` + `.tmp`; assert summarized + nothing written.
- **Commit:** `feat(sf-insights): read-only local-session insights skill (collector + LLM synthesis)`.

### Commit 9 — `sf-improve-skill` honest default (F2b) [tail]
Ground truth: the default `eval_runner` → `run_evals` raises `NotImplementedError`; the baseline eval runs FIRST (`__init__.py:171`) and is **not** caught, so the default path crashes before the proposer's clean exit.
- **Edit** `eval_runner.py::run_evals`: replace the bare `NotImplementedError` with a typed `EvalBackendNotConfiguredError(RuntimeError)` (clear "requires configured eval backend — EXPERIMENTAL" message); keep the pure-logic primitives.
- **Edit** `__init__.py`: catch it at the baseline-eval call (and the in-loop runner) → return a clean `ImproveSkillResult` with new `ExitReason.REQUIRES_CONFIGURED_BACKEND` (no exception escapes). Default proposer keeps its `NO_IMPROVEMENT_POSSIBLE` clean exit.
- **Tests:** update `test_eval_runner.py` (expect the typed error); add an orchestrator test that the default path returns `REQUIRES_CONFIGURED_BACKEND`; re-scope `TestDefaultProposerNotImplemented` to inject a passing runner so the proposer branch stays reachable. Mark **experimental** (banner in Commit 6).
- **Commit:** `feat(sf-improve-skill): honest fail-fast default (REQUIRES_CONFIGURED_BACKEND); mark experimental (F2)`.

### Commit 6 — Framings (docs-only) [after the tail]
- `README.md`: reframe "What you get" around the **Four C's** (attribute Nate lightly); remove the Activity Feed bullet/section + `/sf:catch-up` rows; reword the `gh` requirement (→ `/sf:doctor` update check, Risk 2); add a **default-shift** note, a **keys ≠ instructions** note (→ `/sf:doctor --permissions`), and a **bike-method** sentence on the experimental labels. Commands table: drop `/sf:catch-up`; add `/sf:insights` + `/sf:doctor --permissions`.
- `skills/sf-install/references/stage-7-walkthrough.md`: reframe around the Four C's; drop feed; point at `--permissions` + `/sf:insights`.
- EXPERIMENTAL banners on `sf-wrap`/`sf-improve-skill` `SKILL.md`. `CHANGELOG.md`: "Solo-First Pivot" entry.
- **Commit:** `docs(framing): adopt Four C's spine; default-shift + keys≠instructions + bike-method notes`.

---

## 7. Critical files

- `feed/config.py` → extract CORE to `lib/sf_paths.py` (the dual-purpose, load-bearing module; F1)
- `skills/sf-wrap/lib/classifier.py` (`classify()` @ :315) + `lib/__init__.py` (un-stub; remove feed write) — F2a/F3
- `hooks/wake-up/sf-wake-up.py` — strip feed callback → pure wiki injection; unify wiki-root via `lib.sf_paths`
- `scripts/publish.sh` — F5 `git ls-files` snapshot + artifact guard; allowlist `feed`→`lib`
- `tests/integration/installed_runtime/test_installed_runtime.py` (+ `conftest.py`) — C2→C1-only; headline `CLAUDE_PLUGIN_OPTION_WIKIROOT` test
- `skills/sf-doctor/scripts/check-plugins.sh` — remove feed block; sibling new `check-permissions.sh`
- `skills/sf-improve-skill/lib/{__init__.py,eval_runner.py}` — F2b honest fail-fast
- **New:** `lib/sf_paths.py`, `skills/sf-insights/**`, `skills/sf-doctor/scripts/check-permissions.sh`, `wiki/decisions/031-solo-first-pivot.md`

## 8. Verification — adapted Codex Final Gate

```
claude plugin validate ./ --strict
python3 -m pytest tests/integration/installed_runtime/ -q
for m in hooks/wake-up scripts skills/sf-wrap/lib skills/sf-improve-skill/lib skills/sf-install skills/sf-backup/lib skills/sf-note/lib skills/sf-recall/lib lib ; do ( cd "$m" && python3 -m pytest tests/ -q ) ; done
( cd skills/sf-insights && python3 -m pytest scripts/tests/ -q )
bash skills/sf-doctor/scripts/tests/test_check_plugins.sh      # updated count
bash skills/sf-doctor/scripts/tests/test_check_schemas.sh      # updated count
bash skills/sf-doctor/scripts/tests/test_check_permissions.sh  # new
python3 tests/integration/schema-conformance/conformance.py
python3 scripts/lint-yaml-frontmatter.py .                     # exit 0 after F7
scripts/publish.sh --dry-run
```
**Release assertion (F5, strengthened):** the dry-run snapshot must NOT contain `wiki/`, `.pytest_cache`, `__pycache__`, `*.pyc`, `PLACEHOLDER-ORG`, or `feed/`; and MUST contain `lib/sf_paths.py`.

## 9. Risks / judgment calls

1. **`feed/config.py` dual-purpose** — the main trap; extract-then-delete (Commit 1 shim → Commit 2 delete). A naive `git rm feed/` breaks recall, sf-wrap, and the hook's `handle()` (5+ non-feed consumers).
2. **`gh` does NOT fully evaporate** — `sf-doctor`'s update check + `/sf:update` still use `gh api .../sf-marketplace`. `gh` stays a soft requirement for *updates*, not a feed. Reword, don't delete. (Confirm `sf-backup` uses a configured git remote, not gh.)
3. **Test-count drift** — doctor "8/8"/"5/5", migration-dogfood "17/17", conformance "26 informational" shift when feed-entry rows go. Re-read counts from the Phase-0 green run; don't hard-code blind.
4. **`sf-improve` default = fail-fast, not a real runner** — the honest bike-method choice (a deterministic proposer can't meaningfully self-improve a skill). Revisit if a minimal real default is wanted.
5. **`publish.sh` still ships per-module `tests/`** (they're tracked) — preserves current behavior; caches/bytecode now excluded. Add a `*/tests/*` filter only to change that (a behavior change — flag it).
6. **`handle:` field kept** in `identity.md` (reframed "short name") so the deferred multi-user layer can return without a migration. Costs nothing; remove for zero feed residue.
7. **F2 classifier scope-creep** — file-change heuristics need a `project_files_changed` input that doesn't exist (the F3 confusion). v1 uses transcript + pins only.
8. **`/sf:insights` two disjoint sources** — `.jsonl` (rich, the real signal) vs `.tmp` (sparse, user-dependent). Assume neither exists; parse heterogeneous JSONL tolerantly.
9. **ADR-028/030 are amended, not superseded** — they bake in feed specifics AND non-feed contracts. Supersede-vs-amend distinction matters for wiki integrity.
10. **Permission-audit data shape** — `enabledPlugins` is a dict; `permissions.allow` a flat `Tool(arg)` list; per-project `mcpServers` may be empty; `settings.local.json` may be absent. Tolerate all; never echo secrets.

## 10. Environment notes

- Tests **per-module** (root pytest collision is PRE-EXISTING — do not fix).
- `claude plugin validate ./ --strict` (repo root IS the plugin).
- `Edit` requires a prior `Read` of the file (Bash cat/tail does not count).
- A `block-no-verify` hook blocks `git commit --no-verify` — never pass it (commits work without it).
- Deny-list: no `rm -rf *`, no `sudo` — targeted `git rm` / `rm -f` only.
- Baseline tag `baseline-v1.0-full-wiki` preserves the full pre-pivot tree (the feed implementation is recoverable there + in history).
