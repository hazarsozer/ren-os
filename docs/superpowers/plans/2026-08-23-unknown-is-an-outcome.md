# Unknown Is An Outcome — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the four reporting surfaces that cannot distinguish "nothing found" from "I could not look" a way to say so, enforce that channel with an audit test, and add the one missing doctor check.

**Architecture:** A new `lib/reporting.py` defines a frozen `Unknown` dataclass and a closed `REPORTING_SURFACES` registry. Four surfaces return `Unknown(reason=...)` on their blind path instead of a falsy value of their normal type. `Unknown` is deliberately NOT a subclass of `list`/`dict`/`str`, so a caller that forgets to handle it raises at first use rather than rendering as empty. An audit test walks the registry and proves every entry both constructs `Unknown` and returns it under an induced blind condition.

**Tech Stack:** Python 3.11+, stdlib only. pytest. `uv run` for everything.

**Spec:** `docs/superpowers/specs/2026-08-22-unknown-is-an-outcome-design.md`

## Global Constraints

- Stdlib only in `lib/` — no new dependencies.
- `from __future__ import annotations` at the top of every new/modified module (repo convention).
- Every broad `except Exception` you write or touch MUST carry `# noqa: BLE001 - <reason>` or `tests/audit/test_fail_open_declared.py` fails the build. This is enforced, not advisory.
- Run tests with `uv run pytest`, never bare `pytest`.
- Repo root for all paths below is the worktree: `/Users/hazarsozer/Dev/ren-os/.claude/worktrees/unknown-is-an-outcome`.
- Do NOT hand-edit `~/.renos/wiki` or any `ren:`-managed marker block.
- Commit after every task. Never amend a previous task's commit.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `lib/reporting.py` | create | `Unknown` dataclass + `REPORTING_SURFACES` registry. Nothing else. |
| `tests/audit/test_unknown_is_an_outcome.py` | create | The three registry-wide audit tests. |
| `skills/wiki-health/lib/__init__.py` | modify | `sweep` returns `Unknown`; `render_report` handles it. |
| `skills/wrap/lib/__init__.py` | modify | `harvest_suggestions` skips the wiki-health leg on `Unknown`. |
| `skills/update/lib/__init__.py` | modify | `gc_stale_envs`, `rerender_all_project_claude_md`, `changelog_digest`. |
| `skills/update/SKILL.md` | modify | Closing-step instructions say what to print for `Unknown`. |
| `skills/doctor/lib/__init__.py` | modify | New `check_doctrine_index_pins`. |
| `skills/doctor/SKILL.md` | modify | One row in the check table. |
| `tests/skills/wiki_health/test_sweep.py` | modify | Blind-root test. |
| `tests/skills/update/test_gc_stale_envs.py` | modify | Blind-root test. |
| `tests/skills/update/test_global_rerender.py` | modify | Unreadable-registry test. |
| `tests/skills/update/test_changelog_digest.py` | modify | Missing vs unparseable. |
| `tests/skills/doctor/test_doctor.py` | modify | Three cases for the new check. |

**Task order is load-bearing.** Task 1 creates the type. Tasks 2–5 convert one surface each. Task 6's registry-wide tests only pass once all four are converted. Task 7 is independent and may be done any time after Task 1.

---

### Task 1: The `Unknown` type and the registry

**Files:**
- Create: `lib/reporting.py`
- Test: `tests/audit/test_unknown_is_an_outcome.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `lib.reporting.Unknown` (frozen dataclass, one field `reason: str`); `lib.reporting.REPORTING_SURFACES: tuple[Surface, ...]` where `Surface` is a frozen dataclass with fields `module: str`, `function: str`, `blind_when: str`.

- [ ] **Step 1: Write the failing test**

Create `tests/audit/test_unknown_is_an_outcome.py`:

```python
"""Unknown is an outcome (spec 2026-08-22).

Companion to `test_fail_open_declared.py`. That audit pins "a broad handler
conceals whether it failed"; this one pins "a reporting surface conceals
whether it looked".

Honest floor: the registry is hand-maintained. A genuinely new reporting
surface that nobody registers is invisible to this audit — see the spec's
§7. What IS enforced is that every registered entry resolves, can signal
blindness, and actually does so when blinded.
"""

from __future__ import annotations

import importlib

from lib.reporting import REPORTING_SURFACES, Unknown


def test_unknown_carries_a_reason():
    u = Unknown(reason="wiki root is not a directory")
    assert u.reason == "wiki root is not a directory"


def test_unknown_is_not_a_falsy_collection():
    """The whole point: a caller that forgets to handle Unknown must break
    loudly, not render it as an empty result."""
    u = Unknown(reason="x")
    assert not isinstance(u, (list, dict, str, tuple))


def test_registry_is_not_empty():
    assert len(REPORTING_SURFACES) >= 4


def test_registry_resolves():
    """Every registered entry names a module and function that exist. This
    is what stops the registry rotting into names that were renamed away."""
    for surface in REPORTING_SURFACES:
        module = importlib.import_module(surface.module)
        assert hasattr(module, surface.function), (
            f"{surface.module}.{surface.function} does not exist"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/audit/test_unknown_is_an_outcome.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.reporting'`

- [ ] **Step 3: Write minimal implementation**

Create `lib/reporting.py`:

```python
"""Unknown is an outcome — the "I could not look" channel (spec 2026-08-22).

A function that returns `[]` for *nothing found* and `[]` for *I could not
look* has destroyed the difference at the point where it was still known.
When something renders that value to the friend as a finding, the friend is
told the system is healthy on the strength of a check that never ran.

`Unknown` is deliberately NOT a subclass of the types it replaces. A caller
that forgets to handle it raises at first attribute access — loud, and
fixed once. An `Unknown` that quacked like an empty list would recreate the
exact defect this module exists to remove.

Stdlib only; imported by both `lib/` and `skills/`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Unknown:
    """Returned in place of a result when the check could not run.

    Not an error (nothing crashed) and not health (nothing was verified).
    `reason` is shown to the friend verbatim, so write it as a sentence
    fragment naming what could not be reached.
    """

    reason: str


@dataclass(frozen=True)
class Surface:
    """One registered reporting surface.

    `blind_when` documents the condition that makes it blind — read by a
    human, and by the audit test's failure message.
    """

    module: str
    function: str
    blind_when: str


# The closed list. See the spec's §1.5 for why this is not auto-derived:
# a SKILL.md-prose parser was prototyped and scored 4/8 recall, missing
# doctor — the reference implementation — entirely.
#
# Doctor's `check_*` functions are NOT here: `CheckResult.status == "skip"`
# is already this channel, and all 26 checks use it correctly.
REPORTING_SURFACES: tuple[Surface, ...] = (
    Surface(
        module="skills.wiki-health.lib",
        function="sweep",
        blind_when="wiki root is not a directory",
    ),
    Surface(
        module="skills.update.lib",
        function="gc_stale_envs",
        blind_when="plugin cache root unresolvable",
    ),
    Surface(
        module="skills.update.lib",
        function="rerender_all_project_claude_md",
        blind_when="project registry missing or unreadable",
    ),
    Surface(
        module="skills.update.lib",
        function="changelog_digest",
        blind_when="changelog missing or unparseable",
    ),
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/audit/test_unknown_is_an_outcome.py -v`
Expected: PASS, 4 tests.

Note: `importlib.import_module("skills.wiki-health.lib")` works despite the hyphen — this is the same call `skills/wrap/lib/__init__.py::_run_wiki_health_sweep` already makes.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest tests/ -q`
Expected: PASS. Baseline is 3634 passed, 1 skipped; you should now see 3638 passed.

- [ ] **Step 6: Commit**

```bash
git add lib/reporting.py tests/audit/test_unknown_is_an_outcome.py
git commit -m "feat(reporting): Unknown is an outcome — the 'could not look' channel"
```

---

### Task 2: `sweep()` — the flagship

`sweep()` against a wiki root that is not a directory currently returns a fully-populated all-clear report: zero dangling pointers, zero contradictions, zero orphans, zero stale facts. `render_report` prints a clean bill of health for a wiki that does not exist.

**Files:**
- Modify: `skills/wiki-health/lib/__init__.py` (the `if not wiki_root.is_dir():` block near line 921, and `render_report` near line 988)
- Modify: `skills/wrap/lib/__init__.py` (`harvest_suggestions`, near line 1524)
- Test: `tests/skills/wiki_health/test_sweep.py`

**Interfaces:**
- Consumes: `lib.reporting.Unknown` from Task 1.
- Produces: `sweep(...) -> dict | Unknown`; `render_report(findings: dict | Unknown) -> str`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/skills/wiki_health/test_sweep.py`:

```python
def test_sweep_absent_wiki_root_is_unknown(tmp_path):
    """The flagship instance: an absent wiki root used to return a fully
    populated all-clear report — every findings key present and empty."""
    from lib.reporting import Unknown

    absent = tmp_path / "no-such-wiki"
    result = wiki_health_lib.sweep(wiki_root=absent)

    assert isinstance(result, Unknown)
    assert "not a directory" in result.reason
    assert str(absent) in result.reason


def test_render_report_names_the_reason_when_unknown():
    from lib.reporting import Unknown

    out = wiki_health_lib.render_report(Unknown(reason="wiki root is not a directory: /nope"))

    assert "could not run" in out
    assert "/nope" in out
    # It must NOT render the normal all-clear body.
    assert "- none" not in out
```

Check the import name at the top of `test_sweep.py` first — if the module is imported under a different alias than `wiki_health_lib`, use that alias instead. Do not add a second import.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/skills/wiki_health/test_sweep.py -k "unknown or reason" -v`
Expected: FAIL — `sweep` returns a `dict`, so `isinstance(result, Unknown)` is False.

- [ ] **Step 3: Change `sweep`'s blind path**

In `skills/wiki-health/lib/__init__.py`, find the guard in `sweep` (near line 921):

```python
    wiki_root = wiki_root or ren_paths.wiki_root()
    if not wiki_root.is_dir():
        return {
            "dangling_pointers": [],
            ...
```

Replace the whole returned dict with:

```python
    wiki_root = wiki_root or ren_paths.wiki_root()
    if not wiki_root.is_dir():
        # Spec 2026-08-22: this used to return a fully-populated all-clear
        # report — every findings key present and empty — which render_report
        # printed as a clean bill of health for a wiki that does not exist.
        return Unknown(reason=f"wiki root is not a directory: {wiki_root}")
```

Add the import at the top of the module, beside the other `lib.` imports:

```python
from lib.reporting import Unknown
```

Update `sweep`'s return annotation to `dict | Unknown` and add this paragraph to its docstring, after the existing "Returns the 7 documented keys" paragraph:

```
    Returns `Unknown` instead when the wiki root is not a directory — the
    check could not run, which is neither a finding nor health. Callers
    must branch on `isinstance(result, Unknown)` before touching keys.
```

- [ ] **Step 4: Handle `Unknown` in `render_report`**

In the same file, `render_report` (near line 988) begins:

```python
def render_report(findings: dict) -> str:
    """Render `sweep()`'s findings as the markdown a live session shows the
    friend — one section per finding kind, "none" when a section is empty
    (an explicit "checked, found nothing" beats a silently missing section)."""
    lines = [f"# Wiki health sweep — {findings.get('generated_at', '')}", ""]
```

Change the signature to `findings: dict | Unknown` and insert the branch as the first statement of the body, before `lines = [...]`:

```python
    if isinstance(findings, Unknown):
        return (
            "# Wiki health sweep\n"
            "\n"
            f"The sweep could not run: {findings.reason}\n"
            "\n"
            "This is not a clean result — nothing was checked.\n"
        )
```

Extend its docstring with:

```
    An `Unknown` renders as a single stanza naming the reason and stating
    plainly that nothing was checked — never as an empty findings body.
```

- [ ] **Step 5: Stop wrap from crashing on `Unknown`**

In `skills/wrap/lib/__init__.py`, `harvest_suggestions` currently has (near line 1524):

```python
    try:
        sweep_result = _run_wiki_health_sweep()
    except Exception:  # noqa: BLE001 - sweep failure must not starve the other producers
        sweep_result = None

    if sweep_result is not None:
```

Change the `if` to also skip an `Unknown`:

```python
    try:
        sweep_result = _run_wiki_health_sweep()
    except Exception:  # noqa: BLE001 - sweep failure must not starve the other producers
        sweep_result = None

    # Spec 2026-08-22: an Unknown sweep is skipped exactly as a raised one
    # is. Wrap is NOT a reporting surface — skills/wrap/SKILL.md step 5:
    # "nothing in the end screen below depends on its return value" — so
    # there is no channel here that would carry the reason to the friend,
    # and inventing one would add a warning nothing reads.
    if sweep_result is not None and not isinstance(sweep_result, Unknown):
```

Add the import at the top of `skills/wrap/lib/__init__.py`, beside the other `lib.` imports:

```python
from lib.reporting import Unknown
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/skills/wiki_health/ tests/skills/wrap/ -q`
Expected: PASS. If an existing test asserted `sweep()` returns a dict for a missing root, it is asserting the defect — update it to expect `Unknown` and say so in the commit message.

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest tests/ -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add skills/wiki-health/lib/__init__.py skills/wrap/lib/__init__.py tests/skills/wiki_health/test_sweep.py
git commit -m "fix(wiki-health): an absent wiki root is Unknown, not an all-clear report"
```

---

### Task 3: `gc_stale_envs`

Returns `[]` both when nothing was stale and when the plugin cache root could not be resolved. `skills/update/SKILL.md` says "report it if non-empty, silent otherwise" — so the blind case and the healthy case take the same branch by written instruction.

**Files:**
- Modify: `skills/update/lib/__init__.py` (`gc_stale_envs`, near line 284)
- Modify: `skills/update/SKILL.md` (the "GC stale uv envs" closing step)
- Test: `tests/skills/update/test_gc_stale_envs.py`

**Interfaces:**
- Consumes: `lib.reporting.Unknown`.
- Produces: `gc_stale_envs() -> list[str] | Unknown`.

- [ ] **Step 1: Write the failing test**

Append to `tests/skills/update/test_gc_stale_envs.py`:

```python
def test_gc_stale_envs_unresolvable_cache_root_is_unknown(tmp_path, monkeypatch):
    """[] used to mean both "nothing was stale" and "I could not tell what
    is live". The refusal to delete is correct; the silence about it is not."""
    from lib.reporting import Unknown

    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    framework_root = tmp_path / "framework"
    (framework_root / ".envs" / "0.7.3").mkdir(parents=True)
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(framework_root))

    result = update_lib.gc_stale_envs()

    assert isinstance(result, Unknown)
    assert "cache root" in result.reason
    # The refusal to delete must be unchanged — this is a reporting fix.
    assert (framework_root / ".envs" / "0.7.3").is_dir()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/skills/update/test_gc_stale_envs.py -k unresolvable -v`
Expected: FAIL — returns `[]`, not `Unknown`.

- [ ] **Step 3: Change the blind path**

In `skills/update/lib/__init__.py`, `gc_stale_envs` begins:

```python
    cache_versions_root = plugin_cache_versions_root()
    if cache_versions_root is None or not cache_versions_root.is_dir():
        return []
```

Replace that return:

```python
    cache_versions_root = plugin_cache_versions_root()
    if cache_versions_root is None or not cache_versions_root.is_dir():
        # Spec 2026-08-22: refusing to delete what we cannot confirm is live
        # is correct and unchanged. What changes is that the caller can now
        # tell this apart from "nothing was stale" — both used to be [].
        return Unknown(reason="plugin cache root unresolvable")
```

Leave the second guard (`if not envs_root.is_dir(): return []`) alone — a missing `.envs` dir genuinely means nothing to remove.

Add the import beside the other `lib.` imports at the top of the module:

```python
from lib.reporting import Unknown
```

Change the return annotation to `list[str] | Unknown` and add to the docstring:

```
    Returns `Unknown` when the plugin cache root cannot be resolved: the
    sweep did not run, which is not the same as finding nothing to remove.
```

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/skills/update/test_gc_stale_envs.py -v`
Expected: PASS, all tests in the file.

- [ ] **Step 5: Update the SKILL.md instruction**

In `skills/update/SKILL.md`, the closing step currently reads:

```
- **GC stale uv envs** — call `skills.update.lib.gc_stale_envs()`. It
  removes `framework_root()/.envs/<v>` dirs whose version is no longer in
  the plugin cache (#40 — the versions this same update just made stale)
  and returns the removed version list; report it if non-empty, silent
  otherwise. Best-effort, never a gate.
```

Replace the reporting sentence:

```
- **GC stale uv envs** — call `skills.update.lib.gc_stale_envs()`. It
  removes `framework_root()/.envs/<v>` dirs whose version is no longer in
  the plugin cache (#40 — the versions this same update just made stale)
  and returns the removed version list; report it if non-empty, silent
  otherwise. If it returns `Unknown`, say the GC did not run and name
  `.reason` — silence there would report a sweep that never happened as a
  clean one. Best-effort, never a gate.
```

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest tests/ -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add skills/update/lib/__init__.py skills/update/SKILL.md tests/skills/update/test_gc_stale_envs.py
git commit -m "fix(update): gc_stale_envs reports an unresolvable cache root"
```

---

### Task 4: `rerender_all_project_claude_md`

Returns `{}` both when no project carries an `instructions.md` (the benign case, observed live on 2026-08-22) and when the project registry is missing or unreadable — `ren_paths.load_project_registry()` documents returning `{}` for "missing, unreadable, or malformed".

**Files:**
- Modify: `skills/update/lib/__init__.py` (`rerender_all_project_claude_md`, near line 207)
- Modify: `skills/update/SKILL.md` (the "Re-render project CLAUDE.md blocks" closing step)
- Test: `tests/skills/update/test_global_rerender.py`

**Interfaces:**
- Consumes: `lib.reporting.Unknown`.
- Produces: `rerender_all_project_claude_md() -> dict[str, str] | Unknown`.

- [ ] **Step 1: Write the failing test**

Append to `tests/skills/update/test_global_rerender.py`:

```python
def test_rerender_unreadable_registry_is_unknown(tmp_path, monkeypatch):
    """{} used to mean both "no project has an instructions.md" (benign)
    and "the registry could not be read" (blind)."""
    import json

    from lib.reporting import Unknown

    wiki = tmp_path / "wiki"
    (wiki / "projects").mkdir(parents=True)
    monkeypatch.setenv("REN_WIKI_ROOT", str(wiki))

    registry = tmp_path / "projects.json"
    registry.write_text("{ this is not json", encoding="utf-8")
    monkeypatch.setattr(
        "lib.ren_paths.projects_registry_path", lambda: registry
    )

    result = update_lib.rerender_all_project_claude_md()

    assert isinstance(result, Unknown)
    assert "registry" in result.reason


def test_rerender_readable_but_empty_registry_is_not_unknown(tmp_path, monkeypatch):
    """A registry that reads fine and lists nothing is a real answer: no
    projects. It must NOT be reported as blindness."""
    import json

    from lib.reporting import Unknown

    wiki = tmp_path / "wiki"
    (wiki / "projects").mkdir(parents=True)
    monkeypatch.setenv("REN_WIKI_ROOT", str(wiki))

    registry = tmp_path / "projects.json"
    registry.write_text(json.dumps({"projects": {}}), encoding="utf-8")
    monkeypatch.setattr(
        "lib.ren_paths.projects_registry_path", lambda: registry
    )

    result = update_lib.rerender_all_project_claude_md()

    assert not isinstance(result, Unknown)
    assert result == {}
```

Check the existing imports at the top of `test_global_rerender.py` and reuse its module alias for `skills.update.lib` rather than adding a new import.

- [ ] **Step 2: Run tests to verify the first fails**

Run: `uv run pytest tests/skills/update/test_global_rerender.py -k "unreadable or readable_but_empty" -v`
Expected: the `unreadable` test FAILS (`{}` is not `Unknown`); the `readable_but_empty` test PASSES already.

- [ ] **Step 3: Distinguish the two cases**

`load_project_registry()` collapses both cases to `{}`, so `rerender_all_project_claude_md` must read the registry file itself to tell them apart. In `skills/update/lib/__init__.py`, replace the body of `rerender_all_project_claude_md` from `wiki = wiki_root()` down to the `for` loop:

```python
    from lib import ren_paths
    from lib.adapter import claude_md

    # load_project_registry() returns {} for "no projects" AND for
    # "missing, unreadable, or malformed" (its own docstring). Read the file
    # first so those two can be told apart — {} used to render as "nothing
    # to do" for both (spec 2026-08-22 §3.1).
    registry_path = ren_paths.projects_registry_path()
    if registry_path.exists():
        try:
            registry_path.read_text(encoding="utf-8")
        except OSError as exc:
            return Unknown(reason=f"project registry unreadable: {exc}")
        if not ren_paths.load_project_registry() and _registry_has_entries(registry_path):
            return Unknown(reason="project registry malformed")

    wiki = wiki_root()
    results: dict[str, str] = {}
```

Add this private helper directly above `rerender_all_project_claude_md`:

```python
def _registry_has_entries(registry_path: Path) -> bool:
    """True when the registry file has content that was meant to parse.

    Distinguishes "the file is validly empty" from "the file is malformed":
    `load_project_registry()` returns {} for both, so this reads the raw text
    and asks whether there was anything there to lose.
    """
    try:
        text = registry_path.read_text(encoding="utf-8").strip()
    except OSError:
        # Unreadable is already handled by the caller; nothing was lost here.
        return False
    if not text or text in ("{}", '{"projects": {}}'):
        return False
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return True  # there was content, and it did not parse
    projects = data.get("projects") if isinstance(data, dict) else None
    return bool(projects)
```

Add `import json` to the module's imports if it is not already there, and `from lib.reporting import Unknown` if Task 3 did not already add it. `Path` is already imported in this module.

Change the return annotation to `dict[str, str] | Unknown` and add to the docstring:

```
    Returns `Unknown` when the project registry is missing content it should
    have had, or cannot be read — `{}` alone cannot distinguish that from
    "no project carries an instructions.md".
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/skills/update/test_global_rerender.py -v`
Expected: PASS, all tests in the file.

- [ ] **Step 5: Update the SKILL.md instruction**

In `skills/update/SKILL.md`, the closing step ends:

```
  Best-effort per slug — the returned
  `{slug: "ok" | "error: <msg>"}` dict is informational, never a gate.
```

Replace with:

```
  Best-effort per slug — the returned
  `{slug: "ok" | "error: <msg>"}` dict is informational, never a gate. An
  `Unknown` return means the project registry could not be read: say so and
  name `.reason`, rather than reporting zero projects re-rendered.
```

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest tests/ -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add skills/update/lib/__init__.py skills/update/SKILL.md tests/skills/update/test_global_rerender.py
git commit -m "fix(update): an unreadable project registry is Unknown, not zero projects"
```

---

### Task 5: `changelog_digest`

Returns `""` for three different situations: the range is genuinely empty, a version bound is unparseable, and the changelog file is missing or unreadable. `skills/update/SKILL.md` instructs the session to conflate them: *"If it returns "" (unparseable/missing), say the update landed and point at CHANGELOG.md instead."*

**Files:**
- Modify: `skills/update/lib/__init__.py` (`changelog_digest`, near line 25)
- Modify: `skills/update/SKILL.md` (the "Report what changed" closing step)
- Test: `tests/skills/update/test_changelog_digest.py`

**Interfaces:**
- Consumes: `lib.reporting.Unknown`.
- Produces: `changelog_digest(old: str, new: str, changelog_path: Path | str) -> str | Unknown`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/skills/update/test_changelog_digest.py`:

```python
def test_changelog_digest_missing_file_is_unknown(tmp_path):
    from lib.reporting import Unknown

    result = update_lib.changelog_digest("0.8.3", "0.8.4", tmp_path / "nope.md")

    assert isinstance(result, Unknown)
    assert "could not be read" in result.reason


def test_changelog_digest_unparseable_bound_is_unknown(tmp_path):
    from lib.reporting import Unknown

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [0.8.4] - 2026-08-22\n\nstuff\n", encoding="utf-8")

    result = update_lib.changelog_digest("not-a-version", "0.8.4", changelog)

    assert isinstance(result, Unknown)
    assert "version" in result.reason


def test_changelog_digest_empty_range_is_empty_string_not_unknown(tmp_path):
    """A readable changelog with no sections in range is a real answer:
    nothing changed. It must NOT be reported as blindness."""
    from lib.reporting import Unknown

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [0.8.4] - 2026-08-22\n\nstuff\n", encoding="utf-8")

    result = update_lib.changelog_digest("0.8.4", "0.8.4", changelog)

    assert not isinstance(result, Unknown)
    assert result == ""
```

Reuse the module alias already imported at the top of `test_changelog_digest.py`.

- [ ] **Step 2: Run tests to verify the first two fail**

Run: `uv run pytest tests/skills/update/test_changelog_digest.py -k "missing_file or unparseable_bound or empty_range" -v`
Expected: the first two FAIL (both return `""`); the third PASSES already.

- [ ] **Step 3: Split the two failure causes**

In `skills/update/lib/__init__.py`, `changelog_digest` currently opens:

```python
    try:
        text = Path(changelog_path).read_text(encoding="utf-8")
        old_key, new_key = _version_key(old), _version_key(new)
    except (OSError, ValueError):
        return ""
```

The single `except` conflates a missing file (`OSError`) with an unparseable bound (`ValueError`). Split it:

```python
    # Spec 2026-08-22: these were one handler returning "", which the caller
    # could not tell from "the range is genuinely empty".
    try:
        text = Path(changelog_path).read_text(encoding="utf-8")
    except OSError as exc:
        return Unknown(reason=f"changelog could not be read: {exc}")
    try:
        old_key, new_key = _version_key(old), _version_key(new)
    except ValueError as exc:
        return Unknown(reason=f"version bound is unparseable: {exc}")
```

Change the return annotation to `str | Unknown` and replace the docstring's last sentence:

```
    Returns "" when the range is genuinely empty — a real answer. Returns
    `Unknown` when the file could not be read or a version bound could not
    be parsed: the digest did not run, which is a different fact.
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/skills/update/test_changelog_digest.py -v`
Expected: PASS, all tests in the file.

- [ ] **Step 5: Update the SKILL.md instruction**

In `skills/update/SKILL.md`, the closing step currently reads:

```
  Print it verbatim under a "What changed in
  your RenOS" heading. If it returns "" (unparseable/missing), say the
  update landed and point at CHANGELOG.md instead — the digest is a
  courtesy, never a gate.
```

Replace:

```
  Print it verbatim under a "What changed in
  your RenOS" heading. `""` means the range is genuinely empty — say the
  update landed with no changelog entries in range. An `Unknown` means the
  digest could not be produced at all: say so, name `.reason`, and point at
  CHANGELOG.md. The digest is a courtesy, never a gate — but a courtesy
  that cannot run should not read as a courtesy that found nothing.
```

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest tests/ -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add skills/update/lib/__init__.py skills/update/SKILL.md tests/skills/update/test_changelog_digest.py
git commit -m "fix(update): changelog_digest tells a missing file from an empty range"
```

---

### Task 6: Registry-wide enforcement

The two audit tests that only pass once all four surfaces are converted. Task 1's `test_registry_resolves` proves the entries exist; these prove they work.

**Files:**
- Modify: `tests/audit/test_unknown_is_an_outcome.py`

**Interfaces:**
- Consumes: everything from Tasks 1–5.
- Produces: nothing.

- [ ] **Step 1: Write the failing tests**

Append to `tests/audit/test_unknown_is_an_outcome.py`:

```python
import ast
import inspect
import textwrap

import pytest


def _constructs_unknown(func) -> bool:
    """True when the function's own source constructs `Unknown(...)`.

    AST rather than a string search: a docstring mentioning Unknown must not
    count as signalling it.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "Unknown":
                return True
    return False


@pytest.mark.parametrize(
    "surface", REPORTING_SURFACES, ids=lambda s: f"{s.module}.{s.function}"
)
def test_surface_can_signal_unknown(surface):
    """Every registered surface has a code path that constructs Unknown.

    Necessary but not sufficient — a dead branch satisfies this. The
    blind-condition test below is the load-bearing one.
    """
    module = importlib.import_module(surface.module)
    func = getattr(module, surface.function)
    assert _constructs_unknown(func), (
        f"{surface.module}.{surface.function} is registered as a reporting "
        f"surface but never constructs Unknown. Blind when: {surface.blind_when}"
    )


def test_sweep_signals_when_blind(tmp_path):
    module = importlib.import_module("skills.wiki-health.lib")
    result = module.sweep(wiki_root=tmp_path / "absent")
    assert isinstance(result, Unknown)


def test_gc_stale_envs_signals_when_blind(tmp_path, monkeypatch):
    module = importlib.import_module("skills.update.lib")
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path / "framework"))
    assert isinstance(module.gc_stale_envs(), Unknown)


def test_changelog_digest_signals_when_blind(tmp_path):
    module = importlib.import_module("skills.update.lib")
    result = module.changelog_digest("0.8.3", "0.8.4", tmp_path / "absent.md")
    assert isinstance(result, Unknown)


def test_rerender_signals_when_blind(tmp_path, monkeypatch):
    module = importlib.import_module("skills.update.lib")
    registry = tmp_path / "projects.json"
    registry.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr("lib.ren_paths.projects_registry_path", lambda: registry)
    monkeypatch.setenv("REN_WIKI_ROOT", str(tmp_path / "wiki"))
    assert isinstance(module.rerender_all_project_claude_md(), Unknown)


def test_every_surface_has_a_blind_test():
    """The registry and this file must not drift apart: adding a surface
    without a blind-condition test is the gap this audit exists to close."""
    covered = {
        "sweep",
        "gc_stale_envs",
        "changelog_digest",
        "rerender_all_project_claude_md",
    }
    registered = {s.function for s in REPORTING_SURFACES}
    assert registered <= covered, (
        f"registered surfaces with no blind test: {sorted(registered - covered)}"
    )
```

- [ ] **Step 2: Run to verify they pass**

Run: `uv run pytest tests/audit/test_unknown_is_an_outcome.py -v`
Expected: PASS. All four surfaces were converted in Tasks 2–5, so these should be green on first run. If any fails, the corresponding earlier task is incomplete — fix it there, not here.

- [ ] **Step 3: Verify the audit actually bites**

Temporarily revert one surface to prove the gate fires — this is the probe step, not a permanent change:

```bash
# Make gc_stale_envs return [] again on the blind path, by hand.
uv run pytest tests/audit/test_unknown_is_an_outcome.py -v
# Expect: test_surface_can_signal_unknown[skills.update.lib.gc_stale_envs] FAILS
#     and test_gc_stale_envs_signals_when_blind FAILS
git checkout -- skills/update/lib/__init__.py
uv run pytest tests/audit/test_unknown_is_an_outcome.py -v
# Expect: PASS again
```

Do not commit the temporary revert. Confirm `git status` is clean of it before continuing.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest tests/ -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/audit/test_unknown_is_an_outcome.py
git commit -m "test(audit): every reporting surface must signal when it is blind"
```

---

### Task 7: `check_doctrine_index_pins`

The global CLAUDE.md managed block's doctrine index holds absolute paths pinned to the running plugin version (`.../cache/ren-os/ren/<version>/doctrine/*.md`). A version bump leaves every one naming the previous version — live only until that cache dir is GC'd, then dead links in a file injected into every session. Observed live on 2026-08-22: after v0.8.4 installed, the block still pinned `0.8.3` and nothing reported it.

This task is independent of Tasks 2–6 and may be done any time after Task 1.

**Files:**
- Modify: `skills/doctor/lib/__init__.py` (add beside `check_interpreter_freshness`, near line 936)
- Modify: `skills/doctor/SKILL.md` (the check table, near line 77)
- Test: `tests/skills/doctor/test_doctor.py`

**Interfaces:**
- Consumes: `lib.adapter.claude_md.MARKER_BEGIN` / `MARKER_END`; `lib.ren_paths.framework_version`, `lib.ren_paths.claude_user_dir`.
- Produces: `check_doctrine_index_pins(claude_dir: Path | None = None) -> CheckResult`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/skills/doctor/test_doctor.py`:

```python
def _write_global_block(claude_dir, pinned_version):
    from lib.adapter.claude_md import MARKER_BEGIN, MARKER_END

    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "CLAUDE.md").write_text(
        f"my own notes\n\n{MARKER_BEGIN}\n"
        "## Doctrine index\n\n"
        f"- **Model classes** (`/x/cache/ren-os/ren/{pinned_version}/doctrine/model-classes.md`): pull on demand.\n"
        f"{MARKER_END}\n",
        encoding="utf-8",
    )


def test_doctrine_index_pins_ok_when_current(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_FRAMEWORK_VERSION", "0.8.4")
    _write_global_block(tmp_path / ".claude", "0.8.4")

    result = doctor_lib.check_doctrine_index_pins(claude_dir=tmp_path / ".claude")

    assert result.status == "ok"


def test_doctrine_index_pins_warn_on_drift(tmp_path, monkeypatch):
    """The live 2026-08-22 case: 0.8.4 installed, block still pinning 0.8.3."""
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_FRAMEWORK_VERSION", "0.8.4")
    _write_global_block(tmp_path / ".claude", "0.8.3")

    result = doctor_lib.check_doctrine_index_pins(claude_dir=tmp_path / ".claude")

    assert result.status == "warn"
    assert "0.8.3" in result.message
    assert "0.8.4" in result.message


def test_doctrine_index_pins_skip_when_no_block(tmp_path, monkeypatch):
    """No managed block is not health and not drift — it is 'could not look'."""
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_FRAMEWORK_VERSION", "0.8.4")
    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "CLAUDE.md").write_text("just my notes\n", encoding="utf-8")

    result = doctor_lib.check_doctrine_index_pins(claude_dir=tmp_path / ".claude")

    assert result.status == "skip"


def test_doctrine_index_pins_skip_when_file_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_FRAMEWORK_VERSION", "0.8.4")

    result = doctor_lib.check_doctrine_index_pins(claude_dir=tmp_path / "nothing-here")

    assert result.status == "skip"
```

Reuse the module alias `test_doctor.py` already uses for `skills.doctor.lib`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/skills/doctor/test_doctor.py -k doctrine_index_pins -v`
Expected: FAIL — `AttributeError: module has no attribute 'check_doctrine_index_pins'`

- [ ] **Step 3: Write the check**

Add to `skills/doctor/lib/__init__.py`, directly after `check_interpreter_freshness`:

```python
_DOCTRINE_PIN_RE = re.compile(r"/cache/ren-os/ren/(\d+\.\d+\.\d+)/doctrine/")


def check_doctrine_index_pins(claude_dir: Path | None = None) -> CheckResult:
    """The global CLAUDE.md doctrine index's version pins (spec 2026-08-22 §5).

    `lib.adapter.claude_md._doctrine_index` renders each doctrine file as an
    ABSOLUTE path under the running plugin's versioned cache dir. A version
    bump leaves every one naming the previous version — live only until that
    cache dir is GC'd, then dead links in a file injected into every session.

    `write_global_claude_md()` fixes it, and `/ren:update`'s closing steps
    call that — but nothing reported when the closing step had not run.
    Observed 2026-08-22: v0.8.4 installed with the block still pinning
    0.8.3, silently.

    `check_global_drift` does NOT cover this: it checks page typing under
    `global/`, never the doctrine index.

    Obeys the spec's own rule — an absent file or a missing managed block is
    `skip` ("could not look"), never `ok`.
    """
    from lib.adapter import claude_md

    name = "doctrine_index_pins"
    target_dir = Path(claude_dir) if claude_dir is not None else ren_paths.claude_user_dir()
    path = target_dir / "CLAUDE.md"

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return CheckResult(name, "skip", f"{path} unreadable: {exc}")

    begin = text.find(claude_md.MARKER_BEGIN)
    end = text.find(claude_md.MARKER_END)
    if begin == -1 or end == -1 or end < begin:
        return CheckResult(name, "skip", "no ren-managed block in the global CLAUDE.md")

    block = text[begin:end]
    pinned = sorted({m.group(1) for m in _DOCTRINE_PIN_RE.finditer(block)})
    if not pinned:
        return CheckResult(name, "skip", "managed block carries no doctrine index pins")

    current = ren_paths.framework_version()
    stale = [v for v in pinned if v != current]
    if stale:
        return CheckResult(
            name, "warn",
            f"doctrine index pins {', '.join(stale)} but the framework is {current} — "
            f"re-render with lib.adapter.claude_md.write_global_claude_md()",
        )
    return CheckResult(name, "ok", f"doctrine index pins match the framework ({current})")
```

`re` and `Path` are already imported at the top of this module; `ren_paths` is already imported. Do not add duplicate imports.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/skills/doctor/test_doctor.py -k doctrine_index_pins -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Add the SKILL.md table row**

In `skills/doctor/SKILL.md`, add after the `check_interpreter_freshness` row:

```
| `check_doctrine_index_pins` | spec 2026-08-22 §5: the global CLAUDE.md doctrine index's absolute paths pin a plugin version — a bump leaves them naming the previous one, dead once that cache dir is GC'd. Pins match → `ok`; any pin naming another version → `warn` with both; no file, no managed block, or no pins → `skip` |
```

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest tests/ -q`
Expected: PASS.

- [ ] **Step 7: Verify against the live machine**

This check exists because of a real observation; confirm it reports correctly on the real global CLAUDE.md:

```bash
CLAUDE_PLUGIN_ROOT=/Users/hazarsozer/.claude/plugins/cache/ren-os/ren/0.8.4 \
UV_PROJECT_ENVIRONMENT=/Users/hazarsozer/.renos/.envs/0.8.4 \
uv run python -c "
from skills.doctor import lib
r = lib.check_doctrine_index_pins()
print(r.status, '|', r.message)
"
```

Expected: `ok | doctrine index pins match the framework (0.8.4)` — the block was re-rendered to 0.8.4 on 2026-08-22. If it reports `warn`, that is a real finding, not a test failure: report it.

- [ ] **Step 8: Commit**

```bash
git add skills/doctor/lib/__init__.py skills/doctor/SKILL.md tests/skills/doctor/test_doctor.py
git commit -m "feat(doctor): check the global CLAUDE.md doctrine index version pins"
```

---

## Final verification

- [ ] **Full suite green**

Run: `uv run pytest tests/ -q`
Expected: PASS. Baseline was 3634 passed, 1 skipped; expect roughly 3660 passed.

- [ ] **Both lints green**

```bash
uv run python scripts/lint-yaml-frontmatter.py; echo "exit=$?"
uv run python scripts/lint_no_dev_wiki_content.py; echo "exit=$?"
```
Expected: both `exit=0`.

- [ ] **The fail-open audit still passes**

Run: `uv run pytest tests/audit/ -v`
Expected: PASS. Any broad handler added by this work must carry a written reason.

- [ ] **Spec coverage check**

Confirm each spec section has landed: §3 Part A (Task 1), §3.2 in-repo callers (Task 2 step 5), §3.3 exclusions (Task 1's registry comment), §4 Part B (Tasks 1 + 6), §5 Part C (Task 7), §6 testing (all tasks), §7 limitations (Task 1's module docstring and the audit's).

---

## Notes for the executor

- **`Unknown` must never be made falsy-compatible.** If a caller is awkward to update, that awkwardness is the design working. Do not add `__bool__`, `__len__`, or `__iter__` to make it quack like an empty collection — that recreates the exact defect this plan removes.
- **Do not widen the registry.** The spec's §1.3 measured 230 shape-matching sites and §3.3 excludes them by evidence. Adding a surface because it "looks similar" is out of scope; open a ledger item instead.
- **Do not touch doctor's other 26 checks.** They were probed with and without `CLAUDE_PLUGIN_ROOT` and none falsely reported `ok` while blinded. Doctor is the reference, not a target.
- **`metric-watch` is deliberately excluded** — its blind paths fail loud (a git failure produces a `backup-unconfigured` finding, not a false all-clear). If you find that is untrue, that is a real finding: stop and report it rather than quietly adding it to the registry.
