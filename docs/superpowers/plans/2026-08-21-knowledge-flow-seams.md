# Knowledge-Flow Seams Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four seams where 0.8.0's knowledge-flow producers hand off to consumers that were never taught about them — page typing, stale lint findings, the `place_durable_item` route, and update-verdict merges — plus a scrub false positive.

**Architecture:** One new module (`lib/memory/page_types.py`) owns the path→`type:` table and is consumed by three call sites so they can never disagree. Derivation happens at `propose()` time, *upstream* of `_normalize_body()`, which is what keeps noop-duplicate detection intact. A new `retract()` in the suggestions store — modeled on `expire_stale_pending()`, never on `decide()` — lets verifiable lint findings self-close. `wrap_session()` gains a `merges=` transport so update-verdicts stop dying at a `None` `llm_call`.

**Tech Stack:** Python 3.11+, `uv` for env and test running, pytest, frozen dataclasses, PyYAML frontmatter.

**Spec:** `docs/superpowers/specs/2026-08-21-knowledge-flow-seams-design.md`

## Global Constraints

- **Run everything through `uv run`** — never bare `python`/`pytest`. The user's Python is managed by `uv`, not the system interpreter.
- **Never touch the real wiki in a test.** Every test redirects `ren_paths` via `REN_FRAMEWORK_ROOT` to `tmp_path`. `tests/conftest.py` has a session-scoped `_real_renos_untouched` guard that fails the suite if you do.
- **I1 — derivation never overrides an existing `type:`.** Fill a missing value only.
- **I2 — an unmapped path gets no stamp and raises no error.** It stays untyped so the lint still flags it.
- **`stamp_frontmatter()` keeps owning `ren_*` and nothing else.** Do not add `type:` to it — see Task 1 Step 1 for the regression this prevents.
- **Retraction must not ledger a fingerprint.** `decide()` appends to the decision ledger and `record()` refuses any ledgered fingerprint; using it for retraction would permanently deafen the lint for that page+rule.
- **Baseline at branch point:** 3466 passed, 1 skipped. The full suite must be green at every commit.
- Commit messages end with: `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`

---

## File Structure

**Created:**
- `lib/memory/page_types.py` — the path→`type:` table plus `ensure_type()`. Sole owner of this mapping.
- `migrations/frontmatter-type-1/migrate.py` — one-shot backfill; calls `page_types`, never its own copy of the table.
- `migrations/frontmatter-type-1/README.md` — shape-decision rationale, matching `trust-backfill-1/README.md`.
- `tests/lib/memory/test_page_types.py`
- `tests/migrations/test_frontmatter_type_1.py`
- `tests/lib/suggestions/test_retract.py`
- `tests/skills/wiki_health/test_retract_resolved_findings.py`
- `tests/skills/wrap/test_merges_transport.py`

**Modified:**
- `lib/memory/queue.py` — `propose()` gains the derivation call; imports `replace` and `page_types`.
- `skills/wiki-migration/schemas.json` — 5 new page types, 1 new global migration.
- `lib/suggestions/__init__.py` — `retract()`, `_RESOLVED`, `prune_decided()` extension, `__all__`.
- `skills/wiki-health/lib/lint.py` — `_retract_resolved_findings()`, called from `run_incremental_lint()`.
- `skills/suggestions/lib/__init__.py` — the `place_durable_item` route in `_apply()`.
- `skills/wrap/lib/merge.py` — `validate_merged()` split out of `merge_update()`.
- `skills/wrap/lib/__init__.py` — `merges=` kwarg and the update three-way.
- `skills/wrap/SKILL.md` — phase 2 documentation.
- `lib/memory/scrub.py:117,130` — the follow-set fix.

---

## Task 1: Page-type derivation at the write door

**Files:**
- Create: `lib/memory/page_types.py`
- Create: `tests/lib/memory/test_page_types.py`
- Modify: `lib/memory/queue.py` (imports; `propose()` at line 384)
- Modify: `skills/wiki-migration/schemas.json`
- Test: `tests/lib/memory/test_page_types.py`, `tests/lib/memory/test_queue.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `lib.memory.page_types.derive_type(page: str) -> str | None`
  - `lib.memory.page_types.ensure_type(md_text: str, page: str) -> str`

  Tasks 2 and 3 both import these. Do not rename them.

**Context you need:** `Proposal` is a **frozen** dataclass (`lib/memory/queue.py:106`), so `propose()` cannot mutate `p.content` in place — use `dataclasses.replace`, which re-runs `__post_init__` harmlessly (page normalization is idempotent).

- [ ] **Step 1: Write the failing regression test — the reason this design exists**

This test is the whole point of deriving at `propose()` time instead of in `stamp_frontmatter()`. If someone later "simplifies" by moving derivation into the door, this test fails.

Add to `tests/lib/memory/test_queue.py`, inside `class TestAppliedDedup`:

```python
    def test_typed_page_still_detects_noop_duplicate(self, wiki):
        """The door derives `type:` into the proposal UPSTREAM of
        `_normalize_body`, so a re-proposal of byte-identical raw content
        still normalizes equal to the typed page on disk.

        If derivation ever moves into `stamp_frontmatter` (downstream of the
        comparison), this fails: the stored page would carry `type:` and the
        fresh proposal would not, so every idempotent re-write would register
        as a real change — breaking the distiller's noop-duplicate cap
        exclusion and suggestions' "content already on page" branch.
        """
        p = _proposal(page="lessons/a-lesson.md", content="lesson body\n")
        entry, prov = queue.propose_and_apply(p)
        assert prov is not None

        on_disk = (wiki_root() / "lessons" / "a-lesson.md").read_text(encoding="utf-8")
        assert "type: lesson" in on_disk

        again = queue.propose(
            _proposal(page="lessons/a-lesson.md", content="lesson body\n")
        )
        assert again.status == "noop-duplicate"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/lib/memory/test_queue.py::TestAppliedDedup::test_typed_page_still_detects_noop_duplicate -v`

Expected: FAIL on `assert "type: lesson" in on_disk` — nothing derives a type yet.

- [ ] **Step 3: Write the failing unit tests for the table**

Create `tests/lib/memory/test_page_types.py`:

```python
"""
Tests for lib.memory.page_types — the ONE path -> frontmatter `type:` table
(spec 2026-08-21 §2.4).

Run with: uv run pytest tests/lib/memory/test_page_types.py -v
"""

from __future__ import annotations

import pytest

from lib.memory.page_types import derive_type, ensure_type


class TestDeriveType:
    @pytest.mark.parametrize(
        "page,expected",
        [
            # Rule 1 — a project's own top-level files, direct children ONLY.
            ("projects/hallm/map.md", "l2-map"),
            ("projects/hallm/overview.md", "overview"),
            ("projects/hallm/schema.md", "project-schema"),
            ("projects/hallm/open-work.md", "open-work"),
            ("projects/hallm/instructions.md", "project-instructions"),
            # Rule 2 — folder-note hubs.
            ("projects/hallm/knowledge/lessons/lessons.md", "hub"),
            ("projects/hallm/knowledge/codebase/codebase.md", "hub"),
            # Rule 3 — lessons, global and project-scoped (kind wins).
            ("lessons/some-lesson.md", "lesson"),
            ("projects/flux/knowledge/lessons/some-lesson.md", "lesson"),
            # Rule 4 — session narratives, including archived.
            ("l1/session-x.md", "l1"),
            ("projects/ren-os/l1/session-y.md", "l1"),
            ("archive/l1/session-z.md", "l1"),
            # Rule 5 — everything else under a project knowledge tree.
            ("projects/hallm/knowledge/operations.md", "project-knowledge"),
            ("projects/ren-os/knowledge/architecture/obsidian.md", "project-knowledge"),
            ("projects/hallm/knowledge/pins/pin-2026-08-19.md", "project-knowledge"),
            # Rule 6 — the wiki root's own files.
            ("identity.md", "identity"),
            ("log.md", "log-entry"),
            ("LICENSES.md", "licenses"),
            ("index.md", "l2-map"),
        ],
    )
    def test_table(self, page, expected):
        assert derive_type(page) == expected

    def test_rule_1_depth_qualifier(self):
        """Rule 1 is direct-children-only (exactly 3 segments). A first pass
        at this table read it as 2 and silently dropped
        `projects/<slug>/schema.md` through to I2 — spec §2.4."""
        assert derive_type("projects/hallm/schema.md") == "project-schema"
        assert derive_type("projects/hallm/knowledge/schema.md") == "project-knowledge"

    def test_rule_2_precedes_rule_3(self):
        """A `lessons.md` folder note is a hub, not a lesson."""
        assert derive_type("projects/hallm/knowledge/lessons/lessons.md") == "hub"

    def test_rule_3_precedes_rule_5(self):
        """Kind wins over location for a project-scoped lesson."""
        assert derive_type("projects/flux/knowledge/lessons/x.md") == "lesson"

    def test_i2_unmapped_path_returns_none_without_raising(self):
        assert derive_type("some/novel/shape.md") is None
        assert derive_type("notes.md") is None
        assert derive_type("projects/x/fact.md") is None

    def test_hub_detection_excludes_raw_and_archive(self):
        assert derive_type("projects/h/knowledge/raw/raw.md") != "hub"
        assert derive_type("projects/h/knowledge/archive/archive.md") != "hub"


class TestEnsureType:
    def test_adds_frontmatter_when_absent(self):
        out = ensure_type("# Body\n", "lessons/x.md")
        assert out == "---\ntype: lesson\n---\n# Body\n"

    def test_inserts_into_existing_frontmatter(self):
        out = ensure_type('---\ntitle: "X"\n---\n# Body\n', "lessons/x.md")
        assert out == '---\ntype: lesson\ntitle: "X"\n---\n# Body\n'

    def test_i1_existing_type_is_never_overridden(self):
        text = "---\ntype: project-knowledge\n---\n# Body\n"
        assert ensure_type(text, "projects/h/knowledge/lessons/x.md") == text

    def test_i2_unmapped_path_returns_text_unchanged(self):
        text = "# Body\n"
        assert ensure_type(text, "some/novel/shape.md") == text

    def test_does_not_match_a_suffixed_key(self):
        """`content_type:` is not `type:` — the page still needs a stamp."""
        out = ensure_type("---\ncontent_type: x\n---\n# B\n", "lessons/x.md")
        assert out.startswith("---\ntype: lesson\ncontent_type: x\n---\n")

    def test_empty_frontmatter_fence_does_not_get_a_second_fence(self):
        """The bug the frontmatter regex comment warns about. `---\\n---\\n`
        has no newline before its closing fence, so a naive
        `\\A---\\n(.*?)\\n---\\n` misses it entirely and prepends a SECOND
        fence. Wrap's `_ensure_l1_type` shipped this bug once already."""
        out = ensure_type("---\n---\n\n# S\n", "l1/session-x.md")
        assert out == "---\ntype: l1\n---\n\n# S\n"

    def test_multi_key_frontmatter_keeps_its_order(self):
        out = ensure_type("---\na: 1\nb: 2\n---\nbody\n", "projects/h/knowledge/x/x.md")
        assert out == "---\ntype: hub\na: 1\nb: 2\n---\nbody\n"

    def test_is_idempotent(self):
        once = ensure_type("# Body\n", "lessons/x.md")
        assert ensure_type(once, "lessons/x.md") == once
```

- [ ] **Step 4: Run them to verify they fail**

Run: `uv run pytest tests/lib/memory/test_page_types.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'lib.memory.page_types'`

- [ ] **Step 5: Write the module**

Create `lib/memory/page_types.py`:

```python
"""lib.memory.page_types — the ONE table mapping a wiki page's path to its
frontmatter `type:` (spec 2026-08-21 §2.2).

Two consumers share this module so the write door and the backfill migration
can never disagree about what a page's type should be:

  1. `lib.memory.queue.propose()` — fills a missing `type:` on new content
  2. `migrations/frontmatter-type-1/` — the one-shot backfill

`skills.wiki-health.lib.lint`'s `missing-frontmatter-type` rule checks only
that a `type:` is PRESENT, never what it should be, so it does not import
this module today. It is the natural third consumer if a rule ever validates
the value.

`skills.wrap.lib._ensure_l1_type` overlaps benignly: it stamps `type: l1` on
an L1 narrative before the proposal reaches the door, and I1 means whatever
it set wins. Both agree on `l1`, so there is nothing to reconcile — but if
the two ever disagree, THIS module is the source of truth.

Two invariants (spec §2.3):

  I1 — never override an existing `type:`. Derivation fills a MISSING value
       only, so a human's hand-set type is never renamed out from under them.
  I2 — an unmapped path gets no stamp and raises no error. It stays untyped
       and the lint still flags it as a judgment call. Without I2 the rule
       becomes dead code and a novel path shape lands mistyped forever.

WHERE this is called matters as much as what it returns: `propose()` applies
it UPSTREAM of `_normalize_body()`. A `type:` added downstream (i.e. in
`provenance.stamp_frontmatter`) would sit outside the duplicate-comparison
boundary, and every idempotent re-write would register as a real change.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Final

# NOTE the `^` and re.MULTILINE, and that group(1) KEEPS its trailing
# newline. The obvious `r"\A---\n(.*?)\n---\n"` does NOT match an EMPTY
# frontmatter fence ("---\n---\n"), because there is no `\n` before the
# closing `---`. With that regex `ensure_type` would treat an empty fence as
# "no frontmatter" and prepend a SECOND fence, emitting malformed output.
# This is the same shape a reviewer already caught once in wrap's
# `_ensure_l1_type` (see `test_l1_empty_frontmatter_gains_type`).
_FRONTMATTER_RE: Final[re.Pattern[str]] = re.compile(
    r"\A---\n(.*?)^---\n", re.DOTALL | re.MULTILINE
)
_FM_TYPE_RE: Final[re.Pattern[str]] = re.compile(r"^type:\s*(.+)$", re.MULTILINE)

_ROOT_FILES: Final[dict[str, str]] = {
    "identity.md": "identity",
    "log.md": "log-entry",
    "LICENSES.md": "licenses",
    "index.md": "l2-map",
}

_PROJECT_FILES: Final[dict[str, str]] = {
    "map.md": "l2-map",
    "overview.md": "overview",
    "schema.md": "project-schema",
    "open-work.md": "open-work",
    "instructions.md": "project-instructions",
}

_HUB_EXCLUDED_PARTS: Final[frozenset[str]] = frozenset({"raw", "archive"})


def _is_folder_note_hub(parts: tuple[str, ...]) -> bool:
    """`<dir>/<dirname>.md` under a project knowledge tree.

    Mirrors `skills.wiki-health.lib.lint._is_hub_page`'s folder-note branch,
    which is string-scoped so a project literally NAMED "knowledge" cannot
    false-positive. Root `index.md` is deliberately NOT a hub here — it is
    typed `l2-map` on disk, and I1 would preserve that anyway.
    """
    if len(parts) <= 2:
        return False
    if parts[-1] != f"{parts[-2]}.md":
        return False
    if parts[0] != "projects" or "knowledge" not in parts[2:-1]:
        return False
    return not any(p.startswith(".") or p in _HUB_EXCLUDED_PARTS for p in parts)


def derive_type(page: str) -> str | None:
    """The `type:` for `page`, or `None` when no rule matches (I2).

    Rules are ordered; first match wins. Rule 2 precedes rule 3 so a
    `lessons.md` folder note is a `hub`, not a `lesson`. Rule 3 precedes
    rule 5 so a project-scoped lesson is a `lesson` — kind wins over
    location (spec §2.4).
    """
    parts = PurePosixPath(page).parts
    if not parts:
        return None
    name = parts[-1]

    # Rule 1 — a project's own top-level files. Direct children ONLY: exactly
    # three segments. `projects/<slug>/knowledge/schema.md` is four and must
    # fall through to rule 5.
    if len(parts) == 3 and parts[0] == "projects" and name in _PROJECT_FILES:
        return _PROJECT_FILES[name]

    # Rule 2 — folder-note hubs.
    if _is_folder_note_hub(parts):
        return "hub"

    # Rule 3 — lessons, global or project-scoped (kind wins over location).
    if len(parts) >= 2 and parts[-2] == "lessons":
        return "lesson"

    # Rule 4 — session narratives, including archived ones.
    if "l1" in parts[:-1]:
        return "l1"

    # Rule 5 — everything else under a project knowledge tree.
    if len(parts) > 3 and parts[0] == "projects" and parts[2] == "knowledge":
        return "project-knowledge"

    # Rule 6 — the wiki root's own files.
    if len(parts) == 1 and name in _ROOT_FILES:
        return _ROOT_FILES[name]

    return None


def ensure_type(md_text: str, page: str) -> str:
    """Return `md_text` with a derived `type:` present in its frontmatter.

    Returns the text UNCHANGED when it already declares a `type:` (I1) or
    when no rule matches `page` (I2). Otherwise inserts `type: <derived>` as
    the first frontmatter line, creating a frontmatter block if there is none.
    """
    match = _FRONTMATTER_RE.match(md_text)
    if match is not None and _FM_TYPE_RE.search(match.group(1)):
        return md_text  # I1

    derived = derive_type(page)
    if derived is None:
        return md_text  # I2

    if match is None:
        return f"---\ntype: {derived}\n---\n{md_text}"
    # group(1) keeps its own trailing newline (or is "" for an empty fence),
    # so there is deliberately no `\n` between it and the closing fence here.
    return f"---\ntype: {derived}\n{match.group(1)}---\n{md_text[match.end():]}"


__all__ = ["derive_type", "ensure_type"]
```

- [ ] **Step 6: Run the unit tests to verify they pass**

Run: `uv run pytest tests/lib/memory/test_page_types.py -v`

Expected: PASS (all cases).

- [ ] **Step 7: Wire it into `propose()`**

In `lib/memory/queue.py`, add `replace` to the existing dataclasses import:

```python
from dataclasses import asdict, dataclass, field, replace
```

and add the module import alongside the other `lib.memory` imports:

```python
from lib.memory import page_types
```

Then insert this as the **first statement** in `propose()` (before the `scrub.scrub_or_raise` call at line 400), and add the paragraph to the docstring:

```python
    # Spec 2026-08-21 §2.1: derive `type:` HERE — upstream of the
    # `_normalize_body` comparison below — so a re-proposal of identical raw
    # content still normalizes equal to the typed page on disk. Deriving in
    # `stamp_frontmatter` instead would land downstream of that comparison
    # and break noop-duplicate detection. `Proposal` is frozen, so rebind
    # rather than mutate.
    if p.op in ("ADD", "UPDATE") and p.content is not None:
        typed = page_types.ensure_type(p.content, p.page)
        if typed != p.content:
            p = replace(p, content=typed)
```

- [ ] **Step 8: Run the regression test and the full queue suite**

Run: `uv run pytest tests/lib/memory/test_queue.py -v`

Expected: PASS, including `test_typed_page_still_detects_noop_duplicate`.

Note: the existing tests use pages like `notes.md` and `projects/x/fact.md`, both of which hit I2 and derive `None`, so they are unaffected. If any existing test *does* break, that is real signal — do not adjust the test to fit; report it.

- [ ] **Step 9: Register the missing page types**

In `skills/wiki-migration/schemas.json`, add to `page_types` (keep the existing 8 entries untouched):

```json
    "l1": {
      "current": 1,
      "migrations": []
    },
    "lesson": {
      "current": 1,
      "migrations": []
    },
    "hub": {
      "current": 1,
      "migrations": []
    },
    "licenses": {
      "current": 1,
      "migrations": []
    },
    "log-entry": {
      "current": 1,
      "migrations": []
    }
```

Do **not** touch `global_migrations` here — that append belongs to Task 2, which creates the directory it names. (Pre-flight ruling: every commit stays self-consistent.)

Rationale for the commit body: `migration_chain()` is keyed by page type, so a type the registry has never heard of can never be migrated later.

- [ ] **Step 10: Run the full suite**

Run: `uv run pytest -q`

Expected: PASS. Baseline was 3466 passed, 1 skipped; this task adds tests, so the passed count rises and skipped stays 1.

- [ ] **Step 11: Commit**

```bash
git add lib/memory/page_types.py tests/lib/memory/test_page_types.py \
        lib/memory/queue.py tests/lib/memory/test_queue.py \
        skills/wiki-migration/schemas.json
git commit -m "$(cat <<'EOF'
feat(queue): derive frontmatter type: at the write door (#74)

Derivation happens in propose(), upstream of _normalize_body, so a
re-proposal of identical raw content still normalizes equal to the typed
page on disk. Stamping in stamp_frontmatter instead would land downstream
of that comparison and break the distiller's noop-duplicate cap exclusion
and suggestions' "content already on page" branch — pinned by
test_typed_page_still_detects_noop_duplicate.

Registers l1/lesson/hub/licenses/log-entry so the derivation table and
schemas.json agree; migration_chain() is page-type-keyed, so an
unregistered type could never be migrated later.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: The `frontmatter-type-1` backfill migration

**Files:**
- Create: `migrations/frontmatter-type-1/migrate.py`
- Create: `migrations/frontmatter-type-1/README.md`
- Create: `tests/migrations/test_frontmatter_type_1.py`

**Interfaces:**
- Consumes: `lib.memory.page_types.ensure_type(md_text, page) -> str` from Task 1.
- Produces: a `main(argv)` CLI entry point supporting `--check`. Nothing later depends on it.

**Context you need:** This migration writes **directly** and keeps its own journal — the `trust-backfill-1` / `folder-note-hubs-1` mold — rather than routing through the write queue. That looks like a doctrine violation but isn't: the "never edit a governed page directly" rule binds *sessions*, and tree-wide migrations are reverted by the pre-update whole-wiki snapshot. Inventing a queue-routed second convention here would fragment migration revert. Read `migrations/trust-backfill-1/migrate.py` before writing this.

- [ ] **Step 1: Write the failing test**

Create `tests/migrations/test_frontmatter_type_1.py`:

```python
"""
End-to-end test for the frontmatter-type-1 migration (spec 2026-08-21 §2.5).

Backfills the derived `type:` onto pages created before the write door
derived one. Like trust-backfill-1, it walks the wiki tree directly rather
than following the per-page-type migrate.sh chain — see the README.

Run with: uv run pytest tests/migrations/test_frontmatter_type_1.py -v
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from lib.ren_paths import wiki_root

_MIGRATE_PATH = (
    Path(__file__).resolve().parents[2] / "migrations" / "frontmatter-type-1" / "migrate.py"
)


def _load_migrate():
    spec = importlib.util.spec_from_file_location("frontmatter_type_1_migrate", _MIGRATE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def wiki(monkeypatch, tmp_path):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_stamps_every_path_shape(wiki):
    cases = {
        "projects/h/schema.md": "project-schema",
        "projects/h/knowledge/codebase/codebase.md": "hub",
        "lessons/a.md": "lesson",
        "projects/f/knowledge/lessons/b.md": "lesson",
        "projects/r/l1/session-x.md": "l1",
        "projects/h/knowledge/operations.md": "project-knowledge",
        "identity.md": "identity",
    }
    for rel in cases:
        _write(wiki, rel, "# Body\n")

    migrate = _load_migrate()
    assert migrate.main([]) == 0

    for rel, expected in cases.items():
        text = (wiki / rel).read_text(encoding="utf-8")
        assert f"type: {expected}" in text, rel


def test_i1_already_typed_page_is_untouched(wiki):
    text = "---\ntype: project-knowledge\n---\n# Body\n"
    path = _write(wiki, "projects/h/knowledge/lessons/lessons.md", text)

    migrate = _load_migrate()
    assert migrate.main([]) == 0

    assert path.read_text(encoding="utf-8") == text


def test_i2_unmapped_page_is_untouched(wiki):
    text = "# Body\n"
    path = _write(wiki, "some/novel/shape.md", text)

    migrate = _load_migrate()
    assert migrate.main([]) == 0

    assert path.read_text(encoding="utf-8") == text


def test_check_only_reports_without_writing(wiki):
    path = _write(wiki, "lessons/a.md", "# Body\n")

    migrate = _load_migrate()
    assert migrate.main(["--check"]) == 0

    assert path.read_text(encoding="utf-8") == "# Body\n"


def test_is_idempotent(wiki):
    _write(wiki, "lessons/a.md", "# Body\n")

    migrate = _load_migrate()
    migrate.main([])
    first = (wiki / "lessons" / "a.md").read_text(encoding="utf-8")
    migrate.main([])
    second = (wiki / "lessons" / "a.md").read_text(encoding="utf-8")

    assert first == second
    assert first.count("type: lesson") == 1
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/migrations/test_frontmatter_type_1.py -v`

Expected: FAIL — the migration file does not exist.

- [ ] **Step 3: Write the migration**

Create `migrations/frontmatter-type-1/migrate.py`:

```python
"""frontmatter-type-1 — backfill the derived frontmatter `type:`.

Stamps `type:` onto every wiki page that lacks one and whose path the
derivation table recognizes. Tree-wide global migration in the
trust-backfill-1 mold: direct writes + own journal, revertible via the
whole-wiki pre-update snapshot. Spec:
docs/superpowers/specs/2026-08-21-knowledge-flow-seams-design.md §2.5

The table itself lives in `lib.memory.page_types` and is shared with the
write door and the lint — this migration never carries its own copy.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.memory.page_types import ensure_type  # noqa: E402
from lib.ren_paths import state_dir, wiki_root  # noqa: E402

_SKIP_DIRS = {".ren", ".git"}


def _pages(root: Path):
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root)
        if any(part in _SKIP_DIRS or part.startswith(".") for part in rel.parts[:-1]):
            continue
        yield path, rel


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    check_only = "--check" in argv

    root = wiki_root()
    if not root.is_dir():
        print("frontmatter-type-1: no wiki root, nothing to do")
        return 0

    stamped = 0
    skipped = 0
    journal_lines: list[dict] = []

    for path, rel in _pages(root):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue

        new_text = ensure_type(text, rel.as_posix())
        if new_text == text:
            skipped += 1
            continue

        if check_only:
            print(f"{rel.as_posix()}: WOULD STAMP type:")
        else:
            path.write_text(new_text, encoding="utf-8")
            print(f"{rel.as_posix()}: stamped type:")
            journal_lines.append({
                "migration": "frontmatter-type-1",
                "page": rel.as_posix(),
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
        stamped += 1

    if journal_lines and not check_only:
        log = state_dir() / "migrations" / "frontmatter-type-1.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as fh:
            for line in journal_lines:
                fh.write(json.dumps(line) + "\n")

    verb = "would stamp" if check_only else "stamped"
    print(f"frontmatter-type-1: {stamped} {verb}, {skipped} already typed or unmapped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/migrations/test_frontmatter_type_1.py -v`

Expected: PASS (all five tests).

- [ ] **Step 4b: Register the migration**

In `skills/wiki-migration/schemas.json`, append `"frontmatter-type-1"` to `global_migrations.migrations`. It lands here rather than in Task 1 so the commit that names the directory is the commit that creates it.

Note: `global_migrations` is **discoverability only** — that list does not cause `/ren:update` to run anything. Each global migration is gated by its own hardcoded version function in `skills/update/lib/__init__.py` (`should_run_trust_backfill`, `_PROJECT_KNOWLEDGE_GATE`, …). Adding such a gate for this migration is deliberately **out of scope** for this train: the gate version cannot be chosen until the release version is. It is recorded as a release-time follow-up in Close-out. Do not add a gate function.

- [ ] **Step 5: Write the README**

Create `migrations/frontmatter-type-1/README.md`:

```markdown
# frontmatter-type-1

Backfills the derived frontmatter `type:` onto pages created before the write
door derived one (GitHub #74).

## Shape decision

Like `trust-backfill-1` and `folder-note-hubs-1`, this walks the wiki tree
directly rather than following `skills/wiki-migration`'s per-page-type
`migrate.sh` chain. The chain is keyed by page type — and the whole point of
this migration is that these pages have no type yet, so there is no chain to
walk.

Direct writes plus an append-only journal at
`state_dir()/migrations/frontmatter-type-1.jsonl`; revert is the whole-wiki
pre-update snapshot, same as its two siblings.

## Invariants

- **I1** — a page that already declares a `type:` is never touched.
- **I2** — a page whose path no rule recognizes is never touched; it stays
  untyped so the lint keeps flagging it as a judgment call.
- Idempotent: running twice is a no-op the second time.

## Running

```bash
uv run python migrations/frontmatter-type-1/migrate.py --check   # dry run
uv run python migrations/frontmatter-type-1/migrate.py           # apply
```

## Table

The path→type table lives in `lib/memory/page_types.py` and is shared with
`queue.propose()` and the wiki-health lint. This migration never carries its
own copy.
```

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add migrations/frontmatter-type-1/ tests/migrations/test_frontmatter_type_1.py \
        skills/wiki-migration/schemas.json
git commit -m "$(cat <<'EOF'
feat(migrations): frontmatter-type-1 backfill (#74)

Stamps the derived type: onto pages created before the door derived one.
Shares lib/memory/page_types with the write door and the lint rather than
carrying its own copy of the table.

Direct writes + own journal, trust-backfill-1 mold: the chain-based
migrate.sh shape is page-type-keyed, and these pages have no type yet.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Finding retraction

**Files:**
- Modify: `lib/suggestions/__init__.py`
- Modify: `skills/wiki-health/lib/lint.py`
- Create: `tests/lib/suggestions/test_retract.py`
- Create: `tests/skills/wiki_health/test_retract_resolved_findings.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `lib.suggestions.retract(sid: str, reason: str) -> dict`, and the module constant `_RESOLVED = "resolved"`. Nothing later in this plan depends on them.

**Context you need — read this before writing code.** `decide()` appends to the decision ledger, and `record()` refuses any fingerprint present in `ledger_fingerprints()`. So retracting via `decide(sid, "declined")` would permanently deafen the lint for that page+rule: strip `type:` off the page again later and no finding would ever fire. `expire_stale_pending()` is the model to copy — it sets a status *without* ledgering, precisely so the fingerprint stays free to re-fire.

- [ ] **Step 1: Write the failing store tests**

Create `tests/lib/suggestions/test_retract.py`:

```python
"""
Tests for lib.suggestions.retract — closing a finding that no longer holds
(spec 2026-08-21 §3.3).

The load-bearing test here is `test_retract_does_not_ledger_the_fingerprint`.
Retraction models `expire_stale_pending`, NOT `decide`: decide() ledgers, and
record() refuses any ledgered fingerprint, so retracting via decide would
permanently deafen the producer for that fingerprint.

Run with: uv run pytest tests/lib/suggestions/test_retract.py -v
"""

from __future__ import annotations

import pytest

from lib import suggestions
from lib.suggestions import (
    SuggestionSpec,
    ledger_fingerprints,
    pending_suggestions,
    record,
    retract,
)
from lib.ren_paths import wiki_root


@pytest.fixture
def store(monkeypatch, tmp_path):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    wiki_root().mkdir(parents=True, exist_ok=True)
    return tmp_path


def _spec(fingerprint="wiki-lint:lessons/a.md:missing-frontmatter-type"):
    return SuggestionSpec(
        producer="wiki-health",
        title="Wiki lint: missing-frontmatter-type in lessons/a.md",
        rationale="page has no frontmatter `type:`",
        evidence={"page": "lessons/a.md", "rule": "missing-frontmatter-type"},
        kind="structured_action",
        payload={"action": "review_lint_finding", "page": "lessons/a.md",
                 "rule": "missing-frontmatter-type"},
        fingerprint=fingerprint,
    )


def test_retract_sets_resolved_status(store):
    entry = record(_spec())
    result = retract(entry["sid"], "type: is now present")

    assert result["status"] == "resolved"
    assert result["resolved_reason"] == "type: is now present"
    assert result["resolved_at"] is not None


def test_retracted_entry_leaves_pending(store):
    entry = record(_spec())
    retract(entry["sid"], "fixed")

    assert entry["sid"] not in {e["sid"] for e in pending_suggestions()}


def test_retract_does_not_ledger_the_fingerprint(store):
    """The whole point. A retracted finding must be able to fire again."""
    entry = record(_spec())
    retract(entry["sid"], "fixed")

    assert _spec().fingerprint not in ledger_fingerprints()

    again = record(_spec())
    assert again is not None
    assert again["sid"] != entry["sid"]


def test_retract_refuses_a_non_pending_entry(store):
    entry = record(_spec())
    retract(entry["sid"], "fixed")

    with pytest.raises(ValueError):
        retract(entry["sid"], "again")


def test_retract_raises_keyerror_for_unknown_sid(store):
    with pytest.raises(KeyError):
        retract("s-nope", "fixed")


def test_prune_decided_sweeps_resolved_files(store):
    entry = record(_spec())
    retract(entry["sid"], "fixed")

    # Backdate so it falls outside the retention window.
    stored = suggestions._load(entry["sid"])
    stored["resolved_at"] = "2020-01-01T00:00:00Z"
    suggestions._persist(stored)

    assert suggestions.prune_decided() >= 1
    assert not suggestions._suggestion_path(entry["sid"]).exists()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/lib/suggestions/test_retract.py -v`

Expected: FAIL — `ImportError: cannot import name 'retract'`.

- [ ] **Step 3: Implement `retract()`**

In `lib/suggestions/__init__.py`, add the constant next to `_EXPIRED` (line 39):

```python
_RESOLVED = "resolved"
```

Add the function after `decide()`:

```python
def retract(sid: str, reason: str) -> dict:
    """Close `sid` because the finding it reports no longer holds.

    Models `expire_stale_pending`, NOT `decide`: the fingerprint is
    deliberately NOT ledgered, so if the same defect returns to the same page
    `record()` is free to file it again. Retracting via `decide(sid,
    "declined")` would ledger the fingerprint and permanently deafen the
    producer for that page+rule — the exact bug spec §3.2 exists to prevent.

    Raises `KeyError` for an unknown sid and `ValueError` if the entry is not
    currently pending (decided, expired and resolved entries are immutable,
    same rule as `decide`).
    """
    entry = _load(sid)
    if entry["status"] != _PENDING:
        raise ValueError(
            f"suggestion {sid!r} is already {entry['status']!r} — "
            "retract() only accepts pending entries"
        )
    entry["status"] = _RESOLVED
    entry["resolved_at"] = _now_iso()
    entry["resolved_reason"] = reason
    _persist(entry)
    return entry
```

Extend `prune_decided()` so resolved files are swept too. Replace its status check and timestamp read:

```python
        if entry.get("status") not in (*_DECISIONS, _RESOLVED):
            continue
        decided_at = entry.get("decided_at") or entry.get("resolved_at")
```

and update its docstring's first line to `"""Delete decided (accepted/declined) and resolved entry files whose timestamp is older than `retention_days`."""`

Add `"retract"` and `"_RESOLVED"` to `__all__`.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/lib/suggestions/test_retract.py -v`

Expected: PASS (six tests).

- [ ] **Step 5: Write the failing lint-pass test**

Create `tests/skills/wiki_health/test_retract_resolved_findings.py`:

```python
"""
Tests for the wiki-health lint's retraction pass (spec 2026-08-21 §3.4).

A lint finding is VERIFIABLE — unlike a judgment call, you can re-check
whether it still holds. This pass does that, so a finding fixed by any other
means self-closes instead of sitting pending for the 30-day expiry.

Run with: uv run pytest tests/skills/wiki_health/test_retract_resolved_findings.py -v
"""

from __future__ import annotations

import importlib

import pytest

from lib.suggestions import SuggestionSpec, pending_suggestions, record
from lib.ren_paths import wiki_root

lint = importlib.import_module("skills.wiki-health.lib.lint")


@pytest.fixture
def wiki(monkeypatch, tmp_path):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _file_finding(page: str, rule: str = "missing-frontmatter-type"):
    return record(SuggestionSpec(
        producer="wiki-health",
        title=f"Wiki lint: {rule} in {page}",
        rationale="page has no frontmatter `type:`",
        evidence={"page": page, "rule": rule, "detail": "d"},
        kind="structured_action",
        payload={"action": "review_lint_finding", "page": page, "rule": rule, "detail": "d"},
        fingerprint=f"wiki-lint:{page}:{rule}",
    ))


def _write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_fixed_page_retracts_its_finding(wiki):
    _write(wiki, "lessons/a.md", "---\ntype: lesson\n---\n# A\n")
    entry = _file_finding("lessons/a.md")

    lint._retract_resolved_findings(wiki)

    assert entry["sid"] not in {e["sid"] for e in pending_suggestions()}


def test_unfixed_page_keeps_its_finding_pending(wiki):
    _write(wiki, "lessons/b.md", "# B\n")
    entry = _file_finding("lessons/b.md")

    lint._retract_resolved_findings(wiki)

    assert entry["sid"] in {e["sid"] for e in pending_suggestions()}


def test_deleted_page_retracts_its_finding(wiki):
    entry = _file_finding("lessons/gone.md")

    lint._retract_resolved_findings(wiki)

    assert entry["sid"] not in {e["sid"] for e in pending_suggestions()}


def test_non_lint_suggestions_are_left_alone(wiki):
    entry = record(SuggestionSpec(
        producer="wrap",
        title="Place durable item",
        rationale="unplaceable",
        evidence={},
        kind="structured_action",
        payload={"action": "place_durable_item", "item": "x", "session": "s"},
        fingerprint="wrap-unplaced:s:0",
    ))

    lint._retract_resolved_findings(wiki)

    assert entry["sid"] in {e["sid"] for e in pending_suggestions()}
```

- [ ] **Step 6: Run to verify it fails**

Run: `uv run pytest tests/skills/wiki_health/test_retract_resolved_findings.py -v`

Expected: FAIL — `AttributeError: module has no attribute '_retract_resolved_findings'`.

- [ ] **Step 7: Implement the lint pass**

In `skills/wiki-health/lib/lint.py`, add `retract` to the existing suggestions import (line 51):

```python
from lib.suggestions import SuggestionSpec, pending_suggestions, record, retract
```

Add the function just after `_pending_lint_findings()`:

```python
def _retract_resolved_findings(wiki_root: Path) -> int:
    """Re-verify every pending lint finding and close the ones that no longer
    hold (spec 2026-08-21 §3.4).

    A lint finding is mechanically checkable, unlike a judgment call — so a
    finding fixed by any other means (a migration, a hand edit, a deleted
    page) can self-close instead of sitting pending until the 30-day expiry.
    Uses `retract`, never `decide`: a declined fingerprint is ledgered and
    would never fire again if the defect returned.

    Returns the number retracted.
    """
    retracted = 0
    all_pages = walk_wiki_pages(wiki_root)  # list[str] of wiki-relative paths
    deleted = _deleted_basenames()

    for entry in pending_suggestions():
        fingerprint = str(entry.get("fingerprint", ""))
        if not fingerprint.startswith(_LINT_FINGERPRINT_PREFIX):
            continue

        payload = entry.get("payload") or {}
        page = payload.get("page")
        rule = payload.get("rule")
        if not isinstance(page, str) or not isinstance(rule, str):
            continue

        try:
            text = ren_paths.safe_join(wiki_root, page).read_text(encoding="utf-8")
        except (OSError, ren_paths.PathTraversalError):
            # Page is gone — the finding cannot still hold.
            retract(entry["sid"], f"page {page} no longer exists")
            retracted += 1
            continue

        _, _, judgments = _lint_page(wiki_root, page, text, all_pages, deleted)
        if rule not in {r for r, _ in judgments}:
            retract(entry["sid"], f"{rule} no longer holds for {page}")
            retracted += 1

    return retracted
```

Then call it from `run_incremental_lint()`, immediately after `wiki_root = ren_paths.wiki_root()` and **before** the watermark-seed early return, so a seeded first run still tidies the store:

```python
    retracted = _retract_resolved_findings(wiki_root)
```

and add `"retracted": retracted` to **both** dicts that `run_incremental_lint()` returns (the `"scope": "seeded"` early return and the normal one).

**Note on `walk_wiki_pages`:** it returns `list[str]` — sorted wiki-relative posix paths, not `(page, text)` pairs. `_lint_page(wiki_root, page, text, all_pages, deleted)` wants exactly that list as its 4th argument, so pass it straight through.

- [ ] **Step 8: Run to verify it passes**

Run: `uv run pytest tests/skills/wiki_health/test_retract_resolved_findings.py -v`

Expected: PASS (four tests).

- [ ] **Step 9: Run the wiki-health suite and the full suite**

Run: `uv run pytest tests/skills/wiki_health/ -v` then `uv run pytest -q`

Expected: PASS. Existing `run_incremental_lint` tests may assert on the returned dict's exact keys — if one fails because of the new `"retracted"` key, updating that assertion is correct.

- [ ] **Step 10: Commit**

```bash
git add lib/suggestions/__init__.py tests/lib/suggestions/test_retract.py \
        skills/wiki-health/lib/lint.py \
        tests/skills/wiki_health/test_retract_resolved_findings.py
git commit -m "$(cat <<'EOF'
feat(suggestions,lint): retract findings that no longer hold

A lint finding is verifiable, so a finding fixed by other means can
self-close instead of sitting pending for the 30-day expiry.

retract() models expire_stale_pending, NOT decide: decide() ledgers the
fingerprint and record() refuses any ledgered fingerprint, so retracting
via decline would permanently deafen the lint for that page+rule. Pinned
by test_retract_does_not_ledger_the_fingerprint.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: The `place_durable_item` route (#73)

**Files:**
- Modify: `skills/suggestions/lib/__init__.py` (in `_apply()`, after the `orphan_page` branch at line 224)
- Test: `tests/skills/suggestions/test_suggestions_skill.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: nothing later tasks depend on.

**Context you need:** `_route_unplaced()` in `skills/wrap/lib/__init__.py:747` builds a payload of `{action, item, session}` with **no target page**. There is nothing to write *to*, so a handoff is the only correct shape — matching `orphan_page` and `review_lint_finding`. `accept()` needs no change: an intentional non-write outcome that *returns* (rather than raising) already counts as decided.

- [ ] **Step 1: Write the failing test**

Add to `tests/skills/suggestions/test_suggestions_skill.py` (match the file's existing fixture style — read the `review_lint_finding` test near line 372 first):

```python
def test_accept_place_durable_item_records_the_handoff(store):
    """#73: the distiller and wrap both route unplaceable durable items to
    the store as structured_action/place_durable_item. Before this route
    existed, accept() raised "unknown suggestion kind", decision_recorded was
    False, and the suggestion re-offered on every /ren:suggestions pass
    forever."""
    entry = record(SuggestionSpec(
        producer="wrap",
        title="Place durable item from session s-1",
        rationale="claimed target is not eligible",
        evidence={"item": "the learning", "session": "s-1"},
        kind="structured_action",
        payload={"action": "place_durable_item", "item": "the learning",
                 "session": "s-1"},
        fingerprint="wrap-unplaced:s-1:0",
    ))

    result = accept(entry["sid"], "s-2")

    assert result["applied"] is False
    assert result["decision_recorded"] is True
    assert result["detail"]["item"] == "the learning"
    assert result["detail"]["session"] == "s-1"
    assert entry["sid"] not in {e["sid"] for e in pending_suggestions()}
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/skills/suggestions/test_suggestions_skill.py::test_accept_place_durable_item_records_the_handoff -v`

Expected: FAIL — `decision_recorded` is `False` and `detail` is the string `"unknown suggestion kind 'structured_action' / action 'place_durable_item'"`.

- [ ] **Step 3: Add the route**

In `skills/suggestions/lib/__init__.py`, insert immediately after the `orphan_page` branch and before the final `raise ValueError`:

```python
    if action == "place_durable_item":
        # #73 — judgment finding: the distiller/wrap routed a durable item it
        # could not place (`wrap._route_unplaced`). The payload carries no
        # target page, so there is nothing to write to; the live session
        # places it with the friend. Accepting records the review handoff,
        # same convention as orphan_page and review_lint_finding.
        return {
            "sid": sid,
            "applied": False,
            "detail": {"item": payload.get("item"),
                       "session": payload.get("session")},
        }
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/skills/suggestions/test_suggestions_skill.py -v`

Expected: PASS.

- [ ] **Step 5: Update the `accept()` docstring**

In `accept()`, extend the sentence listing intentional non-write outcomes so `place_durable_item` is named alongside the others:

> Intentional non-write outcomes (duplicate content, review_contradiction handoff, quarantine_release held-on-contradicts, review_lint_finding handoff, place_durable_item handoff) still count as decided — retrying them cannot change the outcome.

- [ ] **Step 6: Run the full suite and commit**

Run: `uv run pytest -q`

```bash
git add skills/suggestions/lib/__init__.py tests/skills/suggestions/test_suggestions_skill.py
git commit -m "$(cat <<'EOF'
fix(suggestions): route place_durable_item in accept() (#73)

The 0.8.0 train shipped the producer side (wrap._route_unplaced) without
the consumer route, so an approved distiller suggestion returned
decision_recorded=false and re-offered forever.

Handoff is the only correct shape: the payload carries no target page.
Formalizes the workaround used in the 2026-08-19 acceptance session.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: The `merges=` transport (#75)

**Files:**
- Modify: `skills/wrap/lib/merge.py`
- Modify: `skills/wrap/lib/__init__.py` (signature at line 768; update branch at line 978)
- Modify: `skills/wrap/SKILL.md`
- Create: `tests/skills/wrap/test_merges_transport.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `skills.wrap.lib.merge.validate_merged(current_text: str, merged_text: str) -> str` — returns `merged_text`, raises `MergeError`.
  - `wrap_session(..., merges: list[str | None] | None = None)`

**Context you need:** Under the standard `/ren:wrap` transport there is no live `llm_call`, so `merge_update()` raises `MergeError("merge llm call failed: 'NoneType' object is not callable")` and the item lands in `gated_out` — the same die-silently class Part A of the 0.8.0 spec fixed for scope-`None` placement. All three durable-affirmed candidates of the 2026-08-19 wrap died this way.

- [ ] **Step 1: Write the failing tests**

Create `tests/skills/wrap/test_merges_transport.py`. Read `tests/skills/wrap/test_wrap_flow.py` first for the fixture idiom and helper names, and reuse them rather than inventing new ones.

```python
"""
Tests for the merges= transport (spec 2026-08-21 §5).

Under the standard verdicts= path there is no live llm_call, so every
update-action durable verdict used to die in the merge step and land in
gated_out. These pin the three-way: pre-computed merge, live llm_call, and
neither (route to suggestions, never gated_out).

Run with: uv run pytest tests/skills/wrap/test_merges_transport.py -v
"""

from __future__ import annotations

import pytest

from skills.wrap.lib.merge import MergeError, validate_merged


class TestValidateMerged:
    def test_accepts_a_well_formed_merge(self):
        current = "---\ntype: lesson\n---\n# A\nold\n"
        merged = "---\ntype: lesson\n---\n# A\nold\nnew\n"
        assert validate_merged(current, merged) == merged

    def test_rejects_altered_frontmatter(self):
        current = "---\ntype: lesson\n---\n# A\n"
        merged = "---\ntype: hub\n---\n# A\nnew\n"
        with pytest.raises(MergeError, match="frontmatter"):
            validate_merged(current, merged)

    def test_rejects_a_no_op_merge(self):
        current = "---\ntype: lesson\n---\n# A\n"
        with pytest.raises(MergeError, match="byte-identical"):
            validate_merged(current, current)

    def test_rejects_empty_or_non_string(self):
        current = "---\ntype: lesson\n---\n# A\n"
        with pytest.raises(MergeError, match="empty or not a string"):
            validate_merged(current, "   ")
        with pytest.raises(MergeError, match="empty or not a string"):
            validate_merged(current, None)
```

Then the `wrap_session` three-way. An update-action verdict may only target a page **this session surfaced**, so the helper seeds `KIND_L3_FETCH` as well as writing the file — a target outside the eligible set is treated as malformed classifier output and never reaches the merge step at all.

```python
from lib import suggestions
from lib.instrument import collect
from skills.wrap.lib import wrap_session


@pytest.fixture
def wiki(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_WIKI_ROOT", str(tmp_path / "wiki"))
    (tmp_path / "wiki").mkdir()
    return tmp_path / "wiki"


_TARGET = "lessons/existing.md"
_CURRENT = "---\ntype: lesson\n---\n# Existing\n\nold line\n"
_MERGED = "---\ntype: lesson\n---\n# Existing\n\nold line\nnew line\n"


def _eligible_target(wiki, session):
    """Put the target on disk AND in this session's eligibility set."""
    path = wiki / "lessons" / "existing.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_CURRENT, encoding="utf-8")
    collect.record(collect.KIND_L3_FETCH, {"session": session, "page": _TARGET})
    return path


def _durable_update():
    return {"verdict": "durable", "reason": "amends the lesson",
            "scope": "global", "action": "update", "target_page": _TARGET}


def test_precomputed_merge_applies(wiki):
    """A merge supplied via merges= reaches the write door with no llm_call."""
    path = _eligible_target(wiki, "s-merge-1")

    result = wrap_session("# n", ["the learning"], "s-merge-1",
                          verdicts=[_durable_update()], merges=[_MERGED])

    assert result["gated_out"] == []
    assert result["unplaced"] == []
    assert [u["page"] for u in result["updated"]] == [_TARGET]
    assert "new line" in path.read_text(encoding="utf-8")


def test_missing_merge_routes_to_suggestions_not_gated_out(wiki):
    """The #75 fix. This previously landed in gated_out with
    "merge llm call failed: 'NoneType' object is not callable"."""
    _eligible_target(wiki, "s-merge-2")

    result = wrap_session("# n", ["the learning"], "s-merge-2",
                          verdicts=[_durable_update()])

    assert result["gated_out"] == []
    assert result["updated"] == []
    assert len(result["unplaced"]) == 1
    assert any(
        s["payload"].get("action") == "place_durable_item"
        and s["fingerprint"].startswith("wrap-unmerged:")
        for s in suggestions.pending_suggestions()
    )


def test_invalid_merge_routes_to_suggestions(wiki):
    """A merge that altered the frontmatter is unplaced, never silently gated."""
    _eligible_target(wiki, "s-merge-3")
    tampered = "---\ntype: hub\n---\n# Existing\n\nold line\nnew line\n"

    result = wrap_session("# n", ["the learning"], "s-merge-3",
                          verdicts=[_durable_update()], merges=[tampered])

    assert result["gated_out"] == []
    assert result["updated"] == []
    assert len(result["unplaced"]) == 1


def test_live_llm_call_path_is_unchanged(wiki):
    """A caller holding a live callable behaves exactly as before."""
    path = _eligible_target(wiki, "s-merge-4")

    result = wrap_session("# n", ["the learning"], "s-merge-4",
                          verdicts=[_durable_update()],
                          llm_call=lambda prompt: _MERGED)

    assert [u["page"] for u in result["updated"]] == [_TARGET]
    assert "new line" in path.read_text(encoding="utf-8")


def test_supplied_merge_wins_over_llm_call(wiki):
    """When both are available the pre-computed merge is used — no LLM call."""
    calls = []

    def spy(prompt):
        calls.append(prompt)
        return _MERGED

    _eligible_target(wiki, "s-merge-5")
    wrap_session("# n", ["the learning"], "s-merge-5",
                 verdicts=[_durable_update()], merges=[_MERGED], llm_call=spy)

    assert calls == []


def test_merges_length_mismatch_raises(wiki):
    with pytest.raises(ValueError, match="merges must match durable_items"):
        wrap_session("# n", ["a", "b"], "s-merge-6",
                     verdicts=[_durable_update(), _durable_update()],
                     merges=["only-one"])
```

**Note on `_target_trust`:** the fixture page carries no `ren_*` provenance, so it is not `trust="user"` and takes the auto-apply path. If you make the target a human-authored page, expect `suggested` rather than `updated` — that branch is unchanged by this task and already covered elsewhere.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/skills/wrap/test_merges_transport.py -v`

Expected: FAIL — `ImportError: cannot import name 'validate_merged'`.

- [ ] **Step 3: Split validation out of `merge_update`**

In `skills/wrap/lib/merge.py`, add:

```python
def validate_merged(current_text: str, merged_text: str) -> str:
    """Return `merged_text` if it is a legitimate merge of `current_text`,
    else raise `MergeError`.

    Split out of `merge_update` (spec 2026-08-21 §5.1) so a merge produced by
    a SUBAGENT — arriving through `wrap_session(merges=...)` with no live
    callable in the process — is held to exactly the same standard as one
    produced by a local `llm_call`. Frontmatter is the door's property: a
    merge that touched it is refused.
    """
    if not isinstance(merged_text, str) or not merged_text.strip():
        raise MergeError("merge output empty or not a string")
    if _frontmatter_block(merged_text) != _frontmatter_block(current_text):
        raise MergeError("merge output altered the frontmatter block")
    if merged_text == current_text:
        raise MergeError("merge output is byte-identical to the current page")
    return merged_text
```

and replace the tail of `merge_update()` (everything after the `llm_call` try/except) with:

```python
    return validate_merged(current_text, raw)
```

Add `"validate_merged"` to `__all__`.

- [ ] **Step 4: Run the validation tests**

Run: `uv run pytest tests/skills/wrap/test_merges_transport.py::TestValidateMerged -v`

Expected: PASS.

- [ ] **Step 5: Add `merges=` to `wrap_session`**

In `skills/wrap/lib/__init__.py`, add the kwarg to the signature after `verdicts`:

```python
    merges: list[str | None] | None = None,
```

Add the length check next to the existing `verdicts` one (line 923):

```python
    if merges is not None and len(merges) != len(durable_items):
        raise ValueError(
            f"merges must match durable_items 1:1 by index: "
            f"{len(merges)} merges for {len(durable_items)} items"
        )
```

Import `validate_merged` alongside the existing merge import:

```python
from .merge import merge_update, validate_merged, MergeError
```

Replace the `if decision.action == "update":` block's merge attempt (lines 978-991) with the three-way:

```python
        if decision.action == "update":
            target = decision.target_page
            try:
                current = ren_paths.safe_join(
                    ren_paths.wiki_root(), target
                ).read_text(encoding="utf-8")
                supplied = merges[i] if merges is not None else None
                if supplied is not None:
                    merged = validate_merged(current, supplied)
                elif llm_call is not None:
                    merged = merge_update(current, item, llm_call)
                else:
                    raise MergeError(
                        "no merge available: the verdicts= transport supplied "
                        "none and there is no live llm_call"
                    )
            except (OSError, MergeError) as exc:
                # Spec 2026-08-21 §5.2: a durable item that cannot be merged
                # goes to a human, NOT to gated_out. Landing it in gated_out
                # is the same die-silently class Part A fixed for scope-None
                # placement — the classifier affirmed it as durable, so
                # dropping it silently loses a real learning.
                unplaced.append(_route_unplaced(
                    item, session, i,
                    reason=f"update to {target} could not be merged: {exc}",
                    fingerprint=f"wrap-unmerged:{session}:{i}"))
                continue
```

Update the `wrap_session` docstring's `"gated_out"` and `"unplaced"` entries to describe the new routing, and document `merges` next to `verdicts`.

- [ ] **Step 6: Run the wrap suite**

Run: `uv run pytest tests/skills/wrap/ -v`

Expected: PASS. Any existing test asserting that a merge failure lands in `gated_out` is now asserting the old buggy behavior — update it to assert `unplaced` instead, and note the change in the commit body.

- [ ] **Step 7: Document phase 2 in SKILL.md**

In `skills/wrap/SKILL.md` step 3, after the classifier-subagent paragraph, add:

```markdown
   - **Phase 2 — merges (spec 2026-08-21 §5.3).** When any verdict came back
     `durable` with `action: "update"`, those items need a merged page body,
     and the `verdicts=` path has no live `llm_call` to produce one. Call
     `skills.wrap.lib.eligible_update_targets(session)` for the eligible set,
     then dispatch ONE batched subagent over the update-verdicts whose
     `target_page` is in it, giving each the item text plus the target page's
     current text and asking for the COMPLETE merged page back — it must copy
     the YAML frontmatter verbatim and change only the section(s) the learning
     affects. Assemble the results into an array index-aligned with the
     candidate list, `null` wherever no merge came back, and pass it as
     `wrap_session(..., verdicts=<array>, merges=<array>)`.
   - An update whose merge is missing or fails validation is NOT discarded:
     it routes to the suggestions store for the friend to place, same as an
     unplaceable item. Passing no `merges` at all is safe — every
     update-verdict simply routes to suggestions instead of auto-applying.
```

- [ ] **Step 8: Run the full suite and commit**

Run: `uv run pytest -q`

```bash
git add skills/wrap/lib/merge.py skills/wrap/lib/__init__.py \
        skills/wrap/SKILL.md tests/skills/wrap/test_merges_transport.py
git commit -m "$(cat <<'EOF'
fix(wrap): merges= transport so update-verdicts stop dying (#75)

Under the standard verdicts= path there is no live llm_call, so every
update-action durable verdict hit "merge llm call failed: 'NoneType'
object is not callable" and landed in gated_out. All three of the
2026-08-19 wrap's durable-affirmed candidates died this way.

Splits validate_merged() out of merge_update() so a subagent-produced
merge is held to the same standard, adds merges= alongside verdicts=,
and routes an unmergeable durable item to suggestions rather than
gated_out — the same die-loudly discipline Part A established.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: The scrub follow-set (#72)

**Files:**
- Modify: `lib/memory/scrub.py:117` and `:130`
- Test: `tests/lib/memory/test_scrub.py`

**Interfaces:**
- Consumes: nothing. Produces: nothing. Fully independent of Tasks 1-5.

**Context you need:** The `#29` type-annotation exemption's negative lookahead only accepts `[`, `|`, whitespace, a quote, or end-of-string after a guard word. Where a secret-shaped key is annotated `str` with a trailing comma, the character after `str` is `,`, so the lookahead does not fire and `[^\s'\"(]{4,}` matches `str,` — exactly 4 characters. This blocked the 0.7.9 release push. The fix below was verified before approval on a 20-case matrix: 7 false positives cleared, 0 regressions.

- [ ] **Step 1: Write the failing tests**

Add to `tests/lib/memory/test_scrub.py` (match the file's existing test style):

```python
class TestTypeAnnotationFollowSet:
    """#72: the #29 exemption's terminator set was incomplete — a trailing
    comma, close-paren or close-bracket after a guard word defeated it, so a
    bare annotated parameter scanned as a password pair."""

    # MANDATORY: assemble every fixture at runtime via the file's existing
    # `_pair(key, op, value)` helper. A literal key=value shape in this file
    # would be scanned by the pre-push guard — which uses THIS scanner — and
    # would block the push that ships the fix for it. Precedent: commit
    # e59bbdd, "reshape secret-shaped literals for the push guard".

    @pytest.mark.parametrize("key,op,value", [
        ("    secret", ": ", "str,"),
        ("    password", ": ", "str,"),
        ("    token", ": ", "int,"),
        ("    api_key", ": ", "str,"),
        ("def f(secret", ": ", "str)"),
        ("x: dict[str, secret", ": ", "str]"),
        ("    token", ": ", "float,"),
    ])
    def test_annotated_parameter_is_clean(self, key, op, value):
        assert scan(_pair(key, op, value)) == []

    @pytest.mark.parametrize("key,op,value", [
        ("    secret", ": ", "str = None"),
        ("secret", ": ", "Final[str]"),
        ("password", ": ", "float | None"),
        ("token", ": ", "4.0"),
        ("api_key", ": ", "128000"),
        ("secret", " = ", "locks.content_token(x)"),
    ])
    def test_existing_exemptions_do_not_regress(self, key, op, value):
        assert scan(_pair(key, op, value)) == []

    def test_bare_keyword_in_prose_does_not_fire(self):
        assert scan("enter your password") == []

    @pytest.mark.parametrize("key,op,value", [
        ("secret", ": ", '"hunter2xyz"'),
        ("password", " = ", '"correcthorse"'),
        ("password", ": ", "1234"),
        ("secret", ": ", "none.of.your.business"),
        ("api_key", ": ", '"sk-' + "abcdef123456\""),
        ("token", ": ", "ghp_" + "realtokenvalue"),
    ])
    def test_real_secrets_still_hit(self, key, op, value):
        assert scan(_pair(key, op, value)) != []
```

- [ ] **Step 2: Run to verify the right ones fail**

Run: `uv run pytest tests/lib/memory/test_scrub.py::TestTypeAnnotationFollowSet -v`

Expected: the 7 `test_annotated_parameter_is_clean` cases FAIL; the other 13 PASS. If any of the 13 fail, stop — the baseline is not what this task assumes.

- [ ] **Step 3: Extend the follow-set**

In `lib/memory/scrub.py`, at **both** line 117 and line 130, change:

```python
            r"(?:[\[\|]|[\s'\"]|$))"  # not a whole type-like token
```

to:

```python
            r"(?:[\[\|,)\]]|[\s'\"]|$))"  # not a whole type-like token
```

Update the comment block above the pattern (around line 99) so the reason is recorded:

```python
        # punctuation/whitespace/end — a secret merely STARTING with one
        # (`none.of.your.business`) still matches (0.7.7 review). The
        # terminator set includes `,`, `)` and `]` (#72): without them a bare
        # annotated parameter (a secret-shaped key annotated `str` with a
        # trailing comma) fell through to the value
        # branch and scanned as a password pair, blocking a release push.
```

- [ ] **Step 4: Run to verify all 20 pass**

Run: `uv run pytest tests/lib/memory/test_scrub.py -v`

Expected: PASS — all 20 new cases plus every pre-existing scrub test.

- [ ] **Step 5: Run the full suite and commit**

Run: `uv run pytest -q`

```bash
git add lib/memory/scrub.py tests/lib/memory/test_scrub.py
git commit -m "$(cat <<'EOF'
fix(scrub): trailing comma no longer defeats the #29 exemption (#72)

The type-annotation lookahead accepted only [ | whitespace quote or
end-of-string after a guard word, so a secret-shaped key annotated `str`
with a trailing comma fell through to the
value branch and matched `str,` as a password pair. Blocked the 0.7.9
release push.

Adds , ) ] to the terminator set on both branches. Verified on a 20-case
matrix: 7 false positives cleared, 0 regressions, all true positives
(quoted values, digits-only PIN, none.of.your.business, ghp_ token)
still hit.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Live acceptance run

**Files:** none — this task runs the shipped code against the real wiki and records what happened.

**Interfaces:** Consumes everything from Tasks 1-6.

**Do not start this task until Tasks 1-6 are committed and `uv run pytest -q` is green.**

- [ ] **Step 1: Back up first**

Run: `/ren:backup` (or `uv run python -c "..."` per `skills/backup/SKILL.md`).

This task writes to the real wiki. The migration's revert path is the pre-update snapshot; make sure one exists.

- [ ] **Step 2: Dry-run the migration**

Run: `uv run python migrations/frontmatter-type-1/migrate.py --check`

Expected: 29 `WOULD STAMP` lines. If the count differs from 29, stop and report — the wiki changed since the spec was written, and the delta needs a look before writing.

- [ ] **Step 3: Apply the migration**

Run: `uv run python migrations/frontmatter-type-1/migrate.py`

Expected: `frontmatter-type-1: 29 stamped, N already typed or unmapped`

- [ ] **Step 4: Verify zero untyped pages remain**

Run: `uv run python -c "$(cat <<'EOF'
import os, re
from lib.ren_paths import wiki_root
fm = re.compile(r'\A---\n(.*?)\n---\n', re.S)
missing = []
root = str(wiki_root())
for d, dirs, files in os.walk(root):
    dirs[:] = [x for x in dirs if x not in ('.ren', '.git')]
    for f in files:
        if not f.endswith('.md'):
            continue
        p = os.path.join(d, f)
        t = open(p, encoding='utf-8', errors='replace').read()
        m = fm.match(t)
        if not (m and re.search(r'^type:', m.group(1), re.M)):
            missing.append(os.path.relpath(p, root))
print('untyped:', len(missing))
for x in missing:
    print(' ', x)
EOF
)"`

Expected: `untyped: 0`

- [ ] **Step 5: Run the retraction sweep**

Run a full lint pass so `_retract_resolved_findings()` re-verifies the 26 findings:

`uv run python -c "import importlib; lint = importlib.import_module('skills.wiki-health.lib.lint'); print(lint.run_incremental_lint('acceptance-2026-08-21', full=True))"`

Expected: `retracted` is 26.

- [ ] **Step 6: Verify the store**

Run: `/ren:suggestions`

Expected: pending count drops 49 → ~23 (17 quarantine-release, 3 map-pointer-missing, 2 dangling-link, 1 hub-split-link-lists). Confirm the 26 retracted entries have `status: "resolved"` and that **none** of their fingerprints appear in `.ren/suggestions/decisions.jsonl` — that absence is what lets the lint fire again if a page regresses.

- [ ] **Step 7: Verify a fresh write is typed on its first write**

Run `/ren:pin` on any throwaway durable fact, then check the created page carries `type:` with no second write in the journal.

- [ ] **Step 8: Run doctor**

Run: `/ren:doctor`

Expected: no worse than its pre-train baseline (20 ok, 4 info/skip, 0 warn/fail as of 2026-08-19).

- [ ] **Step 9: Record the outcome**

Append the measured numbers to the spec's §9 as an "Acceptance run (2026-08-21)" block: pages stamped, findings retracted, pending before/after, and anything that came out different from the prediction. **An honest miss is signal** — if a number lands wrong, record the real one rather than the expected one.

```bash
git add docs/superpowers/specs/2026-08-21-knowledge-flow-seams-design.md
git commit -m "$(cat <<'EOF'
docs(spec): record the knowledge-flow-seams acceptance run

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Close-out

- [ ] **Release-time follow-up (pre-flight ruling):** add a `/ren:update` gate for `frontmatter-type-1` in `skills/update/lib/__init__.py`, matching `should_run_trust_backfill`'s shape, gated at whatever version ships this train. Without it the backfill never runs on other installs — `global_migrations` in `schemas.json` is discoverability only. Deferred because the gate version is unknowable until the release version is chosen.
- [ ] File the follow-up issue for hub typing inconsistency (spec §10): global `lessons/lessons.md` is `hub`, project `.../lessons/lessons.md` is `project-knowledge`, root `index.md` is `l2-map` while the lint's `_is_hub_page()` counts it as a hub. I1 preserved all three; normalizing them is its own decision.
- [ ] Close #72, #73, #74, #75 with a pointer to the spec and the acceptance numbers.
- [ ] Update the open-work ledger: close the `#73`/`#74` lines, and the `_watermark_after` line stays open (untouched by this train).
- [ ] Run `superpowers:requesting-code-review`, then the `ren-reviewer` gate on the full train — clear every CRITICAL/HIGH before merging.
- [ ] `superpowers:finishing-a-development-branch` to decide integration.
