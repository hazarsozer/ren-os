"""
Tests for lib.doctrine.loader — G11 instruction activation model (Task 7.1).

Run with: uv run pytest tests/lib/doctrine/test_activation.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.doctrine.loader import DoctrineFile, active_for, load_all, pull

REPO_DOCTRINE_ROOT = Path(__file__).resolve().parents[3] / "doctrine"

SHIPPED_FILES = {
    "agent-orchestration": "always-on",
    "cadence-matrix": "agent-pulled",
    "conventions": "always-on",
    "companions": "agent-pulled",
}


def _write(root: Path, name: str, frontmatter_lines: str, body: str = "Body text.\n") -> Path:
    path = root / f"{name}.md"
    path.write_text(f"---\n{frontmatter_lines}---\n{body}", encoding="utf-8")
    return path


# --- load_all: shipped files -------------------------------------------------


def test_load_all_parses_all_four_shipped_files_with_correct_activation():
    docs = load_all(REPO_DOCTRINE_ROOT)
    by_stem = {d.path.stem: d for d in docs}

    assert set(SHIPPED_FILES) <= set(by_stem)
    for stem, expected_activation in SHIPPED_FILES.items():
        assert by_stem[stem].activation == expected_activation


def test_all_shipped_doctrine_files_pass_frontmatter_validation():
    """Meta-test: every *.md directly under doctrine/ must load successfully
    (no warnings-only skips) — a shipped file failing this means broken
    frontmatter shipped to friends."""
    docs = load_all(REPO_DOCTRINE_ROOT)
    shipped_md_files = sorted(p.stem for p in REPO_DOCTRINE_ROOT.glob("*.md"))
    loaded_stems = sorted(d.path.stem for d in docs)
    assert loaded_stems == shipped_md_files


def test_companions_contains_verbatim_governance_sentence():
    """Golden assertion — this exact sentence is load-bearing doctrine, not
    just documentation; it must never drift or get paraphrased away."""
    doc = pull("companions", REPO_DOCTRINE_ROOT)
    assert (
        "Browser control that can act on the logged-in web is destructive-tier "
        "under the risk model in docs/data-flow.md and §3.6 — it always asks, "
        "and it never runs unattended."
    ) in doc.body


# --- active_for: always-on / glob-scoped / agent-pulled ---------------------


def test_always_on_files_active_regardless_of_cwd_files(tmp_path):
    _write(tmp_path, "always", "type: doctrine\nactivation: always-on\nscope_glob: null\n")

    active_empty = active_for([], tmp_path)
    active_unrelated = active_for(["some/random/file.txt"], tmp_path)

    assert any(d.path.stem == "always" for d in active_empty)
    assert any(d.path.stem == "always" for d in active_unrelated)


def test_glob_scoped_file_active_only_when_matching_file_present(tmp_path):
    _write(
        tmp_path, "glob-only",
        "type: doctrine\nactivation: glob-scoped\nscope_glob: \"**/*.py\"\n",
    )

    not_matching = active_for(["README.md", "notes.txt"], tmp_path)
    matching = active_for(["src/module.py"], tmp_path)

    assert not any(d.path.stem == "glob-only" for d in not_matching)
    assert any(d.path.stem == "glob-only" for d in matching)


def test_agent_pulled_never_in_active_for_but_pull_returns_it(tmp_path):
    _write(tmp_path, "pulled-only", "type: doctrine\nactivation: agent-pulled\nscope_glob: null\n")

    active = active_for(["anything.py", "everything.md"], tmp_path)
    assert not any(d.path.stem == "pulled-only" for d in active)

    doc = pull("pulled-only", tmp_path)
    assert isinstance(doc, DoctrineFile)
    assert doc.activation == "agent-pulled"


def test_pull_unknown_name_raises_key_error(tmp_path):
    with pytest.raises(KeyError):
        pull("does-not-exist", tmp_path)


# --- malformed doctrine files: skip + warn, never raise ---------------------


def test_unknown_activation_value_skipped_others_still_load(tmp_path, capsys):
    _write(tmp_path, "bad", "type: doctrine\nactivation: sometimes\nscope_glob: null\n")
    _write(tmp_path, "good", "type: doctrine\nactivation: always-on\nscope_glob: null\n")

    docs = load_all(tmp_path)
    stems = {d.path.stem for d in docs}

    assert "good" in stems
    assert "bad" not in stems
    assert "WARNING" in capsys.readouterr().err


def test_glob_scoped_missing_scope_glob_skipped_with_warning(tmp_path, capsys):
    _write(tmp_path, "broken-glob", "type: doctrine\nactivation: glob-scoped\n")
    _write(tmp_path, "good", "type: doctrine\nactivation: always-on\nscope_glob: null\n")

    docs = load_all(tmp_path)
    stems = {d.path.stem for d in docs}

    assert "good" in stems
    assert "broken-glob" not in stems
    assert "WARNING" in capsys.readouterr().err


def test_file_with_no_frontmatter_skipped_with_warning(tmp_path, capsys):
    (tmp_path / "no-frontmatter.md").write_text("# Just a heading\n\nBody.\n", encoding="utf-8")
    _write(tmp_path, "good", "type: doctrine\nactivation: always-on\nscope_glob: null\n")

    docs = load_all(tmp_path)
    stems = {d.path.stem for d in docs}

    assert "good" in stems
    assert "no-frontmatter" not in stems
    assert "WARNING" in capsys.readouterr().err


def test_load_all_missing_directory_returns_empty_list(tmp_path):
    assert load_all(tmp_path / "does-not-exist") == []
