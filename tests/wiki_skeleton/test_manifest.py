"""Structural checks on wiki-skeleton/manifest.yaml — the manifest is the
single source of truth the loader (lib.skeleton) and the doctor/eval fixtures
read. These tests catch drift between the manifest and the template files it
points at, and pin the "venture is a module, not default" contract."""

from __future__ import annotations

from pathlib import Path

import yaml

SKELETON_ROOT = Path(__file__).resolve().parents[2] / "wiki-skeleton"


def _load_manifest() -> dict:
    return yaml.safe_load((SKELETON_ROOT / "manifest.yaml").read_text(encoding="utf-8"))


def test_every_file_entry_template_exists_on_disk():
    manifest = _load_manifest()
    for profile in manifest["profiles"].values():
        for entry in profile["entries"]:
            if entry["type"] != "file":
                continue
            template_path = SKELETON_ROOT / entry["template"]
            assert template_path.is_file(), f"missing template for {entry['path']}: {template_path}"


def test_master_profile_excludes_venture_entries():
    manifest = _load_manifest()
    master_paths = [entry["path"] for entry in manifest["profiles"]["master"]["entries"]]
    assert not any(p.startswith("venture") for p in master_paths)


def test_venture_profile_exists_and_is_separate_from_master():
    manifest = _load_manifest()
    assert "venture" in manifest["profiles"]
    venture_paths = {entry["path"] for entry in manifest["profiles"]["venture"]["entries"]}
    assert venture_paths == {
        "venture/",
        "venture/company.md",
        "venture/market.md",
        "venture/icp.md",
        "venture/team.md",
        "venture/brain-dump.md",
    }


def test_all_write_rules_are_known():
    manifest = _load_manifest()
    known_rules = {"copy_if_missing", "create_if_missing", "never_write"}
    for profile in manifest["profiles"].values():
        for entry in profile["entries"]:
            assert entry["write_rule"] in known_rules


def test_venture_module_directory_matches_manifest_templates():
    manifest = _load_manifest()
    venture_dir = SKELETON_ROOT / "modules" / "venture"
    assert venture_dir.is_dir()

    manifest_templates = {
        entry["template"]
        for entry in manifest["profiles"]["venture"]["entries"]
        if entry["type"] == "file"
    }
    on_disk = {
        f"modules/venture/{p.name}" for p in venture_dir.glob("*.md.tmpl")
    }
    assert manifest_templates == on_disk
