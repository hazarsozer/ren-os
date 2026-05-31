"""
Shared pytest fixtures for sf-improve-skill tests.

The git_mechanics tests need a real git repo per test. This conftest provides
the `tmp_git_repo` fixture that initializes a clean repo with one commit,
then yields the path. Tests run their git operations against this repo.

Per dotfiles python/testing.md (pytest).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Generator

import pytest


@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> Generator[Path, None, None]:
    """
    Init a fresh git repo at tmp_path with one initial commit on `main`.

    Layout:
        tmp_path/
          .git/...
          skills/
            sample-skill/
              SKILL.md         (touched, committed)
              eval/eval.json

    Tests can `cwd=path` against this fixture and exercise real git operations
    in isolation — no shared state across tests, no risk of touching the
    framework's actual git history.

    Yields:
        Path to the repo root.
    """
    # Initialize repo on `main` (override default branch name for predictability)
    subprocess.run(
        ["git", "init", "--initial-branch=main"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=tmp_path, check=True)

    # Layout: minimal sample skill
    skill_dir = tmp_path / "skills" / "sample-skill"
    eval_dir = skill_dir / "eval"
    eval_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: sample-skill\n---\n# sample\n", encoding="utf-8")
    (eval_dir / "eval.json").write_text(
        '{"name":"sample-skill","tests":[{"id":"t1","binary_assertions":["x"]}]}',
        encoding="utf-8",
    )

    # Initial commit
    subprocess.run(["git", "add", "skills/"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    yield tmp_path
