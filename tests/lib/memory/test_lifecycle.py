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
from lib.instrument import collect, miss_log
from lib.memory import journal, lifecycle, locks, queue, quarantine, write_apply
from lib.memory.provenance import Provenance, new_provenance
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


def _record_surface(pages, ts, session="s1"):
    """Write one WAKEUP_SURFACE metric entry directly, stamped with `ts`
    (bypasses `collect.record`'s real-clock timestamp so tests can backdate
    it). `pages` is list-valued, unlike `_record_fetch`'s single `page`."""
    import json

    month_file = ren_paths.state_dir() / "metrics" / f"{ts[:7]}.jsonl"
    month_file.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": ts, "kind": collect.KIND_WAKEUP_SURFACE, "pages": list(pages), "session": session}
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


def test_surfaced_page_survives_decay(wiki_root):
    """A page wake-up injected (KIND_WAKEUP_SURFACE), never fetched, still
    counts as a usage touch and is protected."""
    _add("notes.md", "stale write, but wake-up surfaced it\n")
    _backdate_journal("notes.md", OLD_TS)
    miss_log.log_surface(["notes.md"], session="s1")  # real clock: fresh relative to NOW

    assert lifecycle.decay_candidates(NOW) == []


def test_read_page_survives_decay(wiki_root):
    """A page read directly (KIND_PAGE_READ via miss_log.log_read), never
    fetched or surfaced, still counts as a usage touch and is protected."""
    _add("notes.md", "stale write, but directly read\n")
    _backdate_journal("notes.md", OLD_TS)
    miss_log.log_read("notes.md", "s1")  # real clock: fresh relative to NOW

    assert lifecycle.decay_candidates(NOW) == []


def test_untouched_page_still_decays(wiki_root):
    """Regression guard: a page with no fetch, surface, or read event at all
    still decays on journal age alone."""
    _add("notes.md", "stale content, never touched\n")
    _backdate_journal("notes.md", OLD_TS)

    assert lifecycle.decay_candidates(NOW) == ["notes.md"]


def test_stale_events_do_not_protect(wiki_root):
    """A 100-day-old wake-up surface event does not protect — only a RECENT
    one does (mirrors test_page_with_old_fetch_decays_on_journal_age)."""
    _add("notes.md", "stale write, stale surface\n")
    _backdate_journal("notes.md", OLD_TS)
    _record_surface(["notes.md"], OLD_TS)

    assert lifecycle.decay_candidates(NOW) == ["notes.md"]


@pytest.mark.parametrize(
    "raising_kind", [collect.KIND_L3_FETCH, collect.KIND_WAKEUP_SURFACE, collect.KIND_PAGE_READ]
)
def test_unreadable_usage_log_skips_decay(wiki_root, monkeypatch, raising_kind):
    """If ANY of the three consumed kinds is unreadable, decay is skipped
    entirely (conservative all-or-nothing), not just for that kind."""
    _add("notes.md", "stale content\n")
    _backdate_journal("notes.md", OLD_TS)

    real_read = collect.read

    def selective_raiser(kind=None, since=None):
        if kind == raising_kind:
            raise OSError("usage log unreadable")
        return real_read(kind=kind, since=since)

    monkeypatch.setattr(lifecycle.collect, "read", selective_raiser)

    assert lifecycle.decay_candidates(NOW) == []


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


# ---------------------------------------------------------- consolidate_duplicates


def _add_with_ts(page, content, ts, session="s1", writer="human", trust="user"):
    """Write `page` stamped with an explicit `ren_ts` (bypasses the real
    clock so tests can control which of a pair is 'older')."""
    from ulid import ULID

    prov = Provenance(
        write_id=f"w-{ULID()}",
        ts=ts,
        writer=writer,
        session=session,
        op="ADD",
        page=page,
        supersedes=None,
        trust=trust,
    )
    write_apply.apply_write(page, content, prov)
    return prov


def test_consolidate_merges_high_confidence_duplicate(wiki_root):
    _add_with_ts("a.md", "content a\n", "2026-01-01T00:00:00Z")
    _add_with_ts("b.md", "content b\n", "2026-02-01T00:00:00Z")

    findings = [
        {"page": "a.md", "with": "b.md", "verdict": "duplicate", "confidence": 0.9, "reason": "same fact"}
    ]
    moves = lifecycle.consolidate_duplicates(findings, "s1")

    assert len(moves) == 1
    assert not (wiki_root / "a.md").exists()
    assert (wiki_root / "archive" / "a.md").exists()

    b_content = (wiki_root / "b.md").read_text(encoding="utf-8")
    assert "Merged from [[a.md]] (" in b_content

    a_entries = journal.entries(page="a.md")
    assert any(e.get("op") == "DELETE" for e in a_entries)
    b_entries = journal.entries(page="b.md")
    assert any(e.get("merged_from") == "a.md" for e in b_entries)


def test_consolidate_older_by_ren_ts_regardless_of_finding_order(wiki_root):
    _add_with_ts("older.md", "content older\n", "2026-01-01T00:00:00Z")
    _add_with_ts("newer.md", "content newer\n", "2026-02-01T00:00:00Z")

    # 'page' is the newer one, 'with' is the older one — the pair order must
    # not determine which page archives.
    findings = [
        {"page": "newer.md", "with": "older.md", "verdict": "duplicate", "confidence": 0.9, "reason": "x"}
    ]
    moves = lifecycle.consolidate_duplicates(findings, "s1")

    assert len(moves) == 1
    assert not (wiki_root / "older.md").exists()
    assert (wiki_root / "newer.md").exists()
    assert "Merged from [[older.md]]" in (wiki_root / "newer.md").read_text(encoding="utf-8")


def test_consolidate_sub_threshold_confidence_untouched(wiki_root):
    _add_with_ts("a.md", "content a\n", "2026-01-01T00:00:00Z")
    _add_with_ts("b.md", "content b\n", "2026-02-01T00:00:00Z")

    findings = [
        {"page": "a.md", "with": "b.md", "verdict": "duplicate", "confidence": 0.5, "reason": "meh"}
    ]
    moves = lifecycle.consolidate_duplicates(findings, "s1")

    assert moves == []
    assert (wiki_root / "a.md").exists()
    assert (wiki_root / "archive" / "a.md").exists() is False


def test_consolidate_global_page_untouched(wiki_root):
    _add_with_ts("global/policy.md", "instruction content\n", "2026-01-01T00:00:00Z", writer="human")
    _add_with_ts("b.md", "content b\n", "2026-02-01T00:00:00Z")

    findings = [
        {"page": "global/policy.md", "with": "b.md", "verdict": "duplicate", "confidence": 0.95, "reason": "x"}
    ]
    moves = lifecycle.consolidate_duplicates(findings, "s1")

    assert moves == []
    assert (wiki_root / "global" / "policy.md").exists()


def test_consolidate_foreign_page_untouched(wiki_root):
    _add_with_ts("a.md", "content a\n", "2026-01-01T00:00:00Z", writer="routine", trust="foreign")
    _add_with_ts("b.md", "content b\n", "2026-02-01T00:00:00Z")

    findings = [
        {"page": "a.md", "with": "b.md", "verdict": "duplicate", "confidence": 0.95, "reason": "x"}
    ]
    moves = lifecycle.consolidate_duplicates(findings, "s1")

    assert moves == []
    assert (wiki_root / "a.md").exists()


def test_consolidate_quarantined_page_untouched(wiki_root):
    content = quarantine.QUARANTINE_BANNER + "auto content\n"
    _add_with_ts("a.md", content, "2026-01-01T00:00:00Z", writer="llm-auto", trust="model")
    _add_with_ts("b.md", "content b\n", "2026-02-01T00:00:00Z")

    findings = [
        {"page": "a.md", "with": "b.md", "verdict": "duplicate", "confidence": 0.95, "reason": "x"}
    ]
    moves = lifecycle.consolidate_duplicates(findings, "s1")

    assert moves == []
    assert (wiki_root / "a.md").exists()


def test_consolidate_missing_ren_ts_is_skipped(wiki_root):
    (wiki_root / "a.md").write_text("no frontmatter at all\n", encoding="utf-8")
    _add_with_ts("b.md", "content b\n", "2026-02-01T00:00:00Z")

    findings = [
        {"page": "a.md", "with": "b.md", "verdict": "duplicate", "confidence": 0.95, "reason": "x"}
    ]
    moves = lifecycle.consolidate_duplicates(findings, "s1")

    assert moves == []
    assert (wiki_root / "a.md").exists()


def test_consolidate_non_duplicate_verdict_untouched(wiki_root):
    _add_with_ts("a.md", "content a\n", "2026-01-01T00:00:00Z")
    _add_with_ts("b.md", "content b\n", "2026-02-01T00:00:00Z")

    findings = [
        {"page": "a.md", "with": "b.md", "verdict": "related", "confidence": 0.95, "reason": "x"}
    ]
    moves = lifecycle.consolidate_duplicates(findings, "s1")

    assert moves == []


def test_consolidate_cap_enforced(wiki_root):
    findings = []
    for i in range(4):
        older = f"a{i}.md"
        newer = f"b{i}.md"
        _add_with_ts(older, f"content {older}\n", "2026-01-01T00:00:00Z")
        _add_with_ts(newer, f"content {newer}\n", "2026-02-01T00:00:00Z")
        findings.append(
            {"page": older, "with": newer, "verdict": "duplicate", "confidence": 0.9, "reason": "x"}
        )

    moves = lifecycle.consolidate_duplicates(findings, "s1")

    assert len(moves) == lifecycle.CONSOLIDATE_MAX_PER_WRAP == 3
    archived = sum(1 for i in range(4) if not (wiki_root / f"a{i}.md").exists())
    assert archived == 3


def test_consolidate_concurrent_write_during_archive_is_not_clobbered(wiki_root, monkeypatch):
    """Regression for task-18-review.md CRITICAL: expect_token must be
    captured at the same moment the newer page's content is read (top of
    the loop), not fresh right before the write — otherwise a write landing
    during the archive_page round-trip is silently lost."""
    _add_with_ts("a.md", "content a\n", "2026-01-01T00:00:00Z")
    _add_with_ts("b.md", "content b ORIGINAL\n", "2026-02-01T00:00:00Z")

    from lib.memory import archive as archive_mod

    real_archive_page = archive_mod.archive_page

    def racy_archive_page(rel, session, *, reason):
        result = real_archive_page(rel, session, reason=reason)
        if rel == "a.md":
            # A concurrent writer lands a change to b.md during the window
            # between the read of newer_content and the UPDATE write.
            concurrent_prov = new_provenance("routine", "other-session", "UPDATE", "b.md")
            write_apply.apply_write(
                "b.md", "content b CONCURRENTLY CHANGED\n", concurrent_prov
            )
        return result

    monkeypatch.setattr(lifecycle.archive, "archive_page", racy_archive_page)

    findings = [
        {"page": "a.md", "with": "b.md", "verdict": "duplicate", "confidence": 0.9, "reason": "x"}
    ]
    moves = lifecycle.consolidate_duplicates(findings, "s1")

    # The older page is already archived (irreversible without undo) but the
    # UPDATE must have raised LostUpdate against the stale token — the
    # concurrent writer's content must survive live, untouched.
    b_content = (wiki_root / "b.md").read_text(encoding="utf-8")
    assert "content b CONCURRENTLY CHANGED" in b_content
    assert "Merged from" not in b_content

    assert len(moves) == 1
    assert moves[0]["status"] == "partial"
    assert moves[0]["archived"] == "a.md"
    assert moves[0]["update_failed"] == "b.md"
    assert "error" in moves[0]


def test_consolidate_partial_merge_surfaced_not_dropped(wiki_root, monkeypatch):
    """Regression for task-18-review.md Important: an older-archived,
    newer-UPDATE-failed pair must appear in `moves` with a distinct
    "partial" status, not vanish silently."""
    _add_with_ts("a.md", "content a\n", "2026-01-01T00:00:00Z")
    _add_with_ts("b.md", "content b\n", "2026-02-01T00:00:00Z")

    real_apply_write = write_apply.apply_write

    def flaky_apply_write(rel, content, prov, **kwargs):
        if rel == "b.md":
            raise locks.LostUpdate("racy")
        return real_apply_write(rel, content, prov, **kwargs)

    monkeypatch.setattr(lifecycle.write_apply, "apply_write", flaky_apply_write)

    findings = [
        {"page": "a.md", "with": "b.md", "verdict": "duplicate", "confidence": 0.9, "reason": "x"}
    ]
    moves = lifecycle.consolidate_duplicates(findings, "s1")

    assert len(moves) == 1
    entry = moves[0]
    assert entry["status"] == "partial"
    assert entry["archived"] == "a.md"
    assert entry["archive_page"] == "archive/a.md"
    assert entry["update_failed"] == "b.md"
    assert entry["error"]
    # older page really was archived — this IS the half-done state
    assert not (wiki_root / "a.md").exists()
    assert (wiki_root / "archive" / "a.md").exists()


def test_consolidate_merged_entry_has_merged_status(wiki_root):
    """Normal success path now carries status="merged" alongside the
    pre-existing keys, kept backward compatible."""
    _add_with_ts("a.md", "content a\n", "2026-01-01T00:00:00Z")
    _add_with_ts("b.md", "content b\n", "2026-02-01T00:00:00Z")

    findings = [
        {"page": "a.md", "with": "b.md", "verdict": "duplicate", "confidence": 0.9, "reason": "x"}
    ]
    moves = lifecycle.consolidate_duplicates(findings, "s1")

    assert len(moves) == 1
    assert moves[0]["status"] == "merged"
    assert moves[0]["merged_into"] == "b.md"
