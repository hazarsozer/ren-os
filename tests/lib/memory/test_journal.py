"""
Tests for `lib.memory.journal` — the append-only write journal.

Focus: a corrupt/truncated line must NOT take the whole journal reader down
(0.6.5 final-review finding 3). `entries()` is on the critical path of the
wiki-lint watermark, the incremental lint and the wake-up nudge; wrap step 7
spawns `ren-wiki-lint` NON-BLOCKING while the session keeps appending, so two
processes hold the file open for append and a long line can interleave.

The hook's own stdlib counter (`wakeup._unlinted_count`) counts non-blank
lines and never raises, so a raising `entries()` would also make the two
deliberately-duplicated counters disagree — the watermark could never advance
and the nudge would fire forever.

Run with: uv run pytest tests/lib/memory/test_journal.py -v
"""

from __future__ import annotations

import pytest

from lib.memory import journal
from lib.memory.provenance import Provenance
from lib.ren_paths import state_dir


@pytest.fixture
def journal_env(monkeypatch, tmp_path):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    return tmp_path


def _prov(page: str) -> Provenance:
    return Provenance(
        write_id="w-test", ts="2026-08-02T00:00:00Z", writer="human",
        session="s", op="UPDATE", page=page, supersedes=None,
    )


def test_corrupt_line_is_skipped_not_fatal(journal_env):
    journal.append(_prov("a.md"))
    path = state_dir() / journal.JOURNAL_FILENAME
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json at all\n")
    journal.append(_prov("b.md"))

    entries = journal.entries()

    assert [e["page"] for e in entries] == ["a.md", "b.md"]


def test_truncated_interleaved_line_is_skipped(journal_env):
    """The realistic corruption: two appenders interleave and one line is cut
    mid-object (a `wrap_summary` with a big `pages_touched` can exceed
    PIPE_BUF)."""
    journal.append(_prov("a.md"))
    path = state_dir() / journal.JOURNAL_FILENAME
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"write_id": "w-x", "page": "trunc.md", "pages_tou\n')
    journal.append(_prov("b.md"))

    entries = journal.entries()

    assert [e["page"] for e in entries] == ["a.md", "b.md"]


def test_non_object_json_line_is_skipped(journal_env):
    """A valid-JSON but non-object line would blow up `entry.get(...)` at
    every call site — treat it as corrupt too."""
    journal.append(_prov("a.md"))
    path = state_dir() / journal.JOURNAL_FILENAME
    with path.open("a", encoding="utf-8") as handle:
        handle.write("[1, 2, 3]\n")

    assert [e["page"] for e in journal.entries()] == ["a.md"]


def test_page_filter_still_works_around_a_corrupt_line(journal_env):
    journal.append(_prov("a.md"))
    path = state_dir() / journal.JOURNAL_FILENAME
    with path.open("a", encoding="utf-8") as handle:
        handle.write("garbage\n")
    journal.append(_prov("a.md"))
    journal.append(_prov("b.md"))

    assert len(journal.entries(page="a.md")) == 2
