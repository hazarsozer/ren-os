---
title: "Codex Review"
date: 2026-05-29
reviewer: "Codex"
status: "draft"
scope: "Branch fix/v1.0-preship-blockers at 9774029"
tags:
  - review
  - codex
  - pre-ship
---

# Codex Review

Independent repo-wide review of `startup-framework` after the V1.0 pre-ship blocker fixes.

## Verdict

Do not ship this exact tree to partners yet.

The previous critical install blockers appear materially improved: plugin validation passes, installed-runtime tests pass, and the release dry-run passes. The remaining risks are different: advertised configuration knobs are ignored by shared runtime code, two headline features still have production-default stubs, Activity Feed attribution can be misleading, and the publish path can copy ignored local artifacts into the orphan snapshot.

This is not a "rewrite it" result. It is a short hardening pass before a friend-group rollout.

## Scope

- Branch: `fix/v1.0-preship-blockers`
- Commit reviewed: `9774029`
- Reviewed areas: wiki ADRs/log/index, plugin manifest, README/docs, wake-up hook, Activity Feed module, lifecycle skills, install/doctor/update/publish paths, and test harnesses.
- Focus: installed-runtime behavior, docs versus implementation, privacy expectations, release packaging, and cross-module contracts.
- Code under review was not changed during review.

## Validation Run

- `claude plugin validate ./ --strict` passed.
- `python3 -m pytest tests/integration/installed_runtime/ -q` passed: 5 tests.
- `bash skills/sf-doctor/scripts/tests/test_check_plugins.sh` passed: 8/8.
- `bash skills/sf-doctor/scripts/tests/test_check_schemas.sh` passed: 5/5.
- `python3 tests/integration/schema-conformance/conformance.py` exited 0 with 0 strict blockers and 26 informational failures.
- `scripts/publish.sh --dry-run` passed.
- Module tests for `feed`, `hooks/wake-up`, `scripts`, `sf-wrap`, `sf-improve-skill`, `sf-install`, `sf-backup`, `sf-note`, `sf-recall`, and `sf-catch-up` passed.
- `bash skills/sf-update/scripts/tests/test_snapshot_inode_safety.sh` passed: 4/4.
- `bash skills/sf-update/scripts/version-compare.sh --self-test` passed.
- `bash tests/integration/migration-dogfood.sh` passed: 17/17.
- `python3 wiki-skeleton/tests/lint_no_dev_wiki_content.py` passed.
- `python3 scripts/lint-yaml-frontmatter.py .` failed on `wiki/research/py-harness-engineering.md:9:55`.

## Findings

### F1 - High - Plugin path options are advertised but ignored by the Python feed layer

Evidence:

- `.claude-plugin/plugin.json:23` defines `wikiRoot`.
- `.claude-plugin/plugin.json:43` defines `activityFeedLocalClone`.
- `README.md:79` documents `wikiRoot` as configurable.
- `feed/config.py:92` resolves the framework root only from `SF_FRAMEWORK_ROOT`.
- `feed/config.py:104` returns `framework_root() / "activity-feed"`.
- `feed/config.py:113` returns `framework_root() / "wiki"`.
- `skills/activity-feed/scripts/status.sh:66` calls `config.local_path()`.
- `skills/sf-doctor/scripts/check-plugins.sh:147` computes a feed path, but the status script ignores it.
- `skills/sf-catch-up/scripts/render.py:57` reads from `config.local_path()`.

Reproductions:

- `CLAUDE_PLUGIN_OPTION_ACTIVITYFEEDLOCALCLONE=/tmp/sf-feed-custom ... config.local_path()` still returned `~/.startup-framework/activity-feed`.
- `CLAUDE_PLUGIN_OPTION_WIKIROOT=/tmp/sf-wiki-custom ... config.wiki_path()` still returned `~/.startup-framework/wiki`.
- `CLAUDE_PLUGIN_OPTION_ACTIVITYFEEDLOCALCLONE=/tmp/sf-feed-custom bash skills/activity-feed/scripts/status.sh` still reported the default home path.

Impact:

- A friend who configures a custom wiki/feed path can get a green install while commands read or write the default path.
- Doctor/status checks can verify one path while runtime code uses another.
- This undermines the installed-runtime hardening work because the advertised Claude plugin options are not the single source of truth.

Fix direction:

- Centralize path resolution in `feed.config`.
- Resolve in this order: explicit `SF_*` env override, `CLAUDE_PLUGIN_OPTION_*`, then `~/.startup-framework` defaults.
- Wire `status.sh` to the same resolver, or remove the unused argument plumbing.
- Add installed-runtime tests that set only `CLAUDE_PLUGIN_OPTION_WIKIROOT` and `CLAUDE_PLUGIN_OPTION_ACTIVITYFEEDLOCALCLONE`.

### F2 - High - Advertised headline features still have production-default stubs

Evidence:

- `README.md:20` advertises self-improving skills.
- `README.md:61` to `README.md:63` says `/sf:wrap` consolidates only real signal and usually writes nothing.
- `skills/sf-wrap/lib/classifier.py:286` defines `classify()`.
- `skills/sf-wrap/lib/classifier.py:315` raises `NotImplementedError`.
- `skills/sf-wrap/lib/__init__.py:181` catches that exception and forces labels to `("none",)` with `classifier not yet wired`.
- `skills/sf-improve-skill/lib/__init__.py:95` wires the default eval runner to `run_evals`.
- `skills/sf-improve-skill/lib/__init__.py:101` wires the default change proposer to a function that raises `NotImplementedError`.
- `skills/sf-improve-skill/lib/eval_runner.py:278` defines `run_evals()`.
- `skills/sf-improve-skill/lib/eval_runner.py:316` raises `NotImplementedError`.

Impact:

- The tests mostly validate orchestration and injected fakes; the default user-facing path is not equivalent.
- `/sf:wrap` does not yet have the classifier behavior implied by the docs.
- `/sf:improve-skill` does not yet have a complete default improvement loop.

Fix direction:

- Either implement minimum viable production defaults or mark these capabilities as experimental in README, SKILL docs, and release notes.
- For `/sf:wrap`, a conservative deterministic classifier is acceptable for V1 if the documentation reflects its limits.
- For `/sf:improve-skill`, fail early with an explicit "requires configured eval/proposer backend" message, or provide a real default runner/proposer path.

### F3 - High - `/sf:wrap` can publish wiki maintenance files as Activity Feed touched files

Evidence:

- `skills/sf-wrap/lib/__init__.py:233` to `skills/sf-wrap/lib/__init__.py:237` passes `files_touched=list(apply_result.files_changed)` into the feed writer.
- `apply_result.files_changed` describes wiki files updated by consolidation, not necessarily project files touched during the session.

Impact:

- Feed entries can tell partners that the session touched `CONTEXT.md`, `log.md`, or other wiki maintenance files instead of the actual project files.
- This reduces the feed's coordination value and can confuse privacy expectations.

Fix direction:

- Separate "wiki files changed by wrap" from "project files touched in the session".
- If real project file attribution is unavailable, omit `files_touched` rather than substituting wiki maintenance paths.
- Add a test proving feed output never uses consolidation target files as project-touched files.

### F4 - Medium - Handle validation is incomplete across feed APIs

Evidence:

- `feed/config.py:223` defines `validate_handle`.
- `feed/writer.py:358` to `feed/writer.py:367` validates handles on write.
- `feed/bootstrap.py:461` constructs `path / f"{handle}.log.md"`.
- `feed/bootstrap.py:472` constructs `identities / f"{handle}.md"`.
- `feed/identity_sync.py:33` to `feed/identity_sync.py:35` constructs `target = identities_dir / f"{handle}.md"`.
- `feed/writer.py:305` to `feed/writer.py:309` constructs old/new rename paths directly.
- `skills/sf-install/references/stage-4-identity-bootstrap.md:39` to `skills/sf-install/references/stage-4-identity-bootstrap.md:43` calls rename behavior from install guidance.

Impact:

- Public write paths are safer now, but lower-level and future call paths can still construct paths from raw handles.
- This creates a regression trap: one future caller can reintroduce path traversal or malformed identity/log filenames.

Fix direction:

- Validate every handle at API boundaries and before path construction.
- Add negative tests for bootstrap, identity sync, and rename paths using `../bad`, absolute paths, spaces, and shell metacharacters.
- Prefer a helper that returns the validated log/identity path rather than repeating `f"{handle}.md"` and `f"{handle}.log.md"`.

### F5 - Medium - `publish.sh` copies ignored local artifacts from the working tree

Evidence:

- `scripts/publish.sh:43` to `scripts/publish.sh:57` allowlists whole directories such as `hooks`, `skills`, `feed`, and `wiki-skeleton`.
- `scripts/publish.sh:151` to `scripts/publish.sh:154` uses `cp -r --parents "$entry" "$SNAP/"`.
- `git ls-files -o -i --exclude-standard | wc -l` reported 203 ignored files in the working tree.
- Examples included `.pytest_cache`, `__pycache__`, and `.pyc` files under allowlisted trees.

Impact:

- The orphan snapshot can include cache files and Python bytecode that are ignored in the dev repo.
- A dry-run can still pass because the current guards focus on wiki leakage, placeholders, and broad release safety, not ignored artifact cleanliness.

Fix direction:

- Build the snapshot from `git ls-files` filtered through the shippable allowlist, not from recursive directory copies.
- If untracked release files are intentional, list them explicitly.
- Add a dry-run guard that fails on `__pycache__`, `.pytest_cache`, `*.pyc`, and other known local artifacts.

### F6 - Medium - Activity Feed privacy and behavior docs conflict with implementation and ADRs

Evidence:

- `README.md:18` to `README.md:19` says routine work never pollutes the feed.
- `README.md:61` to `README.md:63` says `/sf:wrap` emits feed entries only for real signal and most sessions write nothing.
- `hooks/wake-up/sf-wake-up.py:122` to `hooks/wake-up/sf-wake-up.py:131` writes a SessionStart entry.
- `skills/sf-wrap/SKILL.md:189` says no-signal wrap still writes a feed entry.
- `wiki/decisions/018-activity-feed.md:98` to `wiki/decisions/018-activity-feed.md:104` says SessionStart writes a start entry.
- `wiki/decisions/021-privacy-boundaries.md:71` to `wiki/decisions/021-privacy-boundaries.md:78` says session-start entries are pushed automatically.

Impact:

- Partner expectations can be wrong on first install: the README implies stricter quiet-by-default behavior than the implementation and ADRs provide.
- This is a trust issue more than a code issue. Privacy controls only work if the user accurately understands the default.

Fix direction:

- Pick one contract and make README, SKILL docs, and ADR summaries consistent.
- If the intended contract is automatic start/end entries, state that directly near the install instructions and link to skip/disable controls.
- If the intended contract is high-signal-only feed writes, change the runtime to match and update ADR-018/ADR-021.

### F7 - Low - Dev wiki frontmatter lint currently fails

Evidence:

- `python3 scripts/lint-yaml-frontmatter.py .` failed on `wiki/research/py-harness-engineering.md:9:55`.
- The likely cause is the unquoted `attribution` value around `wiki/research/py-harness-engineering.md:8`, which contains a colon.

Impact:

- This does not appear to affect the shipped plugin because the dev wiki is excluded from the marketplace snapshot.
- It does weaken confidence in the wiki hygiene gate and should be fixed before tagging the dev repo.

Fix direction:

- Quote the `attribution` value.
- Re-run `python3 scripts/lint-yaml-frontmatter.py .`.

## Confirmed Strengths

- The installed-runtime test suite is the right regression guard for the previous C1/C2 class of failures.
- `claude plugin validate ./ --strict` is clean.
- The release dry-run guards correctly protect against obvious wiki leakage and placeholder leakage.
- The schema-conformance harness exits cleanly with no strict blockers.
- The module test coverage is broad and caught orchestration-level issues well.

## Recommended Fix Order

1. Fix plugin option path resolution across feed/wiki consumers.
2. Decide whether `/sf:wrap` and `/sf:improve-skill` are production features or explicitly experimental.
3. Fix `/sf:wrap` Activity Feed file attribution.
4. Change `publish.sh` to snapshot tracked shippable files only.
5. Complete handle validation across bootstrap, identity sync, and rename APIs.
6. Align Activity Feed privacy docs with the actual default behavior.
7. Fix the dev wiki YAML lint failure.

## Suggested Final Gate

Run these after the fixes:

```bash
claude plugin validate ./ --strict
python3 -m pytest tests/integration/installed_runtime/ -q
python3 -m pytest feed hooks/wake-up scripts skills/sf-wrap skills/sf-improve-skill skills/sf-install skills/sf-backup skills/sf-note skills/sf-recall skills/sf-catch-up -q
bash skills/sf-doctor/scripts/tests/test_check_plugins.sh
bash skills/sf-doctor/scripts/tests/test_check_schemas.sh
python3 tests/integration/schema-conformance/conformance.py
python3 scripts/lint-yaml-frontmatter.py .
scripts/publish.sh --dry-run
```

Add one release-specific assertion: inspect the dry-run snapshot and fail if it contains `wiki/`, `.pytest_cache`, `__pycache__`, `*.pyc`, or `PLACEHOLDER-ORG`.
