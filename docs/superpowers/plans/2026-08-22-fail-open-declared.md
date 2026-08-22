# Fail-Open Must Declare Itself — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every broad exception handler in shippable code declare, in one line, why its failure path is honest — enforced by a test that fails the build on the next undeclared one.

**Architecture:** One new audit test walks `ast.ExceptHandler` nodes across the shippable directories and cross-references `tokenize` comments to find broad handlers lacking a reasoned `# noqa: BLE001` marker. Seven existing sites gain the reason already written in their adjacent docstring; two sites are real defects and are fixed. No production module is added and nothing new ships to an installed instance.

**Tech Stack:** Python ≥3.11, `ast` + `tokenize` (standard library only), pytest, uv.

**Spec:** `docs/superpowers/specs/2026-08-22-fail-open-declared-design.md`

## Global Constraints

- No new third-party dependency. `ast` and `tokenize` are standard library; nothing is added to `pyproject.toml`.
- "Broad handler" means exactly: catches `Exception`, catches `BaseException`, or is bare (`except:`). A handler catching a named exception, or a tuple of them, is out of scope — the exception name is itself the declaration.
- Shippable dirs are `["skills", "hooks", "lib", "doctrine", "wiki-skeleton", ".claude-plugin", "agents"]`, copied verbatim from `tests/test_repo_hygiene.py:28`. `tests/` is never scanned.
- The marker is the existing convention `# noqa: BLE001 - <reason>`. No new marker syntax is introduced.
- A marker with an empty reason is a violation, equal in severity to no marker.
- Ruff is NOT configured and NOT added to CI. This plan enforces one rule with one test (spec §3.2).
- Every task ends with `uv run pytest tests/ -q` green. The suite is green at every commit — no task leaves the repo red for the next one.
- Baseline for this branch: 3613 passed, 1 skipped.

---

### Task 1: The detector and its own tests

Builds the AST/tokenize detector and proves it on fixtures. The repo-wide sweep is deliberately NOT enabled here — it would fail on the nine known violations, which Tasks 2–4 clear. It is switched on in Task 5.

**Files:**
- Create: `tests/audit/test_fail_open_declared.py`
- Test: `tests/audit/test_fail_open_declared.py` (the detector and its tests live in one file, matching `tests/audit/test_destructive_write_paths.py`, which does its own scanning inline)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `undeclared_broad_handlers(src: str, label: str) -> list[str]` — returns `"<label>:<lineno>"` for each broad handler lacking a reasoned marker. Task 5 calls this over the repo.

- [ ] **Step 1: Write the tests and the detector**

Create `tests/audit/test_fail_open_declared.py`:

```python
"""Fail-open must declare itself (spec 2026-08-22).

Companion to `test_destructive_write_paths.py`: that audit pins the class
"a generated write meets an existing file"; this one pins the class "a broad
exception handler conceals whether it failed".

The convention enforced here already exists — 66 handlers carried
`# noqa: BLE001 - <reason>` before this test was written. Ruff is not
configured in this repo and never runs, so the comment functions as
documentation, not suppression. This test is what makes it binding.
"""

from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Copied verbatim from tests/test_repo_hygiene.py:28 — the shippable surface.
SHIPPABLE_DIRS = ["skills", "hooks", "lib", "doctrine", "wiki-skeleton", ".claude-plugin", "agents"]

_MARKER = "BLE001"
# Separators a reason may follow the code with: "BLE001 - why", "BLE001: why".
_REASON_SEPARATORS = " -–—:"


def _comments_by_line(src: str) -> dict[int, str]:
    """Map line number -> comment text. Comments are absent from the AST, so
    they must come from tokenize. The first comment on a line wins."""
    out: dict[int, str] = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                out.setdefault(tok.start[0], tok.string)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # A file that does not tokenize also does not parse; ast.parse in the
        # caller raises and pytest reports it. Returning {} keeps this helper
        # total rather than hiding a parse failure here.
        pass
    return out


def _is_broad(handler: ast.ExceptHandler) -> bool:
    """True for `except:`, `except Exception:`, `except BaseException:` —
    including the `as exc` forms. A tuple or a named exception is not broad."""
    caught = handler.type
    if caught is None:
        return True
    return isinstance(caught, ast.Name) and caught.id in ("Exception", "BaseException")


def undeclared_broad_handlers(src: str, label: str) -> list[str]:
    """Return "<label>:<lineno>" for every broad handler in `src` that lacks a
    `# noqa: BLE001` marker with a non-empty reason on its `except` line."""
    tree = ast.parse(src)
    comments = _comments_by_line(src)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or not _is_broad(node):
            continue
        comment = comments.get(node.lineno, "")
        if _MARKER not in comment:
            offenders.append(f"{label}:{node.lineno}")
            continue
        reason = comment.split(_MARKER, 1)[1].lstrip(_REASON_SEPARATORS).strip()
        if not reason:
            offenders.append(f"{label}:{node.lineno}")
    return offenders


def test_unmarked_broad_handler_is_flagged():
    src = "try:\n    f()\nexcept Exception:\n    pass\n"
    assert undeclared_broad_handlers(src, "x.py") == ["x.py:3"]


def test_bare_except_is_flagged():
    src = "try:\n    f()\nexcept:\n    pass\n"
    assert undeclared_broad_handlers(src, "x.py") == ["x.py:3"]


def test_marker_without_a_reason_is_flagged():
    src = "try:\n    f()\nexcept Exception:  # noqa: BLE001\n    pass\n"
    assert undeclared_broad_handlers(src, "x.py") == ["x.py:3"]


def test_marker_with_a_reason_passes():
    src = "try:\n    f()\nexcept Exception:  # noqa: BLE001 - callers handle None\n    pass\n"
    assert undeclared_broad_handlers(src, "x.py") == []


def test_marker_with_colon_separator_passes():
    src = "try:\n    f()\nexcept Exception:  # noqa: BLE001: callers handle None\n    pass\n"
    assert undeclared_broad_handlers(src, "x.py") == []


def test_as_exc_form_is_still_broad():
    src = "try:\n    f()\nexcept Exception as exc:\n    pass\n"
    assert undeclared_broad_handlers(src, "x.py") == ["x.py:3"]


def test_named_exception_is_out_of_scope():
    src = "try:\n    f()\nexcept OSError:\n    return None\n"
    assert undeclared_broad_handlers(src, "x.py") == []


def test_tuple_of_named_exceptions_is_out_of_scope():
    src = "try:\n    f()\nexcept (OSError, ValueError):\n    return None\n"
    assert undeclared_broad_handlers(src, "x.py") == []


def test_return_shape_is_irrelevant():
    """The rule is about handler breadth, not what the handler returns —
    spec §2.1. A handler returning a plausible-but-wrong literal is exactly
    the case a return-shape rule would miss."""
    src = 'try:\n    f()\nexcept Exception:\n    return "0.8.3"\n'
    assert undeclared_broad_handlers(src, "x.py") == ["x.py:3"]
```

- [ ] **Step 2: Run the tests to verify they pass**

Run: `uv run pytest tests/audit/test_fail_open_declared.py -q`
Expected: 9 passed. Step 1 writes both the tests and the detector, so they pass on first run. If any FAIL, the detector is wrong — fix the detector, never the assertion.

- [ ] **Step 3: Confirm the detector agrees with the spec's count**

A throwaway check, not a committed test. Run:

```bash
uv run python -c "
import sys; sys.path.insert(0, 'tests/audit')
from pathlib import Path
from test_fail_open_declared import undeclared_broad_handlers, SHIPPABLE_DIRS, REPO_ROOT
bad = []
for rel in SHIPPABLE_DIRS:
    root = REPO_ROOT / rel
    if not root.is_dir(): continue
    for p in sorted(root.rglob('*.py')):
        if '__pycache__' in p.parts: continue
        bad += undeclared_broad_handlers(p.read_text(encoding='utf-8'), str(p.relative_to(REPO_ROOT)))
print(len(bad)); [print(' ', b) for b in bad]
"
```

Expected: exactly `9` — the five `skills/wrap/lib/__init__.py` sites, `hooks/wake-up/wakeup/__init__.py:1176`, `lib/memory/quarantine.py:129`, `skills/doctor/lib/__init__.py:806`, `skills/ingest-project/lib/scan.py:74`.

If the number differs, STOP and report it. The spec's evidence and the detector disagree, and the spec is what needs revisiting — do not adjust the detector to reach 9.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest tests/ -q`
Expected: 3622 passed, 1 skipped (3613 baseline + 9 new).

- [ ] **Step 5: Commit**

```bash
git add tests/audit/test_fail_open_declared.py
git commit -m "test(audit): detector for undeclared broad exception handlers

Walks ast.ExceptHandler and cross-references tokenize comments to find
broad handlers lacking a reasoned '# noqa: BLE001' marker. Nine fixture
tests pin the boundaries: bare/Exception/BaseException are broad, named
and tuple handlers are not, an empty reason is a violation, and return
shape is irrelevant (spec 2.1).

The repo-wide sweep lands in a later commit, once the nine existing
violations are cleared."
```

---

### Task 2: Fix `doctor` — a crashed resolver must not read as "no project"

`_project_agents_dir` returns `None` for the legitimate state "no project here". Its bare `except Exception` makes `None` *also* mean "`wiki_root()` raised", so the health checker cannot report its own blindness (spec §5.1).

The fix is a deletion. `run_checks()` already wraps every check in `_wrap`, which catches any exception and returns `CheckResult(status="error", message=f"check crashed: {exc}")` — an honest inability-to-check. The local handler is what suppresses that existing, correct behaviour.

**Files:**
- Modify: `skills/doctor/lib/__init__.py:798-812` (the `_project_agents_dir` docstring and its `try`/`except`)
- Test: `tests/skills/doctor/test_doctor.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `_project_agents_dir()` keeps its signature `() -> Path | None`. `None` now means only "no project here". A resolver failure propagates to `_wrap`.

- [ ] **Step 1: Write the failing test**

Append to `tests/skills/doctor/test_doctor.py`. That file already binds the module at line 21 with `doctor = importlib.import_module("skills.doctor.lib")` — use that existing binding; do NOT add an import inside the test.

```python
def test_agent_shadowing_reports_error_when_wiki_root_raises(monkeypatch):
    """A raised wiki_root() must surface as an 'error' result, never as a
    clean skip. Before this fix _project_agents_dir swallowed the raise and
    returned None, which is indistinguishable from 'no project here'."""

    def boom():
        raise RuntimeError("wiki root exploded")

    monkeypatch.setattr(doctor.ren_paths, "wiki_root", boom)

    results = {r.name: r for r in doctor.run_checks()}
    result = results["agent_shadowing"]

    assert result.status == "error"
    assert "wiki root exploded" in result.message
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/skills/doctor/test_doctor.py::test_agent_shadowing_reports_error_when_wiki_root_raises -v`
Expected: FAIL. The status will be `ok` or `skip` rather than `error`, because the swallowed raise renders as "no project".

- [ ] **Step 3: Delete the swallowing handler**

In `skills/doctor/lib/__init__.py`, replace:

```python
    try:
        wiki_root_ = ren_paths.wiki_root()
    except Exception:
        return None
    if not wiki_root_.is_dir():
        return None
```

with:

```python
    wiki_root_ = ren_paths.wiki_root()
    if not wiki_root_.is_dir():
        return None
```

Then extend the docstring. Replace its closing sentence:

```python
    and the wrap skill on which project "here" is. Returns None when no
    wiki, no mapped project, or no recorded repo path — never raises."""
```

with:

```python
    and the wrap skill on which project "here" is. Returns None when no
    wiki, no mapped project, or no recorded repo path.

    Does NOT catch a failing `wiki_root()`: `None` means "no project here",
    and conflating that with "resolution failed" left the health checker
    unable to report its own blindness. A raise propagates to `_wrap`,
    which renders it as an `"error"` result (spec 2026-08-22 §5.1)."""
```

- [ ] **Step 4: Run the doctor tests to verify they pass**

Run: `uv run pytest tests/skills/doctor/ -q`
Expected: PASS, including the pre-existing doctor tests.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest tests/ -q`
Expected: 3623 passed, 1 skipped.

- [ ] **Step 6: Commit**

```bash
git add skills/doctor/lib/__init__.py tests/skills/doctor/test_doctor.py
git commit -m "fix(doctor): a crashed wiki_root must not read as 'no project'

_project_agents_dir caught Exception and returned None, the same value it
returns for the legitimate 'no project here' state — so the health checker
could not report its own blindness. run_checks already wraps every check in
_wrap, which renders a raise as an 'error' result; the local handler was
suppressing that. Deleting it restores the honest report.

Spec: docs/superpowers/specs/2026-08-22-fail-open-declared-design.md 5.1"
```

---

### Task 3: Fix `ingest` — report an unknown version instead of inventing one

`_framework_version()` falls back to the string literal `"0.8.3"`. On resolver failure it reports a plausible but wrong version, and the literal must be hand-bumped every release or it silently reports a version that has not shipped for months (spec §5.2). This defect is in no ledger; the sweep found it.

`None` is the honest value, and the two call sites record a warning so the failure is visible rather than merely absent. The `facts` contract keeps the key present, so the "COMPLETE facts dict" guarantee at `scan.py:518-522` is preserved.

**Files:**
- Modify: `skills/ingest-project/lib/scan.py:65-75` (the helper), `:522`, `:552` (the two call sites)
- Create: `tests/skills/ingest_project/test_scan.py` — this file does NOT exist yet. The directory holds only `test_l2_map.py`.

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `_framework_version() -> str | None`. `None` means "could not resolve". `facts["framework_version"]` is now `str | None`; the key is always present.

**Import note:** the package directory is `skills/ingest-project/` (hyphen), which is not a valid module name for a plain `import` statement. The repo's pattern — used at `tests/skills/ingest_project/test_l2_map.py:31` — is `importlib.import_module`, which accepts the hyphen. Verified working: `importlib.import_module("skills.ingest-project.lib.scan")`.

- [ ] **Step 1: Write the failing tests**

Create `tests/skills/ingest_project/test_scan.py`:

```python
"""`scan.py` facts-gathering invariants.

Companion to test_l2_map.py; same importlib pattern (the package dir is
hyphenated, so a plain import statement cannot name it).
"""

from __future__ import annotations

import importlib

scan = importlib.import_module("skills.ingest-project.lib.scan")


def test_framework_version_is_none_when_unresolvable(monkeypatch):
    """A resolver failure must yield None, not a stale literal. A wrong-but-
    plausible version is worse than an absent one: nothing downstream can
    detect it."""

    def boom(*_args, **_kwargs):
        raise OSError("no path")

    monkeypatch.setattr(scan.Path, "resolve", boom)

    assert scan._framework_version() is None


def test_scan_warns_when_framework_version_is_unresolvable(monkeypatch, tmp_path):
    """The fact stays present (the COMPLETE-facts contract) and the failure
    is recorded as a warning rather than silently absent."""
    monkeypatch.setattr(scan, "_framework_version", lambda: None)
    (tmp_path / "README.md").write_text("# demo\n")

    facts = scan.scan_repo(tmp_path)

    assert "framework_version" in facts
    assert facts["framework_version"] is None
    assert any("framework version" in w.lower() for w in facts["warnings"])


def test_no_hardcoded_version_literal_remains():
    """Pins the defect class, not the instance: no x.y.z literal may sit in
    a return statement of this module again."""
    import re
    from pathlib import Path as _Path

    src = (_Path(__file__).resolve().parents[3] / "skills/ingest-project/lib/scan.py").read_text(
        encoding="utf-8"
    )
    assert not re.search(r'return\s+"\d+\.\d+\.\d+"', src)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/skills/ingest_project/test_scan.py -q -k "framework_version or hardcoded"`
Expected: FAIL — `_framework_version()` returns `"0.8.3"`, no warning is recorded, and the literal is present.

- [ ] **Step 3: Fix the helper**

In `skills/ingest-project/lib/scan.py`, change the signature line from:

```python
def _framework_version() -> str:
```

to:

```python
def _framework_version() -> str | None:
```

Then replace the docstring and body:

```python
    """Best-effort framework version for page frontmatter. Imports lib.ren_paths
    from the repo root; falls back to the pinned literal below in a bare checkout. Read-only."""
    try:
        plugin_root = Path(__file__).resolve().parents[3]  # lib→ingest-project→skills→<repo root>
        if str(plugin_root) not in sys.path:
            sys.path.insert(0, str(plugin_root))
        from lib.ren_paths import framework_version
        return framework_version()
    except Exception:
        return "0.8.3"
```

with:

```python
    """Best-effort framework version for page frontmatter. Imports lib.ren_paths
    from the repo root. Returns None when the version cannot be resolved —
    never a literal: a hardcoded fallback reports a plausible WRONG version
    and must be hand-bumped every release, which makes staleness invisible
    (spec 2026-08-22 §5.2). Read-only."""
    try:
        plugin_root = Path(__file__).resolve().parents[3]  # lib→ingest-project→skills→<repo root>
        if str(plugin_root) not in sys.path:
            sys.path.insert(0, str(plugin_root))
        from lib.ren_paths import framework_version
        return framework_version()
    except Exception:  # noqa: BLE001 - best-effort: callers record a warning on None
        return None
```

- [ ] **Step 4: Fix the two call sites**

At `scan.py:522` (inside the `if not root.is_dir():` branch), replace:

```python
        facts["framework_version"] = _framework_version()
```

with:

```python
        facts["framework_version"] = _framework_version()
        if facts["framework_version"] is None:
            facts["warnings"].append("framework version could not be resolved")
```

At `scan.py:552`, replace:

```python
    facts["framework_version"] = _framework_version()
```

with:

```python
    facts["framework_version"] = _framework_version()
    if facts["framework_version"] is None:
        facts["warnings"].append("framework version could not be resolved")
```

- [ ] **Step 5: Run the ingest tests to verify they pass**

Run: `uv run pytest tests/skills/ingest_project/ -q`
Expected: PASS. If a pre-existing test asserts `facts["framework_version"]` equals a specific string, it was asserting the stale literal — update it to accept the real resolved version and note that change in the commit body.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest tests/ -q`
Expected: 3626 passed, 1 skipped.

- [ ] **Step 7: Commit**

```bash
git add skills/ingest-project/lib/scan.py tests/skills/ingest_project/test_scan.py
git commit -m "fix(ingest): report an unknown framework version, never a literal

_framework_version fell back to the string 0.8.3 — a plausible WRONG
answer that had to be hand-bumped every release and was undetectable
downstream. It now returns None and both call sites record a warning; the
facts key stays present, preserving the COMPLETE-facts contract.

Found by the fail-open sweep, not by any open-work ledger item.
Spec: docs/superpowers/specs/2026-08-22-fail-open-declared-design.md 5.2"
```

---

### Task 4: Mark the seven deliberate fail-open sites

Every reason below already exists in the site's docstring or an adjacent comment. This task moves it onto the `except` line where the detector can see it. No behaviour changes; the existing suite is the regression proof.

**Files:**
- Modify: `skills/wrap/lib/__init__.py:1352,1371,1393,1422,1451`
- Modify: `hooks/wake-up/wakeup/__init__.py:1176`
- Modify: `lib/memory/quarantine.py:129`
- Test: none new. `uv run pytest tests/ -q` must stay green, proving the marks are comment-only.

**Interfaces:**
- Consumes: nothing.
- Produces: nothing. Comment-only changes.

- [ ] **Step 1: Mark the five `wrap` D-duty handlers**

All five arrived in one commit (`5084b5d`, 2026-08-12) and all five append to `out["warnings"]`, so each failure IS reported — the duties are independent by design and one failing must not abort the rest.

In `skills/wrap/lib/__init__.py`, each line is `except Exception as exc:  # noqa: BLE001` becoming the same line with a reason. **Preserve each line's existing indentation exactly** — it differs between the five (4, 4, 8, 12, 8 spaces):

Line 1352 (4 spaces):
```python
    except Exception as exc:  # noqa: BLE001 - D1 touched-pages is independent; the failure is reported in out["warnings"] and later duties still run
```

Line 1371 (4 spaces):
```python
    except Exception as exc:  # noqa: BLE001 - D2 log entry is independent; the failure is reported in out["warnings"] and later duties still run
```

Line 1393 (8 spaces):
```python
        except Exception as exc:  # noqa: BLE001 - D3 Sessions entry is independent; the failure is reported in out["warnings"] and later duties still run
```

Line 1422 (12 spaces):
```python
            except Exception as exc:  # noqa: BLE001 - D4 auto-pointer is per-page; the failure is reported in out["warnings"] and the remaining pages still run
```

Line 1451 (8 spaces):
```python
        except Exception as exc:  # noqa: BLE001 - spine pointer is independent; the failure is reported in out["warnings"]
```

- [ ] **Step 2: Mark the wake-up backlog counter**

The reason is already in the function's docstring: *"Never raises (same discipline as _unlinted_count): any error reads as 0, wake-up must not die over a nudge."*

In `hooks/wake-up/wakeup/__init__.py:1176`, replace:

```python
    except Exception:  # noqa: BLE001
        return 0
```

with:

```python
    except Exception:  # noqa: BLE001 - wake-up must not die over a nudge; 0 hides the nudge, never blocks the session
        return 0
```

- [ ] **Step 3: Mark the quarantine reader**

The reason is already in the comment directly above the `try`: *"Skip unreadable files (never raise)"*.

In `lib/memory/quarantine.py:129`, replace:

```python
        except Exception:
            continue
```

with:

```python
        except Exception:  # noqa: BLE001 - an unreadable page is skipped, not fatal to the sweep
            continue
```

- [ ] **Step 4: Verify the marks are comment-only**

Run:

```bash
git diff -U0 -- skills/wrap/lib/__init__.py hooks/wake-up/wakeup/__init__.py lib/memory/quarantine.py | grep '^[-+]' | grep -v '^[-+][-+]' | grep -v 'except Exception'
```

Expected: no output. Every changed line must be an `except Exception` line. Anything else printed is an unintended edit — investigate before continuing.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest tests/ -q`
Expected: 3626 passed, 1 skipped — identical to Task 3's result. A comment-only change must not move the count.

- [ ] **Step 6: Commit**

```bash
git add skills/wrap/lib/__init__.py hooks/wake-up/wakeup/__init__.py lib/memory/quarantine.py
git commit -m "docs(fail-open): write the reason on seven deliberate fail-open sites

Comment-only. Every reason already existed in the adjacent docstring or
comment; this moves it onto the except line where the audit can see it.
The five wrap sites all arrived in one commit (5084b5d) and all report
their failure via out['warnings'] — deliberate, now declared.

Spec: docs/superpowers/specs/2026-08-22-fail-open-declared-design.md 4"
```

---

### Task 5: Switch on the repo-wide invariant

With the nine violations cleared, the sweep can be enabled. This is the task that makes the convention binding: from here, a new undeclared broad handler is a failing build.

**Files:**
- Modify: `tests/audit/test_fail_open_declared.py` (append the sweep)

**Interfaces:**
- Consumes: `undeclared_broad_handlers(src, label)`, `SHIPPABLE_DIRS`, `REPO_ROOT` from Task 1.
- Produces: the invariant. Nothing consumes it.

- [ ] **Step 1: Write the test**

Append to `tests/audit/test_fail_open_declared.py`:

```python
def _shippable_py_files() -> list[Path]:
    files: list[Path] = []
    for rel in SHIPPABLE_DIRS:
        root = REPO_ROOT / rel
        if not root.is_dir():
            continue
        files.extend(
            p for p in sorted(root.rglob("*.py")) if "__pycache__" not in p.parts
        )
    return files


def test_every_broad_handler_declares_its_reason():
    """The invariant. A new broad handler is a failing test until someone
    writes down why its failure path is honest — the same contract
    test_destructive_write_paths uses for new write primitives."""
    offenders: list[str] = []
    for path in _shippable_py_files():
        label = str(path.relative_to(REPO_ROOT))
        offenders.extend(
            undeclared_broad_handlers(path.read_text(encoding="utf-8"), label)
        )

    assert not offenders, (
        "Broad exception handler(s) with no written reason:\n\n  "
        + "\n  ".join(offenders)
        + "\n\nA broad handler (`except:`, `except Exception:`, "
        "`except BaseException:`) must say why its failure path is honest:\n\n"
        "    except Exception:  # noqa: BLE001 - <reason>\n\n"
        "Three dispositions:\n"
        "  1. MARK it   - the clean return is a correct answer here. Write the reason.\n"
        "  2. FIX it    - the clean return conceals a failure. Log it, return a\n"
        "                 tri-state, or let it raise.\n"
        "  3. NARROW it - catch the exception you actually expect. A named\n"
        "                 exception is self-documenting and leaves this rule's scope.\n\n"
        "See docs/superpowers/specs/2026-08-22-fail-open-declared-design.md"
    )
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `uv run pytest tests/audit/test_fail_open_declared.py -q`
Expected: 10 passed. If the invariant FAILS, the listed sites were missed by Tasks 2–4 — mark or fix them. Do NOT weaken the rule to make it pass.

- [ ] **Step 3: Verify the invariant actually bites**

An invariant never observed failing is not known to work. Introduce a violation and confirm it is caught:

```bash
printf '\n\ndef _audit_probe():\n    try:\n        pass\n    except Exception:\n        return None\n' >> lib/ren_paths.py
uv run pytest tests/audit/test_fail_open_declared.py::test_every_broad_handler_declares_its_reason -q
```

Expected: FAIL, naming `lib/ren_paths.py` and the probe's line number.

Then revert the probe — this must leave no trace:

```bash
git checkout -- lib/ren_paths.py
git diff --stat
```

Expected: `git diff --stat` prints nothing.

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest tests/ -q`
Expected: 3627 passed, 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add tests/audit/test_fail_open_declared.py
git commit -m "test(audit): make the BLE001 reason convention binding

Sweeps every .py under the shippable dirs; a broad handler without a
written reason now fails the build. The convention was already kept at
88% (66 of 75) with no gate — ruff is unconfigured and never runs — so
the 12% became a discovery queue that refilled every review session.

Failure output names each site and states the three dispositions.

Spec: docs/superpowers/specs/2026-08-22-fail-open-declared-design.md 3"
```

---

## Acceptance

The work is done when all of the following hold:

- [ ] `uv run pytest tests/ -q` reports 3627 passed, 1 skipped.
- [ ] `uv run pytest tests/audit/test_fail_open_declared.py -q` reports 10 passed.
- [ ] The Task 5 Step 3 probe was run and observed to FAIL, then reverted cleanly (`git diff --stat` empty).
- [ ] `grep -rn 'return "0\.8\.3"' skills/` returns nothing.
- [ ] `git log --oneline` shows five commits on `worktree-fail-open-declared` above the spec commit.

## Deliberate non-goals

Carried from spec §3.2 and §7. Do not add these; if one seems necessary, stop and raise it rather than widening scope.

- **No ruff configuration.** Adding `[tool.ruff]` plus a CI lint step would surface findings across 247 files. One rule, one test.
- **No guard-clause rule.** Early returns on unmet preconditions (`if not root.is_dir(): return []`) are pervasive and usually correct. The three silent-skip ledger items are that shape and are NOT closed by this work.
- **No exemption for re-raising handlers.** A broad handler that re-raises is not fail-open, but that carve-out costs detector complexity for zero current sites. Mark such a handler if one appears.
- **No ledger closures claimed.** This work closes none of the fourteen open ren-os items. It prevents a class from regenerating and fixes two defects, one previously unknown.
