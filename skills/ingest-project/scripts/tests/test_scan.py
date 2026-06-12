"""Hermetic tests for skills/ingest-project/scripts/scan.py.

Every test builds a throwaway project tree under tmp_path, runs the read-only
scanner against it, and asserts on the parsed facts JSON. The load-bearing
invariant (Task 7): the scanner mutates NOTHING in the project.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import scan  # noqa: E402


def run_scan(path: Path) -> dict:
    """Call scan.scan() and return the parsed facts dict."""
    return scan.scan(str(path))


def test_empty_dir_is_not_a_project(tmp_path):
    facts = run_scan(tmp_path)
    assert facts["schema_version"] == 1
    assert facts["scanned_path"] == str(tmp_path)
    assert facts["looks_like_project"] is False
    assert "framework_version" in facts


# ---------------------------------------------------------------------------
# Task 2: File enumeration helpers
# ---------------------------------------------------------------------------

def _git_init(root: Path) -> None:
    """Init a git repo with a deterministic identity (read-only-safe for tests)."""
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e",
    }
    subprocess.run(["git", "init", "-q"], cwd=root, env=env, check=True)


def _git_commit_all(root: Path, message: str, when: str | None = None) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e",
    }
    if when:
        env["GIT_AUTHOR_DATE"] = when
        env["GIT_COMMITTER_DATE"] = when
    subprocess.run(["git", "add", "-A"], cwd=root, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=root, env=env, check=True)


def test_enumeration_skips_secrets_and_vendor_dirs(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hi')\n")
    (tmp_path / ".env").write_text("API_KEY=FAKE_SECRET_VALUE_123\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.js").write_text("x" * 100)
    files = scan.enumerate_files(tmp_path)
    rels = {str(p.relative_to(tmp_path)) for p in files}
    assert "src/main.py" in rels
    assert ".env" not in rels                       # never-read glob
    assert not any(r.startswith("node_modules/") for r in rels)  # skip-dir


def test_git_repo_enumeration_respects_gitignore(tmp_path):
    (tmp_path / "keep.py").write_text("print(1)\n")
    (tmp_path / "secret.log").write_text("nope\n")
    (tmp_path / ".gitignore").write_text("*.log\n")
    _git_init(tmp_path)
    _git_commit_all(tmp_path, "init")
    files = scan.enumerate_files(tmp_path)
    rels = {str(p.relative_to(tmp_path)) for p in files}
    assert "keep.py" in rels
    assert "secret.log" not in rels                 # gitignored → not tracked


def test_large_files_excluded(tmp_path):
    (tmp_path / "big.bin").write_bytes(b"0" * (scan.MAX_READ_BYTES + 1))
    (tmp_path / "small.py").write_text("ok\n")
    files = scan.enumerate_files(tmp_path)
    rels = {str(p.relative_to(tmp_path)) for p in files}
    assert "small.py" in rels
    assert "big.bin" not in rels


def test_zero_commit_repo_falls_back_to_walk(tmp_path):
    (tmp_path / "a.py").write_text("print(1)\n")
    _git_init(tmp_path)                 # init, do NOT commit
    rels = {str(p.relative_to(tmp_path)) for p in scan.enumerate_files(tmp_path)}
    assert "a.py" in rels              # uncommitted file still found via walk fallback
