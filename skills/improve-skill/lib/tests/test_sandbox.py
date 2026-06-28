from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from ..sandbox import eval_sandbox


def test_sandbox_redirects_and_restores():
    before = dict(os.environ)
    with eval_sandbox() as sb:
        assert Path(sb.wiki_root).is_dir()
        assert sb.env["SF_WIKI_ROOT"] == str(sb.wiki_root)
        assert sb.env["CLAUDE_PLUGIN_DATA"] == str(sb.plugin_data)
        tmp = sb.wiki_root
    assert not Path(tmp).exists()           # torn down
    assert dict(os.environ) == before        # process env untouched


def test_sandbox_env_is_a_copy_not_global_mutation():
    with eval_sandbox() as sb:
        assert "SF_WIKI_ROOT" not in os.environ or os.environ.get("SF_WIKI_ROOT") != sb.env["SF_WIKI_ROOT"]


def test_isolation_property_sandbox_leaves_real_tree_untouched(tmp_path: Path):
    """
    Property test: A runner that writes under the sandbox env must leave the
    real SF_WIKI_ROOT tree byte-identical to its pre-run state.

    This test verifies that eval_sandbox properly isolates the subprocess
    environment from the orchestrator's actual wiki/plugin-data directories.
    """
    real_wiki = tmp_path / "real_wiki"
    real_plugin = tmp_path / "real_plugin"
    real_wiki.mkdir()
    real_plugin.mkdir()

    # Create a reference structure in the real directories
    (real_wiki / "file1.txt").write_text("original", encoding="utf-8")
    (real_plugin / "data.json").write_text('{"key":"value"}', encoding="utf-8")

    # Capture byte-identical snapshots before sandbox use
    before_wiki_snapshot = {
        path: path.read_bytes()
        for path in sorted(real_wiki.rglob("*")) if path.is_file()
    }
    before_plugin_snapshot = {
        path: path.read_bytes()
        for path in sorted(real_plugin.rglob("*")) if path.is_file()
    }

    # Set real paths in process environment
    old_wiki_root = os.environ.get("SF_WIKI_ROOT")
    old_plugin_data = os.environ.get("CLAUDE_PLUGIN_DATA")
    try:
        os.environ["SF_WIKI_ROOT"] = str(real_wiki)
        os.environ["CLAUDE_PLUGIN_DATA"] = str(real_plugin)

        # Use the sandbox context
        with eval_sandbox() as sb:
            # Verify sandbox env points to isolated temp dirs
            assert str(sb.wiki_root) != str(real_wiki)
            assert str(sb.plugin_data) != str(real_plugin)

            # Simulate writes to sandbox env paths (as a subprocess would)
            sandbox_wiki_file = sb.wiki_root / "new_file.txt"
            sandbox_wiki_file.write_text("sandbox data", encoding="utf-8")
            (sb.plugin_data / "sandbox.json").write_text(
                '{"sandbox":true}', encoding="utf-8"
            )

        # Verify sandbox was torn down
        assert not sb.wiki_root.exists()
        assert not sb.plugin_data.exists()

        # Verify real directories are byte-identical to before
        after_wiki_snapshot = {
            path: path.read_bytes()
            for path in sorted(real_wiki.rglob("*")) if path.is_file()
        }
        after_plugin_snapshot = {
            path: path.read_bytes()
            for path in sorted(real_plugin.rglob("*")) if path.is_file()
        }

        assert before_wiki_snapshot == after_wiki_snapshot, (
            "Real wiki tree was modified during sandbox use"
        )
        assert before_plugin_snapshot == after_plugin_snapshot, (
            "Real plugin-data tree was modified during sandbox use"
        )
    finally:
        # Restore original env
        if old_wiki_root is not None:
            os.environ["SF_WIKI_ROOT"] = old_wiki_root
        elif "SF_WIKI_ROOT" in os.environ:
            del os.environ["SF_WIKI_ROOT"]
        if old_plugin_data is not None:
            os.environ["CLAUDE_PLUGIN_DATA"] = old_plugin_data
        elif "CLAUDE_PLUGIN_DATA" in os.environ:
            del os.environ["CLAUDE_PLUGIN_DATA"]


def test_sandbox_uses_skill_cwd_when_given(tmp_path: Path):
    plugin_root = tmp_path / "repo"
    plugin_root.mkdir()
    with eval_sandbox(skill_cwd=plugin_root) as sb:
        assert sb.cwd == plugin_root              # runs from the plugin-active dir
        assert Path(sb.wiki_root).is_dir()         # writes still redirected to tmp
        assert sb.env["SF_WIKI_ROOT"] == str(sb.wiki_root)
        tmp_wiki = sb.wiki_root
    assert not Path(tmp_wiki).exists()             # tmp torn down
    assert plugin_root.exists()                    # plugin dir NEVER torn down


def test_sandbox_defaults_to_tmp_cwd_when_no_skill_cwd():
    with eval_sandbox() as sb:
        assert sb.cwd == sb.wiki_root.parent        # legacy: cwd is the tmp root
