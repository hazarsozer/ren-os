"""
tests/integration/test_friend_week.py — the "friend week" end-to-end
integration test (Task 9.2a, exit criterion 6's CI stand-in).

Exit criterion 6: "a friend can install → onboard (<= the question budget)
-> see the first-session artifact -> work a week -> update -- without the
founder present." The REAL criterion needs a real friend + a real calendar
week; it stays PENDING-CALENDAR in the exit report. This test drives every
public lib surface the story touches, end to end, against one fresh sandbox
env, proving the MACHINE path works.

Drives ONLY public lib/skill surfaces — no internal state is hand-written;
every wiki page, queue entry, and journal line here is a side effect of a
real call (stamp_wiki, save_identity, ingest, pin, correct, wrap_session,
retrospective, revert, metric-watch, doctor, the update skill's real
version-compare.sh). Every test redirects ren_paths' framework root to
tmp_path via REN_FRAMEWORK_ROOT — never the real ~/.renos or ~/Dev.

Run with: uv run pytest tests/integration/test_friend_week.py -v
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from lib.instrument import collect
from lib.memory import journal, queue, quarantine
from lib.ren_paths import state_dir, wiki_root
from skills.doctor.lib import run_checks
from skills.install.lib import install_state, record_install, stamp_wiki
from skills.interview.lib import save_identity
from skills.pin.lib import correct, pin
from skills.queue.lib import approve_and_apply, revert_write
from skills.recall.lib import fetch as recall_fetch
from skills.remember.lib import remember
from skills.retrospective.lib import analyze, gather, propose_all
from skills.wrap.lib import render_wrap_screen, wrap_session

_ingest_lib = importlib.import_module("skills.ingest-project.lib")
_metric_watch = importlib.import_module("skills.metric-watch.lib")

REPO_ROOT = Path(__file__).resolve().parents[2]
VERSION_COMPARE_SH = REPO_ROOT / "skills" / "update" / "scripts" / "version-compare.sh"

_WAKEUP_DIR = REPO_ROOT / "hooks" / "wake-up"
if str(_WAKEUP_DIR) not in sys.path:
    sys.path.insert(0, str(_WAKEUP_DIR))
import wakeup  # noqa: E402


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in (
        "REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT",
        "CLAUDE_PLUGIN_OPTION_DEVROOT", "CLAUDE_SESSION_ID",
    ):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def sandbox(clean_path_env, tmp_path):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path / "framework"))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _snapshot(root: Path) -> set[str]:
    if not root.is_dir():
        return set()
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}


def test_friend_week_end_to_end(sandbox, tmp_path):
    wiki = sandbox

    # A separate "outside the wiki" area — a fake repo the friend is working
    # in, plus a Dev root for wake-up's cwd-based project detection. Nothing
    # in this whole story should ever write here except the repo fixture
    # itself (read-only scanning).
    dev_root = tmp_path / "Dev"
    dev_root.mkdir()
    repo_dir = dev_root / "falcon"
    repo_dir.mkdir()

    # =========================================================================
    # DAY 0 — install
    # =========================================================================
    session0 = "sess-day0"

    stamp_result = stamp_wiki()
    assert "identity.md" in stamp_result.written
    assert "index.md" in stamp_result.written

    # Partial interview: 2 of 10 questions answered, the rest skipped.
    partial_answers = {"name": "Hazar", "handle": "hazar"}
    identity_entry = save_identity(partial_answers, session=session0)
    queue.approve(identity_entry.qid, approved_by="hazar")
    queue.apply(identity_entry.qid)

    record_install("0.2.0")

    state = install_state(wiki)
    assert state["wiki_stamped"] is True
    assert state["identity_present"] is True
    assert state["backup_configured"] is False  # never configured — expected
    assert state["l2_maps"] >= 1  # index.md itself is type: l2-map
    assert state["installed_version"] == "0.2.0"

    # --- DAY 0 continued: first project ---
    (repo_dir / "pyproject.toml").write_text(
        '[project]\nname = "falcon"\ndependencies = ["fastapi"]\n', encoding="utf-8"
    )
    (repo_dir / "main.py").write_text("def main():\n    pass\n", encoding="utf-8")
    (repo_dir / "utils.py").write_text("def helper():\n    return 1\n", encoding="utf-8")

    outside_before = _snapshot(dev_root)  # snapshot AFTER the fixture repo exists

    scan_facts = _ingest_lib.scan_repo(repo_dir)
    assert isinstance(scan_facts, dict)  # read-only, tolerant — never raises

    knowledge = ["Falcon is a Python project using FastAPI."]
    pointers = [
        {"topic": "framework choice", "path": "projects/falcon/map.md",
         "anchor": "framework", "write_id": None},
    ]
    ingest_result = _ingest_lib.ingest("falcon", knowledge, pointers, session0)
    assert _ingest_lib.FIRST_SESSION_LEAD in ingest_result["artifact"]
    assert "Falcon is a Python project using FastAPI." in ingest_result["artifact"]

    queue.approve(ingest_result["qid"], approved_by="hazar")
    queue.apply(ingest_result["qid"])

    remembered = remember("falcon")
    assert "Here's what I remember about falcon:" in remembered
    assert "Falcon is a Python project using FastAPI." in remembered
    assert "⚠" in remembered  # ingest is llm-auto -> quarantined, must say so

    # =========================================================================
    # DAY 1 — work
    # =========================================================================
    session1 = "sess-day1"

    pin_entry = pin("Always use uv, never pip.", "projects/falcon/preferences.md", session1)
    queue.approve(pin_entry.qid, approved_by="hazar")
    queue.apply(pin_entry.qid)

    l3_before = collect.read(kind=collect.KIND_L3_FETCH)
    recall_results = recall_fetch("FastAPI", session1, k=3)
    l3_after = collect.read(kind=collect.KIND_L3_FETCH)
    assert len(l3_after) > len(l3_before)
    assert any("falcon" in r["page"] for r in recall_results)

    wakeup_surface_before = collect.read(kind=collect.KIND_WAKEUP_SURFACE)
    injected_bytes_before = collect.read(kind=collect.KIND_INJECTED_BYTES)

    context_text = wakeup.compose_wake_up_context(
        cwd=repo_dir, wiki_root=wiki, source="startup", session=session1, dev_root=dev_root,
    )
    assert "falcon" in context_text.lower()
    assert "uv" in context_text  # the salient pin surfaced via the salience boost

    wakeup_surface_after = collect.read(kind=collect.KIND_WAKEUP_SURFACE)
    injected_bytes_after = collect.read(kind=collect.KIND_INJECTED_BYTES)
    assert len(wakeup_surface_after) > len(wakeup_surface_before)
    assert len(injected_bytes_after) > len(injected_bytes_before)

    # =========================================================================
    # DAY 2 — wrap
    # =========================================================================
    session2 = "sess-day2"

    durable_item = "We decided to standardize on FastAPI for all new Python services."
    session_only_item = "Ran the tests again, all green."

    def llm_call(prompt: str) -> str:
        if durable_item in prompt:
            return json.dumps({"verdict": "durable", "reason": "genuine cross-session decision"})
        # Simulate a transient LLM hiccup on the second item — exercises the
        # classifier's real fail-closed path (gate() falls back to the
        # deterministic classifier, which never returns "durable") rather
        # than only ever exercising the clean-success path.
        raise RuntimeError("simulated transient LLM error")

    wrap_result = wrap_session(
        narrative_md="# Day 2 summary\n\nWorked on Falcon.\n",
        durable_items=[durable_item, session_only_item],
        session=session2,
        llm_call=llm_call,
    )
    assert len(wrap_result["durable_qids"]) == 1
    assert len(wrap_result["gated_out"]) == 1

    l1_entry = queue.get(wrap_result["l1_qid"])
    assert l1_entry.status == "applied"
    l1_page_text = (wiki / l1_entry.proposal.page).read_text(encoding="utf-8")
    assert quarantine.is_quarantined(l1_page_text) is True

    screen = render_wrap_screen(wrap_result, session2)
    assert "## What I learned" in screen
    assert "## Auto-saved (revertible)" in screen
    assert "## Needs your OK" in screen
    assert wrap_result["durable_qids"][0] in screen

    durable_qid = wrap_result["durable_qids"][0]
    confirmation = approve_and_apply(durable_qid, "hazar", session2)
    assert "Applied" in confirmation
    durable_write_id = confirmation.split("write_id=")[1].split(")")[0]

    # =========================================================================
    # DAY 3 — correction
    # =========================================================================
    session3 = "sess-day3"

    fact_page = "projects/falcon/facts.md"
    fact_entry = pin("The default port is 8080.", fact_page, session3)
    queue.approve(fact_entry.qid, approved_by="hazar")
    queue.apply(fact_entry.qid)

    correction_entry = correct(fact_page, "The default port is 9090.", session3)
    assert correction_entry.proposal.op == "UPDATE"
    queue.approve(correction_entry.qid, approved_by="hazar")
    queue.apply(correction_entry.qid)

    fact_journal = journal.entries(page=fact_page)
    supersede_entries = [e for e in fact_journal if e.get("op") == "UPDATE" and e.get("supersedes")]
    assert len(supersede_entries) >= 1

    fact_text = (wiki / fact_page).read_text(encoding="utf-8")
    assert "9090" in fact_text
    assert "8080" not in fact_text

    remembered_falcon_after_correction = remember("falcon")
    assert isinstance(remembered_falcon_after_correction, str)  # still renders cleanly

    # =========================================================================
    # DAY 4 — retrospective
    # =========================================================================
    session4 = "sess-day4"

    lesson_page = "projects/falcon/gotcha.md"
    seed_entry = pin("Watch out for timezone bugs.", lesson_page, session4)
    queue.approve(seed_entry.qid, approved_by="hazar")
    queue.apply(seed_entry.qid)

    for i in range(2):  # 2 corrections on ONE page -> crosses LESSON_MIN_CORRECTIONS (2)
        corr = correct(lesson_page, f"Watch out for timezone bugs (correction {i}).", session4)
        queue.approve(corr.qid, approved_by="hazar")
        queue.apply(corr.qid)

    gathered = gather()
    findings = analyze(gathered)
    lesson_findings = [f for f in findings if f["kind"] == "lesson"]
    assert any(f.get("page") == lesson_page for f in lesson_findings)

    proposed_entries = propose_all(findings, session4)
    assert proposed_entries
    assert all(e.status == "pending" for e in proposed_entries)
    assert all(e.proposal.writer == "retrospective" for e in proposed_entries)
    assert all(e.proposal.producer == "retrospective" for e in proposed_entries)

    # =========================================================================
    # DAY 5 — safety drill
    # =========================================================================
    session5 = "sess-day5"

    revert_confirmation = revert_write(durable_write_id)
    assert "Reverted" in revert_confirmation

    watch_findings = _metric_watch.watch(session5)
    backup_findings = [f for f in watch_findings if f.get("kind") == "backup-unconfigured"]
    assert backup_findings  # we never configured backup — the nag surface

    # =========================================================================
    # DAY 6 — update
    # =========================================================================
    version_compare = subprocess.run(
        ["bash", str(VERSION_COMPARE_SH), "0.2.0", "0.2.0"],
        capture_output=True, text=True, timeout=10,
    )
    assert version_compare.returncode == 0
    assert version_compare.stdout.strip() == "eq"

    state_after = install_state(wiki)
    assert state_after["wiki_stamped"] is True
    assert state_after["installed_version"] == "0.2.0"

    doctor_results = run_checks()
    error_results = [r for r in doctor_results if r.status == "error"]
    assert error_results == [], f"doctor found error-status checks: {error_results}"

    # =========================================================================
    # Final coherence assertions
    # =========================================================================
    all_journal_entries = journal.entries()
    write_ids = [e["write_id"] for e in all_journal_entries if e.get("write_id")]
    assert len(write_ids) == len(set(write_ids)), "every write_id must be unique"
    assert all(e.get("writer") for e in all_journal_entries), "every journal entry needs a writer class"

    revert_of_entries = [e for e in all_journal_entries if e.get("revert_of")]
    assert len(revert_of_entries) == 1, "exactly one revert happened this story"

    outside_after = _snapshot(dev_root)
    assert outside_after == outside_before, "nothing was ever written outside the fake repo"

    exercised_kinds = {
        collect.KIND_L3_FETCH, collect.KIND_WAKEUP_SURFACE,
        collect.KIND_INJECTED_BYTES, collect.KIND_CLASSIFIER_EVENT,
    }
    seen_kinds = {e.get("kind") for e in collect.read()}
    assert exercised_kinds <= seen_kinds, f"missing metric kinds: {exercised_kinds - seen_kinds}"
