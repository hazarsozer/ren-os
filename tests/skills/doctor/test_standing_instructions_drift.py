"""
Tests for #63's doctor check: `check_standing_instructions_drift`.

For every registered project with an `instructions.md` in the wiki, the
mapped repo's `CLAUDE.md` managed block must match a fresh render — a
mismatch means a stale splice (re-render never fired), a hand-edit inside
the markers, or a missing CLAUDE.md.

Reuses `test_doctor.py`'s isolation fixtures (`clean_path_env`/`wiki`).

Run with: uv run pytest tests/skills/doctor/test_standing_instructions_drift.py -v
"""

from __future__ import annotations

import importlib

import pytest

from lib import ren_paths
from lib.adapter import claude_md
from lib.ren_paths import wiki_root

doctor = importlib.import_module("skills.doctor.lib")


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in (
        "REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT",
        "CLAUDE_PLUGIN_DATA", "CLAUDE_SESSION_ID",
    ):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def wiki(clean_path_env, tmp_path):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    clean_path_env.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "plugin-data"))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_instructions(wiki, slug, body="- Never force-push to main.\n"):
    page_dir = wiki / "projects" / slug
    page_dir.mkdir(parents=True, exist_ok=True)
    (page_dir / "instructions.md").write_text(
        "---\ntype: project-instructions\nschema_version: 1\n"
        f"project: {slug}\ntitle: \"Standing Instructions\"\n---\n\n"
        f"# Standing instructions — {slug}\n\n## Rules\n\n{body}",
        encoding="utf-8",
    )


def test_skip_when_no_project_has_instructions(wiki):
    res = doctor.check_standing_instructions_drift()
    assert res.status == "skip"


def test_ok_when_block_matches(wiki, tmp_path):
    repo = tmp_path / "flux-repo"
    repo.mkdir()
    ren_paths.record_project_repo("flux", repo)
    _write_instructions(wiki, "flux")

    claude_md.write_project_claude_md(repo, "flux", wiki_root=wiki)

    res = doctor.check_standing_instructions_drift()
    assert res.status == "ok"
    assert "1" in res.message


def test_warn_on_stale_splice(wiki, tmp_path):
    repo = tmp_path / "flux-repo"
    repo.mkdir()
    ren_paths.record_project_repo("flux", repo)
    _write_instructions(wiki, "flux")

    claude_md.write_project_claude_md(repo, "flux", wiki_root=wiki)

    # Change the wiki page body WITHOUT re-rendering the repo's CLAUDE.md.
    _write_instructions(wiki, "flux", body="- Never force-push to main.\n- New rule added later.\n")

    res = doctor.check_standing_instructions_drift()
    assert res.status == "warn"
    assert "flux" in res.message


def test_warn_when_repo_claude_md_missing(wiki, tmp_path):
    repo = tmp_path / "flux-repo"
    repo.mkdir()
    ren_paths.record_project_repo("flux", repo)
    _write_instructions(wiki, "flux")

    res = doctor.check_standing_instructions_drift()
    assert res.status == "warn"
    assert "flux" in res.message
