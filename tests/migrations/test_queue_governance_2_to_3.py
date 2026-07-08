"""
End-to-end test for the queue-governance 2→3 migration (Task 10).

Unlike routine-spec-1-to-2/2-to-3 (page-frontmatter migrations driven by
`skills/wiki-migration`'s per-page `migrate.sh` chain), this migration walks
QUEUE STATE — `state_dir()/queue/*.json` — not a wiki page's frontmatter, so
it does not fit the page-type/schemas.json/migrate.sh shape. It is a
standalone `migrate.py` invoked directly (see this migration's README for
the shape-decision rationale).

A friend upgrading from 0.2.x has pending queue entries that were only
pending because 0.2 gated every write. Under v2.2 policy the DATA plane
(non-global pages, no `contradicts` hold) auto-applies; the INSTRUCTION
plane (`global/` pages) and contradiction holds stay pending as
conversational suggestions — this migration performs exactly that release,
once, idempotently.

Run with: uv run pytest tests/migrations/test_queue_governance_2_to_3.py -v
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from lib.memory import queue
from lib.memory.queue import Proposal
from lib.ren_paths import wiki_root

_MIGRATE_PATH = (
    Path(__file__).resolve().parents[2] / "migrations" / "queue-governance-2-to-3" / "migrate.py"
)


def _load_migrate():
    """Load migrate.py by path — its directory name has hyphens, so it can't
    be a normal importable package; `lib.memory.queue` inside it resolves to
    the SAME module object already imported by this test (via sys.modules),
    so monkeypatched env vars and seeded queue entries are visible to it."""
    spec = importlib.util.spec_from_file_location("_qg23_migrate", _MIGRATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    return monkeypatch


@pytest.fixture
def wiki(clean_path_env, tmp_path):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _proposal(**overrides):
    defaults = dict(
        op="ADD",
        page="lessons/legacy.md",
        content="a 0.2-era gated lesson",
        reason="0.2-style pending seed",
        producer="wrap",
        writer="human",
        session="sess-migrate",
    )
    defaults.update(overrides)
    return Proposal(**defaults)


def _seed_pending_pair():
    """One 0.2-style pending lesson (data-plane, should be released) + one
    pending global/ entry (instruction-plane, must stay pending)."""
    lesson = queue.propose(_proposal())
    global_entry = queue.propose(
        _proposal(page="global/rule.md", producer="promotion", content="a rule")
    )
    assert lesson.status == "pending"
    assert global_entry.status == "pending"
    return lesson, global_entry


def test_migration_releases_data_plane_and_leaves_global_pending(wiki):
    lesson, global_entry = _seed_pending_pair()

    migrate = _load_migrate()
    rc = migrate.main([])

    assert rc == 0
    lesson_after = queue.get(lesson.qid)
    global_after = queue.get(global_entry.qid)

    assert lesson_after.status == "applied"
    assert (wiki / "lessons/legacy.md").exists()
    assert global_after.status == "pending"


def test_migration_is_idempotent_second_run_is_noop(wiki):
    lesson, global_entry = _seed_pending_pair()

    migrate = _load_migrate()
    migrate.main([])

    first_lesson = queue.get(lesson.qid)
    first_global = queue.get(global_entry.qid)
    assert first_lesson.status == "applied"
    assert first_global.status == "pending"

    rc = migrate.main([])

    assert rc == 0
    second_lesson = queue.get(lesson.qid)
    second_global = queue.get(global_entry.qid)

    assert second_lesson.status == "applied"
    assert second_lesson.write_id == first_lesson.write_id
    assert second_global.status == "pending"


def test_migration_no_pending_entries_is_a_clean_noop(wiki):
    migrate = _load_migrate()
    rc = migrate.main([])
    assert rc == 0
