# v1.0 Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the shipped v1.0 plugin's genuine code bugs, doc/contract drift, and privacy leaks, then fix the command-namespace defect — and re-verify and re-publish as one combined release.

**Architecture:** Five sequential phases on a dedicated worktree. Phases 1–3 are surgical TDD fixes (Python correctness, doc/contract drift, security) on the **current `skills/sf-*` paths** — exactly where the investigators verified them. Phase 4 is the namespace rename (the large, blast-radius-wide mechanical sweep), done **last** because it is independent of the fixes, fully reversible in a worktree, and its empirical confirmation belongs at install/publish time. Phase 5 re-verifies the renamed plugin, confirms the namespace fix empirically, and ships one new version.

**Tech Stack:** Python 3 (per-module pytest), Bash (hermetic shell test harnesses), JSON/YAML config, GitHub Actions, the `claude plugin` CLI + `scripts/publish.sh`.

---

## ⚠️ Review Corrections & Decisions (AUTHORITATIVE — read before any task)

This plan was authored from four parallel read-only investigations (2026-05-31). The investigators **empirically verified** the code; several claims in `docs/superpowers/specs/2026-05-31-v1-remediation-findings.md` were corrected. **Where this section conflicts with the findings doc or with a task body below, THIS section wins.**

### Corrected severities (the findings doc overstated)
The "3 Python HIGH bugs" framing is **wrong**. Verified reality:

| Finding | Cited as | **Actual** | Note |
|---|---|---|---|
| `sf_paths.py` unterminated frontmatter → wrong handle | HIGH | **HIGH ✓** | The only genuine HIGH. A body `handle:` in a truncated `identity.md` flows into FS paths. |
| `apply.py` rollback | HIGH | **LOW** | `git clean` already runs unconditionally; rollback WORKS. Real bug is a diagnostic **log count** under-reporting, not data loss. Cited lines 204/128 are wrong → **207**. |
| `budget.py` cache-rate `KeyError` | HIGH | **MED ✓** | Only crashes on a hand-edited partial pricing table; shipped table has all keys. |
| `diff_plan.py` empty-content guard (line 68) | MED | **NOT A BUG** | The cited function `_unified_diff_for_new_file` is **dead code (0 callers)**. Convert to dead-code deletion. |
| `diff_plan.py` framework_version hardcode | MED | **MED ✓, fix caveat** | The naive `import lib.sf_paths` **FAILS** (the skill's own `lib/` package shadows the repo-root `lib/`). Must load via `importlib` by file path (`parents[3]`). |
| `collect.py` decode fallback | LOW | **LOW ✓, expectation corrected** | `my-app` is unrecoverable from the lossy encoding; fix surfaces the encoded `dir_name`, NOT a wrong basename. |

Net: **1 HIGH, 2 MED, 4 LOW/dead-code** in Phase 1. Lead with the HIGH.

### Structural decisions (adopted defaults — flag to maintainer at review)
1. **Ordering = namespace LAST** (changed from the findings § Suggested sequencing, by maintainer decision 2026-05-31). Rationale: the namespace rename is **independent** of the code/doc/security fixes; it is **fully reversible** (isolated worktree) with an already-fully-mapped blast radius (so "surface surprises early" gains nothing); and its only **empirical** confirmation (`/sf` autocomplete) requires an install — the same install Phase 5 needs for the post-publish check. So Phases 1–3 run first on the **current `skills/sf-*` paths the investigators actually verified** (no path translation, maximum fidelity), and the rename + the empirical `/sf` confirmation + the single re-publish are the final unit (Phases 4–5).
2. **wiki-migration dir is KEPT** (not renamed to `migrate-wiki`). Renaming it would touch ~35 functional refs + `$schema` `$ref` pointers; instead fix the **3** doc strings that say `/sf:migrate-wiki` → `/sf:wiki-migration` (the docs are already wrong vs. the dir's real command verb). Note: `skills/wiki-migration/` has **no** `sf-` prefix and is unaffected by Phase 4's dir renames.
3. **kickoff secret → DROP the field** (Phase 3), not redact. Redaction is a leaky denylist; the field is redundant with `topics` and feeds no aggregate.
4. **output-schema.json → fix the 3 dangling refs** (Phase 2), don't create the file (no `--json` renderer ships; the eval does NOT assert it — findings overstated).
5. **alternatives/ → remove from `wiki-skeleton/manifest.yaml`** (Phase 2); keeps the page-type count at **15**.
6. **schemas.schema.json `owner_module` enum** still lists dead `"sf-feed"` — a **live CI validator** (bonus Phase 2 fix the findings missed).

### Namespace landmines (Phase 4 — do not skip)
- **Plugin data dir changes** `startup-framework-sf-marketplace` → **`sf-sf-marketplace`** (CC derives it as `<plugin-name>-<marketplace-name>`). Three hardcoded fallbacks must change, AND any **local** pre-existing data dir must be moved once (migration note in Task 4.3).
- **Re-publish changes every command's surface.** Version bump is **at least MINOR**; target **1.1.0** (the old `/startup-framework:*` invocations change — but they never worked as documented, so MAJOR is arguable; maintainer's call in Phase 5).
- **The empirical `/sf` confirmation** (CC docs rule + 4 live corroborations make it ~99%) is done at **Phase 5 pre-publish** (install-time), before the irreversible publish — NOT as an upfront blocker. It is confirmation before shipping, not discovery before the reversible worktree edits.

### DO NOT TOUCH (verified safe / out of scope — touching these breaks things or is scope creep)
- `lib/` — NOT renamed (it's the framework-root package, not a skill dir). `import lib.sf_paths` is unaffected. (So Phase 1's `sf_paths` work uses `lib/…` regardless of the rename.)
- `hooks/hooks.json` — uses `$CLAUDE_PLUGIN_ROOT`, no skill-dir refs.
- `~/.startup-framework/` — the framework **user-data** root (ADR-017/027), independent of the plugin `name`. Renaming it is a DIFFERENT breaking change; leave it.
- **All `/sf:` doc strings** (123 files) — these become correct **as-is** after the rename. No edits. Tests asserting `/sf:…` literals (e.g. `test_sf_paths.py`) stay green.
- `wiki-migration/` dir + every `skills/wiki-migration/…` path ref (kept per decision 2).
- `eval.json#name` fields and `run_evals("sf-wrap")`-style test args — decoupled labels, not paths.
- `scripts/publish.sh` allowlist — globs `skills` wholesale; survives the rename.
- `marketplace.json:3 "name": "sf-marketplace"` and `hazarsozer/sf-marketplace` repo refs — that's the marketplace/repo id, NOT the plugin name.

### Test convention (ALL phases)
Per-module, never root (root pytest collides on duplicate `lib.tests.*` — pre-existing, do NOT "fix"):
```bash
( cd <skill-dir> && python3 -m pytest <tests-path> -q )      # most skills (Phases 1-3 use skills/sf-<verb>; Phase 5 uses skills/<verb> post-rename)
( python3 -m pytest lib/tests/test_sf_paths.py -q )          # repo-root lib/ (run from repo root; unaffected by rename)
( cd <skill-dir> && bash scripts/tests/<name>.sh )           # bash hermetic harnesses
```
The `block-no-verify` PreToolUse hook false-positives on the literal tokens `pre-commit`/`commit-msg`/`--no-verify` — keep them out of commit messages and bash.

### Worktree (maintainer instruction)
Execute this plan in a **separate git worktree** (`superpowers:using-git-worktrees`), not the primary checkout.

---

## File Structure (what each phase touches)

**Phase 1 — Python correctness (current `skills/sf-*` paths):**
- `lib/sf_paths.py` (HIGH frontmatter + LOW handle cap)
- `skills/sf-improve-skill/lib/budget.py` (MED KeyError)
- `skills/sf-wrap/lib/diff_plan.py` (MED framework_version via importlib; + delete dead helpers)
- `skills/sf-recall/lib/__init__.py` (MED stat race)
- `skills/sf-wrap/lib/apply.py` (LOW diagnostic count + LOW dead ternary)
- `skills/sf-insights/scripts/collect.py` (LOW decode fallback)

**Phase 2 — Doc / contract / consistency drift:**
- `CHANGELOG.md`, `docs/RELEASE_v1.0.0.md`, `docs/SHIP_CHECKLIST.md`, `README.md`
- `skills/sf-doctor/SKILL.md`, `skills/sf-update/SKILL.md`, `skills/wiki-migration/SKILL.md` (contract blocks)
- `skills/sf-update/SKILL.md`, `skills/sf-bootstrap-project/SKILL.md`, `.github/workflows/release.yml`, `skills/wiki-migration/schemas.schema.json` (feed remnants)
- `skills/sf-doctor/SKILL.md` + `skills/sf-doctor/reference.md` (output-schema refs)
- `wiki-skeleton/manifest.yaml` (alternatives/ removal)
- `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` (solo framing)

**Phase 3 — Security/privacy:**
- `skills/sf-doctor/scripts/check-env.sh` (+ new `scripts/tests/test_check_env.sh`)
- `skills/sf-insights/scripts/collect.py` (+ `scripts/tests/test_collect.py`)
- `skills/sf-doctor/scripts/check-permissions.sh`

**Phase 4 — Namespace rename (mechanical sweep, last):**
- Renames: 11 `skills/sf-*/` → `skills/*/` dirs (`wiki-migration` kept).
- Config: `.claude-plugin/plugin.json` (name), `.claude-plugin/marketplace.json` (plugin-entry name).
- Frontmatter: 11 `SKILL.md` `name:` flips.
- Functional refs: 3 data-dir scripts, `check-plugins.sh`, 13 Python path literals, shell test scripts (incl. the new `test_check_env.sh`), 2 CI invocations, 1 conformance glob.
- Doc: ~7 install-id lines, 3 migrate-wiki strings.

**Phase 5 — Re-verify + empirical confirm + version bump + re-publish:**
- Full test sweep (post-rename paths), `claude plugin validate --strict`, install + `/sf` autocomplete confirmation, `.claude-plugin/plugin.json` (version), `CHANGELOG.md` (release entry), `scripts/publish.sh --dry-run`, human-run publish.

---

# PHASE 1 — Python Correctness (current `skills/sf-*` paths)

> All fixes below were empirically verified RED→GREEN by the investigator at these exact paths. `lib/sf_paths.py` is at the repo root (NOT a skill dir). Lead with the one genuine HIGH.

### Task 1.1: [HIGH] `lib/sf_paths.py` — unterminated frontmatter accepts body `handle:` (+ handle length cap)

**Files:**
- Modify: `lib/sf_paths.py` (`_parse_field_from_frontmatter` ~262-279; `validate_handle` ~192-206)
- Test: `lib/tests/test_sf_paths.py`

- [ ] **Step 1: Write the failing tests**

Append to `lib/tests/test_sf_paths.py` (match the file's existing imports — `sf_paths`, `validate_handle`, `InvalidHandleError`, `pytest` are already imported there):

```python
def test_unterminated_frontmatter_handle_in_body_rejected():
    """A `handle:` line in a truncated body with NO closing --- must not be accepted."""
    assert sf_paths._parse_handle_from_frontmatter(
        "---\ntitle: x\nhandle: evil\nmore body\n"
    ) is None

def test_terminated_frontmatter_still_parses():
    assert sf_paths._parse_handle_from_frontmatter(
        "---\nhandle: good\n---\nbody\n"
    ) == "good"

def test_validate_handle_rejects_overlong():
    with pytest.raises(InvalidHandleError):
        validate_handle("a" * 50_000)

def test_validate_handle_accepts_50_char_boundary():
    validate_handle("a" + "b" * 49)  # exactly 50 chars
```

- [ ] **Step 2: Run to verify they fail**

Run: `( python3 -m pytest lib/tests/test_sf_paths.py -q )`
Expected: `test_unterminated_frontmatter_handle_in_body_rejected` FAILS (`'evil' is not None`); `test_validate_handle_rejects_overlong` FAILS (`DID NOT RAISE`).

- [ ] **Step 3: Fix the frontmatter parser**

Replace `_parse_field_from_frontmatter` with the fenced version (only accept a match when a closing `---` is actually reached):

```python
def _parse_field_from_frontmatter(text: str, field: str) -> str | None:
    """Generic frontmatter field reader. Returns the raw string value (sans quotes)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    prefix = f"{field}:"
    found: str | None = None
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            return found  # closing fence reached
        if found is None and stripped.startswith(prefix):
            value = stripped[len(prefix):].strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            found = value or None
    # No closing fence: the block is unterminated, so any match was in the body.
    return None
```

- [ ] **Step 4: Fix `validate_handle` (add length cap)**

In `validate_handle`, add a `len(value) > 50` clause to the existing guard. **Keep the existing `InvalidHandleError(...)` message verbatim** — only extend the condition:

```python
    if not isinstance(value, str) or len(value) > 50 or not HANDLE_RE.match(value):
        raise InvalidHandleError(...)  # keep the existing message argument unchanged
```

- [ ] **Step 5: Run to verify pass**

Run: `( python3 -m pytest lib/tests/test_sf_paths.py -q )`
Expected: PASS (investigator saw 48 passed total).

- [ ] **Step 6: Commit**

```bash
git add lib/sf_paths.py lib/tests/test_sf_paths.py
git commit -m "fix(sf_paths): reject body handle in unterminated frontmatter; cap handle length"
```

---

### Task 1.2: [MED] `skills/sf-improve-skill/lib/budget.py` — `KeyError` on partial pricing table

**Files:**
- Modify: `skills/sf-improve-skill/lib/budget.py` (`compute_usage_cost_usd` ~123-131)
- Test: `skills/sf-improve-skill/lib/tests/test_budget.py`

- [ ] **Step 1: Write the failing test**

Append to the existing `TestComputeUsageCost` class in `skills/sf-improve-skill/lib/tests/test_budget.py` (uses already-imported `ApiUsage`, `compute_usage_cost_usd`, `pytest`):

```python
    def test_missing_cache_rates_no_keyerror(self, tmp_path):
        """A pricing entry that omits cache_read/cache_creation must not crash;
        the missing cache rates contribute $0 rather than raising KeyError."""
        import json
        from ..budget import load_pricing_table
        data = {
            "valid_as_of": "2026-01-01",
            "pricing_usd_per_million_tokens": {"m": {"input": 1.0, "output": 2.0}},
            "default_model": "m",
            "alias_resolution": {},
        }
        path = tmp_path / "partial-pricing.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        table = load_pricing_table(path)
        usage = ApiUsage(
            input_tokens=1_000_000, output_tokens=0, cache_read_input_tokens=500_000
        )
        cost = compute_usage_cost_usd(usage, "m", table)
        assert cost == pytest.approx(1.0)  # 1M input × $1; cache_read counts as $0
```

- [ ] **Step 2: Run to verify it fails**

Run: `( cd skills/sf-improve-skill && python3 -m pytest lib/tests/test_budget.py -q )`
Expected: FAIL with `KeyError: 'cache_read'`.

- [ ] **Step 3: Fix the cost computation (guard the two cache keys)**

```python
    cost = (
        usage.input_tokens * rates["input"]
        + usage.output_tokens * rates["output"]
        + usage.cache_read_input_tokens * rates.get("cache_read", 0.0)
        + usage.cache_creation_input_tokens * rates.get("cache_creation", 0.0)
    ) / 1_000_000.0
```

- [ ] **Step 4: Run to verify pass**

Run: `( cd skills/sf-improve-skill && python3 -m pytest lib/tests/test_budget.py -q )`
Expected: PASS (investigator saw 34 passed total).

- [ ] **Step 5: Commit**

```bash
git add skills/sf-improve-skill/lib/budget.py skills/sf-improve-skill/lib/tests/test_budget.py
git commit -m "fix(budget): default missing cache rates to 0.0 instead of KeyError"
```

---

### Task 1.3: [MED] `skills/sf-wrap/lib/diff_plan.py` — resolve framework_version dynamically (+ delete dead helpers)

**Files:**
- Modify: `skills/sf-wrap/lib/diff_plan.py` (`_frontmatter_for` ~144-155; delete dead `_unified_diff_for_new_file` + `_unified_diff_for_append`)
- Test: `skills/sf-wrap/lib/tests/test_diff_plan.py`

> **Import caveat (verified):** `from lib.sf_paths import framework_version` FAILS here — this skill's own `lib/` package shadows the repo-root `lib/` under the per-module harness. Load `sf_paths.py` by file path via `importlib`. `Path(__file__).resolve().parents[3]` is the repo root from `skills/sf-wrap/lib/diff_plan.py`.

- [ ] **Step 1: Write the failing tests**

Append to `skills/sf-wrap/lib/tests/test_diff_plan.py`:

```python
class TestFrameworkVersionResolution:
    def test_frontmatter_uses_resolver_not_hardcoded(self, monkeypatch):
        """New-page frontmatter must reflect the resolved framework version,
        not a hardcoded '1.0.0'. Override via the highest-precedence env tier."""
        from ..diff_plan import _frontmatter_for
        monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_FRAMEWORK_VERSION", "9.9.9")
        fm = _frontmatter_for("decision", "Title", "2026-05-31")
        assert 'framework_version: "9.9.9"' in fm, fm

    def test_frontmatter_falls_back_when_unresolvable(self, monkeypatch):
        from ..diff_plan import _frontmatter_for
        monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_FRAMEWORK_VERSION", raising=False)
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
        fm = _frontmatter_for("decision", "Title", "2026-05-31")
        assert 'framework_version: "1.0.0"' in fm
```

- [ ] **Step 2: Run to verify it fails**

Run: `( cd skills/sf-wrap && python3 -m pytest lib/tests/test_diff_plan.py::TestFrameworkVersionResolution -q )`
Expected: `test_frontmatter_uses_resolver_not_hardcoded` FAILS — current code emits hardcoded `framework_version: "1.0.0"` regardless of the env override.

- [ ] **Step 3: Add the resolver + use it**

Add the helper near the top of `diff_plan.py` (after imports):

```python
def _framework_version() -> str:
    """Resolve framework version from the repo-root lib/sf_paths.py.

    Loaded by file path (not `import lib.sf_paths`) to avoid the name collision
    with this skill's own `lib/` package under the per-module test harness.
    Falls back to "1.0.0" if unreachable so frontmatter is never broken.
    """
    import importlib.util
    from pathlib import Path as _P
    try:
        root = _P(__file__).resolve().parents[3]
        spec = importlib.util.spec_from_file_location("_sf_paths_repo", root / "lib" / "sf_paths.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.framework_version()
    except Exception:
        return "1.0.0"
```

Then change the framework_version line in `_frontmatter_for`:

```python
-        f'framework_version: "1.0.0"\n'
+        f'framework_version: "{_framework_version()}"\n'
```

- [ ] **Step 4: Run to verify pass**

Run: `( cd skills/sf-wrap && python3 -m pytest lib/tests/test_diff_plan.py -q )`
Expected: PASS (the existing `test_decision_creates_new_page`/`test_context_md_create_when_missing` stay green because the test-env fallback is `"1.0.0"`).

- [ ] **Step 5: Delete the two dead helpers (Finding 6 — not a bug, dead code)**

`_unified_diff_for_new_file` and `_unified_diff_for_append` have **zero callers** (verified). Delete both functions entirely. (The real diff-building is inline in `_context_md_diff`, `_decision_or_pattern_create_diff`, `_log_append_diff`.)

- [ ] **Step 6: Run to verify nothing broke**

Run: `( cd skills/sf-wrap && python3 -m pytest lib/tests/test_diff_plan.py -q )`
Expected: PASS, same count (deletion is behavior-neutral — the helpers were uncalled).

- [ ] **Step 7: Commit**

```bash
git add skills/sf-wrap/lib/diff_plan.py skills/sf-wrap/lib/tests/test_diff_plan.py
git commit -m "fix(diff_plan): resolve framework_version dynamically; drop dead diff helpers"
```

---

### Task 1.4: [MED] `skills/sf-recall/lib/__init__.py` — unguarded `stat()` in sort key

**Files:**
- Modify: `skills/sf-recall/lib/__init__.py` (`grep_wiki` ~243-244)
- Test: `skills/sf-recall/lib/tests/test_recall.py`

- [ ] **Step 1: Write the failing test**

Append to the existing `TestGrepWiki` class in `skills/sf-recall/lib/tests/test_recall.py` (`Path` is already imported):

```python
    def test_concurrent_delete_during_sort_not_fatal(self, tmp_path, monkeypatch):
        """A file deleted between the scan and the mtime-sort must not crash grep_wiki
        (the sort key's stat() is the unguarded call in grep_wiki)."""
        from ..__init__ import grep_wiki
        wiki = tmp_path / "wiki"
        decisions = wiki / "decisions"
        decisions.mkdir(parents=True)
        (decisions / "a.md").write_text("---\ntitle: A\n---\n# A\n\nfoo here\n", encoding="utf-8")
        (decisions / "b.md").write_text("---\ntitle: B\n---\n# B\n\nfoo here\n", encoding="utf-8")
        real_stat = Path.stat
        def flaky_stat(self, *a, **k):
            if self.name == "a.md":
                raise OSError("simulated concurrent delete")
            return real_stat(self, *a, **k)
        monkeypatch.setattr(Path, "stat", flaky_stat)
        hits, _ = grep_wiki(wiki, "foo")  # must not raise
        assert len(hits) >= 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `( cd skills/sf-recall && python3 -m pytest lib/tests/test_recall.py -q )`
Expected: FAIL with `OSError: simulated concurrent delete` raised from the sort key.

- [ ] **Step 3: Fix the sort key (guard stat with a safe-mtime helper)**

Replace the sort line:

```python
    # Sort by score desc, then by mtime desc (newer wins ties). Guard stat()
    # so a file deleted between rglob and sort can't crash the call.
    def _safe_mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0
    raw_hits.sort(key=lambda t: (t[0], _safe_mtime(t[1].path)), reverse=True)
```

- [ ] **Step 4: Run to verify pass**

Run: `( cd skills/sf-recall && python3 -m pytest lib/tests/test_recall.py -q )`
Expected: PASS (investigator saw 26 passed total).

- [ ] **Step 5: Commit**

```bash
git add skills/sf-recall/lib/__init__.py skills/sf-recall/lib/tests/test_recall.py
git commit -m "fix(recall): guard stat() in grep_wiki sort key against concurrent delete"
```

---

### Task 1.5: [LOW] `skills/sf-wrap/lib/apply.py` — diagnostic count symmetry + dead ternary

**Files:**
- Modify: `skills/sf-wrap/lib/apply.py` (rollback diagnostic ~202-208; dead ternary ~123)
- Test: `skills/sf-wrap/lib/tests/test_apply.py`

> Corrected Finding 1 (diagnostic-only, LOW — rollback itself works) + Finding 8 (dead ternary). Extract a tiny pure helper to make the count cleanly unit-testable instead of the original fragile caplog test.

- [ ] **Step 1: Write the failing test**

Append to `skills/sf-wrap/lib/tests/test_apply.py`:

```python
def test_count_differing_includes_post_only_files():
    """A file present only in post (a surviving NEW file) must be counted —
    the rollback-incomplete diagnostic was previously asymmetric (pre-only)."""
    from ..apply import _count_differing
    assert _count_differing({"a.md": "h1"}, {"a.md": "h1", "leaked.md": "h2"}) == 1
    assert _count_differing({"a.md": "h1"}, {"a.md": "h1"}) == 0
    assert _count_differing({"a.md": "h1"}, {"a.md": "CHANGED"}) == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `( cd skills/sf-wrap && python3 -m pytest lib/tests/test_apply.py::test_count_differing_includes_post_only_files -q )`
Expected: FAIL with `ImportError`/`AttributeError` (`_count_differing` not defined yet).

- [ ] **Step 3: Add the symmetric helper and use it at the diagnostic site**

Add the helper:

```python
def _count_differing(pre: dict, post: dict) -> int:
    """Count files that differ between two wiki snapshots, counting files present
    in only one side (symmetric — a surviving NEW file in post must be counted)."""
    return sum(1 for k in (pre.keys() | post.keys()) if pre.get(k) != post.get(k))
```

Replace the inline `sum(...)` at the diagnostic site (~line 207):

```python
            if pre_snapshot != post_snapshot:
                logger.error(
                    "Rollback incomplete: %d files still differ from pre-apply state",
                    _count_differing(pre_snapshot, post_snapshot),
                )
```

- [ ] **Step 4: Collapse the dead ternary (~line 123)**

```python
-    rel = str(wiki_root) if not wiki_root.is_absolute() else str(wiki_root)
+    rel = str(wiki_root)
```

- [ ] **Step 5: Run to verify pass**

Run: `( cd skills/sf-wrap && python3 -m pytest lib/tests/test_apply.py -q )`
Expected: PASS — the new helper test passes and the existing rollback tests (investigator saw 7) stay green.

- [ ] **Step 6: Commit**

```bash
git add skills/sf-wrap/lib/apply.py skills/sf-wrap/lib/tests/test_apply.py
git commit -m "fix(apply): count post-only files in rollback diagnostic; drop dead ternary"
```

---

### Task 1.6: [LOW] `skills/sf-insights/scripts/collect.py` — lossy project-name fallback

**Files:**
- Modify: `skills/sf-insights/scripts/collect.py` (project fallback ~485-486)
- Test: `skills/sf-insights/scripts/tests/test_collect.py`

> NOTE: `collect.py` + `test_collect.py` are also edited in Phase 3 (Task 3.2, kickoff drop) at different lines (112/360-369/592-593). This task touches line ~486 only — no conflict, but do Phase 1 before Phase 3 cleanly.

- [ ] **Step 1: Write the failing test**

Append to `skills/sf-insights/scripts/tests/test_collect.py` (reuses the file's existing `SCRIPTS_DIR`, `write_jsonl`, `_rec`, `_assistant`, `REF_NOW`):

```python
class TestProjectFallbackNoCwd:
    def test_no_cwd_prefers_encoded_dir_over_lossy_decode(self, tmp_path):
        """When a record has neither project nor cwd, the fallback must NOT use the
        lossy decode (which collapses '-' to '/', turning 'my-app' into 'app').
        It should surface the unambiguous encoded dir name instead."""
        import sys
        if str(SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPTS_DIR))
        import collect as _collect
        claude = tmp_path / ".claude"
        proj = claude / "projects" / "-home-h-Dev-my-app"
        write_jsonl(proj / "s.jsonl", [
            _rec("user", sid="s", message={"role": "user", "content": "hi build"}),
            _assistant([{"type": "text", "text": "ok"}], sid="s"),
        ])
        data = _collect.collect(days=3650, claude_dir=str(claude), now=REF_NOW)
        assert len(data.sessions) == 1
        assert data.sessions[0].project != "app", "still using lossy decode → wrong basename"
        assert data.sessions[0].project == "-home-h-Dev-my-app"
```

- [ ] **Step 2: Run to verify it fails**

Run: `( cd skills/sf-insights && python3 -m pytest scripts/tests/test_collect.py::TestProjectFallbackNoCwd -q )`
Expected: FAIL — current code yields `project == "app"`.

- [ ] **Step 3: Fix the fallback (prefer cwd basename, then encoded dir_name; never lossy decode)**

```python
        if not facts.project:
            facts.project = _project_basename(facts.cwd) or dir_name
```

- [ ] **Step 4: Run to verify pass**

Run: `( cd skills/sf-insights && python3 -m pytest scripts/tests/test_collect.py -q )`
Expected: PASS (investigator saw 22 passed total).

- [ ] **Step 5: Commit**

```bash
git add skills/sf-insights/scripts/collect.py skills/sf-insights/scripts/tests/test_collect.py
git commit -m "fix(collect): surface encoded dir name instead of lossy project basename"
```

---

# PHASE 2 — Doc / Contract / Consistency Drift

> Mostly text edits — verified by grep, `claude plugin validate --strict`, and the schema validator (`skills/sf-doctor/scripts/check-schemas.sh`). Current `skills/sf-*` paths. (Item 9 — `sf-improve-skill` has no `eval/eval.json` — is a **documented, accepted exception**; NO action.)

### Task 2.1: [HIGH] Reconcile the page-type count to 15

**Files:**
- Modify: `CHANGELOG.md:49`, `CHANGELOG.md:74`, `docs/RELEASE_v1.0.0.md:35`

Source of truth: `skills/wiki-migration/schemas.json` registers **15** page types: `identity`, `master-index`, `project-index`, `licenses`, `project-main`, `project-state`, `project-roadmap`, `project-requirements`, `project-context`, `research`, `decision`, `pattern`, `log-entry`, `project-log-entry`, `skill`. CHANGELOG (says 11) omits `master-index`, `project-index`, `licenses`, `project-log-entry`. RELEASE says 16.

- [ ] **Step 1: CHANGELOG.md:49** — change `**11 page-types**` → `**15 page-types**` and the parenthetical list to include all 15:

```
- **Schema-versioning machinery** (`skills/wiki-migration/`, ADR-027): `schemas.json` registers **15 page-types** (identity, master-index, project-index, licenses, project-main, project-state, project-roadmap, project-requirements, project-context, research, decision, pattern, log-entry, project-log-entry, skill); `schemas.schema.json` + `verify.schema.json` validators; `MIGRATION_PATTERN.md` + `migrations/_template/`; snapshot retention (latest 3, `userConfig.snapshotRetain`, at `${CLAUDE_PLUGIN_DATA}/wiki-snapshots/`); predicate vocabulary v1.
```

- [ ] **Step 2: CHANGELOG.md:74** — `All **11 page-types**` → `All **15 page-types**`:

```
- All **15 page-types** start at schema version 1, supported_from 1, no migrations. Future MINOR/MAJOR releases will add migrations here. (The `feed-entry` page-type was removed pre-ship with the Activity Feed — RETIRED, not migrated, per ADR-031 + ADR-027.)
```

- [ ] **Step 3: docs/RELEASE_v1.0.0.md:35** — `16 page-types` → `15 page-types`:

```
- **Schema-versioned wiki pages** — 15 page-types registered at schema v1. Future versions ship migrations; your wiki stays readable.
```

- [ ] **Step 4: Verify + commit**

```bash
grep -rn '11 page-type\|16 page-type' CHANGELOG.md docs/RELEASE_v1.0.0.md   # expect: NO output
git add CHANGELOG.md docs/RELEASE_v1.0.0.md
git commit -m "docs: reconcile page-type count to 15 (matches schemas.json registry)"
```

---

### Task 2.2: [HIGH] Add `contract:` + `license:` to the 3 skills missing them

**Files:**
- Modify: `skills/sf-doctor/SKILL.md`, `skills/sf-update/SKILL.md`, `skills/wiki-migration/SKILL.md` (frontmatter)

> Template (from `skills/sf-wrap`, `skills/sf-insights`, `skills/sf-backup`): insert `version:` + `license:` right after `description:`, and a `contract:` block after `owner_module:`. The 3 targets currently use unquoted `framework_version: 1.0.0` — preserve unquoted for minimal diff. Each block was drafted from the skill's actual behavior. (Contract bodies reference `skills/wiki-migration/...` and relative `scripts/...` — both rename-stable.)

- [ ] **Step 1: `skills/sf-doctor/SKILL.md`** — after `description:` add `version: 0.1.0` + `license: MIT`; after `owner_module: sf-distribution` add a blank line + this block:

```yaml
contract:
  required_outputs:
    - "A human-readable report with five sections (ENVIRONMENT, PLUGINS, SCHEMA VERSIONS, FRAMEWORK UPDATE, BACKUP) plus a final summary line"
    - "With --permissions: a standalone read-only 'KEYS ON YOUR RING' audit (MCP servers by name+transport, allow/deny/ask tallies, broad-grant flags, plugins + hooks) that NEVER prints a secret/env/token/header value"
    - "With --json: machine-readable JSON of the same status sections + summary"
    - "Exit code 0 when no blocker (❌) is present; exit 1 only on a blocker"
  budgets:
    turns: 4
    files_written: 0
    duration_seconds: 60
  permissions:
    read:
      - "skills/wiki-migration/schemas.json"
      - "~/.startup-framework/wiki/**"
      - "~/.claude.json"
      - "~/.claude/settings.json"
      - "~/.claude/settings.local.json"
      - "hooks/hooks.json"
    write: []
    execute:
      - "scripts/check-env.sh"
      - "scripts/check-plugins.sh"
      - "scripts/check-schemas.sh"
      - "scripts/check-update.sh"
      - "scripts/check-backup.sh"
      - "scripts/check-permissions.sh"
      - "gh (read-only: gh api repos/<org>/sf-marketplace/contents/.claude-plugin/marketplace.json)"
  completion_conditions:
    - "All five status sections rendered (or a crashed check-script degraded to a per-section failure note without crashing the report)"
    - "Run is side-effect-free: nothing under the wiki or settings is created, modified, or deleted"
    - "With --permissions: no secret/env/token/header value appears anywhere in the output"
  output_paths: []
```

- [ ] **Step 2: `skills/sf-update/SKILL.md`** (MOST IMPORTANT — full wiki write + migrations) — add `version: 0.1.0` + `license: MIT` after `description:`, then this block after `owner_module:`:

```yaml
contract:
  required_outputs:
    - "A printed migration plan (per-page-type ordered migration chain) before any write"
    - "A pre-migration wiki snapshot under ${CLAUDE_PLUGIN_DATA}/wiki-snapshots/v<from>-pre-update-<ISO8601>/"
    - "Migrated wiki pages written to disk only after per-page verify.json PASS + diff approval, with frontmatter schema_version/framework_version bumped"
    - "An appended migration entry in wiki/log.md (snapshot path + update record)"
    - "A post-update /sf:doctor --post-update report; on new issues, an explicit no-auto-rollback message naming the snapshot path"
    - "On --dry-run: the plan only, with zero writes to wiki, snapshot dir, or marketplace"
  budgets:
    turns: 30
    files_written: 200
    duration_seconds: 600
  permissions:
    read:
      - "${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json"
      - "skills/wiki-migration/schemas.json"
      - "skills/wiki-migration/migrations/**"
      - "~/.startup-framework/wiki/**"
      - "${CLAUDE_PLUGIN_DATA}/wiki-snapshots/**"
    write:
      - "~/.startup-framework/wiki/**"
      - "~/.startup-framework/wiki/.git/**"
      - "${CLAUDE_PLUGIN_DATA}/wiki-snapshots/**"
    execute:
      - "scripts/version-compare.sh"
      - "scripts/snapshot.sh"
      - "scripts/restore.sh"
      - "scripts/prune-snapshots.sh"
      - "skills/wiki-migration/scripts/compute-migration-chain.sh"
      - "skills/wiki-migration/scripts/apply-migration.sh"
      - "skills/wiki-migration/scripts/verify-page.sh"
      - "git (in ~/.startup-framework/wiki/, only if a remote is configured)"
      - "gh (read-only: gh api repos/<org>/sf-marketplace/contents/.claude-plugin/plugin.json)"
  completion_conditions:
    - "Equal version → exits without snapshotting"
    - "A snapshot exists before any page is migrated"
    - "Every applied page passed verify.json and was approved (or --auto for MINOR additive only; MAJOR always prompts)"
    - "Failed/crashed pages were reverted from snapshot (ROLLBACK_PAGE) while other pages continued; snapshot retained"
    - "wiki/log.md has the appended migration entry and the post-update doctor report was printed"
    - "On --dry-run: no writes occurred anywhere"
  output_paths:
    - "~/.startup-framework/wiki/"
    - "${CLAUDE_PLUGIN_DATA}/wiki-snapshots/"
```

- [ ] **Step 3: `skills/wiki-migration/SKILL.md`** — add `version: 0.1.0` + `license: MIT` after `description:`, then this block after `owner_module:`:

```yaml
contract:
  required_outputs:
    - "For /sf:update PLANNING: a JSON migration plan of shape {page_type: [migration_id, ...]} computed from schemas.json"
    - "For /sf:update MIGRATING: each affected page transformed via its migrate.sh (scripted), migrate.md (LLM-driven), or both (hybrid)"
    - "For /sf:update VERIFYING: per-page PASS/FAIL from verify.json assertions (exit 0 all pass, 1 any fail, 2 missing inputs)"
    - "For /sf:doctor: read-only per-page drift status (up-to-date / migration-available / read-only-beyond-N+3) with zero writes"
  budgets:
    turns: 20
    files_written: 200
    duration_seconds: 300
  permissions:
    read:
      - "schemas.json"
      - "migrations/**"
      - "~/.startup-framework/wiki/**"
      - "${CLAUDE_PLUGIN_DATA}/wiki-snapshots/**"
    write:
      - "~/.startup-framework/wiki/**"
    execute:
      - "scripts/compute-migration-chain.sh"
      - "scripts/apply-migration.sh"
      - "scripts/verify-page.sh"
  completion_conditions:
    - "Under /sf:doctor: no file is created, modified, or deleted (read-only scan only)"
    - "Under /sf:update: page writes occur only when the /sf:update-owned snapshot already exists at ${CLAUDE_PLUGIN_DATA}/wiki-snapshots/<latest>/"
    - "verify-page.sh returned a clean exit code (0/1/2) for every migrated page"
  output_paths:
    - "~/.startup-framework/wiki/"
```

- [ ] **Step 4: Verify + commit**

```bash
python3 -c "import yaml; [yaml.safe_load(open(f).read().split('---')[1]) for f in ['skills/sf-doctor/SKILL.md','skills/sf-update/SKILL.md','skills/wiki-migration/SKILL.md']]; print('frontmatter OK')"
grep -L 'contract:' skills/sf-doctor/SKILL.md skills/sf-update/SKILL.md skills/wiki-migration/SKILL.md   # expect: NO output (all now have it)
claude plugin validate ./ --strict    # expect: OK
git add skills/sf-doctor/SKILL.md skills/sf-update/SKILL.md skills/wiki-migration/SKILL.md
git commit -m "docs(contract): add contract+license blocks to doctor, update, wiki-migration (ADR-011)"
```

---

### Task 2.3: [MED] Purge live feed remnants (ADR-031)

**Files:**
- Modify: `skills/sf-update/SKILL.md:174-175`, `skills/sf-bootstrap-project/SKILL.md:133`, `.github/workflows/release.yml:125-138`, `skills/wiki-migration/schemas.schema.json:56`

> Only the LIVE remnants below are touched. The ~60 other `feed` hits are legitimate historical/explanatory prose ("removed with the feed module") — **leave them**.

- [ ] **Step 1: `skills/sf-update/SKILL.md:174-175`** — delete the dead `### With sf-feed (feed-2)` subsection (both lines). The still-true git-push fact is already covered by the `COMMITTING` state in the state machine.

- [ ] **Step 2: `skills/sf-bootstrap-project/SKILL.md:133`** — delete the obsolete anti-pattern line (`Don't write to ~/.startup-framework/activity-feed/ … That's sf-feed's territory.`); its referent no longer exists.

- [ ] **Step 3: `.github/workflows/release.yml:125-138`** — delete the entire `Print Activity Feed announcement template` step. (`docs/RELEASE_v1.0.0.md:10` already states notifications go out-of-band via CHANGELOG + `/sf:doctor`.)

- [ ] **Step 4: `skills/wiki-migration/schemas.schema.json:56`** — remove dead `"sf-feed"` from the `owner_module` enum (a LIVE CI validator). First confirm no page declares it:

```bash
grep -rn '"owner_module": "sf-feed"\|owner_module: sf-feed' skills/wiki-migration/schemas.json skills/   # expect: NO output
```
Then:
```json
-          "enum": ["sf-onboarding", "sf-lifecycle", "sf-feed", "sf-distribution", "universal"],
+          "enum": ["sf-onboarding", "sf-lifecycle", "sf-distribution", "universal"],
```

- [ ] **Step 5: Verify + commit**

```bash
( cd skills/sf-doctor && bash scripts/tests/test_check_schemas.sh )    # schema validator still PASS
grep -rn 'With sf-feed\|Activity Feed announcement\|activity-feed/' skills/ .github/   # expect: NO output
git add -A && git commit -m "docs: purge live Activity Feed remnants (ADR-031); drop sf-feed from owner_module enum"
```

---

### Task 2.4: [MED] Fix dangling `output-schema.json` references

**Files:**
- Modify: `skills/sf-doctor/SKILL.md:147`, `skills/sf-doctor/reference.md:5`, `skills/sf-doctor/reference.md:202`

> `output-schema.json` does not exist and no `--json` renderer ships; the eval does NOT assert it. Point the refs at the inline schema in `reference.md` (don't create an unshipped artifact).

- [ ] **Step 1: SKILL.md:147**
```
-- `--json` output is valid JSON conforming to `output-schema.json`
+- `--json` output is valid JSON conforming to the `--json` output schema sketched in `reference.md` § "`--json` output schema"
```

- [ ] **Step 2: reference.md:5**
```
-- The `--json` mode's `output-schema.json`
+- The `--json` mode's output schema (defined inline below in § "`--json` output schema")
```

- [ ] **Step 3: reference.md:202**
```
-See `output-schema.json` in this same skill directory. Roughly:
+The `--json` mode emits this shape (canonical schema; there is no separate schema file in v1):
```

- [ ] **Step 4: Verify + commit**
```bash
grep -rn 'output-schema.json' skills/sf-doctor/   # expect: NO output
git add skills/sf-doctor/SKILL.md skills/sf-doctor/reference.md
git commit -m "docs(doctor): point --json refs at inline schema (no output-schema.json file ships)"
```

---

### Task 2.5: [MED] Remove the orphan `alternatives/` skeleton entry

**Files:**
- Modify: `wiki-skeleton/manifest.yaml:60-63`

> `alternatives/` is stamped by `/sf:install` but has no registered page-type, no template, no consumer — exactly the drift `/sf:doctor` is meant to catch. Remove it (keeps the page-type count at 15).

- [ ] **Step 1: Confirm no consumer**
```bash
grep -rn 'wiki/alternatives\|alternatives/' --include='*.py' --include='*.sh' --include='*.json' --include='*.yaml' --include='*.md' . | grep -v 'wiki-skeleton/manifest.yaml'   # expect: NO functional output
```

- [ ] **Step 2: Delete the 4-line entry (`manifest.yaml:60-63`)**
```yaml
      - path: "alternatives/"
        type: directory
        write_rule: create_if_missing
        min_framework_version: "1.0.0"
```

- [ ] **Step 3: Verify + commit**
```bash
grep -n 'alternatives' wiki-skeleton/manifest.yaml   # expect: NO output
git add wiki-skeleton/manifest.yaml
git commit -m "fix(skeleton): remove orphan alternatives/ dir (no registered page-type)"
```

---

### Task 2.6: [MED] Reconcile the CHANGELOG date

**Files:**
- Modify: `CHANGELOG.md:23`, `docs/SHIP_CHECKLIST.md:290`

> CHANGELOG says 2026-05-30, SHIP_CHECKLIST pre-stamp says 2026-05-29; today is 2026-05-31. (Note: Phase 5 ships as 1.1.0, so the [1.0.0] line is historical — align it anyway; Phase 5 dates the new [1.1.0] entry to ship day.)

- [ ] **Step 1: CHANGELOG.md:23**
```
-## [1.0.0] — 2026-05-30
+## [1.0.0] — 2026-05-31
```

- [ ] **Step 2: SHIP_CHECKLIST.md:290** — update the pre-stamped reference to match:
```
> ⚠️ **DATE FOOT-GUN — read before tagging.** `CHANGELOG.md`'s `## [1.0.0]` line is pre-stamped
> **2026-05-31**. If you are tagging on any **later** day, **edit that date to today first** — otherwise
```

- [ ] **Step 3: Commit**
```bash
git add CHANGELOG.md docs/SHIP_CHECKLIST.md
git commit -m "docs: align CHANGELOG [1.0.0] date and SHIP_CHECKLIST pre-stamp to 2026-05-31"
```

---

### Task 2.7: [LOW] Fix the README Claude Code version floor

**Files:**
- Modify: `README.md:57`

> The enforced floor is `1.0.33` (in `check-env.sh:46`, `sf-doctor/SKILL.md:59`, `sf-install/references/stage-1-environment.md:9`). README's `2.1.154` is the dev baseline, mis-stated as the install requirement.

- [ ] **Step 1: README.md:57**
```
-- **Claude Code** ≥ 2.1.154 (run `claude --version`; update with `npm i -g @anthropic-ai/claude-code@latest` or `brew upgrade claude-code`).
+- **Claude Code** ≥ 1.0.33 (run `claude --version`; update with `npm i -g @anthropic-ai/claude-code@latest` or `brew upgrade claude-code`).
```

- [ ] **Step 2: Commit**
```bash
git add README.md
git commit -m "docs(readme): correct CC version floor to the enforced 1.0.33"
```

---

### Task 2.8: [LOW] Replace friend-group framing with solo-first

**Files:**
- Modify: `.claude-plugin/plugin.json` (description line 6, keywords line 17), `.claude-plugin/marketplace.json` (descriptions lines 4 & 14, keywords line 25)

> README/CHANGELOG positioning is "solo-first." Swap the framing tokens only (surgical — don't rewrite whole descriptions).

- [ ] **Step 1: Token swaps**

| File:line | Change |
|---|---|
| `plugin.json:6` (description) | `Per-friend` → `Per-builder` |
| `plugin.json:17` (keywords) | `"friend-group"` → `"solo-builder"` |
| `marketplace.json:4` (top description) | `private friend-group distribution` → `solo-first private distribution`; `Per-friend` → `Per-builder` |
| `marketplace.json:14` (plugin description) | `Per-friend` → `Per-builder` |
| `marketplace.json:25` (keywords) | `"friend-group"` → `"solo-builder"` |

Leave `marketplace.json:3 "name": "sf-marketplace"` and `hazarsozer/sf-marketplace` untouched.

- [ ] **Step 2: Verify + commit**
```bash
grep -rn 'friend' .claude-plugin/   # expect: NO output
claude plugin validate ./ --strict   # expect: OK
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "docs(manifest): solo-first framing (drop friend-group remnants)"
```

---

# PHASE 3 — Security / Privacy Hardening (current `skills/sf-*` paths)

### Task 3.1: [MED] `check-env.sh` leaks raw `OTEL_EXPORTER_OTLP_ENDPOINT`

**Files:**
- Modify: `skills/sf-doctor/scripts/check-env.sh` (~line 144)
- Test: `skills/sf-doctor/scripts/tests/test_check_env.sh` (**NEW**)

> OTLP endpoints (Grafana/Honeycomb/Datadog) routinely embed basic-auth or a token query param. The script must report presence (`configured`), not the value — mirroring how `ANTHROPIC_API_KEY` emits `set`, not the key.

- [ ] **Step 1: Write the failing test (new hermetic harness)**

Create `skills/sf-doctor/scripts/tests/test_check_env.sh`. The `CHECK_SCRIPT` path is computed relative to the test's own location (`$SCRIPT_DIR/..`) so it survives the Phase 4 dir rename without edits:

```bash
#!/usr/bin/env bash
# test_check_env.sh — hermetic pin tests for the /sf:doctor ENVIRONMENT section.
# SECURITY guarantee: when OTEL_EXPORTER_OTLP_ENDPOINT is set, the raw endpoint
# URL (which can embed basic-auth or a token) is NEVER printed; the otel line
# reports presence ("configured"), mirroring ANTHROPIC_API_KEY's "set".

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK_SCRIPT="$(cd "$SCRIPT_DIR/.." && pwd)/check-env.sh"   # rename-stable (relative to this test)

PASS_COUNT=0
FAIL_COUNT=0
pass() { printf '\033[32m  ✓ PASS\033[0m  %s\n' "$1"; PASS_COUNT=$((PASS_COUNT+1)); }
fail() { printf '\033[31m  ✗ FAIL\033[0m  %s\n' "$1"; FAIL_COUNT=$((FAIL_COUNT+1)); }

OTEL_SECRET_URL="https://u5er:sk-FAKE-OTEL-TOKEN-9999@otlp.example.com/v1/traces?token=FAKE-OTEL-TOKEN-9999"

echo "▶ Scenario A — OTLP endpoint set: 'configured' shown, raw URL never printed"
OUT_A="$(OTEL_EXPORTER_OTLP_ENDPOINT="$OTEL_SECRET_URL" bash "$CHECK_SCRIPT" 2>&1)"; RC_A=$?
[[ $RC_A -eq 0 ]] && pass "exits 0" || fail "expected exit 0, got $RC_A"
echo "$OUT_A" | grep -q '^otel|ok|configured|' \
  && pass "otel reported as 'configured' when endpoint is set" \
  || fail "expected line 'otel|ok|configured|'"
if echo "$OUT_A" | grep -Fq "$OTEL_SECRET_URL"; then
  fail "SECRET LEAK — raw OTLP endpoint URL appeared in output"
elif echo "$OUT_A" | grep -Fq "FAKE-OTEL-TOKEN-9999"; then
  fail "SECRET LEAK — embedded OTLP token appeared in output"
else
  pass "raw OTLP endpoint URL + embedded token both absent from output"
fi

echo
echo "▶ Scenario B — OTLP endpoint unset: skip status"
OUT_B="$(env -u OTEL_EXPORTER_OTLP_ENDPOINT bash "$CHECK_SCRIPT" 2>&1)"; RC_B=$?
[[ $RC_B -eq 0 ]] && pass "exits 0" || fail "expected exit 0, got $RC_B"
echo "$OUT_B" | grep -q '^otel|skip|' \
  && pass "otel reported as skip when endpoint unset" \
  || fail "expected 'otel|skip|' line"

echo
echo "═══════════════════════════════════════════════════════════════"
if (( FAIL_COUNT == 0 )); then
  printf '\033[32m  check-env pin tests: %d/%d PASS\033[0m\n' "$PASS_COUNT" "$((PASS_COUNT+FAIL_COUNT))"
  exit 0
else
  printf '\033[31m  check-env pin tests: %d FAIL / %d total\033[0m\n' "$FAIL_COUNT" "$((PASS_COUNT+FAIL_COUNT))"
  exit 1
fi
```

- [ ] **Step 2: Run to verify it fails**

Run: `( cd skills/sf-doctor && bash scripts/tests/test_check_env.sh )`
Expected: Scenario A FAILS twice — no `otel|ok|configured|` line (current line is `otel|ok|https://u5er:...|`), and the SECRET-LEAK assertion fires (raw URL + token present).

- [ ] **Step 3: Fix `check-env.sh` (~line 144)**

```bash
 if [[ -n "${OTEL_EXPORTER_OTLP_ENDPOINT:-}" ]]; then
-  emit "otel" "ok" "${OTEL_EXPORTER_OTLP_ENDPOINT}" ""
+  emit "otel" "ok" "configured" ""
 else
   emit "otel" "skip" "" "no OTLP endpoint configured (optional)"
 fi
```

- [ ] **Step 4: Run to verify pass**

Run: `( cd skills/sf-doctor && bash scripts/tests/test_check_env.sh )`
Expected: all PASS; line is `otel|ok|configured|`; URL/token gone.

- [ ] **Step 5: Commit**

```bash
chmod +x skills/sf-doctor/scripts/tests/test_check_env.sh
git add skills/sf-doctor/scripts/check-env.sh skills/sf-doctor/scripts/tests/test_check_env.sh
git commit -m "fix(doctor): report OTLP endpoint as configured, never the raw URL (secret leak)"
```

---

### Task 3.2: [MED] `collect.py` forwards verbatim first user message (`kickoff`) — drop the field

**Files:**
- Modify: `skills/sf-insights/scripts/collect.py` (field ~line 112; user-branch capture ~360-369; render ~592-593)
- Test: `skills/sf-insights/scripts/tests/test_collect.py`

> Decision: DROP the field (not redact). It's redundant with `topics` (which already distills the same first-message content in bounded form), feeds no aggregate, and dropping removes the whole leak class with less code. The `## SESSIONS` block is piped to the synthesis LLM, so a pasted secret in message #1 currently lands in model context.

- [ ] **Step 1: Write the failing test**

Append to `skills/sf-insights/scripts/tests/test_collect.py` (uses `collect`, `write_jsonl`, `_rec`, `_assistant`, `REF_NOW`, `Path` — all already imported):

```python
class TestKickoffSecretSafety:
    SECRET = "sk-ant-api03-FAKESECRET-DO-NOT-EMIT-0123456789"

    def _seed_secret_first_message(self, tmp_path: Path) -> Path:
        claude = tmp_path / ".claude"
        proj = claude / "projects" / "-home-hsozer-Dev-app"
        lines = [
            _rec(
                "user",
                sid="s",
                cwd="/home/hsozer/Dev/app",
                message={
                    "role": "user",
                    "content": f"Use my key {self.SECRET} to call the API and debug this",
                },
            ),
            _assistant([{"type": "tool_use", "name": "Bash", "input": {}}], sid="s"),
        ]
        write_jsonl(proj / "s.jsonl", lines)
        return claude

    def test_secret_in_first_message_absent_from_output(self, tmp_path):
        claude = self._seed_secret_first_message(tmp_path)
        out = collect.render(
            collect.collect(days=3650, claude_dir=str(claude), now=REF_NOW)
        )
        assert self.SECRET not in out          # credential must not reach the LLM-fed block
        assert "kickoff" not in out            # the verbatim-echo line is gone entirely

    def test_session_facts_has_no_kickoff_field(self, tmp_path):
        assert not hasattr(collect.SessionFacts(), "kickoff")
```

- [ ] **Step 2: Run to verify it fails**

Run: `( cd skills/sf-insights && python3 -m pytest scripts/tests/test_collect.py::TestKickoffSecretSafety -q )`
Expected: FAIL — the rendered `kickoff` line contains the secret; `hasattr(..., "kickoff")` is True.

- [ ] **Step 3: Remove the field (3 surgical deletions)**

3a. Delete the field declaration (~line 112) from `SessionFacts`:
```python
    kickoff: str = ""  # first user-text snippet (bounded)
```

3b. In the `if rtype == "user":` branch (~360-369), delete ONLY the kickoff-capture block (leave everything else in the branch exactly as-is):
```python
                if not facts.kickoff:
                    cleaned = _TAG_RE.sub(" ", text).strip()
                    if cleaned:
                        facts.kickoff = cleaned[:160]
```

3c. In `render()` (~592-593), delete the emit lines:
```python
        if s.kickoff:
            lines.append(f"- kickoff: {s.kickoff}")
```

- [ ] **Step 4: Fix the now-stale existing assertion**

An existing test asserts `sf.kickoff` (~line 232) and will `AttributeError` after the field is gone. **Delete that single line** — an identical `assert "postgres" in sf.topic_counts` two lines above already covers the first-message-content intent.

- [ ] **Step 5: Run to verify pass**

Run: `( cd skills/sf-insights && python3 -m pytest scripts/tests/test_collect.py -q )`
Expected: PASS (the new class + the existing suite; `TestProjectFallbackNoCwd` from Task 1.6 also stays green).

- [ ] **Step 6: Commit**

```bash
git add skills/sf-insights/scripts/collect.py skills/sf-insights/scripts/tests/test_collect.py
git commit -m "fix(collect): drop kickoff field (verbatim first message could leak a secret to the LLM)"
```

---

### Task 3.3: [LOW] `check-permissions.sh` fallback can print a full project path

**Files:**
- Modify: `skills/sf-doctor/scripts/check-permissions.sh` (~line 219)

> The `or path` fallback fires on a degenerate key (e.g. `"/"`) and dumps the absolute path. Reduce it to a single path component so it never discloses the full filesystem layout.

- [ ] **Step 1: Fix line 219**

```python
-        label = os.path.basename(path.rstrip("/")) or path
+        label = os.path.basename(path.rstrip("/")) or os.path.basename(os.path.dirname(path.rstrip("/"))) or "(root)"
```
Behavior: normal key `/home/u/Dev/proj-a` → `proj-a` (unchanged); degenerate `"/"` → `(root)`; never the full path.

- [ ] **Step 2: Verify (existing harness stays green) + commit**

```bash
( cd skills/sf-doctor && bash scripts/tests/test_check_permissions.sh )   # expect: PASS (Scenario A's proj-a assertion still holds)
git add skills/sf-doctor/scripts/check-permissions.sh
git commit -m "fix(doctor): never print full project path in permissions fallback label"
```
> Optional regression pin (LOW): add a fixture project keyed `"/"` to `test_check_permissions.sh` asserting the output contains neither a home path nor an empty label.

---

# PHASE 4 — Namespace Rename (`startup-framework` → `sf`)

> **Nature:** mechanical transformation + verification gate, not red-green TDD. Runs AFTER Phases 1–3, so it `git mv`s the already-fixed files (the body fixes travel with the move). The "test" is: the suites stay green at the new paths, stale-ref greps return empty, and `claude plugin validate --strict` passes. The empirical `/sf` autocomplete confirmation happens in Phase 5 (install-time, pre-publish).

### Task 4.1: Rename the 11 skill directories + flip `SKILL.md` `name:` fields

**Files:**
- Rename (git mv): all 11 `skills/sf-*/` dirs below. **Keep `skills/wiki-migration/`.**
- Modify: the `name:` line in each renamed dir's `SKILL.md`.

- [ ] **Step 1: git mv the 11 directories**

```bash
cd "$(git rev-parse --show-toplevel)"
git mv skills/sf-backup            skills/backup
git mv skills/sf-bootstrap-project skills/bootstrap-project
git mv skills/sf-doctor            skills/doctor
git mv skills/sf-improve-skill     skills/improve-skill
git mv skills/sf-insights          skills/insights
git mv skills/sf-install           skills/install
git mv skills/sf-interview         skills/interview
git mv skills/sf-note              skills/note
git mv skills/sf-recall            skills/recall
git mv skills/sf-update            skills/update
git mv skills/sf-wrap              skills/wrap
```

- [ ] **Step 2: Flip the `name:` field in each renamed SKILL.md**

Each `skills/<verb>/SKILL.md` line 2 currently reads `name: sf-<verb>`. Change to `name: <verb>`:

| File | Before | After |
|---|---|---|
| `skills/backup/SKILL.md` | `name: sf-backup` | `name: backup` |
| `skills/bootstrap-project/SKILL.md` | `name: sf-bootstrap-project` | `name: bootstrap-project` |
| `skills/doctor/SKILL.md` | `name: sf-doctor` | `name: doctor` |
| `skills/improve-skill/SKILL.md` | `name: sf-improve-skill` | `name: improve-skill` |
| `skills/insights/SKILL.md` | `name: sf-insights` | `name: insights` |
| `skills/install/SKILL.md` | `name: sf-install` | `name: install` |
| `skills/interview/SKILL.md` | `name: sf-interview` | `name: interview` |
| `skills/note/SKILL.md` | `name: sf-note` | `name: note` |
| `skills/recall/SKILL.md` | `name: sf-recall` | `name: recall` |
| `skills/update/SKILL.md` | `name: sf-update` | `name: update` |
| `skills/wrap/SKILL.md` | `name: sf-wrap` | `name: wrap` |

> `skills/wiki-migration/SKILL.md` `name: wiki-migration` is **unchanged**.

- [ ] **Step 3: Sanity-check + commit**

```bash
ls -d skills/*/        # expect: backup bootstrap-project doctor improve-skill insights install interview note recall update wrap wiki-migration
grep -rn '^name: sf-' skills/*/SKILL.md    # expect: NO output
git add -A
git commit -m "refactor(ns): rename 11 skill dirs to drop sf- prefix; flip SKILL.md name fields"
```

---

### Task 4.2: Flip the plugin `name` in both manifests

**Files:**
- Modify: `.claude-plugin/plugin.json:3`
- Modify: `.claude-plugin/marketplace.json:12` (the plugin **entry** name, NOT the top-level marketplace name on line 3)

- [ ] **Step 1: plugin.json**
```
# .claude-plugin/plugin.json line 3
-  "name": "startup-framework",
+  "name": "sf",
```
Leave `displayName` ("Startup Framework"), `homepage`, `repository` unchanged.

- [ ] **Step 2: marketplace.json**
```
# .claude-plugin/marketplace.json line 12 (inside plugins[0])
-      "name": "startup-framework",
+      "name": "sf",
```
**Leave line 3 `"name": "sf-marketplace"` UNCHANGED.**

- [ ] **Step 3: Verify + commit**
```bash
grep -n '"name"' .claude-plugin/plugin.json .claude-plugin/marketplace.json
# plugin.json → "sf"; marketplace.json line 3 → "sf-marketplace"; line 12 → "sf"
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "refactor(ns): set plugin name to sf in both manifests"
```

---

### Task 4.3: Functional refs D1 — plugin data-dir literals (`sf-sf-marketplace`)

**Files:**
- Modify: `skills/update/scripts/snapshot.sh:24`, `skills/update/scripts/restore.sh:23`, `skills/update/scripts/prune-snapshots.sh:17`
- Modify: `docs/RECOVERY.md` (lines ~80,81,95,102,115,170 — doc mirrors; RECOVERY.md ships)

- [ ] **Step 1: Update the three script fallbacks** — `.../data/startup-framework-sf-marketplace}` → `.../data/sf-sf-marketplace}` in each.

- [ ] **Step 2: Update the RECOVERY.md mirrors**
```bash
grep -n 'startup-framework-sf-marketplace' docs/RECOVERY.md   # replace each with sf-sf-marketplace
```

- [ ] **Step 3: Local data-migration note (one-time, maintainer)**
```bash
OLD="$HOME/.claude/data/startup-framework-sf-marketplace"
NEW="$HOME/.claude/data/sf-sf-marketplace"
[ -d "$OLD" ] && [ ! -e "$NEW" ] && mv "$OLD" "$NEW" && echo "migrated plugin data dir" || echo "nothing to migrate"
```
(Verify the base path with `ls ~/.claude/data/`. Local one-time op, not shipped.)

- [ ] **Step 4: Verify + commit**
```bash
grep -rn 'startup-framework-sf-marketplace' skills/ docs/   # expect: NO output
git add -A && git commit -m "refactor(ns): update plugin-data-dir literals to sf-sf-marketplace"
```

---

### Task 4.4: Functional refs D2 — doctor plugin-cache lookup

**Files:**
- Modify: `skills/doctor/scripts/check-plugins.sh:35,36,51,53`

- [ ] **Step 1: Update the cache-dir lookups + install hint**
```bash
# line 35:  [[ -d "$mkt_dir/startup-framework" ]] || continue   →   "$mkt_dir/sf"
# line 36:  for ver_dir in "$mkt_dir/startup-framework"/*/; do   →   "$mkt_dir/sf"/*/
# line 51:  emit "startup-framework" "ok" ...                    →   emit "sf" "ok" ...
# line 53:  ... "→ /plugin install startup-framework@sf-marketplace"  →  "→ /plugin install sf@sf-marketplace"
```
(Also update the comment on line ~7 listing plugin names.)

- [ ] **Step 2: Verify + commit**
```bash
grep -n 'startup-framework' skills/doctor/scripts/check-plugins.sh   # expect: NO output
git add skills/doctor/scripts/check-plugins.sh
git commit -m "refactor(ns): point doctor plugin-cache lookup at sf"
```

---

### Task 4.5: Functional refs D3 — 13 Python path-segment literals

**Files:**
- Modify: `skills/install/tests/integration/test_daily_loop_e2e.py:146,182`
- Modify: `skills/improve-skill/lib/tests/test_eval_runner.py:47,48,49,50`
- Modify: `skills/improve-skill/lib/tests/test_preflight.py:120,121,122,123,126,127,128`

- [ ] **Step 1: Replace each `"skills" / "sf-X"` Path segment with the bare verb**

| File:line | Before segment | After segment |
|---|---|---|
| `test_daily_loop_e2e.py:146` | `"skills" / "sf-note" / "lib"` | `"skills" / "note" / "lib"` |
| `test_daily_loop_e2e.py:182` | `"skills" / "sf-wrap" / "lib"` | `"skills" / "wrap" / "lib"` |
| `test_eval_runner.py:47` | `"skills" / "sf-install"` | `"skills" / "install"` |
| `test_eval_runner.py:48` | `"sf-interview"` | `"interview"` |
| `test_eval_runner.py:49` | `"sf-bootstrap-project"` | `"bootstrap-project"` |
| `test_eval_runner.py:50` | `"sf-wrap"` | `"wrap"` |
| `test_preflight.py:120` | `"skills" / "sf-install" / "eval"` | `"skills" / "install" / "eval"` |
| `test_preflight.py:121` | `"sf-interview"` | `"interview"` |
| `test_preflight.py:122` | `"sf-bootstrap-project"` | `"bootstrap-project"` |
| `test_preflight.py:123` | `"sf-wrap"` | `"wrap"` |
| `test_preflight.py:126` | `"sf-backup"` | `"backup"` |
| `test_preflight.py:127` | `"sf-note"` | `"note"` |
| `test_preflight.py:128` | `"sf-recall"` | `"recall"` |

- [ ] **Step 2: Verify + commit**
```bash
( cd skills/improve-skill && python3 -m pytest lib/tests/test_eval_runner.py lib/tests/test_preflight.py -q )   # expect: PASS
( cd skills/install && python3 -m pytest tests/integration/test_daily_loop_e2e.py -q )                          # expect: PASS
git add -A && git commit -m "refactor(ns): update Python skill-path literals to bare verbs"
```

---

### Task 4.6: Functional refs D4 — shell test-script paths

**Files:**
- Modify: `skills/update/scripts/tests/test_snapshot_inode_safety.sh:18`
- Modify: `skills/doctor/scripts/tests/test_check_permissions.sh:22`
- Modify: `skills/doctor/scripts/tests/test_check_schemas.sh:16` (leave `:17` wiki-migration ref)
- Modify: `skills/doctor/scripts/tests/test_check_plugins.sh:19`
- Modify: `tests/integration/migration-dogfood.sh:137,247`

> `test_check_env.sh` (added in Task 3.1) uses a **relative** `CHECK_SCRIPT` path, so it needs NO edit. Catch any other stragglers with the grep in Step 2.

- [ ] **Step 1: Update each `$REPO_ROOT/skills/sf-X/...` path** (`sf-update`→`update`, `sf-doctor`→`doctor`; leave `wiki-migration` refs):

| File:line | Before | After |
|---|---|---|
| `test_snapshot_inode_safety.sh:18` | `…/skills/sf-update/scripts/snapshot.sh` | `…/skills/update/scripts/snapshot.sh` |
| `test_check_permissions.sh:22` | `…/skills/sf-doctor/scripts/check-permissions.sh` | `…/skills/doctor/…` |
| `test_check_schemas.sh:16` | `…/skills/sf-doctor/scripts/check-schemas.sh` | `…/skills/doctor/…` |
| `test_check_plugins.sh:19` | `…/skills/sf-doctor/scripts/check-plugins.sh` | `…/skills/doctor/…` |
| `migration-dogfood.sh:137` | `…/skills/sf-update/scripts/snapshot.sh` | `…/skills/update/…` |
| `migration-dogfood.sh:247` | `…/skills/sf-update/scripts/restore.sh` | `…/skills/update/…` |

- [ ] **Step 2: Grep-driven safety sweep + run + commit**
```bash
grep -rn 'skills/sf-\(doctor\|update\)' skills/*/scripts/tests tests/integration   # fix any remaining hits
( cd skills/update && bash scripts/tests/test_snapshot_inode_safety.sh )
( cd skills/doctor && for t in scripts/tests/*.sh; do echo "== $t =="; bash "$t" || break; done )
git add -A && git commit -m "refactor(ns): update shell test-script skill paths to bare verbs"
```

---

### Task 4.7: Functional refs D6 + D7 — CI invocations + conformance glob

**Files:**
- Modify: `.github/workflows/validate.yml:141`, `.github/workflows/release.yml:82`
- Modify: `tests/integration/schema-conformance/conformance.py:81`

- [ ] **Step 1: CI version-compare invocations (D6)** — both files: `bash skills/sf-update/scripts/version-compare.sh --self-test` → `skills/update/scripts/...`. (Leave `skills/wiki-migration/...` paths.)

- [ ] **Step 2: Conformance glob (D7)** — `conformance.py:81`: `skills/sf-bootstrap-project/templates/**/*.md.tmpl` → `skills/bootstrap-project/templates/**/*.md.tmpl`. (Leave `skills/wiki-migration/...` on lines 35,90.)

- [ ] **Step 3: Verify + commit**
```bash
bash skills/update/scripts/version-compare.sh --self-test    # expect: self-test PASS
( cd tests/integration/schema-conformance && python3 conformance.py )   # expect: PASS
git add -A && git commit -m "refactor(ns): update CI + conformance skill paths to bare verbs"
```

---

### Task 4.8: Install-id doc lines (F) + migrate-wiki strings (C)

**Files:**
- Modify (install id `startup-framework@` → `sf@`): `README.md:69,76`, `CHANGELOG.md:37`, `docs/RECOVERY.md:36`, `docs/RELEASE_v1.0.0.md:45`, `docs/SHIP_CHECKLIST.md:245`
- Modify (migrate-wiki → wiki-migration): `skills/install/SKILL.md:80`, `skills/bootstrap-project/references/template-loader.md:103`, `wiki/decisions/017-per-friend-wiki-scope.md:111`

- [ ] **Step 1: Update install-id lines** — `/plugin install startup-framework@sf-marketplace` → `/plugin install sf@sf-marketplace`:
```bash
grep -rn 'install startup-framework@sf-marketplace' README.md CHANGELOG.md docs/
```
**Leave `/plugin marketplace add hazarsozer/sf-marketplace` lines UNCHANGED.**

- [ ] **Step 2: Fix the 3 migrate-wiki doc strings** — `/sf:migrate-wiki` → `/sf:wiki-migration` (the dir's real command verb).

- [ ] **Step 3: Verify + commit**
```bash
grep -rn 'install startup-framework@sf-marketplace' README.md CHANGELOG.md docs/   # expect: NO output
grep -rn '/sf:migrate-wiki' skills/ wiki/                                          # expect: NO output
git add -A && git commit -m "docs(ns): update install id to sf@sf-marketplace; fix migrate-wiki -> wiki-migration"
```

---

### Task 4.9: Phase 4 verification gate

**Files:** none (verification only).

- [ ] **Step 1: Stale-reference greps must be empty (functional surface)**
```bash
cd "$(git rev-parse --show-toplevel)"
grep -rEn 'skills/sf-(backup|bootstrap-project|doctor|improve-skill|insights|install|interview|note|recall|update|wrap)' \
  --include='*.py' --include='*.sh' --include='*.json' --include='*.yaml' --include='*.yml' .   # expect: NO output
grep -rn 'startup-framework-sf-marketplace' skills/ docs/        # expect: NO output
grep -rn 'install startup-framework@sf-marketplace' .            # expect: NO output
```
(Doc `/sf:` strings and `skills/wiki-migration/...` refs are intentionally retained.)

- [ ] **Step 2: All per-module suites green at new paths**
```bash
( python3 -m pytest lib/tests/test_sf_paths.py -q )
( cd skills/wrap          && python3 -m pytest lib/tests -q )
( cd skills/insights      && python3 -m pytest scripts/tests -q )
( cd skills/improve-skill && python3 -m pytest lib/tests -q )
( cd skills/recall        && python3 -m pytest lib/tests -q )
( cd skills/note          && python3 -m pytest lib/tests -q )
( cd skills/backup        && python3 -m pytest lib/tests -q )
( cd skills/install       && python3 -m pytest tests -q )
( cd skills/doctor && for t in scripts/tests/*.sh; do bash "$t" || break; done )
( cd skills/update && for t in scripts/tests/*.sh; do bash "$t" || break; done )
```
Expected: every suite passes (includes the Phase 1–3 fixes + new tests, now at renamed paths).

- [ ] **Step 3: Plugin validates**
```bash
claude plugin validate ./ --strict    # expect: OK (name "sf" + 11 bare-verb dirs + wiki-migration)
```
If any grep is non-empty or any suite fails, fix the missed reference before Phase 5.

---

# PHASE 5 — Re-verify, Empirical Confirm, Version Bump, Re-publish

> The rename changes the shipped command surface, so this ships a new version. This phase also hosts the **empirical `/sf` confirmation** (the deferred Task 1.0) — done at install time, before the irreversible publish. The actual publish is **human-gated**.

### Task 5.1: Full test sweep (green baseline)

**Files:** none (verification).

- [ ] **Step 1: Run every per-module suite + bash harness (post-rename paths)**
```bash
cd "$(git rev-parse --show-toplevel)"
( python3 -m pytest lib/tests -q )
( cd skills/wrap          && python3 -m pytest lib/tests -q )
( cd skills/insights      && python3 -m pytest scripts/tests -q )
( cd skills/improve-skill && python3 -m pytest lib/tests -q )
( cd skills/recall        && python3 -m pytest lib/tests -q )
( cd skills/note          && python3 -m pytest lib/tests -q )
( cd skills/backup        && python3 -m pytest lib/tests -q )
( cd skills/install       && python3 -m pytest tests -q )
( cd skills/doctor && for t in scripts/tests/*.sh; do echo "== $t =="; bash "$t" || break; done )
( cd skills/update && for t in scripts/tests/*.sh; do echo "== $t =="; bash "$t" || break; done )
# plus the wake-up hook suite under hooks/wake-up/ and tests/integration/migration-dogfood.sh if part of the suite
```
Expected: all green. (Adjust module list to the repo's actual layout.)

- [ ] **Step 2: Final stale-ref + validate**
```bash
grep -rEn 'skills/sf-(backup|bootstrap-project|doctor|improve-skill|insights|install|interview|note|recall|update|wrap)' \
  --include='*.py' --include='*.sh' --include='*.json' --include='*.yaml' --include='*.yml' .   # expect: NO output
claude plugin validate ./ --strict    # expect: OK
```

---

### Task 5.2: Version bump + CHANGELOG release entry

**Files:**
- Modify: `.claude-plugin/plugin.json:5` (version)
- Modify: `CHANGELOG.md` (new release section)

> **Maintainer decision:** target **1.1.0** (MINOR). The command surface changes, but the old `/startup-framework:*` invocations never worked as documented, so nothing real breaks → MAJOR is arguable but not required. Confirm before tagging.

- [ ] **Step 1: Bump plugin.json:5**
```
-  "version": "1.0.0",
+  "version": "1.1.0",
```

- [ ] **Step 2: Add a `## [1.1.0] — <ship-date>` CHANGELOG section** summarizing this remediation:
```
## [1.1.0] — 2026-05-31

### Changed
- **Command namespace fixed:** the plugin now installs as `sf@sf-marketplace` and commands are `/sf:wrap`, `/sf:doctor`, … (previously shipped as `/startup-framework:sf-*`, which never matched the docs). All 11 skill dirs de-prefixed; `wiki-migration` invoked as `/sf:wiki-migration`.

### Fixed
- `sf_paths` no longer accepts a `handle:` from an unterminated frontmatter body; handle length capped at 50.
- `budget` tolerates pricing tables missing cache-rate keys (no `KeyError`).
- `diff_plan` stamps the resolved framework version (not a hardcoded `1.0.0`); dropped dead diff helpers.
- `recall` survives a file deleted mid-scan; `apply` rollback diagnostic counts surviving files; `collect` surfaces the encoded project dir instead of a lossy basename.
- Privacy: `/sf:doctor` reports the OTLP endpoint as `configured` (never the raw URL); `/sf:insights` no longer forwards the verbatim first user message; permissions audit never prints a full project path.

### Docs
- Reconciled page-type count to 15; added `contract:`+`license:` to doctor/update/wiki-migration; purged Activity Feed remnants (ADR-031); corrected the CC version floor (1.0.33) and install id; solo-first manifest framing; removed the orphan `alternatives/` skeleton dir.
```
(Follow the existing CHANGELOG style. If the maintainer chooses MAJOR, retitle `## [2.0.0]` and note the command-surface break.)

- [ ] **Step 3: Commit**
```bash
git add .claude-plugin/plugin.json CHANGELOG.md
git commit -m "chore(release): bump to 1.1.0 with v1.0 remediation changelog"
```

---

### Task 5.3: Empirical `/sf` confirmation → dry-run → human-run publish

**Files:** none (release op).

- [ ] **Step 1: EMPIRICAL CONFIRMATION (the deferred Task 1.0) — install the renamed plugin locally and confirm**

The maintainer adds the local repo (or the dry-run snapshot) as a marketplace and installs, then checks autocomplete:
```bash
# from a Claude Code session:
# /plugin marketplace add /home/hsozer/Dev/startup-framework    (or the worktree path)
# /plugin install sf@sf-marketplace
```
Then type `/sf` and `/startup-framework` at the prompt. **Expected (fix confirmed):** `/sf:wrap`, `/sf:doctor`, … autocomplete; `/startup-framework:*` no longer exists. If `/sf:` still shows nothing → STOP and re-investigate before publishing.

- [ ] **Step 2: Dry-run the snapshot/publish**
```bash
bash scripts/publish.sh --dry-run    # expect: Guards 0–4 pass; snapshot excludes wiki/; name "sf" reflected; install id shows sf@sf-marketplace
```
Confirm the snapshot allowlist still captures all 11 renamed skill dirs + `wiki-migration`.

- [ ] **Step 3: HUMAN-GATED — the maintainer runs the real publish**

Do NOT auto-run. The maintainer runs `bash scripts/publish.sh` (orphan snapshot → private `hazarsozer/sf-marketplace`) and then `/plugin marketplace update sf-marketplace` per the script's printed instructions.

- [ ] **Step 4: Post-publish sanity**

In a fresh session with the re-published plugin: `/sf:doctor` → confirm `Startup Framework: ✅ v1.1.0`, all sections green; `/sf` autocompletes the command set. The original namespace defect is closed.

---

## Spec Coverage (self-review map)

Every item in `docs/superpowers/specs/2026-05-31-v1-remediation-findings.md` maps to a task (or is a documented no-op). Phases reordered to **namespace-last** (maintainer decision 2026-05-31):

| Findings item | Task(s) | Note |
|---|---|---|
| §1 sf_paths frontmatter | 1.1 | the only true HIGH |
| §1 sf_paths HANDLE_RE len | 1.1 | paired |
| §1 budget.py KeyError | 1.2 | |
| §1 diff_plan framework_version | 1.3 | importlib caveat |
| §1 diff_plan empty-content | 1.3 | corrected: dead code → deleted |
| §1 recall stat race | 1.4 | |
| §1 apply.py rollback | 1.5 | corrected to LOW (diagnostic count) |
| §1 apply.py dead ternary | 1.5 | |
| §1 collect.py decode | 1.6 | expectation corrected |
| §2 page-type count | 2.1 | →15 |
| §2 3 missing contracts | 2.2 | |
| §2 feed remnants | 2.3 | +owner_module enum (bonus) |
| §2 output-schema.json | 2.4 | fix refs (corrected: eval doesn't assert it) |
| §2 alternatives/ | 2.5 | removed |
| §2 CHANGELOG date | 2.6 | |
| §2 README CC floor | 2.7 | |
| §2 friend-group framing | 2.8 | |
| §2 sf-improve-skill no eval | — | accepted exception, no-op |
| §2 no CI eval runner | — | out of scope (structural; needs an eval runner first) |
| §3 OTEL leak | 3.1 | |
| §3 kickoff passthrough | 3.2 | drop field |
| §3 HANDLE_RE max length | 1.1 | reassigned to Python track |
| §3 check-permissions fallback | 3.3 | |
| §0 Namespace defect | 4.1–4.9 | full sweep; empirical `/sf` confirm at 5.3 |
| Re-verify + re-publish | 5.1–5.3 | human-gated publish |
