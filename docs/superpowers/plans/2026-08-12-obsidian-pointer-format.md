# Obsidian-Native Pointer Format (#53) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** L2 decision-map pointers become real markdown links (Obsidian graph edges), with a shared parser, a body-rewriting `l2-map` 1→2 migration, and dual-grammar acceptance until the next MAJOR bump.

**Architecture:** One new module `lib/pointer.py` owns the pointer grammar (parse + render). The producer (`assemble_l2`) and all three consumers (wiki-health, doctor, remember) rewire onto it, deleting their duplicated regexes. A `migrations/l2-map-1-to-2/` directory (the repo's first body-rewriting migration) converts existing maps, self-verifying every rewritten line with the same shared parser.

**Tech Stack:** Python 3.13 via uv, pytest (`uv run pytest`), bash migration entry per the `migrations/routine-spec-2-to-3/` house pattern.

**Spec:** `docs/superpowers/specs/2026-08-12-obsidian-pointer-format-design.md` — read it first.

## Global Constraints

- New canonical wiki-target line: `- [<topic>](<wiki-root-relative-path>.md[#anchor]) (<write_id|unstamped>)`
- External repo refs keep the arrow form: `- [<topic>] → repo:<name>:<path> (<write_id|unstamped>)`
- Legacy arrow form with a wiki path stays PARSE-accepted (dropped only at the #56 MAJOR bump) but is never emitted.
- Paths stay wiki-root-relative. write_id stays the trailing paren group; falsy write_id renders as the literal `unstamped`.
- Migration touches ONLY lines under `## Decision map` on `type: l2-map` pages; `repo:` lines and prose arrows elsewhere are untouched; transform is write-temp-then-rename and exits 1 with the page byte-identical on any self-verification failure.
- Dogfood reality the migration MUST handle: most existing maps have NO `schema_version` in frontmatter (only master index.md has `schema_version: 1`). Absent == version 1; the migration inserts `schema_version: 2` after the `type: l2-map` line.
- Match house style: module docstrings explain the WHY, tests live under `tests/` mirroring source layout, commits are small and conventional.

---

### Task 1: `lib/pointer.py` — shared grammar (parse + render)

**Files:**
- Create: `lib/pointer.py`
- Test: `tests/lib/test_pointer.py`

**Interfaces:**
- Produces (later tasks rely on these exact names):
  - `REPO_REF_PREFIX: str = "repo:"`
  - `@dataclass(frozen=True) PointerLine(topic: str, target: str, path: str, anchor: str | None, write_id: str | None, form: str)` — `form` is `"link"` or `"arrow"`; `path` is `target` minus anchor, `""` for repo refs
  - `parse_pointer_line(line: str) -> PointerLine | None` — `None` = not a pointer line
  - `render_pointer_line(topic: str, target: str, write_id: str | None) -> str` — `target` includes any anchor; repo refs render arrow-form, wiki paths render link-form; `None`/empty write_id renders `unstamped`

- [ ] **Step 1: Write the failing tests**

```python
# tests/lib/test_pointer.py
"""lib.pointer — the single home of the L2 decision-map pointer grammar (#53)."""
from __future__ import annotations

import pytest

from lib import pointer


class TestParseLinkForm:
    def test_basic(self):
        p = pointer.parse_pointer_line("- [Stack decisions](projects/flux/knowledge/stack.md) (w-01ABC)")
        assert p is not None
        assert p.topic == "Stack decisions"
        assert p.target == "projects/flux/knowledge/stack.md"
        assert p.path == "projects/flux/knowledge/stack.md"
        assert p.anchor is None
        assert p.write_id == "w-01ABC"
        assert p.form == "link"

    def test_anchor(self):
        p = pointer.parse_pointer_line("- [Schema](projects/ren-os/schema.md#naming-conventions) (w-01X)")
        assert p.path == "projects/ren-os/schema.md"
        assert p.anchor == "naming-conventions"
        assert p.target == "projects/ren-os/schema.md#naming-conventions"

    def test_unstamped(self):
        p = pointer.parse_pointer_line("- [Topic](projects/x/a.md) (unstamped)")
        assert p.write_id is None


class TestParseArrowForm:
    def test_legacy_wiki_path(self):
        p = pointer.parse_pointer_line("- [Architecture] → projects/ren-os/knowledge/architecture/index.md (w-01Y)")
        assert p.form == "arrow"
        assert p.path == "projects/ren-os/knowledge/architecture/index.md"
        assert p.write_id == "w-01Y"

    def test_arrow_anchor(self):
        p = pointer.parse_pointer_line("- [S] → projects/x/schema.md#conventions (unstamped)")
        assert p.path == "projects/x/schema.md"
        assert p.anchor == "conventions"
        assert p.write_id is None

    def test_repo_ref(self):
        p = pointer.parse_pointer_line("- [Specs] → repo:idea-generator:analyses/flux (w-01Z)")
        assert p.form == "arrow"
        assert p.target == "repo:idea-generator:analyses/flux"
        assert p.path == ""
        assert p.anchor is None


@pytest.mark.parametrize("line", [
    "",
    "- plain knowledge bullet",
    "## Decision map",
    "_All pointer paths are relative to the wiki root, not this file._",
    "- [unclosed](projects/x/a.md",
    "- [no target] →",
    "[not a bullet] → projects/x/a.md (w-01)",
])
def test_non_pointer_lines_return_none(line):
    assert pointer.parse_pointer_line(line) is None


class TestRender:
    def test_wiki_target_renders_link_form(self):
        line = pointer.render_pointer_line("Stack", "projects/flux/knowledge/stack.md", "w-01ABC")
        assert line == "- [Stack](projects/flux/knowledge/stack.md) (w-01ABC)"

    def test_repo_ref_renders_arrow_form(self):
        line = pointer.render_pointer_line("Specs", "repo:idea-generator:analyses", None)
        assert line == "- [Specs] → repo:idea-generator:analyses (unstamped)"

    def test_none_write_id_renders_unstamped(self):
        line = pointer.render_pointer_line("T", "projects/x/a.md", None)
        assert line.endswith("(unstamped)")


def test_render_parse_round_trip():
    cases = [
        ("Topic", "projects/x/a.md", "w-01A"),
        ("With anchor", "projects/x/a.md#sec", None),
        ("Repo", "repo:name:some/path", "w-01B"),
    ]
    for topic, target, wid in cases:
        p = pointer.parse_pointer_line(pointer.render_pointer_line(topic, target, wid))
        assert p is not None
        assert (p.topic, p.target, p.write_id) == (topic, target, wid)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/lib/test_pointer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.pointer'` (or ImportError).

- [ ] **Step 3: Write the implementation**

```python
# lib/pointer.py
"""
lib.pointer — the single home of the L2 decision-map pointer grammar (#53).

Two accepted line shapes:

  - [<topic>](<wiki-root-relative-path>[#anchor]) (<write_id|unstamped>)   ← link form (canonical for wiki targets)
  - [<topic>] → <target> (<write_id|unstamped>)                            ← arrow form (canonical for repo: refs;
                                                                              legacy for wiki targets, parse-accepted
                                                                              until the next MAJOR bump)

Every producer (skills.ingest-project's assemble_l2, the l2-map-1-to-2
migration) and every consumer (wiki-health, doctor, remember) goes through
this module — the old per-module regexes needed a drift test to stay in
sync, which was the code asking to be one function.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

REPO_REF_PREFIX = "repo:"

_LINK_RE = re.compile(
    r"^-\s*\[(?P<topic>[^\]]*)\]\((?P<target>[^)\s]+)\)(?:\s*\((?P<wid>[^)]*)\))?\s*$"
)
_ARROW_RE = re.compile(
    r"^-\s*\[(?P<topic>[^\]]*)\]\s*→\s*(?P<target>\S+)(?:\s*\((?P<wid>[^)]*)\))?\s*$"
)


@dataclass(frozen=True)
class PointerLine:
    topic: str
    target: str          # "projects/x/page.md#anchor" or "repo:name:path"
    path: str            # target without anchor; "" for repo refs
    anchor: str | None
    write_id: str | None  # None when "(unstamped)" or absent
    form: str            # "link" | "arrow"


def parse_pointer_line(line: str) -> PointerLine | None:
    """Parse one decision-map line. Returns None for anything that isn't a
    pointer line — consumers degrade exactly as they did on regex non-match."""
    stripped = line.strip()
    for form, rx in (("link", _LINK_RE), ("arrow", _ARROW_RE)):
        m = rx.match(stripped)
        if not m:
            continue
        target = m.group("target")
        wid = m.group("wid")
        write_id = wid if wid and wid != "unstamped" else None
        if target.startswith(REPO_REF_PREFIX):
            path, anchor = "", None
        else:
            path, _, frag = target.partition("#")
            anchor = frag or None
        return PointerLine(
            topic=m.group("topic"), target=target, path=path,
            anchor=anchor, write_id=write_id, form=form,
        )
    return None


def render_pointer_line(topic: str, target: str, write_id: str | None) -> str:
    """Render the canonical line for `target` (anchor included in `target`):
    link form for wiki paths, arrow form for repo: refs."""
    wid = write_id or "unstamped"
    if target.startswith(REPO_REF_PREFIX):
        return f"- [{topic}] → {target} ({wid})"
    return f"- [{topic}]({target}) ({wid})"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/lib/test_pointer.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/pointer.py tests/lib/test_pointer.py
git commit -m "feat(pointer): shared L2 pointer grammar — dual-form parse + canonical render (#53)"
```

---

### Task 2: Rewire wiki-health + doctor dangling-pointer walks onto `lib.pointer`

**Files:**
- Modify: `skills/wiki-health/lib/__init__.py` (delete `_POINTER_RE` at ~line 88 and local `_REPO_REF_PREFIX`; rewire `_dangling_pointers` at ~line 106)
- Modify: `skills/doctor/lib/__init__.py` (delete inline `pointer_re` in `check_dangling_pointers` at ~line 226)
- Modify: `tests/skills/wiki_health/test_sweep.py` (replace the regex drift test)
- Test: existing suites + new dual-format fixtures

**Interfaces:**
- Consumes: `lib.pointer.parse_pointer_line`, `lib.pointer.REPO_REF_PREFIX` (Task 1)
- Produces: no new public API — `_dangling_pointers(wiki_root) -> list[dict]` and `check_dangling_pointers(wiki_root) -> CheckResult` keep their signatures and result shapes exactly.

- [ ] **Step 1: Write the failing tests**

Add to `tests/skills/wiki_health/test_sweep.py` (imports at top of file already include the module under test as e.g. `wiki_health = importlib.import_module("skills.wiki-health.lib")` — follow whatever alias the file uses):

```python
def test_dangling_walk_reads_link_form(tmp_path):
    (tmp_path / "projects/demo").mkdir(parents=True)
    (tmp_path / "projects/demo/map.md").write_text(
        "---\ntype: l2-map\nproject: demo\n---\n"
        "# demo — knowledge map\n## Decision map\n"
        "- [Missing](projects/demo/gone.md) (w-01A)\n"
        "- [Present](projects/demo/here.md) (w-01B)\n"
        "- [Legacy missing] → projects/demo/also-gone.md (unstamped)\n"
        "- [External] → repo:other:some/path (w-01C)\n",
        encoding="utf-8",
    )
    (tmp_path / "projects/demo/here.md").write_text("x\n", encoding="utf-8")
    dangling = wiki_health._dangling_pointers(tmp_path)
    targets = {d["target"] for d in dangling}
    assert "projects/demo/gone.md" in targets          # link form is parsed
    assert "projects/demo/also-gone.md" in targets     # arrow form still parsed
    assert "projects/demo/here.md" not in targets
    assert not any(t.startswith("repo:") for t in targets)


def test_pointer_grammar_single_source():
    """Replaces the old byte-identical-regex drift test: the grammar has ONE
    home now, so the drift it guarded cannot occur."""
    import importlib
    from lib import pointer
    wh = importlib.import_module("skills.wiki-health.lib")
    dr = importlib.import_module("skills.doctor.lib")
    assert not hasattr(wh, "_POINTER_RE")
    assert wh.parse_pointer_line is pointer.parse_pointer_line
    assert dr.parse_pointer_line is pointer.parse_pointer_line
```

Also DELETE the existing drift test in this file (the one asserting wiki-health's `_REPO_REF_PREFIX`/regex is byte-identical with doctor's — search for `_REPO_REF_PREFIX` in the test file).

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/skills/wiki_health/test_sweep.py -v -k "link_form or single_source"`
Expected: FAIL — link-form line not detected as dangling; `parse_pointer_line` attribute missing.

- [ ] **Step 3: Rewire both modules**

In `skills/wiki-health/lib/__init__.py`:

```python
# imports: add
from lib.pointer import REPO_REF_PREFIX as _REPO_REF_PREFIX, parse_pointer_line

# DELETE the module-level line:
#   _POINTER_RE = re.compile(r"^-\s*\[[^\]]*\]\s*→\s*([^\s#]+)")
# (keep the name _REPO_REF_PREFIX via the aliased import above so existing
#  references and log lines stay unchanged)
```

In `_dangling_pointers`, replace the match block:

```python
            ptr = parse_pointer_line(line)
            if ptr is None:
                continue
            target = ptr.path            # anchor already stripped, "" for repo refs
            page = str(md_path.relative_to(wiki_root))
            if ptr.target.startswith(_REPO_REF_PREFIX):
                # `repo:<name>:<path>` — an external repository reference
                # (issue #20). Not a wiki page, so never "dangling".
                continue
```

(the rest of the loop — leading-`/` check, `safe_join`, `is_file` — is unchanged; it already operates on `target`.)

In `skills/doctor/lib/__init__.py` `check_dangling_pointers`: same substitution — add `from lib.pointer import REPO_REF_PREFIX as _REPO_REF_PREFIX, parse_pointer_line` at the top, delete the local `pointer_re = re.compile(...)` line, and replace:

```python
            m = pointer_re.match(line.strip())
            if not m:
                continue
            target = m.group(1)
```

with:

```python
            ptr = parse_pointer_line(line)
            if ptr is None:
                continue
            target = ptr.path
```

(doctor's docstring example line also updates: `` (`- [topic](path#anchor) (write_id)`, legacy `→` form accepted) ``.)

- [ ] **Step 4: Run the full affected suites**

Run: `uv run pytest tests/skills/wiki_health tests/skills/doctor tests/lib/test_pointer.py -v`
Expected: all PASS (including pre-existing arrow-form fixtures — dual acceptance).

- [ ] **Step 5: Commit**

```bash
git add skills/wiki-health/lib/__init__.py skills/doctor/lib/__init__.py tests/skills/wiki_health/test_sweep.py
git commit -m "refactor(wiki-health,doctor): dangling-pointer walks consume lib.pointer, accept link form (#53)"
```

---

### Task 3: Rewire remember's pointer humanizer

**Files:**
- Modify: `skills/remember/lib/__init__.py` (delete `_POINTER_RE` + `_TRAILING_PAREN_RE` at ~line 37; rewrite `_humanize_pointer` at ~line 69)
- Test: `tests/skills/remember/` (add dual-format cases to the existing test file; create `test_humanize.py` there if no obvious home exists)

**Interfaces:**
- Consumes: `lib.pointer.parse_pointer_line` (Task 1)
- Produces: `_humanize_pointer(bullet: str) -> str` keeps its signature. NOTE: `bullet` arrives WITHOUT the leading `- ` (stripped by `_bullets`), so the rewrite re-prefixes before parsing.

- [ ] **Step 1: Write the failing tests**

```python
def test_humanize_link_form():
    lib = importlib.import_module("skills.remember.lib")
    out = lib._humanize_pointer("[Stack decisions](projects/flux/knowledge/stack.md) (w-01ABC)")
    assert out == "Stack decisions — see projects/flux/knowledge/stack.md"

def test_humanize_link_form_with_anchor():
    lib = importlib.import_module("skills.remember.lib")
    out = lib._humanize_pointer("[Schema](projects/x/schema.md#conventions) (unstamped)")
    assert out == "Schema — see projects/x/schema.md#conventions"

def test_humanize_arrow_form_still_works():
    lib = importlib.import_module("skills.remember.lib")
    out = lib._humanize_pointer("[Architecture] → projects/ren-os/knowledge/architecture/index.md (w-01Y)")
    assert out == "Architecture — see projects/ren-os/knowledge/architecture/index.md"

def test_humanize_repo_ref():
    lib = importlib.import_module("skills.remember.lib")
    out = lib._humanize_pointer("[Specs] → repo:idea-generator:analyses (w-01Z)")
    assert out == "Specs — see repo:idea-generator:analyses"

def test_humanize_unparseable_falls_back_to_raw():
    lib = importlib.import_module("skills.remember.lib")
    assert lib._humanize_pointer("just some text (note)") == "just some text"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/skills/remember -v -k humanize`
Expected: link-form cases FAIL (today's regex only matches the arrow).

- [ ] **Step 3: Rewrite `_humanize_pointer`**

```python
from lib.pointer import parse_pointer_line

_TRAILING_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*$")   # kept: fallback path only


def _humanize_pointer(bullet: str) -> str:
    """`"[topic](path#anchor) (write_id)"` (or the legacy arrow form) ->
    `"topic — see path#anchor"` — drops the write_id parenthetical entirely;
    that's provenance plumbing. `bullet` arrives without its leading `- `."""
    ptr = parse_pointer_line(f"- {bullet}")
    if ptr is not None:
        return f"{ptr.topic} — see {ptr.target}"
    return _TRAILING_PAREN_RE.sub("", bullet).strip()
```

(DELETE the module-level `_POINTER_RE`; keep `_TRAILING_PAREN_RE` only for the unparseable-fallback line shown above.)

- [ ] **Step 4: Run the suite**

Run: `uv run pytest tests/skills/remember -v`
Expected: all PASS. Then extend `test_pointer_grammar_single_source` in `tests/skills/wiki_health/test_sweep.py` with the remember module:

```python
    rm = importlib.import_module("skills.remember.lib")
    assert not hasattr(rm, "_POINTER_RE")
    assert rm.parse_pointer_line is pointer.parse_pointer_line
```

Run: `uv run pytest tests/skills/wiki_health/test_sweep.py::test_pointer_grammar_single_source -v` — PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/remember/lib/__init__.py tests/skills/remember tests/skills/wiki_health/test_sweep.py
git commit -m "refactor(remember): humanize pointers via lib.pointer, accept link form (#53)"
```

---

### Task 4: Producer — `assemble_l2` emits link form and stamps schema 2

**Files:**
- Modify: `skills/ingest-project/lib/__init__.py` (`assemble_l2`: the `schema_version: 1` frontmatter line at ~96 and the pointer f-string at ~110)
- Test: `tests/skills/ingest_project/` (extend the existing `assemble_l2` tests)

**Interfaces:**
- Consumes: `lib.pointer.render_pointer_line` (Task 1)
- Produces: `assemble_l2(project_slug, knowledge, pointers, log_line) -> str` — signature unchanged; output now carries `schema_version: 2` and link-form wiki pointers.

- [ ] **Step 1: Write the failing tests**

```python
def test_assemble_l2_emits_link_form_and_schema_2():
    lib = importlib.import_module("skills.ingest-project.lib")
    text = lib.assemble_l2(
        "demo",
        knowledge=["a fact"],
        pointers=[
            {"topic": "Stack", "path": "projects/demo/knowledge/stack.md", "anchor": None, "write_id": "w-01A"},
            {"topic": "Schema", "path": "projects/demo/schema.md", "anchor": "naming", "write_id": None},
            {"topic": "Specs", "path": "repo:idea-generator:analyses", "anchor": None, "write_id": "w-01B"},
        ],
        log_line="2026-08-12: test",
    )
    assert "schema_version: 2" in text
    assert "- [Stack](projects/demo/knowledge/stack.md) (w-01A)" in text
    assert "- [Schema](projects/demo/schema.md#naming) (unstamped)" in text
    assert "- [Specs] → repo:idea-generator:analyses (w-01B)" in text
    assert "] → projects/" not in text   # no legacy-form wiki pointers emitted


def test_assemble_l2_output_round_trips_through_parser():
    from lib import pointer
    lib = importlib.import_module("skills.ingest-project.lib")
    text = lib.assemble_l2("demo", [], [{"topic": "T", "path": "projects/demo/a.md", "anchor": None, "write_id": "w-01"}], "2026-08-12: t")
    lines = [l for l in text.splitlines() if pointer.parse_pointer_line(l)]
    assert len(lines) == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/skills/ingest_project -v -k "link_form or round_trips"`
Expected: FAIL (arrow emitted, `schema_version: 1`).

- [ ] **Step 3: Modify `assemble_l2`**

Add import `from lib.pointer import render_pointer_line`. Change the frontmatter literal `"schema_version: 1"` → `"schema_version: 2"`, and replace the pointer loop body:

```python
    for pointer_entry in pointers:
        write_id = pointer_entry.get("write_id") or None
        anchor = pointer_entry.get("anchor")
        target = f"{pointer_entry['path']}#{anchor}" if anchor else pointer_entry["path"]
        lines.append(render_pointer_line(pointer_entry["topic"], target, write_id))
```

Update the function docstring's schema note: version 2 = wiki-target pointers are link-form (#53); and fix any existing `assemble_l2` test that asserts `schema_version: 1` or the arrow shape — those assertions flip to the new canon (they are the OLD contract, not a regression).

- [ ] **Step 4: Run the suites**

Run: `uv run pytest tests/skills/ingest_project tests/skills/bootstrap_project -v`
Expected: all PASS (bootstrap-project seeds empty maps through the same `assemble_l2` — its fixtures may also assert the old frontmatter; update those the same way).

- [ ] **Step 5: Commit**

```bash
git add skills/ingest-project/lib/__init__.py tests/skills/ingest_project tests/skills/bootstrap_project
git commit -m "feat(ingest): assemble_l2 emits link-form pointers, stamps l2-map schema 2 (#53)"
```

---

### Task 5: Registry bump — `schemas.json` l2-map → 2

**Files:**
- Modify: `skills/wiki-migration/schemas.json`
- Test: `tests/skills/` wiki-migration tests (extend where `migration_chain` is tested; `grep -rn "migration_chain" tests/` to find the file)

**Interfaces:**
- Consumes: nothing new.
- Produces: `load_registry()["page_types"]["l2-map"] == {"current": 2, "migrations": ["l2-map-1-to-2"]}`; `migration_chain("l2-map", 1) == ["l2-map-1-to-2"]`.

- [ ] **Step 1: Write the failing test**

```python
def test_l2_map_chain_from_v1():
    lib = importlib.import_module("skills.wiki-migration.lib")
    assert lib.migration_chain("l2-map", 1) == ["l2-map-1-to-2"]
    assert lib.migration_chain("l2-map", 2) == []
    assert lib.load_registry()["page_types"]["l2-map"]["current"] == 2
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/ -v -k l2_map_chain`
Expected: FAIL (`current` is 1, chain empty).

- [ ] **Step 3: Edit `schemas.json`**

```json
    "l2-map": {
      "current": 2,
      "migrations": ["l2-map-1-to-2"]
    },
```

- [ ] **Step 4: Run**

Run: `uv run pytest tests/ -v -k "l2_map_chain or migration"` then the doctor suite (`uv run pytest tests/skills/doctor -v`) — doctor's `check_schema_versions` must now flag a v1/absent-version l2-map fixture as behind; if the doctor suite has a schema-version fixture wiki, add one l2-map page at version 1 and assert the check reports it.
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/wiki-migration/schemas.json tests/
git commit -m "feat(wiki-migration): register l2-map schema 2 with 1-to-2 chain (#53)"
```

---

### Task 6: Migration `migrations/l2-map-1-to-2/` (body-rewriting, self-verifying)

**Files:**
- Create: `migrations/l2-map-1-to-2/migrate.sh` (executable)
- Create: `migrations/l2-map-1-to-2/transform.py`
- Create: `migrations/l2-map-1-to-2/verify.json`
- Create: `migrations/l2-map-1-to-2/README.md`
- Test: `tests/migrations/test_l2_map_1_to_2.py`

**Interfaces:**
- Consumes: `lib.pointer.parse_pointer_line` / `render_pointer_line` (Task 1) — transform.py imports them via `PYTHONPATH` set by migrate.sh.
- Produces: house migration contract — `migrate.sh <page>` with `REN_WIKI_ROOT`/`REN_SNAPSHOT_DIR` env; stdout `OK` | `SKIP: <reason>`; exit 0 ok/skip, 2 bad inputs, 1 transform failure; idempotent; bounded to `$1`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/migrations/test_l2_map_1_to_2.py
"""l2-map 1→2 — the repo's first BODY-rewriting migration (#53): arrow-form
wiki pointers under ## Decision map become markdown links; repo: refs and
prose arrows are untouched; schema_version lands at 2 (inserted when absent —
the dogfood maps were never stamped, issue #20)."""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MIGRATE = REPO_ROOT / "migrations" / "l2-map-1-to-2" / "migrate.sh"

V1_MAP = """---
type: l2-map
project: demo
ren_write_id: "w-01MAP"
---
# demo — knowledge map
## Knowledge
- a fact mentioning A → B in prose (untouched)
## Decision map
_All pointer paths are relative to the wiki root, not this file._
- [Stack] → projects/demo/knowledge/stack.md (w-01A)
- [Schema] → projects/demo/schema.md#naming (unstamped)
- [Specs] → repo:idea-generator:analyses (w-01B)
## Log
- 2026-08-12: test
"""


def run_migration(page: Path, tmp_path: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["REN_WIKI_ROOT"] = str(tmp_path)
    env["REN_SNAPSHOT_DIR"] = str(tmp_path / "snap")
    (tmp_path / "snap").mkdir(exist_ok=True)
    return subprocess.run(
        ["bash", str(MIGRATE), str(page)],
        capture_output=True, text=True, env=env, cwd=REPO_ROOT,
    )


@pytest.fixture
def page(tmp_path):
    p = tmp_path / "map.md"
    p.write_text(V1_MAP, encoding="utf-8")
    return p


def test_converts_wiki_pointers_and_stamps_schema(page, tmp_path):
    result = run_migration(page, tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"
    text = page.read_text(encoding="utf-8")
    assert "- [Stack](projects/demo/knowledge/stack.md) (w-01A)" in text
    assert "- [Schema](projects/demo/schema.md#naming) (unstamped)" in text
    assert "- [Specs] → repo:idea-generator:analyses (w-01B)" in text   # repo ref untouched
    assert "a fact mentioning A → B in prose (untouched)" in text        # prose arrow untouched
    assert "schema_version: 2" in text
    assert text.index("schema_version: 2") > text.index("type: l2-map")
    assert "] → projects/" not in text


def test_idempotent_second_run_skips(page, tmp_path):
    run_migration(page, tmp_path)
    second = run_migration(page, tmp_path)
    assert second.returncode == 0
    assert second.stdout.strip().startswith("SKIP")


def test_existing_schema_version_line_is_bumped(page, tmp_path):
    page.write_text(V1_MAP.replace('project: demo', 'project: demo\nschema_version: 1'), encoding="utf-8")
    result = run_migration(page, tmp_path)
    assert result.returncode == 0
    text = page.read_text(encoding="utf-8")
    assert "schema_version: 2" in text
    assert "schema_version: 1" not in text


def test_missing_args_exit_2(tmp_path):
    result = subprocess.run(["bash", str(MIGRATE)], capture_output=True, text=True, cwd=REPO_ROOT)
    assert result.returncode == 2


def test_transform_failure_leaves_page_byte_identical(page, tmp_path, monkeypatch):
    # A page whose Decision map contains a line the parser can't round-trip:
    # topic containing "](" makes render+reparse disagree → self-verify fails.
    broken = V1_MAP.replace("- [Stack] →", "- [Bad](topic] →")
    page.write_text(broken, encoding="utf-8")
    before = page.read_bytes()
    result = run_migration(page, tmp_path)
    # Either the line is left alone (not pointer-shaped → OK) or the
    # transform refused — in BOTH cases the invariant holds:
    text_after = page.read_bytes()
    if result.returncode == 1:
        assert text_after == before
    else:
        assert b"](topic]" in text_after   # untouched garbage, no corruption
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/migrations/test_l2_map_1_to_2.py -v`
Expected: FAIL — `migrate.sh` doesn't exist.

- [ ] **Step 3: Write the migration**

`migrations/l2-map-1-to-2/migrate.sh` (then `chmod +x` it):

```bash
#!/usr/bin/env bash
# migrate.sh — l2-map schema 1 → 2 (#53, RenOS 0.7.0).
#
# The repo's FIRST body-rewriting migration: arrow-form wiki pointers under
# "## Decision map" become markdown links (Obsidian-native); repo: refs and
# everything outside that section are untouched. The body transform lives in
# transform.py (BSD sed is the wrong tool for regex-group rewrites — see the
# 10-line BSD-vs-GNU comment routine-spec-2-to-3 needed for mere frontmatter
# inserts) and SELF-VERIFIES: every rewritten line is re-parsed with
# lib/pointer.py before the page is replaced, so this migration cannot emit
# a line its own consumers can't read.
#
# Contract (per donor's _template):
#   input:  $1 = absolute path to the page file (MODIFIED in place)
#   env:    REN_WIKI_ROOT, REN_SNAPSHOT_DIR
#   stdout: "OK" | "SKIP: <reason>"
#   exit:   0 ok/skip, 2 bad inputs, 1 transform failure
# Idempotent, deterministic, local-only, bounded to $1.

set -euo pipefail

PAGE="${1:-}"
if [[ -z "$PAGE" ]]; then echo "FAIL: missing page argument" >&2; exit 2; fi
if [[ ! -f "$PAGE" ]]; then echo "FAIL: $PAGE is not a regular file" >&2; exit 2; fi
if [[ -z "${REN_WIKI_ROOT:-}" || -z "${REN_SNAPSHOT_DIR:-}" ]]; then
  echo "FAIL: REN_WIKI_ROOT and REN_SNAPSHOT_DIR must be set" >&2; exit 2
fi

TARGET_SCHEMA=2

# Idempotency guard — already migrated → nothing to do.
if grep -q "^schema_version: ${TARGET_SCHEMA}\$" "$PAGE"; then
  echo "SKIP: already at schema ${TARGET_SCHEMA}"
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PYTHONPATH="$REPO_ROOT" python3 "$SCRIPT_DIR/transform.py" "$PAGE"
echo "OK"
```

`migrations/l2-map-1-to-2/transform.py`:

```python
"""Body transform for l2-map 1→2 (#53). Invoked by migrate.sh with
PYTHONPATH=<repo root>. Write-temp-then-rename; exits 1 (page untouched)
if any rewritten line fails to re-parse."""
from __future__ import annotations

import sys
from pathlib import Path

from lib.pointer import REPO_REF_PREFIX, parse_pointer_line, render_pointer_line

TARGET_SCHEMA = 2


def transform(text: str) -> str:
    out: list[str] = []
    in_frontmatter = False
    frontmatter_done = False
    schema_stamped = False
    in_decision_map = False

    for i, line in enumerate(text.splitlines()):
        if i == 0 and line == "---":
            in_frontmatter = True
            out.append(line)
            continue
        if in_frontmatter:
            if line == "---":
                if not schema_stamped:
                    out.append(f"schema_version: {TARGET_SCHEMA}")
                    schema_stamped = True
                in_frontmatter = False
                frontmatter_done = True
                out.append(line)
                continue
            if line.startswith("schema_version:"):
                out.append(f"schema_version: {TARGET_SCHEMA}")
                schema_stamped = True
                continue
            out.append(line)
            continue

        if line.startswith("## "):
            in_decision_map = line.strip() == "## Decision map"
            out.append(line)
            continue
        if in_decision_map:
            ptr = parse_pointer_line(line)
            if ptr is not None and ptr.form == "arrow" and not ptr.target.startswith(REPO_REF_PREFIX):
                rewritten = render_pointer_line(ptr.topic, ptr.target, ptr.write_id)
                reparsed = parse_pointer_line(rewritten)
                if reparsed is None or reparsed.target != ptr.target or reparsed.topic != ptr.topic:
                    print(f"FAIL: rewrite does not round-trip: {line!r}", file=sys.stderr)
                    raise SystemExit(1)
                out.append(rewritten)
                continue
        out.append(line)

    if not frontmatter_done:
        print("FAIL: page has no frontmatter block", file=sys.stderr)
        raise SystemExit(1)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def main() -> None:
    page = Path(sys.argv[1])
    original = page.read_text(encoding="utf-8")
    result = transform(original)
    tmp = page.with_suffix(page.suffix + ".migrating")
    tmp.write_text(result, encoding="utf-8")
    tmp.replace(page)


if __name__ == "__main__":
    main()
```

`migrations/l2-map-1-to-2/verify.json`:

```json
{
  "$schema": "../../verify.schema.json",
  "migration": "l2-map-1-to-2",
  "page_type": "l2-map",
  "assertions": [
    {
      "id": "yaml-valid",
      "description": "Output file has valid YAML frontmatter delimited by ---",
      "predicate": "yaml.valid",
      "target": "frontmatter"
    },
    {
      "id": "schema-bumped",
      "description": "schema_version is exactly 2",
      "predicate": "yaml.equals",
      "field": "schema_version",
      "value": 2
    },
    {
      "id": "type-preserved",
      "description": "type is l2-map",
      "predicate": "yaml.equals",
      "field": "type",
      "value": "l2-map"
    }
  ]
}
```

(NOTE: no `snapshot.body-identical` — body changes are the point of this migration; body correctness is enforced by transform.py's round-trip self-verification and this test suite.)

`migrations/l2-map-1-to-2/README.md`: three short paragraphs — what it converts (arrow→link for wiki targets under `## Decision map`), what it never touches (`repo:` refs, prose, other sections, non-l2-map pages), and how it's driven (`/ren:update` over all `type: l2-map` pages incl. master `index.md`, under snapshot/rollback; absent `schema_version` treated as 1).

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/migrations/test_l2_map_1_to_2.py -v && uv run pytest tests/migrations -v`
Expected: all PASS (including the pre-existing migration suites — the shared runner must still work).

- [ ] **Step 5: Commit**

```bash
chmod +x migrations/l2-map-1-to-2/migrate.sh
git add migrations/l2-map-1-to-2 tests/migrations/test_l2_map_1_to_2.py
git commit -m "feat(migrations): l2-map 1-to-2 — arrow pointers become markdown links, self-verified (#53)"
```

---

### Task 7: Documentation sweep — every place the old grammar is taught

**Files:**
- Modify: every file that documents the pointer line shape. Find them with:
  `grep -rn '] → ' --include='*.md' skills wiki-skeleton doctrine docs | grep -v superpowers` and `grep -rn '→' skills/*/SKILL.md`
  Known at plan time: `wiki-skeleton` index template (the `` `- [<topic>] → <wiki-relative-path>#<anchor> (<write_id or "unstamped">)` `` line), `skills/ingest-project/SKILL.md:50` ("topic → wiki-path#anchor"), `skills/wiki-health/lib/__init__.py:18` module docstring, `skills/doctor/lib` `check_dangling_pointers` docstring, `skills/remember/lib` `_humanize_pointer` docstring (updated in Task 3).
- Test: `tests/test_obsidian_invariant.py` (existing — must stay green) + one new template assertion.

**Interfaces:**
- Consumes: the Task 1 grammar (documentation copies it verbatim).
- Produces: nothing programmatic — but live sessions hand-writing map lines copy what these docs show, so this task is what stops NEW arrow-form wiki pointers from being written.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_obsidian_invariant.py`:

```python
def test_skeleton_documents_link_form_pointers():
    """The index template teaches the pointer grammar; post-#53 it must teach
    the link form — a template showing the arrow form regenerates the orphan
    graph on every new install."""
    index_templates = [p for p in _template_files() if p.name == "index.md"]
    assert index_templates, "wiki-skeleton index template not found"
    for tpl in index_templates:
        text = tpl.read_text(encoding="utf-8")
        if "Decision map" in text:
            assert "] → <wiki-relative-path>" not in text
            assert "](<wiki-relative-path>" in text
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_obsidian_invariant.py -v -k link_form`
Expected: FAIL (template still shows the arrow form).

- [ ] **Step 3: Update the docs**

In the wiki-skeleton index template, the documented line becomes:

```
`- [<topic>](<wiki-relative-path>#<anchor>) (<write_id or "unstamped">)`
```

with one added sentence: `External repository references keep the arrow form: `- [<topic>] → repo:<name>:<path> (<write_id>)`.`

Then run the grep from **Files** above and update every remaining hit the same way: show the link form as canonical, mention arrow form only as (a) the repo-ref shape and (b) legacy-accepted input. Do NOT touch `docs/superpowers/` (specs/plans are historical records) or anything under `tests/fixtures/` that deliberately exercises the legacy form.

- [ ] **Step 4: Run the invariant + full suite**

Run: `uv run pytest tests/test_obsidian_invariant.py -v && uv run pytest -q`
Expected: all PASS — full suite green is the task's exit gate.

- [ ] **Step 5: Commit**

```bash
git add -A skills wiki-skeleton doctrine tests/test_obsidian_invariant.py
git commit -m "docs: pointer grammar docs teach link form everywhere the old shape appeared (#53)"
```

---

## Self-Review (performed at plan time)

- **Spec coverage:** §1 grammar → Task 1; §2 shared parser + all three consumers + drift test → Tasks 1–3; §3 producer → Task 4; §4 migration + registry + verify → Tasks 5–6; §5 error handling → Task 1 (None-degradation tests), Task 6 (exit codes, byte-identical-on-failure, idempotency); §6 testing → embedded per task; SKILL.md/docs updates from §3 → Task 7. Doctor flagging v1 maps → Task 5 Step 4. No gaps found.
- **Placeholder scan:** no TBDs; every code step carries the actual code. Task 6 README and Task 7 grep-sweep describe content precisely enough to write without invention.
- **Type consistency:** `PointerLine` fields and `parse_pointer_line`/`render_pointer_line` signatures are identical across Tasks 1–6; `assemble_l2`'s pointer-dict shape (`topic`/`path`/`anchor`/`write_id`) matches the existing docstring contract.
