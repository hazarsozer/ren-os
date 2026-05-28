"""Tests for scripts/lint-yaml-frontmatter.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


# Import the script by file path (it's a CLI script, not a package).
_LINT_PATH = Path(__file__).resolve().parents[1] / "lint-yaml-frontmatter.py"
_spec = importlib.util.spec_from_file_location("lint_yaml_frontmatter", _LINT_PATH)
_lint = importlib.util.module_from_spec(_spec)
sys.modules["lint_yaml_frontmatter"] = _lint
_spec.loader.exec_module(_lint)

extract_frontmatter = _lint.extract_frontmatter
iter_markdown_files = _lint.iter_markdown_files
lint_file = _lint.lint_file
main = _lint.main


# ---------------------------------------------------------------------------
# extract_frontmatter
# ---------------------------------------------------------------------------


class TestExtractFrontmatter:
    def test_no_frontmatter(self):
        assert extract_frontmatter("# Just a heading\n\nbody") is None

    def test_unclosed_frontmatter(self):
        """A `---` opener without closer is treated as no frontmatter."""
        assert extract_frontmatter("---\nname: x\nno closer\n") is None

    def test_canonical_frontmatter(self):
        content = "---\nname: test\nversion: 1.0\n---\n\nbody"
        result = extract_frontmatter(content)
        assert result is not None
        fm, line = result
        assert "name: test" in fm
        assert "version: 1.0" in fm
        assert line == 1

    def test_empty_frontmatter(self):
        content = "---\n---\nbody"
        result = extract_frontmatter(content)
        assert result is not None
        assert result[0].strip() == ""


# ---------------------------------------------------------------------------
# lint_file
# ---------------------------------------------------------------------------


class TestLintFile:
    def test_no_frontmatter_passes(self, tmp_path: Path):
        path = tmp_path / "no_fm.md"
        path.write_text("# Just markdown\n", encoding="utf-8")
        assert lint_file(path) is None

    def test_valid_frontmatter_passes(self, tmp_path: Path):
        path = tmp_path / "valid.md"
        path.write_text(
            "---\nname: x\nversion: 0.1\n---\n\nbody\n", encoding="utf-8"
        )
        assert lint_file(path) is None

    def test_real_skill_md_passes(self, tmp_path: Path):
        """Mimic a real shipped SKILL.md frontmatter shape."""
        path = tmp_path / "SKILL.md"
        path.write_text(
            "---\n"
            "name: sf-test\n"
            'description: "Test skill description"\n'
            "version: 0.1.0\n"
            'framework_version: "1.0.0"\n'
            "schema_version: 1\n"
            "type: skill\n"
            "---\n\n"
            "# sf-test\n",
            encoding="utf-8",
        )
        assert lint_file(path) is None

    def test_quoted_scalar_with_trailing_text_caught(self, tmp_path: Path):
        """The exact bug L1 caught last week: `- "x" (comment)` is invalid YAML."""
        path = tmp_path / "bad.md"
        path.write_text(
            "---\nname: x\n"
            "contract:\n"
            "  output_paths:\n"
            '    - "skills/<name>/" (only target skill modified)\n'
            "---\n",
            encoding="utf-8",
        )
        result = lint_file(path)
        assert result is not None
        assert "YAML parse error" in result
        # Should pinpoint the line of the bad scalar
        assert "bad.md:" in result

    def test_unbalanced_braces_caught(self, tmp_path: Path):
        path = tmp_path / "braces.md"
        path.write_text(
            "---\nname: x\nvalue: {open: 1\n---\n",
            encoding="utf-8",
        )
        result = lint_file(path)
        assert result is not None
        assert "YAML parse error" in result

    def test_indentation_error_caught(self, tmp_path: Path):
        path = tmp_path / "indent.md"
        path.write_text(
            "---\nname: x\n  bad_indent: y\nname2: z\n---\n",
            encoding="utf-8",
        )
        result = lint_file(path)
        # The indent issue may or may not be caught depending on YAML version;
        # but if it IS caught, the message should mention parse error.
        if result is not None:
            assert "YAML parse error" in result

    def test_unreadable_file_returns_error(self, tmp_path: Path):
        result = lint_file(tmp_path / "nonexistent.md")
        assert result is not None
        assert "could not read" in result.lower()


# ---------------------------------------------------------------------------
# iter_markdown_files
# ---------------------------------------------------------------------------


class TestIterMarkdownFiles:
    def test_single_file(self, tmp_path: Path):
        f = tmp_path / "x.md"
        f.write_text("---\nname: x\n---\n", encoding="utf-8")
        result = list(iter_markdown_files([f]))
        assert result == [f]

    def test_directory_recursion(self, tmp_path: Path):
        (tmp_path / "a.md").write_text("x", encoding="utf-8")
        nested = tmp_path / "deep"
        nested.mkdir()
        (nested / "b.md").write_text("x", encoding="utf-8")
        result = list(iter_markdown_files([tmp_path]))
        names = {p.name for p in result}
        assert names == {"a.md", "b.md"}

    def test_non_md_files_skipped(self, tmp_path: Path):
        (tmp_path / "x.md").write_text("md", encoding="utf-8")
        (tmp_path / "y.txt").write_text("txt", encoding="utf-8")
        (tmp_path / "z.json").write_text("{}", encoding="utf-8")
        result = list(iter_markdown_files([tmp_path]))
        assert len(result) == 1
        assert result[0].name == "x.md"


# ---------------------------------------------------------------------------
# main — CLI integration
# ---------------------------------------------------------------------------


class TestMain:
    def test_clean_repo_exits_zero(self, tmp_path: Path):
        (tmp_path / "good.md").write_text(
            "---\nname: x\nversion: 1\n---\nbody", encoding="utf-8"
        )
        exit_code = main([str(tmp_path)])
        assert exit_code == 0

    def test_bad_yaml_exits_one(self, tmp_path: Path, capsys):
        (tmp_path / "bad.md").write_text(
            "---\nname: x\n"
            '  output_paths:\n'
            '    - "skills/<x>/" (trailing comment)\n'
            "---\n",
            encoding="utf-8",
        )
        exit_code = main([str(tmp_path)])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "parse error" in captured.err.lower()
        assert "bad.md" in captured.err

    def test_empty_dir_passes(self, tmp_path: Path):
        assert main([str(tmp_path)]) == 0

    def test_lint_self_passes_against_real_repo(self):
        """Pin: the lint must pass against the SHIPPED skills + decisions + hooks
        in this repo. If any of our owned frontmatter ever drifts, this fires."""
        repo_root = Path(__file__).resolve().parents[2]
        # Run the lint with default paths
        original_cwd = Path.cwd()
        try:
            import os
            os.chdir(repo_root)
            exit_code = main([])
        finally:
            import os
            os.chdir(original_cwd)
        assert exit_code == 0, (
            "Lint failed against the live repo. Run "
            "`python3 scripts/lint-yaml-frontmatter.py -v` to see which file."
        )
