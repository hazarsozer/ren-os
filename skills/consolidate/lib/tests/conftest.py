"""
Shared fixtures for sf-consolidate tests.

`tmp_wiki_repo` gives a real git repo with a `wiki/` tree so diff-building and the
atomic-apply primitive can be exercised against actual `git apply` (the only
reliable check that generated diffs are well-formed).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Generator

import pytest


def _git(args: list[str], cwd: Path, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, input=stdin, capture_output=True, text=True, check=False
    )


@pytest.fixture
def tmp_wiki_repo(tmp_path: Path) -> Generator[Path, None, None]:
    """
    Init a git repo at tmp_path with a minimal wiki/ tree, one commit on `main`.

    Layout:
        tmp_path/                  (git root = cwd for git apply)
          wiki/
            patterns/index.md      (an existing curated page to append to)
            projects/dry/instincts.md  (a hot-tier file with entries)

    Yields the repo root (use as both `cwd` and parent of `wiki/`).
    """
    subprocess.run(["git", "init", "--initial-branch=main"], cwd=tmp_path, check=True, capture_output=True)
    _git(["config", "user.email", "test@example.com"], tmp_path)
    _git(["config", "user.name", "Test"], tmp_path)
    _git(["config", "commit.gpgsign", "false"], tmp_path)

    wiki = tmp_path / "wiki"
    (wiki / "patterns").mkdir(parents=True)
    (wiki / "projects" / "dry").mkdir(parents=True)
    (wiki / "patterns" / "index.md").write_text(
        "---\ntitle: Patterns\ntype: index\n---\n\n# Patterns\n\n- existing entry\n",
        encoding="utf-8",
    )
    (wiki / "projects" / "dry" / "instincts.md").write_text(
        "---\ntype: instincts\nschema_version: 1\nscope: project\n---\n\n"
        "# Instincts — dry\n\n"
        "- **[worked]** 2026-06-28 — run each tests dir as its own pytest call\n",
        encoding="utf-8",
    )

    _git(["add", "wiki/"], tmp_path)
    _git(["commit", "-m", "initial wiki"], tmp_path)
    yield tmp_path


@pytest.fixture
def tmp_link_repo(tmp_path: Path) -> Generator[Path, None, None]:
    """
    Init a git repo with a wiki/ tree containing DEAD links (for C3c link repair).

    Layout:
        wiki/patterns/schema-versioning.md   (target of a typo'd wikilink)
        wiki/patterns/read-before-edit.md    (target; also holds one dead wikilink)
        wiki/decisions/037.md                (two dead wikilinks on separate lines)

    The dead links are near-miss typos that fuzzy-match their targets:
      [[scheme-versioning]] → schema-versioning,  [[reed-before-edit]] → read-before-edit
    """
    subprocess.run(["git", "init", "--initial-branch=main"], cwd=tmp_path, check=True, capture_output=True)
    _git(["config", "user.email", "test@example.com"], tmp_path)
    _git(["config", "user.name", "Test"], tmp_path)
    _git(["config", "commit.gpgsign", "false"], tmp_path)

    wiki = tmp_path / "wiki"
    (wiki / "patterns").mkdir(parents=True)
    (wiki / "decisions").mkdir(parents=True)
    (wiki / "patterns" / "schema-versioning.md").write_text("# Schema Versioning\n\nbody\n", encoding="utf-8")
    (wiki / "patterns" / "read-before-edit.md").write_text(
        "# Read Before Edit\n\nsee [[scheme-versioning]] for the schema\n", encoding="utf-8"
    )
    (wiki / "decisions" / "037.md").write_text(
        "# 037\n\nsee [[scheme-versioning]] for schema\nand [[reed-before-edit]] for editing\n",
        encoding="utf-8",
    )

    _git(["add", "wiki/"], tmp_path)
    _git(["commit", "-m", "initial wiki with dead links"], tmp_path)
    yield tmp_path
