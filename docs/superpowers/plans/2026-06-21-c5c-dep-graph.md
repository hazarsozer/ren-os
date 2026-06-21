# C5c — Dependency-map + Auto-refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the code-map a **dependency-graph layer** (module-level import edges, the "dependency-map" Pillar 5 needs) plus **auto-refresh** (regenerate a stale cache on consumption), and surface both to `/ren:code-map` and the self-improvement loop.

**Architecture:** A new engine-agnostic `lib/codemap/deps.py` derives `{src_file: (dep_files,…)}` edges from Python `import` statements via stdlib `ast` (no external dep; non-Python files degrade to no edges). `CodeMap` gains a `dependencies` field; `core.generate()` populates it and `_serialize`/`_deserialize` persist it (backward-compatible). A new `core.load_fresh()` regenerates the cache when `is_stale` reports drift (trust-but-verify; on-demand only, never wake-up injection per ADR-008/ADR-035). `/ren:code-map --deps` renders the graph; `skills/improve-skill/lib/impact.py` reports a target's dependency footprint.

**Tech Stack:** Python 3 stdlib only (`ast`, `pathlib`, `os`). pytest. Existing `lib/codemap/` engine.

## Global Constraints

- **Engine-agnostic + read-only over the project:** `deps.py` imports nothing from lean-ctx; it only reads source files. The code-map cache stays under `${CLAUDE_PLUGIN_DATA}/code-maps/` — **never** write into the user's project or wiki (ADR-035).
- **Graceful degradation:** unparseable files (`SyntaxError`), non-UTF-8 (`errors="replace"`), missing files (`OSError`), and non-Python files produce **no edges**, never an exception. The whole pipeline must not raise on a malformed project.
- **Backward-compatible model:** `dependencies` is an optional `CodeMap` field defaulting to `{}`; old `.json` sidecars without it deserialize cleanly.
- **Auto-refresh is on-demand only:** `load_fresh` regenerates when stale at the moment of consumption. It does **not** schedule, daemonize, or inject into the wake-up hook (ADR-003 no-daemon, ADR-008 load-on-demand).
- **Deferred (document, don't build):** symbol-level call-graph (function→function). lean-ctx's graph DB is class-only with no usable edge table (`lib/codemap/SPIKE_FINDINGS.md` §2-3); a true call-graph exceeds the adopted tooling. The module-import dependency-graph delivers the Pillar-5 dependency-map need.
- **Gate (run suites SEPARATELY):** `python3 -m pytest lib/codemap/tests/ -q` AND `python3 -m pytest skills/improve-skill/lib/tests/ -q` (combining the two dirs in one pytest call triggers a basename-collision collection error) + `claude plugin validate ./ --strict`.
- **Style:** PEP 8, type annotations on signatures, frozen dataclasses, `from __future__ import annotations`. Match the existing `lib/codemap/` voice.

---

## File Structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `lib/codemap/deps.py` | **Create** | `extract_dependencies(project_root, rel_files) -> dict` — ast import → module-level edges. |
| `lib/codemap/model.py` | **Modify** | Add `dependencies: dict` field to `CodeMap`; add `depends_on(cm, file)` / `dependents_of(cm, file)` pure queries. |
| `lib/codemap/core.py` | **Modify** | `generate()` populates `dependencies`; `_serialize`/`_deserialize` persist it; add `load_fresh(project_name, project_root)`. |
| `lib/codemap/digest.py` | **Modify** | Render a `## Dependencies` section in the digest. |
| `lib/codemap/__init__.py` | **Modify** | Export `load_fresh`, `depends_on`, `dependents_of`, `extract_dependencies`. |
| `lib/codemap/tests/test_deps.py` | **Create** | Edge extraction: absolute + relative imports, hyphenated skill dirs, unparseable/non-py/non-utf8. |
| `lib/codemap/tests/test_core.py` | **Modify** | `load_fresh` regenerates-if-stale; dependencies round-trip through serialize/deserialize. |
| `lib/codemap/tests/test_model.py` | **Modify** | `depends_on`/`dependents_of` + `dependencies` default. |
| `skills/code-map/scripts/code_map.py` | **Modify** | `--deps` flag (uses `load_fresh`; prints the dependency view). |
| `skills/code-map/scripts/tests/` or inline | **Create/Modify** | CLI `--deps` smoke test. |
| `skills/improve-skill/lib/impact.py` | **Create** | `dependency_footprint(target_files, cm) -> ImpactReport` (dependents + dependencies). |
| `skills/improve-skill/lib/tests/test_impact.py` | **Create** | Footprint over a fixture map. |
| `skills/improve-skill/SKILL.md` | **Modify** | One note: the loop surfaces the target's dependency footprint. |
| `skills/code-map/SKILL.md`, `skills/code-map/reference.md` (if present) | **Modify** | Document `--deps`. |
| `CHANGELOG.md`, roadmap, `wiki/log.md`, `wiki/decisions/035-code-map-context-layer.md` | **Modify** | Wire-up (Task 5). |

---

## Task 1: Dependency-graph layer (`deps.py` + model)

**Files:** Create `lib/codemap/deps.py`; Modify `lib/codemap/model.py`; Create `lib/codemap/tests/test_deps.py`; Modify `lib/codemap/tests/test_model.py`.

**Interfaces — Produces:**
- `extract_dependencies(project_root: Path, rel_files: list[str]) -> dict` → `{src_rel: tuple[dst_rel, …]}`, only edges whose target resolves to an in-project file; sorted, self-edges excluded.
- `CodeMap.dependencies: dict` (default `{}`).
- `depends_on(cm: CodeMap, file: str) -> tuple[str, …]` (direct deps of `file`); `dependents_of(cm: CodeMap, file: str) -> tuple[str, …]` (files that import `file`).

- [ ] **Step 1: Write the failing test** — `lib/codemap/tests/test_deps.py`:

```python
import textwrap
from pathlib import Path
from lib.codemap.deps import extract_dependencies

def _w(root, rel, src):
    p = root / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(textwrap.dedent(src)); return rel

def test_absolute_import_edge(tmp_path):
    _w(tmp_path, "lib/codemap/model.py", "X = 1\n")
    _w(tmp_path, "lib/codemap/core.py", "from lib.codemap.model import X\n")
    deps = extract_dependencies(tmp_path, ["lib/codemap/model.py", "lib/codemap/core.py"])
    assert deps["lib/codemap/core.py"] == ("lib/codemap/model.py",)
    assert "lib/codemap/model.py" not in deps  # no outgoing edges

def test_import_package_resolves_to_init(tmp_path):
    _w(tmp_path, "lib/codemap/__init__.py", "\n")
    _w(tmp_path, "app.py", "import lib.codemap\n")
    deps = extract_dependencies(tmp_path, ["lib/codemap/__init__.py", "app.py"])
    assert deps["app.py"] == ("lib/codemap/__init__.py",)

def test_relative_import_in_hyphenated_skill_dir(tmp_path):
    _w(tmp_path, "skills/improve-skill/lib/types.py", "class A: ...\n")
    _w(tmp_path, "skills/improve-skill/lib/preflight.py", "from .types import A\n")
    rels = ["skills/improve-skill/lib/types.py", "skills/improve-skill/lib/preflight.py"]
    deps = extract_dependencies(tmp_path, rels)
    assert deps["skills/improve-skill/lib/preflight.py"] == ("skills/improve-skill/lib/types.py",)

def test_unparseable_and_nonpy_and_external_yield_no_edges(tmp_path):
    _w(tmp_path, "broken.py", "def (:\n")          # SyntaxError
    _w(tmp_path, "data.json", "{}\n")               # non-py
    _w(tmp_path, "ext.py", "import os\nimport requests\n")  # external, not in project
    deps = extract_dependencies(tmp_path, ["broken.py", "data.json", "ext.py"])
    assert deps == {}  # no in-project edges, no crash

def test_non_utf8_is_tolerated(tmp_path):
    p = tmp_path / "weird.py"; p.write_bytes(b"\xff\xfe import os\n")
    assert extract_dependencies(tmp_path, ["weird.py"]) == {}  # no crash, no edge
```

- [ ] **Step 2: Run to verify it fails** — `python3 -m pytest lib/codemap/tests/test_deps.py -q` → FAIL (`No module named lib.codemap.deps`).

- [ ] **Step 3: Implement** `lib/codemap/deps.py`:

```python
"""Module-level dependency graph from Python imports (stdlib ast). Engine-agnostic.
Resolves both absolute imports (via a dotted-name index) and relative imports
(directory-relative, so hyphenated skill dirs like skills/improve-skill/ work)."""
from __future__ import annotations

import ast
from pathlib import Path


def _module_index(py_rel_files: list[str]) -> dict:
    """dotted importable name -> rel file. 'a/b/c.py'->'a.b.c'; 'a/b/__init__.py'->'a.b'."""
    index: dict = {}
    for rel in py_rel_files:
        parts = rel[:-3].split("/")
        dotted = ".".join(parts[:-1]) if parts[-1] == "__init__" else ".".join(parts)
        if dotted:
            index.setdefault(dotted, rel)
    return index


def _resolve_absolute(dotted: str, index: dict) -> str | None:
    """Longest-prefix match: 'lib.codemap.model.X' -> file for 'lib.codemap.model'."""
    parts = dotted.split(".")
    while parts:
        cand = ".".join(parts)
        if cand in index:
            return index[cand]
        parts.pop()
    return None


def _resolve_relative(node: ast.ImportFrom, importer_rel: str, present: set) -> str | None:
    """Directory-relative resolution for `from . / .. import` (handles hyphenated dirs)."""
    pkg = Path(importer_rel).parent
    for _ in range(node.level - 1):           # level 1 = same dir; each extra level goes up
        pkg = pkg.parent
    sub = Path(*node.module.split(".")) if node.module else Path()
    for cand in (f"{(pkg / sub)}.py", f"{(pkg / sub / '__init__')}.py"):
        cand = cand.replace("\\", "/")
        if cand in present:
            return cand
    return None


def extract_dependencies(project_root, rel_files: list[str]) -> dict:
    """{src_rel: tuple[dst_rel,...]} import edges resolved to in-project files. Never raises."""
    project_root = Path(project_root).resolve()
    py = [r for r in rel_files if r.endswith(".py")]
    index, present = _module_index(py), set(py)
    deps: dict = {}
    for rel in py:
        try:
            tree = ast.parse((project_root / rel).read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError, ValueError):
            continue
        targets: set = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    hit = _resolve_absolute(a.name, index)
                    if hit:
                        targets.add(hit)
            elif isinstance(node, ast.ImportFrom):
                hit = (_resolve_relative(node, rel, present) if node.level
                       else _resolve_absolute(node.module or "", index))
                if hit:
                    targets.add(hit)
        targets.discard(rel)
        if targets:
            deps[rel] = tuple(sorted(targets))
    return deps
```

- [ ] **Step 4: Run to verify it passes** — `python3 -m pytest lib/codemap/tests/test_deps.py -q` → PASS (5/5).

- [ ] **Step 5: Extend the model** — in `lib/codemap/model.py` add `from dataclasses import dataclass, field`, add to `CodeMap` (after `symbols`): `dependencies: dict = field(default_factory=dict)  # {src_rel: tuple[dst_rel,...]}`. Add two pure queries:

```python
def depends_on(cm: "CodeMap", file: str) -> tuple:
    """Direct dependencies of `file` (its import targets)."""
    return tuple(cm.dependencies.get(file, ()))

def dependents_of(cm: "CodeMap", file: str) -> tuple:
    """Files that import `file` (reverse edges)."""
    return tuple(sorted(src for src, dsts in cm.dependencies.items() if file in dsts))
```

Add to `lib/codemap/tests/test_model.py`:

```python
def test_dependencies_default_empty_and_queries():
    from lib.codemap.model import CodeMap, depends_on, dependents_of
    cm = CodeMap(project_path="/p", generated_at="t", git_commit="", file_hashes={}, symbols=(),
                 dependencies={"a.py": ("b.py",), "c.py": ("b.py",)})
    assert depends_on(cm, "a.py") == ("b.py",)
    assert dependents_of(cm, "b.py") == ("a.py", "c.py")
    cm2 = CodeMap(project_path="/p", generated_at="t", git_commit="", file_hashes={}, symbols=())
    assert cm2.dependencies == {}  # backward-compatible default
```

- [ ] **Step 6: Run model + deps tests** — `python3 -m pytest lib/codemap/tests/test_deps.py lib/codemap/tests/test_model.py -q` → PASS.

- [ ] **Step 7: Commit** — `git add lib/codemap/deps.py lib/codemap/model.py lib/codemap/tests/test_deps.py lib/codemap/tests/test_model.py && git commit -m "feat(c5c): module-level dependency graph (ast) + CodeMap.dependencies + queries"`

---

## Task 2: Persist dependencies + `load_fresh` auto-refresh (`core.py`)

**Files:** Modify `lib/codemap/core.py`, `lib/codemap/__init__.py`; Modify `lib/codemap/tests/test_core.py`.

**Interfaces:**
- Consumes: `extract_dependencies` (Task 1), existing `is_stale`, `generate`, `load_cached_map`.
- Produces: `load_fresh(project_name: str, project_root) -> CodeMap | None` — returns a non-stale map, regenerating if the cache drifted; `None` if no cache and generation is impossible (engine unavailable). `_serialize`/`_deserialize` round-trip `dependencies`.

- [ ] **Step 1: Write failing tests** — add to `lib/codemap/tests/test_core.py`:

```python
def test_dependencies_round_trip(tmp_path, monkeypatch):
    from lib.codemap import core
    from lib.codemap.model import CodeMap
    cm = CodeMap(project_path="/p", generated_at="t", git_commit="abc",
                 file_hashes={"a.py": "h"}, symbols=(), dependencies={"a.py": ("b.py",)})
    text = core._serialize(cm)
    assert core._deserialize(text).dependencies == {"a.py": ("b.py",)}

def test_deserialize_legacy_without_dependencies():
    from lib.codemap import core
    legacy = '{"project_path":"/p","generated_at":"t","git_commit":"","file_hashes":{},"symbols":[]}'
    assert core._deserialize(legacy).dependencies == {}

def test_load_fresh_regenerates_when_stale(tmp_path, monkeypatch):
    from lib.codemap import core
    calls = {"n": 0}
    fake = object()
    monkeypatch.setattr(core, "load_cached_map", lambda name: _StubMap())
    monkeypatch.setattr(core, "is_stale", lambda cm, root: _StaleTrue())
    monkeypatch.setattr(core, "generate", lambda root, *, project_name: calls.__setitem__("n", calls["n"]+1) or fake)
    out = core.load_fresh("proj", tmp_path)
    assert out is fake and calls["n"] == 1   # regenerated because stale

def test_load_fresh_uses_cache_when_fresh(tmp_path, monkeypatch):
    from lib.codemap import core
    cached = _StubMap()
    monkeypatch.setattr(core, "load_cached_map", lambda name: cached)
    monkeypatch.setattr(core, "is_stale", lambda cm, root: _StaleFalse())
    monkeypatch.setattr(core, "generate", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not regenerate")))
    assert core.load_fresh("proj", tmp_path) is cached

class _StubMap: pass
class _StaleTrue:
    def __bool__(self): return True
class _StaleFalse:
    def __bool__(self): return False
```

- [ ] **Step 2: Run → FAIL** (`load_fresh` undefined; serialize lacks dependencies).

- [ ] **Step 3: Implement** in `lib/codemap/core.py`:
  - import: `from lib.codemap.deps import extract_dependencies`.
  - In `_serialize`, add `"dependencies": {k: list(v) for k, v in cm.dependencies.items()}` to the dict.
  - In `_deserialize`, add `dependencies={k: tuple(v) for k, v in d.get("dependencies", {}).items()}` to the `CodeMap(...)` call.
  - In `generate()`, compute the source list once and pass it both places:
    ```python
    sources = enumerate_source_files(project_root)
    cm = CodeMap(
        project_path=str(project_root),
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        git_commit=_git_commit(project_root),
        file_hashes=hash_files(project_root, sources),
        symbols=tuple(symbols),
        dependencies=extract_dependencies(project_root, sources),
    )
    ```
  - Add:
    ```python
    def load_fresh(project_name: str, project_root) -> "CodeMap | None":
        """Return a non-stale CodeMap, regenerating the cache if it drifted (trust-but-verify).
        On-demand only — never scheduled or injected at wake-up (ADR-008/ADR-035)."""
        cm = load_cached_map(project_name)
        if cm is None:
            return None
        if is_stale(cm, Path(project_root)):
            return generate(Path(project_root), project_name=project_name)
        return cm
    ```

- [ ] **Step 4: Run → PASS**; export in `lib/codemap/__init__.py` (`load_fresh`, `depends_on`, `dependents_of`, `extract_dependencies`).

- [ ] **Step 5: Commit** — `git commit -m "feat(c5c): persist dependencies + load_fresh auto-refresh (regenerate-if-stale)"`

---

## Task 3: Surface in the digest + `/ren:code-map --deps`

**Files:** Modify `lib/codemap/digest.py`, `skills/code-map/scripts/code_map.py`; add a CLI smoke test; Modify `skills/code-map/SKILL.md` (+ `reference.md` if present).

- [ ] **Step 1 (RED): digest test** — read `lib/codemap/digest.py` + `tests/test_digest.py` first. Add a test asserting that a `CodeMap` with `dependencies={"a.py": ("b.py",)}` renders a `## Dependencies` section containing `a.py → b.py`. Then add a `## Dependencies` block to `render_digest` (omit the section entirely when `dependencies` is empty, to keep small maps clean).

- [ ] **Step 2 (RED): CLI test** — add a smoke test (mirror the existing code-map script test pattern) that runs `code_map.py <fixture> --name t --deps` and asserts exit 0 and that dependency lines (or a "no dependencies" note) print. Then add to `code_map.py`:
  - `ap.add_argument("--deps", action="store_true", help="show the module dependency graph (auto-refreshes if stale)")`.
  - import `load_fresh, depends_on, dependents_of` from `lib.codemap`.
  - When `args.deps`: call `cm = load_fresh(args.name, project_root)`; if `None`, print the existing `INSTALL_HINT`/"run /ren:code-map first" and return 0; else print a compact view:
    ```
    DEPENDENCIES (<E> edges across <F> files) — auto-refreshed
    <src> → <dep1>, <dep2>
    ...
    ```
    Handle `--deps` before the staleness-banner branch. Keep graceful-degrade + exit 0.

- [ ] **Step 3: GREEN** — run `python3 -m pytest lib/codemap/tests/ -q` and the code-map script test; both pass. `claude plugin validate ./ --strict` ✔.

- [ ] **Step 4: Commit** — `git commit -m "feat(c5c): /ren:code-map --deps + digest Dependencies section"`

---

## Task 4: Minimal improve-skill impact-surface (`impact.py`)

**Files:** Create `skills/improve-skill/lib/impact.py`, `skills/improve-skill/lib/tests/test_impact.py`; Modify `skills/improve-skill/SKILL.md`.

**Interface — Produces:** `dependency_footprint(target_files: set[str], cm: CodeMap) -> ImpactReport` where `ImpactReport` is a frozen dataclass `(dependencies: tuple, dependents: tuple)` — the union of what the target files import, and what imports them (both excluding the target set itself). Pure function over a `CodeMap`; no I/O.

- [ ] **Step 1 (RED)** — `skills/improve-skill/lib/tests/test_impact.py`:

```python
from lib.codemap.model import CodeMap
from skills_improve_skill_lib_impact import dependency_footprint  # see import note below
```

> Import note: improve-skill tests import the package as it is laid out; mirror the existing `test_*` imports in `skills/improve-skill/lib/tests/` (they import siblings via the same mechanism `preflight`/`types` use). Use that exact pattern — do not invent a new import path.

```python
def test_footprint_reports_deps_and_dependents():
    cm = CodeMap(project_path="/p", generated_at="t", git_commit="", file_hashes={}, symbols=(),
                 dependencies={
                     "skills/x/lib/a.py": ("lib/codemap/model.py",),   # target depends on model
                     "skills/y/lib/b.py": ("skills/x/lib/a.py",),      # y depends on target
                 })
    rep = dependency_footprint({"skills/x/lib/a.py"}, cm)
    assert rep.dependencies == ("lib/codemap/model.py",)
    assert rep.dependents == ("skills/y/lib/b.py",)

def test_footprint_excludes_target_set_and_is_empty_safe():
    cm = CodeMap(project_path="/p", generated_at="t", git_commit="", file_hashes={}, symbols=(), dependencies={})
    rep = dependency_footprint({"skills/x/lib/a.py"}, cm)
    assert rep.dependencies == () and rep.dependents == ()
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** `skills/improve-skill/lib/impact.py`:

```python
"""Dependency footprint of an improve-skill target, over the code-map dependency graph.
Read-only impact awareness for the Karpathy loop (Pillar 5 dependency-map consumer)."""
from __future__ import annotations

from dataclasses import dataclass

from lib.codemap.model import CodeMap, depends_on, dependents_of


@dataclass(frozen=True)
class ImpactReport:
    dependencies: tuple   # what the target imports (outgoing), minus the target set
    dependents: tuple     # what imports the target (incoming), minus the target set


def dependency_footprint(target_files: set, cm: CodeMap) -> ImpactReport:
    deps: set = set()
    dependents: set = set()
    for f in target_files:
        deps.update(depends_on(cm, f))
        dependents.update(dependents_of(cm, f))
    deps -= set(target_files)
    dependents -= set(target_files)
    return ImpactReport(dependencies=tuple(sorted(deps)), dependents=tuple(sorted(dependents)))
```

- [ ] **Step 4: Run → PASS** (`python3 -m pytest skills/improve-skill/lib/tests/test_impact.py -q`). Add ONE sentence to `skills/improve-skill/SKILL.md` (in the pre-flight / context section): the loop may surface the target skill's dependency footprint (its `lib/` dependencies + dependents) via `impact.dependency_footprint` over the project code-map, so the operator sees the blast radius before iterating. Keep it informational (not a new gate).

- [ ] **Step 5: Commit** — `git commit -m "feat(c5c): improve-skill dependency-footprint impact surface"`

---

## Task 5: Wire-up

**Files:** `CHANGELOG.md`, roadmap, `wiki/log.md`, `wiki/decisions/035-code-map-context-layer.md`.

- [ ] **Step 1:** `CHANGELOG.md` — Added bullet: C5c dependency-map (ast import graph) + `load_fresh` auto-refresh + `/ren:code-map --deps` + improve-skill impact surface; symbol-level call-graph deferred. **No version bump** (release human-gated).
- [ ] **Step 2:** Roadmap — flip the **C5c** row to `✅ DONE 2026-06-21 — dependency-map (module import graph) + auto-refresh + --deps + improve-skill impact; call-graph deferred; plan docs/superpowers/plans/2026-06-21-c5c-dep-graph.md`. Update the critical-path note if it lists C5c pending.
- [ ] **Step 3:** `wiki/log.md` — APPEND a chronological 2026-06-21 milestone (append-only; do not touch prior entries). Record what shipped + the call-graph deferral + the lean-ctx-graph-is-class-only finding.
- [ ] **Step 4:** `wiki/decisions/035-code-map-context-layer.md` — append a brief **amendment 2026-06-21** noting C5c realized the "doubles as C5's dep-map" consequence via a stdlib-ast module-import graph (engine-agnostic, not the lean-ctx graph DB which is class-only), plus `load_fresh` on-demand auto-refresh; symbol call-graph explicitly deferred. (Light amendment, not a new ADR.)
- [ ] **Step 5: Commit** — `git commit -m "docs(c5c): wire-up — CHANGELOG, roadmap, wiki log + ADR-035 amendment"`

---

## Self-Review

**Spec coverage:** roadmap C5c = "self-improvement dep/call-graph + auto-refresh; extends sf-improve-skill + lib/codemap/." → dep-graph = Task 1; auto-refresh = Task 2 (`load_fresh`); extends lib/codemap = Tasks 1-3; extends sf-improve-skill = Task 4; call-graph = explicitly deferred + documented (Task 5 / ADR-035). Covered.

**Placeholder scan:** `deps.py`, model queries, `load_fresh`, `impact.py` are complete code. The digest/CLI/SKILL edits reference reading the existing file first (digest.py, code_map.py, the improve-skill test import pattern) — concrete instructions, not "handle appropriately."

**Type/name consistency:** `dependencies: dict {src_rel: tuple[dst_rel]}` is consistent across `extract_dependencies` (producer), `CodeMap.dependencies` (storage), `_serialize`/`_deserialize` (list↔tuple), `depends_on`/`dependents_of` (queries), and `dependency_footprint` (consumer). `load_fresh(project_name, project_root)` signature matches its test and the CLI call site.

**Risk note for the implementer:** the improve-skill test import mechanism differs from `lib/codemap` tests — Task 4 Step 1 must mirror the EXISTING `skills/improve-skill/lib/tests/` import pattern (how they reach `preflight`/`types`/`lib.codemap`), not the placeholder name shown. Read a sibling test first.
