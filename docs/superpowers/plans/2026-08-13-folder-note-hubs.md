# Folder-Note Hubs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename every knowledge-hub `index.md` to a folder note (`<topic>/<topic>.md`), rewrite all inbound links, move parsers/emitters in lockstep, and ship a default Obsidian graph config — so the wiki graph reads as a legible hierarchy.

**Architecture:** One global tree-wide migration (`migrations/folder-note-hubs-1/migrate.py` + `verify.py`) following the `project-knowledge-1` precedent, driven by `/ren:update`'s prose with a gate helper in `skills/update/lib`. Parser updates in wiki-health/lint/doctor accept the folder-note convention (dual-accepting legacy `index.md` where transition safety needs it). A `write_default_graph_config` helper in `skills/install/lib` writes `.obsidian/graph.json` only when absent.

**Tech Stack:** Python 3.11+, pytest via `uv run pytest`, no new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-13-folder-note-hubs-design.md`

## Deviations from the spec (approved rationale, flag to Hazar at review)

1. **Global migration, not a per-page chain.** `run_migration` executes only per-page `migrate.sh`, and a hub rename must see the whole tree (renames + cross-page link rewrites). Ships as a `global_migrations` entry with `migrate.py`, like `project-knowledge-1` (which also did renames + pointer rewrites).
2. **Direct writes + migration journal, not queue writes.** Every existing migration writes directly and journals to `state_dir()/migrations/<name>.jsonl`; `project-knowledge-1`'s docstring documents why (invented write_ids would make the queue journal lie). Revertibility comes from the whole-wiki pre-update snapshot (`skills/update/scripts/snapshot.sh`).
3. **No `schema_version` bump.** The rename is structural (filenames), not page-schema. `verify_page`'s predicates are frontmatter-only and `migration_chain` can't drive a tree operation. Migrated-ness is tracked by the migration journal plus a new doctor check that warns on any surviving `knowledge/**/index.md`.
4. **Quarantine graph group keys on banner text.** Obsidian color groups accept content queries; the group matches `"ren-quarantine"`, the distinctive token in `lib.memory.quarantine.QUARANTINE_BANNER`.

## Explicit no-change notes (spec §2 items verified as already correct)

- `skills/remember/lib` needs no change: `_resolve_map_path` touches only `map.md` and the root `index.md`, both unrenamed.
- `skills/wrap/lib/links.py` D4 dedup (`if path in page_text`, L123) needs no change: post-migration maps contain only folder-note paths, so fresh pointers dedup correctly; pre-migration staleness is resolved by the migration itself rewriting the maps.
- `skills/ingest-project/lib` emits no hub filenames in code (hubs are drafted in prose per its SKILL.md) — only the SKILL.md prose changes (Task 7).
- `skills/bootstrap-project/lib` creates `knowledge/` as an empty directory, no hubs — only its SKILL.md prose changes (Task 7).

## Global Constraints

- New migrations must be written in Python (`migrations/README.md` doctrine; shell is legacy).
- Migration output contract: stdout `OK` or `SKIP: <reason>`; exit 0 on ok/skip, 1 on failure.
- Never touch `raw/`, `archive/`, or any dot-directory (`.ren/`, `.obsidian/`) when scanning or rewriting.
- Root `index.md` is never renamed (it is `WIKI_STAMP_MARKER`, the vault entry point).
- `wiki-skeleton/` must never contain a `.obsidian/` directory (`tests/test_obsidian_invariant.py`).
- Okabe-Ito palette only: blue `#0072b2`, bluish green `#009e73`, sky blue `#56b4e9`, orange `#e69f00`. Colour never carries meaning alone — the folder-note naming is the second signal.
- All tests: `uv run pytest tests/... -v`. Full suite must stay green after every task.

---

### Task 1: Migration core — rename map, hub renames, `hub: true` stamp

**Files:**
- Create: `migrations/folder-note-hubs-1/migrate.py`
- Test: `tests/migrations/test_folder_note_hubs_1.py`

**Interfaces:**
- Consumes: `lib.ren_paths.wiki_root()`, `lib.ren_paths.state_dir()` (same imports as `migrations/project-knowledge-1/migrate.py` — open that file first and mirror its import header exactly).
- Produces: `build_rename_map(root: Path) -> dict[Path, Path]` (resolved-absolute old→new), `stamp_hub_true(text: str) -> str`, `main() -> int`. Task 2 adds `rewrite_links` into this same file and its `main`.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for migrations/folder-note-hubs-1. Run with: uv run pytest tests/migrations/test_folder_note_hubs_1.py -v"""
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "migrations" / "folder-note-hubs-1" / "migrate.py"


def _load():
    spec = importlib.util.spec_from_file_location("folder_note_hubs_1", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


HUB = """---
type: project-knowledge
schema_version: 1
project: demo
title: "Research"
hub: true
---

# Research

- [Body Doubling](body-doubling.md)
"""

HUB_NO_FLAG = HUB.replace("hub: true\n", "")


def _mk_wiki(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    import lib.ren_paths as rp
    root = rp.wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_rename_map_finds_knowledge_hubs(tmp_path, monkeypatch):
    root = _mk_wiki(tmp_path, monkeypatch)
    hub = root / "projects/demo/knowledge/research/index.md"
    hub.parent.mkdir(parents=True)
    hub.write_text(HUB, encoding="utf-8")
    nested = root / "projects/demo/knowledge/research/interventions/index.md"
    nested.parent.mkdir(parents=True)
    nested.write_text(HUB, encoding="utf-8")
    mod = _load()
    renames = mod.build_rename_map(root)
    assert renames[hub.resolve()] == hub.parent.resolve() / "research.md"
    assert renames[nested.resolve()] == nested.parent.resolve() / "interventions.md"


def test_rename_map_skips_root_index_raw_and_hidden(tmp_path, monkeypatch):
    root = _mk_wiki(tmp_path, monkeypatch)
    (root / "index.md").write_text("# Root\n", encoding="utf-8")
    raw = root / "projects/demo/raw/knowledge/x/index.md"
    raw.parent.mkdir(parents=True)
    raw.write_text("raw copy", encoding="utf-8")
    snap = root / ".ren/snapshots/w-1/projects/demo/knowledge/research/index.md"
    snap.parent.mkdir(parents=True)
    snap.write_text(HUB, encoding="utf-8")
    mod = _load()
    assert mod.build_rename_map(root) == {}


def test_rename_map_collision_left_alone(tmp_path, monkeypatch):
    root = _mk_wiki(tmp_path, monkeypatch)
    hub = root / "projects/demo/knowledge/research/index.md"
    hub.parent.mkdir(parents=True)
    hub.write_text(HUB, encoding="utf-8")
    (hub.parent / "research.md").write_text("occupied", encoding="utf-8")
    mod = _load()
    assert mod.build_rename_map(root) == {}


def test_stamp_hub_true_inserts_when_missing():
    mod = _load()
    stamped = mod.stamp_hub_true(HUB_NO_FLAG)
    assert "hub: true" in stamped.split("---\n")[1]
    assert mod.stamp_hub_true(HUB) == HUB  # idempotent when present


def test_main_renames_and_stamps(tmp_path, monkeypatch, capsys):
    root = _mk_wiki(tmp_path, monkeypatch)
    hub = root / "projects/demo/knowledge/research/index.md"
    hub.parent.mkdir(parents=True)
    hub.write_text(HUB_NO_FLAG, encoding="utf-8")
    mod = _load()
    assert mod.main() == 0
    assert capsys.readouterr().out.strip().endswith("OK")
    new = hub.parent / "research.md"
    assert not hub.exists() and new.exists()
    assert "hub: true" in new.read_text(encoding="utf-8")


def test_main_skips_when_already_migrated(tmp_path, monkeypatch, capsys):
    root = _mk_wiki(tmp_path, monkeypatch)
    done = root / "projects/demo/knowledge/research/research.md"
    done.parent.mkdir(parents=True)
    done.write_text(HUB, encoding="utf-8")
    mod = _load()
    assert mod.main() == 0
    assert capsys.readouterr().out.startswith("SKIP:")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/migrations/test_folder_note_hubs_1.py -v`
Expected: FAIL — `spec_from_file_location` cannot load a missing `migrate.py` (FileNotFoundError) for every test.

- [ ] **Step 3: Write the migration core**

First open `migrations/project-knowledge-1/migrate.py` and mirror its import header (the `sys.path` bootstrap it uses so `lib.ren_paths` imports when run as a script) and its `_journal` helper shape. Then:

```python
"""folder-note-hubs-1 — knowledge hubs become folder notes.

Renames every `index.md` below a `projects/<slug>/knowledge/` root to
`<parent-folder>.md`, stamps `hub: true` where missing, and (Task 2)
rewrites every inbound link wiki-wide. Tree-wide global migration in the
project-knowledge-1 mold: direct writes + own journal, revertible via the
whole-wiki pre-update snapshot. Spec:
docs/superpowers/specs/2026-08-13-folder-note-hubs-design.md
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

# <sys.path bootstrap copied from project-knowledge-1/migrate.py>
from lib.ren_paths import state_dir, wiki_root

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_SKIP_PARTS = {"raw", "archive"}


def _skipped(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    return any(p.startswith(".") or p in _SKIP_PARTS for p in rel.parts)


def build_rename_map(root: Path) -> dict[Path, Path]:
    """Resolved-absolute {old_index_md: new_folder_note}; collisions skipped with a WARN."""
    renames: dict[Path, Path] = {}
    for knowledge in sorted(root.glob("projects/*/knowledge")):
        for old in sorted(knowledge.rglob("index.md")):
            if _skipped(old, root):
                continue
            new = old.parent / f"{old.parent.name}.md"
            if new.exists():
                print(f"WARN: {new.relative_to(root)} exists; leaving "
                      f"{old.relative_to(root)} for manual repair", file=sys.stderr)
                continue
            renames[old.resolve()] = new.resolve()
    return renames


def stamp_hub_true(text: str) -> str:
    m = _FRONTMATTER_RE.match(text)
    if m is None:
        return text
    block = m.group(1)
    if re.search(r"^hub:", block, re.MULTILINE):
        return text
    return f"---\n{block}\nhub: true\n---\n" + text[m.end():]


def _journal(entries: list[dict]) -> None:
    path = state_dir() / "migrations" / "folder-note-hubs-1.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")


def main() -> int:
    root = wiki_root()
    renames = build_rename_map(root)
    if not renames:
        print("SKIP: no knowledge hubs named index.md")
        return 0
    # Task 2 inserts the link-rewrite pass here, before any rename.
    entries = []
    for old, new in sorted(renames.items()):
        new.write_text(stamp_hub_true(old.read_text(encoding="utf-8")), encoding="utf-8")
        old.unlink()
        entries.append({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "from": str(old.relative_to(root)),
            "to": str(new.relative_to(root)),
        })
    _journal(entries)
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/migrations/test_folder_note_hubs_1.py -v`
Expected: all 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add migrations/folder-note-hubs-1/migrate.py tests/migrations/test_folder_note_hubs_1.py
git commit -m "feat(migration): folder-note-hubs-1 core — hub renames + hub:true stamp (#56)"
```

---

### Task 2: Migration link-rewrite pass

**Files:**
- Modify: `migrations/folder-note-hubs-1/migrate.py`
- Test: `tests/migrations/test_folder_note_hubs_1.py` (append)

**Interfaces:**
- Consumes: Task 1's `build_rename_map`, `main`.
- Produces: `rewrite_links(text: str, page: Path, root: Path, renames: dict[Path, Path]) -> tuple[str, int]`; `main` gains the rewrite pass (all non-skipped `*.md`, before any rename) and a schema.md convention-line rewrite. Journal entries gain a final `{"rewrites": <int>}` record.

- [ ] **Step 1: Write the failing tests (append to the test file)**

```python
MAP = """---
type: l2-map
schema_version: 2
project: demo
---
# demo — map

## Decision map
- [Research](projects/demo/knowledge/research/index.md) (w-01ABC)
- [External](repo:demo:src/main.py) (w-01DEF)

## Sessions
- [session-1](projects/demo/l1/session-1.md)
"""

LEAF = """---
type: project-knowledge
schema_version: 1
project: demo
---
# Body Doubling

Back to the [hub](index.md), or [up](../research/index.md#anchor).
See also [interventions](interventions/index.md).
"""


def _full_wiki(tmp_path, monkeypatch):
    root = _mk_wiki(tmp_path, monkeypatch)
    hub = root / "projects/demo/knowledge/research/index.md"
    hub.parent.mkdir(parents=True)
    hub.write_text(HUB, encoding="utf-8")
    nested = root / "projects/demo/knowledge/research/interventions/index.md"
    nested.parent.mkdir(parents=True)
    nested.write_text(HUB, encoding="utf-8")
    (root / "projects/demo/knowledge/research/body-doubling.md").write_text(LEAF, encoding="utf-8")
    (root / "projects/demo/map.md").write_text(MAP, encoding="utf-8")
    return root


def test_rewrite_root_relative_pointer(tmp_path, monkeypatch):
    root = _full_wiki(tmp_path, monkeypatch)
    mod = _load()
    renames = mod.build_rename_map(root)
    text, n = mod.rewrite_links(MAP, root / "projects/demo/map.md", root, renames)
    assert "- [Research](projects/demo/knowledge/research/research.md) (w-01ABC)" in text
    assert "repo:demo:src/main.py" in text          # repo pointer untouched
    assert "l1/session-1.md" in text                # non-hub link untouched
    assert n == 1


def test_rewrite_file_relative_variants_preserve_style_and_anchor(tmp_path, monkeypatch):
    root = _full_wiki(tmp_path, monkeypatch)
    mod = _load()
    renames = mod.build_rename_map(root)
    leaf = root / "projects/demo/knowledge/research/body-doubling.md"
    text, n = mod.rewrite_links(LEAF, leaf, root, renames)
    assert "[hub](research.md)" in text
    assert "[up](../research/research.md#anchor)" in text
    assert "[interventions](interventions/interventions.md)" in text
    assert n == 3


def test_main_full_run_rewrites_then_renames(tmp_path, monkeypatch, capsys):
    root = _full_wiki(tmp_path, monkeypatch)
    mod = _load()
    assert mod.main() == 0
    map_text = (root / "projects/demo/map.md").read_text(encoding="utf-8")
    assert "research/research.md" in map_text and "research/index.md" not in map_text
    assert (root / "projects/demo/knowledge/research/research.md").exists()
    assert (root / "projects/demo/knowledge/research/interventions/interventions.md").exists()


def test_schema_md_convention_line_rewritten(tmp_path, monkeypatch):
    root = _full_wiki(tmp_path, monkeypatch)
    schema = root / "projects/demo/schema.md"
    schema.write_text(
        "---\ntype: project-schema\nschema_version: 1\n---\n"
        "# Schema\n\n- Hub files are always named `index.md`.\n",
        encoding="utf-8",
    )
    mod = _load()
    assert mod.main() == 0
    text = schema.read_text(encoding="utf-8")
    assert "always named `index.md`" not in text
    assert "folder notes" in text


def test_second_run_is_noop_skip(tmp_path, monkeypatch, capsys):
    root = _full_wiki(tmp_path, monkeypatch)
    mod = _load()
    assert mod.main() == 0
    before = {p: p.read_text(encoding="utf-8") for p in root.rglob("*.md")}
    assert mod.main() == 0
    assert capsys.readouterr().out.strip().endswith("SKIP: no knowledge hubs named index.md")
    assert {p: p.read_text(encoding="utf-8") for p in root.rglob("*.md")} == before
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/migrations/test_folder_note_hubs_1.py -v`
Expected: the 5 new tests FAIL (`rewrite_links` not defined; full-run assertions unmet); Task 1's 6 still pass.

- [ ] **Step 3: Implement the rewrite pass**

Add to `migrate.py` (regex adapted from wiki-health's `_MD_LINK_RE`, split into groups so only the target substring is replaced):

```python
_MD_LINK_RE = re.compile(
    r"(\]\(\s*<?)"                       # opener through optional <
    r"([^()\s#>]+\.md)"                  # target path (no anchor)
    r"((?:#[^()\s>]*)?>?(?:\s+\"[^\"]*\")?\s*\))"  # anchor/title/closer
)
_SCHEMA_HUB_LINE_RE = re.compile(
    r"^- Hub files are always named `index\.md`\.\s*$", re.MULTILINE
)
_SCHEMA_HUB_REPLACEMENT = (
    "- Hub files are folder notes named after their folder "
    "(`<topic>/<topic>.md`), with `hub: true` in frontmatter."
)


def rewrite_links(text: str, page: Path, root: Path,
                  renames: dict[Path, Path]) -> tuple[str, int]:
    """Rewrite md-link targets that resolve (file- or root-relative) to a renamed hub."""
    count = 0

    def _sub(m: re.Match) -> str:
        nonlocal count
        target = m.group(2)
        if not target.endswith("index.md") or target.startswith(("http://", "https://", "repo:", "/")):
            return m.group(0)
        for base in (page.parent, root):
            try:
                cand = (base / target).resolve()
            except OSError:
                continue
            if cand in renames:
                count += 1
                new_target = target[: -len("index.md")] + renames[cand].name
                return m.group(1) + new_target + m.group(3)
        return m.group(0)

    return _MD_LINK_RE.sub(_sub, text), count
```

In `main`, insert between the SKIP guard and the rename loop:

```python
    rewrites = 0
    for page in sorted(root.rglob("*.md")):
        if _skipped(page, root):
            continue
        text = page.read_text(encoding="utf-8")
        new_text, n = rewrite_links(text, page, root, renames)
        if page.name == "schema.md":
            new_text, n2 = _SCHEMA_HUB_LINE_RE.subn(_SCHEMA_HUB_REPLACEMENT, new_text)
            n += n2
        if n:
            page.write_text(new_text, encoding="utf-8")
            rewrites += n
```

and append `{"ts": ..., "rewrites": rewrites}` as a final journal entry (same `ts` expression as the rename entries).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/migrations/test_folder_note_hubs_1.py -v`
Expected: all 11 PASS.

- [ ] **Step 5: Commit**

```bash
git add migrations/folder-note-hubs-1/migrate.py tests/migrations/test_folder_note_hubs_1.py
git commit -m "feat(migration): folder-note-hubs-1 link rewrite — all link classes, style-preserving (#56)"
```

---

### Task 3: Migration verifier, README, registry entry

**Files:**
- Create: `migrations/folder-note-hubs-1/verify.py`
- Create: `migrations/folder-note-hubs-1/README.md`
- Modify: `skills/wiki-migration/schemas.json` (global_migrations list, lines 33–36)
- Test: `tests/migrations/test_folder_note_hubs_1_verify.py`

**Interfaces:**
- Consumes: `lib.ren_paths.wiki_root()`; `lib.pointer.parse_pointer_line` (signature `(line: str) -> PointerLine | None`).
- Produces: `verify.py` with `main() -> int` (exit 0 pass / 1 fail, failures printed one per line as `FAIL <check>: <detail>`) and check functions `leftover_hubs(root) -> list[str]`, `stale_hub_links(root) -> list[str]`, `misnamed_hubs(root) -> list[str]`, `unparseable_pointers(root) -> list[str]`.

The four checks implement the spec's verify assertions:
(a) `leftover_hubs` — zero `index.md` below any `projects/*/knowledge/` (same `_skipped` rules as migrate.py);
(b) `stale_hub_links` — zero md links wiki-wide whose target still ends in `index.md` AND resolves (file- or root-relative) under a `knowledge/` tree — this catches missed rewrites without failing on pre-existing unrelated danglers (e.g. genshin's six, which don't target hub index files);
(c) `misnamed_hubs` — every `hub: true` page under a `knowledge/` tree has `name == f"{parent.name}.md"`;
(d) `unparseable_pointers` — in every `type: l2-map` page, each `## Decision map` bullet starting `- [` parses via `parse_pointer_line`.

- [ ] **Step 1: Write the failing tests**

```python
"""Run with: uv run pytest tests/migrations/test_folder_note_hubs_1_verify.py -v"""
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERIFY = REPO_ROOT / "migrations" / "folder-note-hubs-1" / "verify.py"
MIGRATE = REPO_ROOT / "migrations" / "folder-note-hubs-1" / "migrate.py"


def _load(script):
    spec = importlib.util.spec_from_file_location(script.stem + "_fnh", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mk_wiki(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    import lib.ren_paths as rp
    root = rp.wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


GOOD_HUB = ("---\ntype: project-knowledge\nschema_version: 1\nhub: true\n---\n# Research\n")
GOOD_MAP = ("---\ntype: l2-map\nschema_version: 2\n---\n## Decision map\n"
            "- [Research](projects/demo/knowledge/research/research.md) (w-01ABC)\n")


def _migrated_wiki(tmp_path, monkeypatch):
    root = _mk_wiki(tmp_path, monkeypatch)
    hub = root / "projects/demo/knowledge/research/research.md"
    hub.parent.mkdir(parents=True)
    hub.write_text(GOOD_HUB, encoding="utf-8")
    (root / "projects/demo/map.md").write_text(GOOD_MAP, encoding="utf-8")
    return root


def test_clean_migrated_wiki_passes(tmp_path, monkeypatch):
    _migrated_wiki(tmp_path, monkeypatch)
    assert _load(VERIFY).main() == 0


def test_leftover_index_md_fails(tmp_path, monkeypatch):
    root = _migrated_wiki(tmp_path, monkeypatch)
    stray = root / "projects/demo/knowledge/design/index.md"
    stray.parent.mkdir(parents=True)
    stray.write_text(GOOD_HUB, encoding="utf-8")
    assert _load(VERIFY).main() == 1


def test_stale_hub_link_fails_but_unrelated_dangler_passes(tmp_path, monkeypatch):
    root = _migrated_wiki(tmp_path, monkeypatch)
    page = root / "projects/demo/knowledge/research/note.md"
    page.write_text("---\ntype: project-knowledge\n---\n[x](missing-leaf.md)\n", encoding="utf-8")
    assert _load(VERIFY).main() == 0            # unrelated dangler: not this migration's problem
    page.write_text("---\ntype: project-knowledge\n---\n[x](../research/index.md)\n", encoding="utf-8")
    assert _load(VERIFY).main() == 1            # stale hub link: missed rewrite


def test_misnamed_hub_flag_fails(tmp_path, monkeypatch):
    root = _migrated_wiki(tmp_path, monkeypatch)
    bad = root / "projects/demo/knowledge/design/wrong-name.md"
    bad.parent.mkdir(parents=True)
    bad.write_text(GOOD_HUB, encoding="utf-8")
    assert _load(VERIFY).main() == 1


def test_broken_pointer_line_fails(tmp_path, monkeypatch):
    root = _migrated_wiki(tmp_path, monkeypatch)
    (root / "projects/demo/map.md").write_text(
        GOOD_MAP + "- [broken](projects/demo/knowledge/research/research.md (w-01\n",
        encoding="utf-8")
    assert _load(VERIFY).main() == 1


def test_end_to_end_migrate_then_verify(tmp_path, monkeypatch):
    root = _mk_wiki(tmp_path, monkeypatch)
    hub = root / "projects/demo/knowledge/research/index.md"
    hub.parent.mkdir(parents=True)
    hub.write_text(GOOD_HUB, encoding="utf-8")
    (root / "projects/demo/map.md").write_text(
        GOOD_MAP.replace("research/research.md", "research/index.md"), encoding="utf-8")
    assert _load(MIGRATE).main() == 0
    assert _load(VERIFY).main() == 0


def test_registry_lists_migration():
    import json
    registry = json.loads((REPO_ROOT / "skills/wiki-migration/schemas.json").read_text())
    assert "folder-note-hubs-1" in registry["global_migrations"]["migrations"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/migrations/test_folder_note_hubs_1_verify.py -v`
Expected: FAIL — verify.py missing; registry test fails on membership.

- [ ] **Step 3: Implement verify.py, README, registry entry**

`verify.py` (same `sys.path` bootstrap and `_skipped`/`_MD_LINK_RE`/`_FRONTMATTER_RE` shapes as migrate.py — duplicate them; migration dirs are self-contained by convention, they don't import each other):

```python
"""folder-note-hubs-1 verifier — tree assertions the frontmatter-only
verify_page primitive cannot express. Exit 0 pass, 1 fail."""
from __future__ import annotations

import re
import sys
from pathlib import Path

# <sys.path bootstrap copied from migrate.py>
from lib.pointer import parse_pointer_line
from lib.ren_paths import wiki_root

_SKIP_PARTS = {"raw", "archive"}
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_MD_LINK_RE = re.compile(r"\]\(\s*<?([^()\s#>]+\.md)>?(?:#[^()\s]*)?(?:\s+\"[^\"]*\")?\s*\)")


def _skipped(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    return any(p.startswith(".") or p in _SKIP_PARTS for p in rel.parts)


def _fm(text: str) -> str:
    m = _FRONTMATTER_RE.match(text)
    return m.group(1) if m else ""


def _pages(root: Path):
    for p in sorted(root.rglob("*.md")):
        if not _skipped(p, root):
            yield p


def leftover_hubs(root: Path) -> list[str]:
    return [str(p.relative_to(root))
            for knowledge in sorted(root.glob("projects/*/knowledge"))
            for p in sorted(knowledge.rglob("index.md"))
            if not _skipped(p, root)]


def stale_hub_links(root: Path) -> list[str]:
    out = []
    for page in _pages(root):
        for target in _MD_LINK_RE.findall(page.read_text(encoding="utf-8")):
            if not target.endswith("index.md") or target.startswith(("http", "repo:", "/")):
                continue
            for base in (page.parent, root):
                cand = (base / target).resolve()
                if "knowledge" in cand.parts:
                    out.append(f"{page.relative_to(root)} -> {target}")
                    break
    return out


def misnamed_hubs(root: Path) -> list[str]:
    out = []
    for page in _pages(root):
        if "knowledge" not in page.relative_to(root).parts:
            continue
        if re.search(r"^hub:\s*true\s*$", _fm(page.read_text(encoding="utf-8")), re.MULTILINE):
            if page.name != f"{page.parent.name}.md":
                out.append(str(page.relative_to(root)))
    return out


def unparseable_pointers(root: Path) -> list[str]:
    out = []
    for page in _pages(root):
        text = page.read_text(encoding="utf-8")
        if "type: l2-map" not in _fm(text):
            continue
        in_dm = False
        for line in text.splitlines():
            if line.startswith("## "):
                in_dm = line.strip() == "## Decision map"
                continue
            if in_dm and line.lstrip().startswith("- [") and parse_pointer_line(line) is None:
                out.append(f"{page.relative_to(root)}: {line.strip()[:60]}")
    return out


def main() -> int:
    root = wiki_root()
    failures = []
    for name, fn in (("leftover-hub", leftover_hubs), ("stale-link", stale_hub_links),
                     ("misnamed-hub", misnamed_hubs), ("pointer-parse", unparseable_pointers)):
        for detail in fn(root):
            failures.append(f"FAIL {name}: {detail}")
    for f in failures:
        print(f)
    if failures:
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Note on `unparseable_pointers` vs `lib.pointer`: `parse_pointer_line` returns a `PointerLine` for plain-link bullets without a write_id parenthetical too (the `wid` group is optional), so D1/D3-style narrative bullets inside a Decision map would pass — correct, since the check targets syntax breakage, not grammar policy.

`README.md` (mirror the section shape of `migrations/project-knowledge-1/README.md`): what it does, why global (tree-wide rename + rewrite), contract (`OK`/`SKIP:`/exit codes), how to run (`uv run python migrations/folder-note-hubs-1/migrate.py` then `verify.py`), rollback (whole-wiki pre-update snapshot via `skills/update/scripts/restore.sh`), journal location.

`schemas.json`: append `"folder-note-hubs-1"` to `global_migrations.migrations`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/migrations/test_folder_note_hubs_1_verify.py tests/skills/wiki_migration/ -v`
Expected: all PASS (including existing registry tests — the global list is discoverability-only, nothing walks it as a chain).

- [ ] **Step 5: Commit**

```bash
git add migrations/folder-note-hubs-1/ skills/wiki-migration/schemas.json tests/migrations/test_folder_note_hubs_1_verify.py
git commit -m "feat(migration): folder-note-hubs-1 verifier + registry entry (#56)"
```

---

### Task 4: Update-skill gate + driver prose; doctor mixed-convention check

**Files:**
- Modify: `skills/update/lib/__init__.py` (append near `should_run_foreign_remint_1`)
- Modify: `skills/update/SKILL.md` (new driver step after the l2-map chain walk, lines ~147–195 region)
- Modify: `skills/doctor/lib/__init__.py` (new check near `check_dangling_pointers`, L222)
- Test: `tests/skills/update/test_update_lib.py` (or the module where existing `should_run_*` tests live — find with `grep -rn "should_run_trust_backfill" tests/`), `tests/skills/doctor/test_doctor_hub_convention.py`

**Interfaces:**
- Consumes: `lib.ren_paths.wiki_root()`; doctor's `CheckResult(name: str, status: str, message: str)` frozen dataclass (L64–68) and the existing check-registration pattern (find where `check_dangling_pointers` is aggregated — `grep -n "check_dangling_pointers" skills/doctor/` — and register identically).
- Produces: `should_run_folder_note_hubs_1(wiki_root_path: Path | None = None) -> bool`; `check_hub_convention(wiki_root: Path | None = None) -> CheckResult`.

- [ ] **Step 1: Write the failing tests**

Gate helper (mirror the arrange style of the existing `should_run_*` tests in the same file):

```python
def test_should_run_folder_note_hubs_1_true_when_legacy_hub_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    import lib.ren_paths as rp
    root = rp.wiki_root()
    hub = root / "projects/demo/knowledge/research/index.md"
    hub.parent.mkdir(parents=True)
    hub.write_text("---\ntype: project-knowledge\nhub: true\n---\n# R\n", encoding="utf-8")
    from skills.update.lib_import_helper import update_lib  # use the file's existing import idiom
    assert update_lib.should_run_folder_note_hubs_1() is True


def test_should_run_folder_note_hubs_1_false_when_migrated_or_only_raw(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    import lib.ren_paths as rp
    root = rp.wiki_root()
    done = root / "projects/demo/knowledge/research/research.md"
    done.parent.mkdir(parents=True)
    done.write_text("---\nhub: true\n---\n", encoding="utf-8")
    raw = root / "projects/demo/raw/knowledge/x/index.md"
    raw.parent.mkdir(parents=True)
    raw.write_text("raw", encoding="utf-8")
    from skills.update.lib_import_helper import update_lib
    assert update_lib.should_run_folder_note_hubs_1() is False
```

(The `lib_import_helper` line is a stand-in for however the existing tests in that file import `skills/update/lib` — copy their exact idiom, e.g. `importlib.import_module`. Same applies to the doctor test imports below.)

Doctor check:

```python
def test_check_hub_convention_warns_on_legacy_hub(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    import lib.ren_paths as rp
    root = rp.wiki_root()
    hub = root / "projects/demo/knowledge/research/index.md"
    hub.parent.mkdir(parents=True)
    hub.write_text("---\nhub: true\n---\n", encoding="utf-8")
    result = doctor_lib.check_hub_convention()
    assert result.status == "warn"
    assert "projects/demo/knowledge/research/index.md" in result.message


def test_check_hub_convention_ok_on_migrated_wiki(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    import lib.ren_paths as rp
    root = rp.wiki_root()
    done = root / "projects/demo/knowledge/research/research.md"
    done.parent.mkdir(parents=True)
    done.write_text("---\nhub: true\n---\n", encoding="utf-8")
    result = doctor_lib.check_hub_convention()
    assert result.status == "ok"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/skills/update/ tests/skills/doctor/test_doctor_hub_convention.py -v`
Expected: new tests FAIL (AttributeError: no such function).

- [ ] **Step 3: Implement**

`skills/update/lib/__init__.py`:

```python
def should_run_folder_note_hubs_1(wiki_root_path: Path | None = None) -> bool:
    """True if any legacy knowledge-hub index.md remains (raw/, archive/, dot-dirs excluded)."""
    root = wiki_root_path or wiki_root()
    for knowledge in root.glob("projects/*/knowledge"):
        for p in knowledge.rglob("index.md"):
            rel = p.relative_to(root)
            if any(part.startswith(".") or part in ("raw", "archive") for part in rel.parts):
                continue
            return True
    return False
```

(match the existing `should_run_*` helpers' import of `wiki_root` in that file.)

`skills/doctor/lib/__init__.py` — same body reused to collect paths, first 5 in the message:

```python
def check_hub_convention(wiki_root: Path | None = None) -> CheckResult:
    """Warn on knowledge hubs still named index.md (pre folder-note-hubs-1)."""
    root = wiki_root or _wiki_root()          # match the module's existing root-resolution idiom
    legacy = []
    for knowledge in sorted(root.glob("projects/*/knowledge")):
        for p in sorted(knowledge.rglob("index.md")):
            rel = p.relative_to(root)
            if any(part.startswith(".") or part in ("raw", "archive") for part in rel.parts):
                continue
            legacy.append(str(rel))
    if legacy:
        shown = ", ".join(legacy[:5])
        more = f" (+{len(legacy) - 5} more)" if len(legacy) > 5 else ""
        return CheckResult("hub_convention", "warn",
                           f"legacy index.md hubs pending folder-note-hubs-1: {shown}{more}")
    return CheckResult("hub_convention", "ok", "all knowledge hubs are folder notes")
```

Register it wherever `check_dangling_pointers` is registered (doctor SKILL.md check list and/or an aggregation list in the lib — mirror exactly).

`skills/update/SKILL.md` — after the l2-map chain-walk section (~L195), add a numbered step:

> **Global migration: folder-note-hubs-1.** Gate: `should_run_folder_note_hubs_1()` from `skills.update.lib`. If true — show the friend the pending rename list (the gate's paths), get approval (this is a MAJOR-classified structural change), then run `uv run python migrations/folder-note-hubs-1/migrate.py` followed by `uv run python migrations/folder-note-hubs-1/verify.py`. On verify failure: stop, show the FAIL lines, offer whole-wiki restore via `skills/update/scripts/restore.sh --whole <snapshot>` (the snapshot taken at the start of this update). Never proceed to the closing summary with a failed verify.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/skills/update/ tests/skills/doctor/ -v`
Expected: all PASS, existing doctor/update tests green.

- [ ] **Step 5: Commit**

```bash
git add skills/update/ skills/doctor/ tests/skills/update/ tests/skills/doctor/
git commit -m "feat(update,doctor): folder-note-hubs-1 gate, driver step, hub-convention check (#56)"
```

---

### Task 5: wiki-health + lint accept folder notes (dual-accept legacy)

**Files:**
- Modify: `skills/wiki-health/lib/__init__.py` — `_knowledge_tree_findings` (L328–387)
- Modify: `skills/wiki-health/lib/lint.py` — hub dispatch (L316–319), `_hub_missing_entries` (L151–183), `_incremental_scope` (L356–366)
- Test: `tests/skills/wiki_health/test_folder_note_hubs.py` (new; existing wiki-health tests must stay green)

**Interfaces:**
- Consumes: existing private helpers in those modules (do not change signatures of exported sweep functions).
- Produces: a module-level helper in each file — `_hub_candidates(directory: Path) -> tuple[Path, Path]` returning `(directory / f"{directory.name}.md", directory / "index.md")` (folder-note first, legacy second) — and hub predicates keyed on it. Dual-accept is deliberate: wiki-health must not spray findings on a not-yet-migrated wiki (plugin update lands before the friend runs `/ren:update`); doctor's `check_hub_convention` (Task 4) is the single voice for "you haven't migrated."

Behavior changes, precisely:
1. `_knowledge_tree_findings` hub corpus: for each directory under `knowledge/` (recursive) that contains any `*.md`, the hub is the first existing candidate from `_hub_candidates`; "hubless" fires when neither exists. Leaf-skip rule becomes `if leaf.name in (f"{leaf.parent.name}.md", "index.md") or leaf.parent == knowledge: continue`. The report line `"missing index.md hub page"` (L887–898 rendering) becomes `"missing hub page (<dir>.md)"`.
2. `lint.py` dispatch (L316): `if Path(page).name == "index.md"` becomes a call to `_is_hub_page(page)`:

```python
def _is_hub_page(page: str) -> bool:
    p = Path(page)
    if p.name == "index.md":       # root index + legacy hubs
        return True
    return p.name == f"{p.parent.name}.md" and "knowledge" in p.parts
```

3. `_hub_missing_entries` sibling exclusion (L158) `sib.name != "index.md"` becomes `sib.name != Path(page).name and sib.name != "index.md"` (never list the hub itself, either name).
4. `_incremental_scope` (L356–366): add both candidates of the touched page's parent, not just `parent / "index.md"`.

- [ ] **Step 1: Write the failing tests**

Build a migrated fixture wiki (folder-note hubs) and a legacy fixture (index.md hubs) with the same shape used by existing wiki-health tests (open `tests/skills/wiki_health/` and copy the prevailing fixture idiom — wiki-root env var + literal pages). Assert:

```python
def test_folder_note_hub_recognized_no_hubless_finding(migrated_wiki):
    findings = wh._knowledge_tree_findings(migrated_wiki)
    hubless, unlinked = findings
    assert hubless == []

def test_legacy_index_hub_still_recognized(legacy_wiki):
    hubless, unlinked = wh._knowledge_tree_findings(legacy_wiki)
    assert hubless == []

def test_truly_hubless_dir_flagged_with_folder_note_name(migrated_wiki):
    bare = migrated_wiki / "projects/demo/knowledge/bare"
    bare.mkdir()
    (bare / "leaf.md").write_text("---\ntype: project-knowledge\n---\n# L\n", encoding="utf-8")
    hubless, _ = wh._knowledge_tree_findings(migrated_wiki)
    assert any("bare" in h for h in hubless)

def test_lint_dispatches_hub_fix_on_folder_note(migrated_wiki):
    hub = migrated_wiki / "projects/demo/knowledge/research/research.md"
    hub.write_text(
        "---\ntype: project-knowledge\nhub: true\n---\n# Research\n\n## Pages\n",
        encoding="utf-8",
    )
    (hub.parent / "unlisted-leaf.md").write_text(
        "---\ntype: project-knowledge\n---\n# Unlisted Leaf\n", encoding="utf-8"
    )
    text, added = lint._hub_missing_entries(
        migrated_wiki, "projects/demo/knowledge/research/research.md",
        hub.read_text(encoding="utf-8"),
    )
    assert "- [Unlisted Leaf](unlisted-leaf.md)" in text
    assert added  # non-empty list of added entries


def test_hub_missing_entries_never_lists_hub_itself(migrated_wiki):
    hub = migrated_wiki / "projects/demo/knowledge/research/research.md"
    hub.write_text(
        "---\ntype: project-knowledge\nhub: true\n---\n# Research\n\n## Pages\n",
        encoding="utf-8",
    )
    text, added = lint._hub_missing_entries(
        migrated_wiki, "projects/demo/knowledge/research/research.md",
        hub.read_text(encoding="utf-8"),
    )
    assert "research.md" not in "".join(added)
```

(`lint` = the imported `skills/wiki-health/lib/lint.py` module, imported the same way the existing lint tests import it. Check `_hub_missing_entries`'s exact signature at `lint.py:151` before writing — the argument order above follows the report `(wiki_root, page, text) -> tuple[str, list[str]]`; if the real signature differs, follow the source, and confirm the second return element is the list of added entry strings. Also add a regression assertion to an existing root-index lint test if one exists — root `index.md` must keep its current dispatch behavior via the `p.name == "index.md"` branch of `_is_hub_page`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/skills/wiki_health/test_folder_note_hubs.py -v`
Expected: folder-note cases FAIL (hub not recognized → spurious hubless finding; lint doesn't dispatch); legacy cases PASS.

- [ ] **Step 3: Implement the four behavior changes above**

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/skills/wiki_health/ -v`
Expected: new tests PASS, all existing wiki-health/lint tests PASS unchanged.

- [ ] **Step 5: Commit**

```bash
git add skills/wiki-health/ tests/skills/wiki_health/
git commit -m "feat(wiki-health): folder-note hub convention, dual-accept legacy during transition (#56)"
```

---

### Task 6: Default Obsidian graph config

**Files:**
- Modify: `skills/install/lib/__init__.py`
- Modify: `skills/install/SKILL.md` (Stage 2 "Stamp wiki", ~L58)
- Modify: `skills/update/SKILL.md` (post-migration step from Task 4 gains one line)
- Test: `tests/skills/install/test_graph_config.py`

**Interfaces:**
- Consumes: the module's existing `wiki_root` resolution (see `stamp_wiki`, L138–153).
- Produces: `DEFAULT_GRAPH_CONFIG: dict`, `write_default_graph_config(wiki_root_path: Path | None = None) -> bool` (True = written, False = already present). NOT routed through `stamp_skeleton`/`apply_write` (those stamp YAML frontmatter and scrub — wrong for JSON) and NOT added to `wiki-skeleton/` (the `.obsidian` invariant test forbids it). A plain guarded file write; the write-gate hook governs Claude tool calls, not library code invoked by the install flow's sanctioned `uv run` entrypoints.

- [ ] **Step 1: Write the failing tests**

```python
"""Run with: uv run pytest tests/skills/install/test_graph_config.py -v"""
import importlib
import json

install_lib = importlib.import_module("skills.install.lib")


def _root(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    import lib.ren_paths as rp
    root = rp.wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_writes_when_absent(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    assert install_lib.write_default_graph_config() is True
    cfg = json.loads((root / ".obsidian" / "graph.json").read_text())
    assert cfg["search"] == "-path:raw -path:archive"
    assert [g["query"] for g in cfg["colorGroups"]][0] == '"ren-quarantine"'


def test_never_clobbers_existing(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    dest = root / ".obsidian" / "graph.json"
    dest.parent.mkdir(parents=True)
    dest.write_text('{"search": "user-tuned"}', encoding="utf-8")
    assert install_lib.write_default_graph_config() is False
    assert json.loads(dest.read_text())["search"] == "user-tuned"


def test_okabe_ito_only(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    okabe_ito = {0x0072B2, 0x009E73, 0x56B4E9, 0xE69F00, 0xD55E00, 0xCC79A7}
    for group in install_lib.DEFAULT_GRAPH_CONFIG["colorGroups"]:
        assert group["color"]["rgb"] in okabe_ito


def test_skeleton_still_has_no_obsidian_dir():
    # regression guard alongside tests/test_obsidian_invariant.py
    from tests.test_obsidian_invariant import WIKI_SKELETON
    assert not list(WIKI_SKELETON.rglob(".obsidian"))
```

(If `WIKI_SKELETON` isn't importable from that module, inline the same two lines it uses to compute the path.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/skills/install/test_graph_config.py -v`
Expected: FAIL — `write_default_graph_config` not defined.

- [ ] **Step 3: Implement**

```python
# Okabe-Ito, colour-vision-safe; tier naming is the second signal (never colour alone).
# Group order matters: Obsidian applies the first matching group, so the
# quarantine content-match outranks the path-based tiers.
DEFAULT_GRAPH_CONFIG = {
    "search": "-path:raw -path:archive",
    "colorGroups": [
        {"query": '"ren-quarantine"', "color": {"a": 1, "rgb": 0xE69F00}},   # orange: quarantined
        {"query": "file:index.md OR file:map.md", "color": {"a": 1, "rgb": 0x0072B2}},  # blue: spine
        {"query": "path:knowledge", "color": {"a": 1, "rgb": 0x009E73}},     # green: knowledge
        {"query": "path:l1", "color": {"a": 1, "rgb": 0x56B4E9}},            # sky: session narratives
    ],
    "showTags": False,
    "showAttachments": False,
    "showOrphans": True,
}


def write_default_graph_config(wiki_root_path: Path | None = None) -> bool:
    """Write .obsidian/graph.json with the default tier view — only if absent."""
    root = wiki_root_path or _resolve_wiki_root()   # match stamp_wiki's root idiom
    dest = root / ".obsidian" / "graph.json"
    if dest.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(DEFAULT_GRAPH_CONFIG, indent=2) + "\n", encoding="utf-8")
    return True
```

`skills/install/SKILL.md` Stage 2: after the stamp-wiki call, one line — call `write_default_graph_config()` and report "default graph view written" / "existing graph config kept".
`skills/update/SKILL.md`: the Task 4 driver step gains a final line — after a successful verify, call `write_default_graph_config()` (same absent-only semantics).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/skills/install/ tests/test_obsidian_invariant.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/install/ skills/update/SKILL.md tests/skills/install/test_graph_config.py
git commit -m "feat(install): default Obsidian graph config — tier colors, raw/archive filtered (#56)"
```

---

### Task 7: Docs sweep + full-suite gate

**Files:**
- Modify: `skills/ingest-project/SKILL.md` (L24, L69, L74, L81–82 — hub naming prose and examples)
- Modify: `skills/bootstrap-project/SKILL.md` (L63)
- Modify: `skills/wiki-health/SKILL.md`, `skills/remember/SKILL.md` (any `index.md` hub-path examples — find with `grep -rn "knowledge.*index\.md" skills/*/SKILL.md`)
- Test: full suite

**Interfaces:** none — prose only; every example that shows a hub path becomes folder-note form (`knowledge/research/research.md`), and ingest's contract line states: "every `knowledge/` subdirectory gets a hub named after the folder (`<topic>/<topic>.md`) with `hub: true` in frontmatter."

- [ ] **Step 1: Apply the prose edits** (grep first; the line numbers above drift)

- [ ] **Step 2: Run the full suite**

Run: `uv run pytest -v`
Expected: everything green. If any test fails, fix forward within its owning task's files before committing.

- [ ] **Step 3: Sanity-run the migration against a disposable copy of the real wiki**

```bash
SCRATCH=/private/tmp/claude-501/-Users-hazarsozer-Dev-ren-os/d2918665-4fc0-426d-8897-b4fe80a61467/scratchpad/wiki-dry-run
mkdir -p "$SCRATCH" && cp -a ~/.renos/wiki/. "$SCRATCH/wiki"
mkdir -p "$SCRATCH/framework" && ln -sfn "$SCRATCH/wiki" "$SCRATCH/framework/wiki"
REN_FRAMEWORK_ROOT="$SCRATCH/framework" uv run python migrations/folder-note-hubs-1/migrate.py
REN_FRAMEWORK_ROOT="$SCRATCH/framework" uv run python migrations/folder-note-hubs-1/verify.py
```

(Confirm first how `wiki_root()` derives the wiki path from `REN_FRAMEWORK_ROOT` — read `lib/ren_paths.py` and shape `$SCRATCH` accordingly; the copy, not the live wiki, must be the target. The live wiki is NOT migrated in this train — that happens when Hazar runs `/ren:update` after release.)
Expected: `OK` then `OK`; spot-check `projects/ren-os/map.md` links and `knowledge/research/research.md` in the copy.

- [ ] **Step 4: Commit**

```bash
git add skills/ingest-project/SKILL.md skills/bootstrap-project/SKILL.md skills/wiki-health/SKILL.md skills/remember/SKILL.md
git commit -m "docs: folder-note hub convention across skill docs (#56)"
```

---

## Post-plan (not tasks in this plan)

- Release: changelog entry; version bump classified by `version-compare.sh --bump` (structural migration ⇒ MAJOR-classified per #56).
- After Hazar runs `/ren:update` on the live wiki: the one-time repair session (4 live orphans + 6 genshin dangling pointers) via `/ren:wiki-health` — spec §4.
- Issue bookkeeping: close #56; close #59 re-scoped ("Obsidian-only decided 2026-08-13"); #54 stays open for the repair session only.
