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


# ---------------------------------------------------------------------------
# Task 3: Stack detection
# ---------------------------------------------------------------------------

def test_stack_python_uv(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='x'\ndependencies=['fastapi']\n[tool.uv]\n"
    )
    (tmp_path / "uv.lock").write_text("# lock\n")
    st = scan.detect_stack(tmp_path, scan.enumerate_files(tmp_path))
    langs = {l["name"] for l in st["languages"]}
    assert "Python" in langs
    assert "uv" in st["package_managers"]
    assert "fastapi" in st["frameworks"]
    assert "pyproject.toml" in st["manifests"]


def test_stack_typescript_npm(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"name":"x","dependencies":{"next":"14","react":"18"}}'
    )
    (tmp_path / "package-lock.json").write_text("{}")
    (tmp_path / "tsconfig.json").write_text("{}")
    st = scan.detect_stack(tmp_path, scan.enumerate_files(tmp_path))
    langs = {l["name"] for l in st["languages"]}
    assert "TypeScript" in langs
    assert "npm" in st["package_managers"]
    assert "next" in st["frameworks"]
    assert "react" in st["frameworks"]


def test_stack_polyglot(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / "Cargo.toml").write_text("[package]\nname='y'\n")
    st = scan.detect_stack(tmp_path, scan.enumerate_files(tmp_path))
    langs = {l["name"] for l in st["languages"]}
    assert {"Python", "Rust"} <= langs


def test_stack_unknown_is_empty_not_error(tmp_path):
    (tmp_path / "notes.txt").write_text("hello\n")
    st = scan.detect_stack(tmp_path, scan.enumerate_files(tmp_path))
    assert st["languages"] == []
    assert st["package_managers"] == []


def test_stack_framework_hints_avoid_false_positives(tmp_path):
    # guardrails-ai must NOT trip "rails"; a "reactive" mention must NOT trip
    # "react"; next-auth must NOT trip "next" (anchored-hint regression guard).
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='x'\ndependencies=['guardrails-ai','reactivex']\n"
    )
    (tmp_path / "package.json").write_text(
        '{"name":"x","dependencies":{"next-auth":"4","torchlight":"1"}}'
    )
    st = scan.detect_stack(tmp_path, scan.enumerate_files(tmp_path))
    assert "rails" not in st["frameworks"]
    assert "react" not in st["frameworks"]
    assert "next" not in st["frameworks"]
    assert "pytorch" not in st["frameworks"]


# ---------------------------------------------------------------------------
# Task 4: Tree digest, entry points, doc inventory
# ---------------------------------------------------------------------------

def test_tree_digest_and_entry_points(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main():\n    pass\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_x():\n    pass\n")
    files = scan.enumerate_files(tmp_path)
    td = scan.build_tree_digest(tmp_path, files)
    assert "src" in td["top_dirs"]
    assert "tests" in td["top_dirs"]
    assert td["entry_count"] == len(files)
    eps = scan.detect_entry_points(tmp_path, files)
    assert "src/main.py" in eps


def test_doc_inventory_classifies(tmp_path):
    (tmp_path / "README.md").write_text("# Title\nbody\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "adr").mkdir()
    (tmp_path / "docs" / "adr" / "0001-foo.md").write_text("# ADR\n")
    files = scan.enumerate_files(tmp_path)
    inv = scan.build_doc_inventory(tmp_path, files)
    kinds = {d["kind"] for d in inv}
    paths = {d["path"] for d in inv}
    assert "readme" in kinds
    assert "README.md" in paths
    assert "adr" in kinds
    assert any(d["path"] == "README.md" and d["bytes"] > 0 for d in inv)
    assert inv == sorted(inv, key=lambda d: d["path"])


def test_tree_digest_truncated_by_depth(tmp_path):
    deep = tmp_path / "a" / "b" / "c" / "d"          # file 5 parts deep > TREE_DEPTH_CAP=4
    deep.mkdir(parents=True)
    (deep / "f.py").write_text("x")
    td = scan.build_tree_digest(tmp_path, scan.enumerate_files(tmp_path))
    assert td["truncated"] is True


def test_tree_digest_notable_files(tmp_path):
    (tmp_path / "README.md").write_text("hi")
    (tmp_path / "Makefile").write_text("all:")
    td = scan.build_tree_digest(tmp_path, scan.enumerate_files(tmp_path))
    assert "README.md" in td["notable_files"] and "Makefile" in td["notable_files"]
    assert td["truncated"] is False


def test_tree_digest_entry_cap_boundary(tmp_path):
    # synthetic file list (no real I/O) pins 500=not-truncated, 501=truncated
    files_500 = [tmp_path / f"f{i}.py" for i in range(500)]
    files_501 = [tmp_path / f"f{i}.py" for i in range(501)]
    assert scan.build_tree_digest(tmp_path, files_500)["truncated"] is False
    assert scan.build_tree_digest(tmp_path, files_501)["truncated"] is True


# ---------------------------------------------------------------------------
# Task 5: Git facts
# ---------------------------------------------------------------------------

def test_git_facts_non_repo(tmp_path):
    (tmp_path / "x.py").write_text("1\n")
    g = scan.collect_git_facts(tmp_path)
    assert g == {"is_repo": False}


def test_git_facts_repo_with_commits_and_tag(tmp_path):
    (tmp_path / "a.py").write_text("1\n")
    _git_init(tmp_path)
    _git_commit_all(tmp_path, "feat: first", when="2025-01-10T12:00:00")
    (tmp_path / "b.py").write_text("2\n")
    _git_commit_all(tmp_path, "feat: second", when="2025-03-15T12:00:00")
    subprocess.run(["git", "tag", "v1.0"], cwd=tmp_path, check=True)
    g = scan.collect_git_facts(tmp_path)
    assert g["is_repo"] is True
    assert g["commit_count"] == 2
    months = {b["month"] for b in g["timeline"]}
    assert "2025-01" in months and "2025-03" in months
    tag_names = {t["name"] for t in g["tags"]}
    assert "v1.0" in tag_names
    assert g["recent"]                       # at least one recent commit
    assert g["branch"]                        # some branch name
    assert g["dirty"] is False                # clean working tree after commit


def test_git_facts_zero_commit_repo(tmp_path):
    (tmp_path / "a.py").write_text("1\n")
    _git_init(tmp_path)                 # no commit
    g = scan.collect_git_facts(tmp_path)
    assert g["is_repo"] is True
    assert g["commit_count"] == 0
    assert g["no_commits"] is True
    assert g["dirty"] is False         # untracked-only is NOT "dirty" here


def test_git_facts_detached_head(tmp_path):
    (tmp_path / "a.py").write_text("1\n")
    _git_init(tmp_path); _git_commit_all(tmp_path, "first")
    (tmp_path / "b.py").write_text("2\n"); _git_commit_all(tmp_path, "second")
    first = subprocess.run(["git", "rev-parse", "HEAD~1"], cwd=tmp_path,
                           capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "checkout", first], cwd=tmp_path,
                   capture_output=True)   # detach
    g = scan.collect_git_facts(tmp_path)
    assert g["is_repo"] is True
    assert g["branch"] == ""              # detached HEAD -> no branch name


# ---------------------------------------------------------------------------
# Task 6: Full facts assembly (name candidates, size signals, looks_like_project)
# ---------------------------------------------------------------------------

def test_full_scan_python_project(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='my-app'\ndependencies=['flask']\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main():\n    pass\n")
    (tmp_path / "README.md").write_text("# My App\nDoes things.\n")
    _git_init(tmp_path)
    _git_commit_all(tmp_path, "init", when="2025-02-01T10:00:00")
    facts = scan.scan(str(tmp_path))
    assert facts["looks_like_project"] is True
    assert facts["name_candidates"]["chosen"] == "my-app"
    assert any(l["name"] == "Python" for l in facts["stack"]["languages"])
    assert "flask" in facts["stack"]["frameworks"]
    assert facts["git"]["is_repo"] is True
    assert facts["size_signals"]["file_count"] >= 3
    assert "src/main.py" in facts["entry_points"]


def test_name_falls_back_to_dir_when_no_manifest_name(tmp_path):
    proj = tmp_path / "cool-tool"
    proj.mkdir()
    (proj / "README.md").write_text("# Cool Tool\n")
    facts = scan.scan(str(proj))
    assert facts["looks_like_project"] is True   # README alone counts
    assert facts["name_candidates"]["chosen"] == "cool-tool"


def test_recommend_subagents_for_large_repo(tmp_path):
    facts_small = scan.scan(str(tmp_path))
    assert facts_small["looks_like_project"] is False
    # size_signals present even on empty dir
    assert facts_small["size_signals"]["recommend_subagents"] is False


def test_recommend_subagents_true_when_file_count_exceeds_threshold():
    fake_files = [Path(f"/fake/f{i}.py") for i in range(scan.SUBAGENT_FILE_THRESHOLD + 1)]
    signals = scan._build_size_signals(fake_files)
    assert signals["recommend_subagents"] is True
    assert signals["file_count"] == scan.SUBAGENT_FILE_THRESHOLD + 1


# ---------------------------------------------------------------------------
# Task 2 deferred: force-added tracked secret still excluded by enumerate_files
# ---------------------------------------------------------------------------

def test_never_read_blocks_force_added_tracked_secret(tmp_path):
    (tmp_path / ".env").write_text("SECRET=abc\n")
    (tmp_path / ".gitignore").write_text("")            # do NOT ignore it
    _git_init(tmp_path)
    _git_commit_all(tmp_path, "oops tracked .env")
    files = scan.enumerate_files(tmp_path)
    assert not any(p.name == ".env" for p in files)     # excluded even though tracked


# ---------------------------------------------------------------------------
# Task 7: Read-only invariant + secret-skip property tests (LOAD-BEARING)
# ---------------------------------------------------------------------------

def _snapshot(root: Path) -> dict[str, tuple[int, float, str]]:
    snap: dict[str, tuple[int, float, str]] = {}
    for p in sorted(root.rglob("*")):
        if ".git" not in p.parts and p.is_file():
            st = p.stat()
            data = p.read_bytes()
            snap[str(p.relative_to(root))] = (
                st.st_size, st.st_mtime, hashlib.sha256(data).hexdigest()
            )
    return snap


def test_scan_mutates_nothing_in_project(tmp_path):
    # Build a realistic repo, snapshot it, scan, snapshot again — byte-identical.
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main():\n    pass\n")
    (tmp_path / "README.md").write_text("# X\n")
    _git_init(tmp_path)
    _git_commit_all(tmp_path, "init", when="2025-02-01T10:00:00")
    before = _snapshot(tmp_path)
    scan.scan(str(tmp_path))
    after = _snapshot(tmp_path)
    assert before == after


def test_secret_values_never_appear_in_facts(tmp_path):
    secret = "FAKE_SECRET_sk_live_abc123XYZ"
    (tmp_path / ".env").write_text(f"API_KEY={secret}\n")
    (tmp_path / "config.pem").write_text(f"-----BEGIN KEY-----\n{secret}\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / "README.md").write_text("# X\n")
    facts = scan.scan(str(tmp_path))
    blob = json.dumps(facts)
    assert secret not in blob          # secret content never read → never emitted


def test_subprocess_scan_writes_nothing_and_emits_json(tmp_path):
    # Scan a real git repo via subprocess so the no-mutation check exercises the
    # git path (`git status`/`git ls-files` touch .git/index). `_snapshot` excludes
    # .git/, so git-index churn from those reads can't trip a false failure.
    (tmp_path / "main.py").write_text("print(1)\n")
    (tmp_path / "README.md").write_text("# demo\n")
    _git_init(tmp_path)
    _git_commit_all(tmp_path, "init")
    before = _snapshot(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "scan.py"), str(tmp_path)],
        capture_output=True, text=True, cwd=str(tmp_path),
    )
    after = _snapshot(tmp_path)
    assert proc.returncode == 0, proc.stderr
    parsed = json.loads(proc.stdout)   # stdout is valid JSON
    assert parsed["schema_version"] == 1
    assert before == after             # nothing created/modified/deleted
