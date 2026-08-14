"""#63 end-to-end: promote -> human approve -> repo CLAUDE.md carries the rule.

Reuses the queue/registry fixture pattern from Task 8's
`tests/lib/memory/test_instructions_rerender.py` (REN_FRAMEWORK_ROOT
redirected to tmp_path — never the real ~/.renos).

Run with: uv run pytest tests/integration/test_standing_instructions_e2e.py -v
"""

from __future__ import annotations

import importlib

import pytest

from lib import ren_paths
from lib.adapter import claude_md
from lib.memory import promotion, queue
from lib.ren_paths import wiki_root

doctor = importlib.import_module("skills.doctor.lib")


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


@pytest.fixture
def tmp_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo


def test_pin_to_claude_md_round_trip(wiki, tmp_repo):
    ren_paths.record_project_repo("flux", tmp_repo)

    entry = promotion.promote_to_project("Never force-push to main.", "flux", "s-e2e")
    assert entry.status == "pending"

    queue.approve_and_apply(entry.qid, who="human:pin")

    text = (tmp_repo / "CLAUDE.md").read_text(encoding="utf-8")
    assert "- Never force-push to main." in text
    assert text.count(claude_md.MARKER_BEGIN) == 1

    assert doctor.check_standing_instructions_drift().status == "ok"
