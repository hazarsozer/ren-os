"""
Tests for #63: applying a `projects/<slug>/instructions.md` write through
the queue best-effort re-renders the mapped repo's `CLAUDE.md` managed
block (Task 7's `lib.adapter.claude_md.write_project_claude_md`).

Reuses the queue tests' `state_dir`/`wiki_root` isolation fixture pattern
(REN_FRAMEWORK_ROOT redirected to tmp_path — never the real ~/.renos) and
registers a tmp repo dir via `lib.ren_paths.record_project_repo`.

Run with: uv run pytest tests/lib/memory/test_instructions_rerender.py -v
"""

from __future__ import annotations

import pytest

from lib import ren_paths
from lib.adapter import claude_md
from lib.memory.queue import Proposal, approve_and_apply, propose
from lib.memory.revert import revert
from lib.ren_paths import wiki_root


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


def _instructions_proposal(**overrides):
    defaults = dict(
        op="ADD",
        page="projects/flux/instructions.md",
        content="Always run tests before committing.",
        reason="testing",
        producer="promotion",
        writer="human",
        session="sess-1",
    )
    defaults.update(overrides)
    return Proposal(**defaults)


def test_applying_instructions_write_rerenders_repo_claude_md(wiki, tmp_repo):
    ren_paths.record_project_repo("flux", tmp_repo)

    entry = propose(_instructions_proposal())
    approve_and_apply(entry.qid, who="hazar")

    rendered = (tmp_repo / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Always run tests before committing." in rendered
    assert "<!-- ren:begin -->" in rendered
    assert "<!-- ren:end -->" in rendered


def test_unmapped_project_applies_without_error(wiki):
    entry = propose(_instructions_proposal(page="projects/unmapped/instructions.md"))
    prov = approve_and_apply(entry.qid, who="hazar")

    assert prov.write_id
    assert (wiki / "projects" / "unmapped" / "instructions.md").exists()


def test_render_failure_never_fails_the_write(wiki, tmp_repo, monkeypatch):
    ren_paths.record_project_repo("flux", tmp_repo)

    from lib.adapter import claude_md

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(claude_md, "write_project_claude_md", _boom)

    entry = propose(_instructions_proposal())
    prov = approve_and_apply(entry.qid, who="hazar")

    assert prov.write_id
    assert (wiki / "projects" / "flux" / "instructions.md").read_text(encoding="utf-8")


def test_revert_of_instructions_write_rerenders(wiki, tmp_repo):
    ren_paths.record_project_repo("flux", tmp_repo)

    first = propose(_instructions_proposal())
    approve_and_apply(first.qid, who="hazar")

    second = propose(
        _instructions_proposal(op="UPDATE", content="Always write tests first.")
    )
    second_prov = approve_and_apply(second.qid, who="hazar")

    rendered_after_update = (tmp_repo / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Always write tests first." in rendered_after_update

    revert(second_prov.write_id)

    rendered_after_revert = (tmp_repo / "CLAUDE.md").read_text(encoding="utf-8")
    expected = claude_md.render_project_block("flux", wiki_root=wiki)
    assert claude_md.spliced_text(rendered_after_revert, expected) == rendered_after_revert
    assert "Always run tests before committing." in rendered_after_revert
    assert "Always write tests first." not in rendered_after_revert


def test_update_rerender_all_refreshes_stale_block(wiki, tmp_repo):
    from skills.update.lib import rerender_all_project_claude_md

    ren_paths.record_project_repo("flux", tmp_repo)

    entry = propose(_instructions_proposal())
    approve_and_apply(entry.qid, who="hazar")

    (tmp_repo / "CLAUDE.md").write_text(
        f"{claude_md.MARKER_BEGIN}\nSTALE CONTENT\n{claude_md.MARKER_END}\n",
        encoding="utf-8",
    )

    result = rerender_all_project_claude_md()

    assert result == {"flux": "ok"}
    rendered = (tmp_repo / "CLAUDE.md").read_text(encoding="utf-8")
    expected = claude_md.render_project_block("flux", wiki_root=wiki)
    assert claude_md.spliced_text(rendered, expected) == rendered
    assert "STALE CONTENT" not in rendered


def test_rerender_all_never_raises_on_broken_repo(wiki, tmp_path):
    from skills.update.lib import rerender_all_project_claude_md

    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    broken_repo = blocker / "sub"
    ren_paths.record_project_repo("flux", broken_repo)

    entry = propose(_instructions_proposal())
    approve_and_apply(entry.qid, who="hazar")

    result = rerender_all_project_claude_md()

    assert set(result.keys()) == {"flux"}
    assert result["flux"].startswith("error:")
