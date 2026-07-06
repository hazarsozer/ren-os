"""
Tests for skills/update/scripts/*.sh — carried near-verbatim from donor
`skills/update/scripts/` (Task 7.3). Drives the bash scripts via subprocess
against tmp_path fixtures; renamed env vars (REN_WIKI_ROOT, REN_SNAPSHOT_MODE)
per this skill's delta from donor.

Run with: uv run pytest tests/skills/update/test_update_scripts.py -v
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[3] / "skills" / "update" / "scripts"
_SNAPSHOT = _SCRIPTS / "snapshot.sh"
_RESTORE = _SCRIPTS / "restore.sh"
_PRUNE = _SCRIPTS / "prune-snapshots.sh"
_VERSION_COMPARE = _SCRIPTS / "version-compare.sh"


def _run(cmd: list[str], **env: str) -> subprocess.CompletedProcess[str]:
    import os
    base = {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": os.environ.get("HOME", "/tmp")}
    base.update(env)
    return subprocess.run(cmd, capture_output=True, text=True, env=base)


@pytest.fixture
def wiki_and_plugin_data(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "log.md").write_text("# Wiki Log\n", encoding="utf-8")
    (wiki / "identity.md").write_text("---\ntitle: x\n---\n", encoding="utf-8")
    plugin_data = tmp_path / "plugin-data"
    return wiki, plugin_data


# ------------------------------------------------------------------- snapshot


def test_snapshot_creates_dir_and_copies_wiki(wiki_and_plugin_data):
    wiki, plugin_data = wiki_and_plugin_data
    r = _run(["bash", str(_SNAPSHOT), "1.0.0"], REN_WIKI_ROOT=str(wiki), CLAUDE_PLUGIN_DATA=str(plugin_data))
    assert r.returncode == 0, r.stderr
    snap_path = Path(r.stdout.strip())
    assert snap_path.is_dir()
    assert (snap_path / "identity.md").is_file()
    assert "v1.0.0-pre-update-" in snap_path.name


def test_snapshot_logs_to_wiki_log(wiki_and_plugin_data):
    wiki, plugin_data = wiki_and_plugin_data
    _run(["bash", str(_SNAPSHOT), "1.0.0"], REN_WIKI_ROOT=str(wiki), CLAUDE_PLUGIN_DATA=str(plugin_data))
    log_text = (wiki / "log.md").read_text(encoding="utf-8")
    assert "snapshot" in log_text


def test_snapshot_missing_wiki_root_fails(tmp_path):
    r = _run(["bash", str(_SNAPSHOT), "1.0.0"], REN_WIKI_ROOT=str(tmp_path / "nope"), CLAUDE_PLUGIN_DATA=str(tmp_path / "pd"))
    assert r.returncode == 2


def test_snapshot_prunes_beyond_retain(wiki_and_plugin_data):
    wiki, plugin_data = wiki_and_plugin_data
    for _ in range(5):
        r = _run(
            ["bash", str(_SNAPSHOT), "1.0.0"],
            REN_WIKI_ROOT=str(wiki), CLAUDE_PLUGIN_DATA=str(plugin_data),
            CLAUDE_PLUGIN_OPTION_SNAPSHOTRETAIN="2",
        )
        assert r.returncode == 0, r.stderr
    remaining = list((plugin_data / "wiki-snapshots").glob("v*-pre-update-*"))
    assert len(remaining) <= 2


# --------------------------------------------------------------------- restore


def test_restore_list_empty_when_no_snapshots(tmp_path):
    r = _run(["bash", str(_RESTORE), "--list"], CLAUDE_PLUGIN_DATA=str(tmp_path / "pd"))
    assert r.returncode == 0
    assert "no snapshots" in r.stdout


def test_restore_whole_restores_wiki(wiki_and_plugin_data):
    wiki, plugin_data = wiki_and_plugin_data
    snap_r = _run(["bash", str(_SNAPSHOT), "1.0.0"], REN_WIKI_ROOT=str(wiki), CLAUDE_PLUGIN_DATA=str(plugin_data))
    snap_path = snap_r.stdout.strip()

    (wiki / "identity.md").write_text("CORRUPTED", encoding="utf-8")

    r = _run(
        ["bash", str(_RESTORE), "--whole", snap_path],
        REN_WIKI_ROOT=str(wiki), CLAUDE_PLUGIN_DATA=str(plugin_data),
    )
    assert r.returncode == 0, r.stderr
    assert "restored from" in r.stdout
    assert "CORRUPTED" not in (wiki / "identity.md").read_text(encoding="utf-8")


def test_restore_page_restores_single_file(wiki_and_plugin_data):
    wiki, plugin_data = wiki_and_plugin_data
    snap_r = _run(["bash", str(_SNAPSHOT), "1.0.0"], REN_WIKI_ROOT=str(wiki), CLAUDE_PLUGIN_DATA=str(plugin_data))
    snap_path = snap_r.stdout.strip()

    (wiki / "identity.md").write_text("CORRUPTED", encoding="utf-8")

    r = _run(
        ["bash", str(_RESTORE), "--page", snap_path, "identity.md"],
        REN_WIKI_ROOT=str(wiki), CLAUDE_PLUGIN_DATA=str(plugin_data),
    )
    assert r.returncode == 0, r.stderr
    assert "CORRUPTED" not in (wiki / "identity.md").read_text(encoding="utf-8")


def test_restore_whole_requires_valid_snapshot_dir(wiki_and_plugin_data):
    wiki, plugin_data = wiki_and_plugin_data
    r = _run(
        ["bash", str(_RESTORE), "--whole", "/does/not/exist"],
        REN_WIKI_ROOT=str(wiki), CLAUDE_PLUGIN_DATA=str(plugin_data),
    )
    assert r.returncode == 2


# ---------------------------------------------------------------------- prune


def test_prune_dry_run_reports_without_deleting(wiki_and_plugin_data):
    wiki, plugin_data = wiki_and_plugin_data
    for _ in range(4):
        _run(["bash", str(_SNAPSHOT), "1.0.0"], REN_WIKI_ROOT=str(wiki), CLAUDE_PLUGIN_DATA=str(plugin_data), CLAUDE_PLUGIN_OPTION_SNAPSHOTRETAIN="10")

    before = list((plugin_data / "wiki-snapshots").glob("v*-pre-update-*"))
    r = _run(["bash", str(_PRUNE), "1", "--dry-run"], CLAUDE_PLUGIN_DATA=str(plugin_data))
    assert r.returncode == 0
    assert "dry-run" in r.stdout
    after = list((plugin_data / "wiki-snapshots").glob("v*-pre-update-*"))
    assert len(before) == len(after)


def test_prune_actually_deletes_when_not_dry_run(wiki_and_plugin_data):
    wiki, plugin_data = wiki_and_plugin_data
    for _ in range(4):
        _run(["bash", str(_SNAPSHOT), "1.0.0"], REN_WIKI_ROOT=str(wiki), CLAUDE_PLUGIN_DATA=str(plugin_data), CLAUDE_PLUGIN_OPTION_SNAPSHOTRETAIN="10")

    r = _run(["bash", str(_PRUNE), "1"], CLAUDE_PLUGIN_DATA=str(plugin_data))
    assert r.returncode == 0
    remaining = list((plugin_data / "wiki-snapshots").glob("v*-pre-update-*"))
    assert len(remaining) == 1


# ------------------------------------------------------------- version-compare


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ("1.0.0", "1.0.0", "eq"),
        ("1.0.0", "1.0.1", "lt"),
        ("1.0.1", "1.0.0", "gt"),
        ("1.3.0-alpha", "1.3.0", "lt"),
    ],
)
def test_version_compare_basic_ordering(a, b, expected):
    r = _run(["bash", str(_VERSION_COMPARE), a, b])
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == expected


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ("1.0.0", "1.0.1", "patch"),
        ("1.0.0", "1.1.0", "minor"),
        ("1.0.0", "2.0.0", "major"),
        ("1.1.0", "1.0.0", "downgrade"),
        ("1.0.0", "1.0.0", "equal"),
    ],
)
def test_version_compare_bump_classification(a, b, expected):
    r = _run(["bash", str(_VERSION_COMPARE), "--bump", a, b])
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == expected
