# Cross-team Code Review — sf-build-v1

**Reviewer:** onboarding-2
**Date:** 2026-05-28
**Scope:** feed-2 (priority 1), distribution-2 (priority 2), lifecycle-2 (priority 3)
**Lens:** ADR-fidelity + contract-break + load-bearing correctness; no style nits unless they obscure intent.

Findings are numbered per teammate. Severity uses team-lead's rubric: `critical | high | medium | low | nit`.

---

## feed-2 — `feed/` module + `skills/sf-disable-feed/`

### finding-F1 [severity: high]
**File:** `feed/io_github.py:83`
**Issue:** `check_auth()` invokes `gh auth status --show-token`. The `--show-token` flag prints the friend's OAuth token to stderr. `check_auth()` then captures `result.stderr + result.stdout` and parses it for scopes. On the failure path, `reason=(result.stderr.strip() or ...)` — meaning if `gh auth status --show-token` ever returns a non-zero exit code while the token is still present in output (e.g., partial-auth or expired-but-readable token), the literal token is placed into the returned `AuthStatus.reason` and propagates up to callers. Onboarding's Stage 3 surfaces this via the install-state abort_log, which is persisted in plaintext at `$XDG_STATE_HOME/sf/install-state.json`. Even on the success path, having the token in stdout/stderr means a future caller adding logging would expose it.
**ADR/contract reference:** ADR-006 §provider trust + ADR-021 §"no secret scanning" (implicit corollary: don't introduce secrets where they don't already exist).
**Suggested fix:** Drop `--show-token` from the `gh auth status` invocation. The scopes line ("Token scopes: 'repo', 'workflow'") still appears in `gh auth status` output without `--show-token`; `_parse_gh_scopes` will still work. Two-character fix (delete the flag), no semantic change for the success path.
**Pinning recommendation:** Add `test_check_auth_does_not_include_show_token_flag` that asserts `--show-token` is NOT in the subprocess argv. Also a `test_authstatus_reason_does_not_contain_oauth_token_pattern` that runs the function in a mocked subprocess emitting a fake `gho_xxxx`-shaped token and asserts the returned `AuthStatus.reason` doesn't contain it.

### finding-F2 [severity: medium]
**File:** `feed/writer.py:266-278` (compute_entry_id + dispatcher idempotency check)
**Issue:** Idempotency key uses `summary[:40]` and `ts_unix_minute`. Two distinct entries written within the same minute whose summaries share the first 40 characters collide → second entry is silently dropped with `success=True, pushed=False, entry_id=<existing>`. Realistic trigger: a long-running task that produces two `/sf:wrap` calls in the same minute with summaries both starting "Worked on auth-flow — refactored the JWT middl…" (40-char prefix identical, but the second describes additional work). The friend sees success but the second entry never lands.
**ADR/contract reference:** ADR-018 (Activity Feed) — entries are append-only chronological record. Silent loss breaks the chronological invariant.
**Suggested fix:** Either (a) raise the prefix cap to ~120 chars so collision requires deliberate engineering, or (b) include a monotonic counter / hash of the full body in the key. Option (a) is the smaller change; option (b) is more robust.
**Pinning recommendation:** Add `test_distinct_summaries_with_shared_prefix_same_minute_get_separate_entries` — two writes within the same minute with summaries that share the first 40 chars but diverge afterward should produce two distinct entries in the log file.

### finding-F3 [severity: medium]
**File:** `feed/reader.py:217-241` (`_parse_log_file` frontmatter skip)
**Issue:** Frontmatter skip uses a simple `while lines[i].strip() != "---"` loop. If the closing `---` is missing (corrupted file, mid-edit), the loop runs to end of file (`i == n`), then `i += 1` makes `i == n+1`, and the entry-parsing `while i < n` immediately exits — **the entire log is silently treated as empty**. A friend with a malformed frontmatter sees zero entries in their wake-up Activity Feed display with no warning.
**ADR/contract reference:** ADR-018 (Activity Feed graceful degradation) — file corruption should surface a warning, not silently elide content.
**Suggested fix:** When the closing `---` isn't found within reasonable bounds (e.g., first 50 lines or end of file), log a warning AND fall back to parsing from line 0 (treating no frontmatter). Optionally surface via `FriendsTail.stale` or a new `FriendsTail.parse_warnings: tuple[str, ...]` field.
**Pinning recommendation:** `test_parse_log_with_missing_closing_frontmatter_marker_falls_back_not_silent` — feed a log file with `---\nschema_version: 1\n` (no closing marker) and assert entries below it are still parsed.

### finding-F4 [severity: medium]
**File:** `feed/reader.py:394-429` (`_truncate_to_budget`)
**Issue:** Truncation drops the oldest entries across all friends until under budget. If a friend has only 1 entry total and it happens to be the oldest, that friend disappears entirely from the FriendsTail result. The wake-up hook then can't surface "friend X is also active" — silently zero coverage. This contradicts the "silent-friend coverage" rationale that motivated `feed_read_friends_tails`'s per-friend bucketing in the first place.
**ADR/contract reference:** ADR-018 §"silent friends" + lifecycle-2 plan rider 2 (active vs quiet auto-scaling).
**Suggested fix:** Truncation should preserve ≥1 entry per friend present in the input. Concretely: change the inner drop loop to skip an entry if removing it would empty its friend's bucket; if every remaining friend has only one entry and budget still exceeded, truncate the per-entry rendered SIZE (e.g., trim the summary) rather than dropping the friend.
**Pinning recommendation:** `test_truncate_preserves_at_least_one_entry_per_friend` — input is 5 friends with mixed entry counts, max_tokens forces aggressive truncation; assert all 5 friends still appear in result.friends.

### finding-F5 [severity: low]
**File:** `feed/format.py:200-217` (`validate_end_entry` shape check)
**Issue:** Line-1 shape check is `line1.startswith("Worked on ") and line1.endswith(".")` — it does NOT verify the em-dash separator that distinguishes a valid entry (`Worked on X — Y.`) from a degenerate one (`Worked on X Y.` with no separator). A consolidate skill that drops the em-dash by accident produces an entry that passes shape validation but renders ambiguously when reader.py's `END_PROJECT_BRIEF_RE` (which DOES require `—`) parses it back — `project` field ends up None.
**ADR/contract reference:** ADR-021 §"format constraint IS the privacy mechanism".
**Suggested fix:** Add a substring check `" — " in line1` before the prefix/suffix check, OR use a regex matching the writer's intended shape.
**Pinning recommendation:** `test_end_entry_without_em_dash_separator_is_rejected` — feed a body `"Worked on auth my changes.\nTouched: a.py."`, expect `FormatViolation("shape-mismatch")`.

### finding-F6 [severity: low]
**File:** `feed/skip.py:90-110` (`_session_state_file` fallback)
**Issue:** When `CLAUDE_SESSION_ID` is unset, `_session_state_file()` returns the most-recently-modified `session-*.json`. In production this should never fire (Claude Code populates the env var). But if a friend ever runs `/sf:disable-feed` in session A, ends session A, then starts session B in an environment where the env var is missing (e.g. shell aliased `claude` wrapper that strips env), session B reads A's disable-marker and silently skips the feed for an entire session.
**ADR/contract reference:** ADR-021 §"--skip-feed-start" + the principle that opt-out should be explicit, not inherited.
**Suggested fix:** Either remove the fallback entirely (return None on missing env var; `_session_disabled()` returns False — fail open), or scope the fallback to a clearly-marked dev/test mode via a separate env var (`SF_ALLOW_TEST_STATE_FALLBACK=1`). Removal is the safer choice.
**Pinning recommendation:** `test_session_disabled_returns_false_when_env_var_missing_and_stale_marker_exists` — write a stale `session-stale.json` with `skip_feed=true`; clear `CLAUDE_SESSION_ID`; assert `is_skip_active()` returns `(False, "not-skipping")`.

---

## distribution-2 — `skills/wiki-migration/`, `skills/sf-doctor/`, `skills/sf-update/`, `.github/workflows/`, docs

### finding-D1 [severity: medium]
**File:** `skills/sf-doctor/scripts/check-schemas.sh:155`
**Issue:** `files_without_schema_field = files_found - files_without_fm - len(yours_set)`. The arithmetic uses `len(yours_set)` (count of DISTINCT schema_version values) as a proxy for "files with a schema_version field". When multiple files share the same schema_version (the normal case for a healthy wiki), this UNDERCOUNTS files-with-schema-field and OVERCOUNTS files-without. Concrete example: 5 `decision/` files, all at `schema_version: 1`, no fm-parse failures → `yours_set = {1}`, `len = 1` → `files_without_schema_field = 5 − 0 − 1 = 4`. The hint then reports `"4/5 file(s) missing schema_version field. Assuming schema_version: 1 for those per ADR-027 fallback."` even though all 5 files declare `schema_version: 1` correctly. Friends will see false-positive warnings in every `/sf:doctor` run on any wiki with >1 file per page-type.
**ADR/contract reference:** ADR-027 §"Pages without schema_version" fallback behavior. The fallback path is meant for pre-v1 pages, not for healthy current pages.
**Suggested fix:** Track per-file presence of the `schema_version` field explicitly:
```python
files_with_schema = 0
for fp in files:
    fm = parse_frontmatter(fp)
    if not fm:
        files_without_fm += 1
        continue
    sv_raw = fm.get("schema_version", "")
    if not sv_raw:
        continue  # missing field — fallback applies
    files_with_schema += 1
    try:
        yours_set.add(int(sv_raw))
    except ValueError:
        yours_set.add(sv_raw)
files_without_schema_field = files_found - files_without_fm - files_with_schema
```
**Pinning recommendation:** Add a self-test fixture under `skills/sf-doctor/scripts/tests/` (or a synthetic wiki) where multiple files share a schema_version; assert `check-schemas.sh` reports `ok` with no false-positive `files_without_schema_field` warnings.

### finding-D2 [severity: low]
**File:** `skills/sf-update/scripts/snapshot.sh:48`
**Issue:** `cp -al` (hard-linked archive) is used as the preferred snapshot mechanism. Hard-linked snapshots are inode-sharing: snapshot dir and live wiki share the same inodes. This is correct ONLY if every wiki-mutating operation downstream uses rename-on-write atomicity (GNU `sed -i` does — writes a temp file and renames). But editors / migrators that truncate-and-rewrite (naive `open(path, "w")` without atomic-rename) would modify the snapshot's inode in place, defeating the snapshot. The script's fallback to `cp -a` (real copy) only triggers when `cp -al` errors at copy-time, not when downstream tooling is unsafe.
**ADR/contract reference:** ADR-027 § snapshot-before-migration contract.
**Suggested fix:** Either (a) prefer `cp -a` (real copy) by default — wikis are small KB-MB scale and the storage savings rarely matter, or (b) keep `cp -al` but document the constraint in `MIGRATION_PATTERN.md` that all migration scripts MUST use atomic-rename-on-write semantics.
**Pinning recommendation:** A small CI smoke test that runs `snapshot.sh`, then truncate-and-rewrites a wiki file in place (`open(p, "w").write("new")`), then asserts the snapshot copy still has the original content.

### Notes (not findings)

- `.github/workflows/release.yml` is clean. `${{ }}` interpolations are properly funnelled through `env:` blocks; tag-glob restricts arbitrary content from entering shell or awk regex; `gh release create` args are quoted or expand-empty-safe. No security findings.
- `version-compare.sh` self-tests cover the `rc.2` vs `rc.10` numeric-not-lexical ordering (line 170). The `1.3.0-rc.1 → 1.3.0` → `prerelease` classification is documented intent per the script header; if surfaced to friends, downstream UX may want a separate "stable-promotion" label, but the classifier itself is correct.
- `docs/RECOVERY.md` covers the 8 documented scenarios. Spot-checked scenario 1: `/sf:install --restore <url>` is mechanically correct given Stage 5's additive-diff semantics — restore clones into wikiRoot, Stage 5's loader detects existing content, only NEW templates (if any) are offered. Honest framing of "claude-mem + Context Mode observation history is also gone unless YOU backed up" is appropriate.
- `schemas.json` registry verified: 16 page-types after task #39 bump, all 4 onboarding-requested types present, my templates' `type:` values all align.

---

## lifecycle-2 — `hooks/wake-up/`, `skills/sf-wrap/`, ADR amendments

### finding-L1 [severity: critical]
**File:** `skills/sf-improve-skill/lib/preflight.py:163-184`
**Issue:** Schema fork between two camps. Preflight's `_validate_eval_file` expects:
- top-level `test_cases` array
- each case has an `assertions` list of objects
- each object has a `binary: true` field

ADR-011 § "eval.json schema" specifies — and every framework-shipped skill outside `skills/sf-wrap/` / `skills/sf-improve-skill/` uses:
- top-level `tests` array
- each test has a `binary_assertions` list of **strings** (not objects)

Lifecycle-2's own `skills/sf-wrap/eval/eval.json` uses the lifecycle-2 internal shape (`test_cases` + `assertions` + `binary: true` objects), so their internal tests pass. But running `/sf:improve-skill sf-install` (or any other framework skill) fails at gate 2 with `PreFlightError: skills/sf-install/eval/eval.json must contain a non-empty 'test_cases' array per ADR-011 schema.` — even though that file IS valid per the actual ADR-011 schema. **`/sf:improve-skill` is unusable on any framework-shipped skill that follows ADR-011 until preflight is fixed.**
**ADR/contract reference:** ADR-011 § "eval.json schema (compatible with Skill Creator's run_eval.py)" — `tests` + `binary_assertions` as strings is the load-bearing spec. ADR-012 (Layer 2 self-improvement) relies on `/sf:improve-skill` working against ADR-011-conformant skills.
**Suggested fix:** Surfaced separately to team-lead via SendMessage. Short version: replace preflight's parser with one that reads `data["tests"]` + each test's `binary_assertions` as a list of strings; reject non-string assertions with an explicit error pointing back at ADR-011.
**Pinning recommendation:** Add `test_preflight_accepts_adr011_eval_shape` that loads `skills/sf-install/eval/eval.json` (or a copy in test fixtures) and asserts preflight passes. The fact that this test doesn't exist is why the drift shipped.

### finding-L2 [severity: low]
**File:** `skills/sf-wrap/SKILL.md` activation description + body
**Issue:** SKILL.md prose refers to the feed call as `feed.write_session_end()`. The locked exported name in `feed/__init__.py` is `feed_write_session_end` (with `feed_` prefix). A reader following the prose to write the import would get `from feed import write_session_end` → ImportError. Minor — the AI executing the skill should figure it out from context — but doc precision matters when SKILL.md is the activation contract.
**ADR/contract reference:** Locked feed API names (team-lead arbitration 2026-05-28).
**Suggested fix:** Two-character: `feed.write_session_end()` → `feed.feed_write_session_end()` in the SKILL.md prose, or rephrase to "via `feed_write_session_end()` from the feed module".
**Pinning recommendation:** A doc-lint that greps SKILL.md text for `feed\.write_(start|end|release)` (without `feed_` prefix) and fails when found. Could live in distribution-2's CI alongside the schemas check.

### Notes (not findings)

- `hooks/wake-up/CC_API_NOTES.md` is exemplary verification work. Conversation-layer injection (vs system-prompt mutation) is confirmed against four authoritative sources; ADR-008's central promise is preserved empirically. No issues.
- ADR-009 amendment (2026-05-28 `revise-claude-md` complement note) is clean — framed as "different surface, not competitor" without overcommitting to coupling.
- ADR-012 amendment (`--max-turns` dropped per option a) is correct per the verified CC CLI flag inventory in CC_API_NOTES.md. Saves friends from refusal-to-run on a CLI surface that doesn't exist in CC 2.1.154.
- `sf-wrap/lib/validate.py` defense-in-depth validator chain is well-designed — format-shape only, no secret scanning, properly mirrors `feed.format.validate_end_entry` for the pre-feed reprompt loop. Aligns with ADR-021.

---

## Summary

| Severity | Count | Teammates |
|---|---|---|
| critical | 1 | lifecycle-2 |
| high | 1 | feed-2 |
| medium | 4 | feed-2 (×3), distribution-2 (×1) |
| low | 3 | feed-2 (×2), distribution-2 (×1), lifecycle-2 (×1) |
| nit | 0 | — |
| **total** | **9** | — |

**Critical surfaced to team-lead immediately** (eval-schema fork — finding-L1).

The team's overall quality is high. Most findings cluster around (a) parser arithmetic that breaks at scale (D1, F2, F3, F4), (b) safety-mechanism placement (F1 token leak path, F6 cross-session contamination), (c) silent-loss in edge cases (F2, F3, F4). Nothing critical except the eval-schema fork, and that's a coordination issue — both eval shapes are individually coherent, they just don't align with each other or with ADR-011.
