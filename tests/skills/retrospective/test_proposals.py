"""
Tests for skills.retrospective.lib — the G21 retrospective engine + D-2
skill-candidate mining (Task 8.3a).

Each analyze() rule gets a firing test (on a synthetic fixture) and a quiet
test; thresholds are checked at the boundary (N-1 sessions doesn't fire, N
does). propose_all queues pending entries with retrospective producer+writer;
an end-to-end test proves a proposed lesson approve→apply lands with
retrospective provenance.

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos or ~/.claude.

Run with: uv run pytest tests/skills/retrospective/test_proposals.py -v
"""

from __future__ import annotations

import importlib
import json

import pytest

from lib.instrument import collect
from lib.memory import journal, queue
from lib.memory.provenance import new_provenance
from lib.ren_paths import wiki_root

retro = importlib.import_module("skills.retrospective.lib")


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in (
        "REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT",
        "CLAUDE_PLUGIN_DATA", "CLAUDE_SESSION_ID", "CLAUDE_CONFIG_DIR",
    ):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def wiki(clean_path_env, tmp_path):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _journal_update_with_supersedes(page: str, supersedes: str = "w-old"):
    prov = new_provenance(writer="human", session="s", op="UPDATE", page=page, supersedes=supersedes)
    journal.append(prov)


# --------------------------------------------------------------------- lesson


def test_lesson_fires_at_threshold(wiki):
    _journal_update_with_supersedes("projects/x/notes.md", "w-1")
    _journal_update_with_supersedes("projects/x/notes.md", "w-2")

    gathered = retro.gather()
    findings = retro.analyze(gathered)

    lesson = next((f for f in findings if f["kind"] == "lesson"), None)
    assert lesson is not None
    assert lesson["page"] == "projects/x/notes.md"
    assert lesson["count"] == 2


def test_lesson_quiet_below_threshold(wiki):
    _journal_update_with_supersedes("projects/x/notes.md", "w-1")

    gathered = retro.gather()
    findings = retro.analyze(gathered)

    assert not any(f["kind"] == "lesson" for f in findings)


def test_lesson_ignores_updates_without_supersedes(wiki):
    prov = new_provenance(writer="human", session="s", op="UPDATE", page="x.md", supersedes=None)
    journal.append(prov)
    prov2 = new_provenance(writer="human", session="s", op="UPDATE", page="x.md", supersedes=None)
    journal.append(prov2)

    gathered = retro.gather()
    findings = retro.analyze(gathered)
    assert not any(f["kind"] == "lesson" for f in findings)


# ------------------------------------------------------------- instruction-tweak


def test_instruction_tweak_fires_at_threshold(wiki):
    for _ in range(3):
        collect.record(collect.KIND_CLASSIFIER_EVENT, {"event": "fail_closed", "reason": "x"})

    gathered = retro.gather()
    findings = retro.analyze(gathered)

    tweak = next((f for f in findings if f["kind"] == "instruction-tweak"), None)
    assert tweak is not None
    assert tweak["count"] == 3


def test_instruction_tweak_quiet_below_threshold(wiki):
    for _ in range(2):
        collect.record(collect.KIND_CLASSIFIER_EVENT, {"event": "fail_closed", "reason": "x"})

    gathered = retro.gather()
    findings = retro.analyze(gathered)
    assert not any(f["kind"] == "instruction-tweak" for f in findings)


def test_instruction_tweak_ignores_no_llm_events(wiki):
    for _ in range(5):
        collect.record(collect.KIND_CLASSIFIER_EVENT, {"event": "no_llm"})

    gathered = retro.gather()
    findings = retro.analyze(gathered)
    assert not any(f["kind"] == "instruction-tweak" for f in findings)


# --------------------------------------------------------------- skill-candidate


def _fixture_transcript(claude_dir, cwd, session_id, user_texts):
    encoded = cwd.replace("/", "-")
    project_dir = claude_dir / "projects" / encoded
    project_dir.mkdir(parents=True, exist_ok=True)
    path = project_dir / f"{session_id}.jsonl"
    lines = []
    for text in user_texts:
        lines.append(json.dumps({"type": "user", "message": {"role": "user", "content": text}}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_skill_candidate_fires_at_three_sessions(wiki, tmp_path):
    claude_dir = tmp_path / "claude-home"
    cwd = "/home/tester/Dev/widget"
    for i in range(3):
        _fixture_transcript(claude_dir, cwd, f"session-{i}", ["deploy staging environment please"])

    gathered = retro.gather(claude_dir=claude_dir, cwd=cwd)
    findings = retro.analyze(gathered)

    candidate = next((f for f in findings if f["kind"] == "skill-candidate"), None)
    assert candidate is not None
    assert candidate["frequency"] == 3
    assert candidate["task"] == "deploy-staging-environment"


def test_skill_candidate_quiet_at_two_sessions(wiki, tmp_path):
    claude_dir = tmp_path / "claude-home"
    cwd = "/home/tester/Dev/widget"
    for i in range(2):
        _fixture_transcript(claude_dir, cwd, f"session-{i}", ["deploy staging environment please"])

    gathered = retro.gather(claude_dir=claude_dir, cwd=cwd)
    findings = retro.analyze(gathered)
    assert not any(f["kind"] == "skill-candidate" for f in findings)


def test_skill_candidate_no_transcripts_returns_empty_sessions(wiki, tmp_path):
    claude_dir = tmp_path / "claude-home-empty"
    gathered = retro.gather(claude_dir=claude_dir, cwd="/no/such/project")
    assert gathered["sessions"] == []
    findings = retro.analyze(gathered)
    assert not any(f["kind"] == "skill-candidate" for f in findings)


# ----------------------------------------------------------------- propose_all


def test_propose_all_queues_pending_entries_with_retrospective_provenance(wiki):
    findings = [
        {"kind": "lesson", "page": "projects/x/notes.md", "count": 2, "message": "m"},
        {"kind": "instruction-tweak", "count": 3, "message": "m"},
    ]
    entries = retro.propose_all(findings, session="sess-1")

    assert len(entries) == 2
    for entry in entries:
        assert entry.status == "pending"
        assert entry.proposal.producer == "retrospective"
        assert entry.proposal.writer == "retrospective"
        assert entry.proposal.page.startswith("retrospective/")


def test_propose_all_nothing_auto_applies(wiki):
    findings = [{"kind": "instruction-tweak", "count": 5, "message": "m"}]
    entries = retro.propose_all(findings, session="sess-1")

    reloaded = queue.get(entries[0].qid)
    assert reloaded.status == "pending"
    page_abs = wiki / reloaded.proposal.page
    assert not page_abs.exists()


def test_proposed_lesson_approve_apply_lands_with_retrospective_provenance(wiki):
    findings = [{"kind": "lesson", "page": "projects/x/notes.md", "count": 2, "message": "capture the truth"}]
    entries = retro.propose_all(findings, session="sess-1")
    entry = entries[0]

    queue.approve(entry.qid, approved_by="hazar")
    prov = queue.apply(entry.qid)

    assert prov.writer == "retrospective"

    page_abs = wiki / entry.proposal.page
    assert page_abs.exists()
    text = page_abs.read_text(encoding="utf-8")
    assert "retrospective-finding" in text
    assert "capture the truth" in text

    journal_entries = journal.entries(page=entry.proposal.page)
    assert len(journal_entries) == 1
    assert journal_entries[0]["writer"] == "retrospective"

# ------------------------------------------- skill-candidate scaffold (item 5)


def test_skill_candidate_includes_executable_scaffold(wiki, tmp_path):
    """Finalize-v0.2 agenda item 5: a skill-candidate proposes an executable
    script scaffold, not just an idea."""
    claude_dir = tmp_path / "claude-home"
    cwd = "/home/tester/Dev/widget"
    for i in range(3):
        _fixture_transcript(claude_dir, cwd, f"session-{i}", ["deploy staging environment please"])

    gathered = retro.gather(claude_dir=claude_dir, cwd=cwd)
    findings = retro.analyze(gathered)

    candidate = next(f for f in findings if f["kind"] == "skill-candidate")
    scaffold = candidate["proposed_scaffold"]
    assert "skills/deploy-staging-environment/SKILL.md" in scaffold
    assert "skills/deploy-staging-environment/lib/run.py" in scaffold
    assert "def run(" in scaffold


def test_render_finding_puts_scaffold_in_code_block(wiki, tmp_path):
    claude_dir = tmp_path / "claude-home"
    cwd = "/home/tester/Dev/widget"
    for i in range(3):
        _fixture_transcript(claude_dir, cwd, f"session-{i}", ["deploy staging environment please"])

    findings = retro.analyze(retro.gather(claude_dir=claude_dir, cwd=cwd))
    candidate = next(f for f in findings if f["kind"] == "skill-candidate")

    rendered = retro._render_finding(candidate)
    assert "```" in rendered
    assert "def run(" in rendered
    # scaffold must not leak into the bullet list as a one-line value
    assert "- **proposed_scaffold**" not in rendered
