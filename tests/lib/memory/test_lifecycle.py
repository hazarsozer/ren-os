"""
Tests for lib.memory.lifecycle — 90-day decay at wrap (Task 17, RenOS 0.5.3
"learning brain").

Conservative decay: a data-plane page (never `global/`, never already
`archive/`, never quarantined) with no salience boost decays only when BOTH
its last journal write AND its last miss-log fetch (if any) are older than
`DECAY_WINDOW_DAYS`. A page with no fetch record decays on journal age
alone — absence of recall IS the signal. An unreadable miss-log blocks decay
entirely (conservative fail-closed), never partially.

Run with: uv run pytest tests/lib/memory/test_lifecycle.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from lib import ren_paths
from lib.instrument import collect
from lib.memory import journal, lifecycle, locks, queue, quarantine, write_apply
from lib.memory.provenance import new_provenance
from lib.memory.queue import Proposal

NOW = datetime(2026, 7, 12, tzinfo=timezone.utc)
OLD_TS = "2026-01-01T00:00:00Z"  # ~192 days before NOW: stale
RECENT_TS = "2026-07-01T00:00:00Z"  # ~11 days before NOW: fresh


@pytest.fixture
def wiki_root(tmp_path, monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    root = tmp_path / "wiki"
    root.mkdir()
    monkeypatch.setenv("REN_WIKI_ROOT", str(root))
    return root


def _add(page, content, session="s1"):
    prov = new_provenance("human", session, "ADD", page)
    write_apply.apply_write(page, content, prov)
    return prov


def _backdate_journal(page, ts):
    """Rewrite the most recent journal entry for `page` to carry `ts`."""
    path = ren_paths.state_dir() / journal.JOURNAL_FILENAME
    lines = path.read_text(encoding="utf-8").splitlines()
    import json

    for i in range(len(lines) - 1, -1, -1):
        entry = json.loads(lines[i])
        if entry.get("page") == page:
            entry["ts"] = ts
            lines[i] = json.dumps(entry)
            break
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _record_fetch(page, ts, session="s1"):
    """Write one L3_FETCH metric entry directly, stamped with `ts` (bypasses
    `collect.record`'s real-clock timestamp so tests can backdate it)."""
    import json

    month_file = ren_paths.state_dir() / "metrics" / f"{ts[:7]}.jsonl"
    month_file.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": ts, "kind": collect.KIND_L3_FETCH, "page": page, "query": "q", "session": session}
    with month_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------- candidates


def test_stale_and_unrecalled_page_is_a_candidate(wiki_root):
    _add("notes.md", "stale content\n")
    _backdate_journal("notes.md", OLD_TS)

    assert lifecycle.decay_candidates(NOW) == ["notes.md"]


def test_recently_fetched_page_is_not_a_candidate(wiki_root):
    _add("notes.md", "stale-write but recently fetched\n")
    _backdate_journal("notes.md", OLD_TS)
    _record_fetch("notes.md", RECENT_TS)

    assert lifecycle.decay_candidates(NOW) == []


def test_page_with_old_fetch_decays_on_journal_age(wiki_root):
    """An old fetch record does not protect a page — only a RECENT one does."""
    _add("notes.md", "stale write, stale fetch\n")
    _backdate_journal("notes.md", OLD_TS)
    _record_fetch("notes.md", OLD_TS)

    assert lifecycle.decay_candidates(NOW) == ["notes.md"]


def test_recently_written_page_is_not_a_candidate(wiki_root):
    _add("notes.md", "fresh content\n")

    assert lifecycle.decay_candidates(NOW) == []


def test_salient_page_is_not_a_candidate(wiki_root):
    entry, _prov = queue.propose_and_apply(
        Proposal(
            op="ADD",
            page="pinned.md",
            content="important pinned fact\n",
            reason="pin",
            producer="pin",
            writer="human",
            session="s1",
            salience=True,
        )
    )
    assert entry.status == "applied"
    _backdate_journal("pinned.md", OLD_TS)
    # Force the salience-granting queue entry's own ts to be recent relative
    # to the fixed `NOW` test point (real wall-clock "now" at propose time is
    # already fresh, but NOW here is a fixed point in the past).
    _touch_queue_entry_ts(entry.qid, RECENT_TS)

    assert lifecycle.decay_candidates(NOW) == []


def _touch_queue_entry_ts(qid, ts):
    import json

    path = ren_paths.state_dir() / "queue" / f"{qid}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["ts"] = ts
    path.write_text(json.dumps(data), encoding="utf-8")


def test_global_pages_never_candidates(wiki_root):
    _add("global/policy.md", "instruction content\n")
    _backdate_journal("global/policy.md", OLD_TS)

    assert lifecycle.decay_candidates(NOW) == []


def test_already_archived_pages_never_candidates(wiki_root):
    from lib.memory import archive

    _add("notes.md", "will be archived\n")
    _backdate_journal("notes.md", OLD_TS)
    archive.archive_page("notes.md", "s1", reason="manual")
    _backdate_journal("archive/notes.md", OLD_TS)

    assert lifecycle.decay_candidates(NOW) == []


def test_quarantined_pages_excluded(wiki_root):
    content = quarantine.QUARANTINE_BANNER + "stale quarantined content\n"
    _add("auto.md", content)
    _backdate_journal("auto.md", OLD_TS)

    assert quarantine.is_quarantined((wiki_root / "auto.md").read_text(encoding="utf-8"))
    assert lifecycle.decay_candidates(NOW) == []


def test_unreadable_miss_log_blocks_all_decay(wiki_root, monkeypatch):
    _add("notes.md", "stale content\n")
    _backdate_journal("notes.md", OLD_TS)

    def raiser(*args, **kwargs):
        raise OSError("miss-log unreadable")

    monkeypatch.setattr(lifecycle.collect, "read", raiser)

    assert lifecycle.decay_candidates(NOW) == []


def test_cap_enforced_oldest_first(wiki_root):
    ts_by_page = {
        "a.md": "2025-01-01T00:00:00Z",
        "b.md": "2025-02-01T00:00:00Z",
        "c.md": "2025-03-01T00:00:00Z",
        "d.md": "2025-04-01T00:00:00Z",
        "e.md": "2025-05-01T00:00:00Z",
        "f.md": "2025-06-01T00:00:00Z",
    }
    for page, ts in ts_by_page.items():
        _add(page, f"stale {page}\n")
        _backdate_journal(page, ts)

    candidates = lifecycle.decay_candidates(NOW)
    assert candidates == ["a.md", "b.md", "c.md", "d.md", "e.md", "f.md"]

    moves = lifecycle.run_decay("s1")
    assert len(moves) == lifecycle.DECAY_MAX_PER_WRAP == 5
    archived = {m["archive_page"] for m in moves}
    assert archived == {"archive/a.md", "archive/b.md", "archive/c.md", "archive/d.md", "archive/e.md"}
    assert not (wiki_root / "archive" / "f.md").exists()


# --------------------------------------------------------------------- run_decay


def test_run_decay_archives_via_archive_page(wiki_root):
    _add("notes.md", "stale content\n")
    _backdate_journal("notes.md", OLD_TS)

    moves = lifecycle.run_decay("s1")

    assert len(moves) == 1
    assert moves[0]["archive_page"] == "archive/notes.md"
    assert not (wiki_root / "notes.md").exists()
    assert (wiki_root / "archive" / "notes.md").exists()


def test_run_decay_skips_page_on_lost_update_and_continues(wiki_root, monkeypatch):
    _add("a.md", "stale a\n")
    _backdate_journal("a.md", OLD_TS)
    _add("b.md", "stale b\n")
    _backdate_journal("b.md", OLD_TS)

    from lib.memory import archive as archive_mod

    real_archive_page = archive_mod.archive_page

    def flaky_archive_page(rel, session, *, reason):
        if rel == "a.md":
            raise locks.LostUpdate("racy")
        return real_archive_page(rel, session, reason=reason)

    monkeypatch.setattr(lifecycle.archive, "archive_page", flaky_archive_page)

    moves = lifecycle.run_decay("s1")

    assert len(moves) == 1
    assert moves[0]["archive_page"] == "archive/b.md"
    assert (wiki_root / "a.md").exists()  # untouched — skipped, not aborted
