"""Tests for lib.companions — registry, detection, choices, reconcile."""

import json
from pathlib import Path

import pytest

from lib import companions, ren_paths


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    return monkeypatch


@pytest.fixture
def wiki(clean_path_env, tmp_path):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = ren_paths.wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


class TestRegistry:
    def test_registry_ids_are_unique(self):
        ids = [c.cid for c in companions.REGISTRY]
        assert len(ids) == len(set(ids))

    def test_registry_seeds_the_curated_list(self):
        ids = {c.cid for c in companions.REGISTRY}
        assert {"graphify", "markitdown", "yt-dlp", "superpowers"} <= ids

    def test_kinds_are_valid(self):
        assert all(c.kind in ("tool", "plugin") for c in companions.REGISTRY)


class TestDetection:
    def test_tool_installed_when_on_path(self, monkeypatch):
        monkeypatch.setattr(companions.shutil, "which", lambda name: "/usr/bin/" + name)
        tool = next(c for c in companions.REGISTRY if c.kind == "tool")
        assert companions.is_installed(tool) is True

    def test_tool_absent_when_not_on_path(self, monkeypatch):
        monkeypatch.setattr(companions.shutil, "which", lambda name: None)
        tool = next(c for c in companions.REGISTRY if c.kind == "tool")
        assert companions.is_installed(tool) is False

    def test_plugin_detected_via_cache_glob(self, tmp_path, monkeypatch):
        monkeypatch.setattr(companions.ren_paths, "claude_user_dir", lambda: tmp_path)
        plugin = next(c for c in companions.REGISTRY if c.kind == "plugin")
        assert companions.is_installed(plugin) is False
        (tmp_path / "plugins" / "cache" / "some-marketplace" / plugin.detect).mkdir(parents=True)
        assert companions.is_installed(plugin) is True


class TestChoices:
    def test_load_choices_empty_when_no_file(self, clean_path_env, wiki):
        assert companions.load_choices() == {}

    def test_record_and_load_round_trip(self, clean_path_env, wiki):
        companions.record_choice("graphify", "accepted")
        choices = companions.load_choices()
        assert choices["graphify"]["decision"] == "accepted"
        assert "offered_at_version" in choices["graphify"]
        assert "ts" in choices["graphify"]

    def test_corrupt_choices_file_degrades_to_empty(self, clean_path_env, wiki):
        path = ren_paths.state_dir() / companions.CHOICES_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        assert companions.load_choices() == {}

    def test_record_rejects_bad_decision(self, clean_path_env, wiki):
        with pytest.raises(ValueError):
            companions.record_choice("graphify", "maybe")

    def test_record_rejects_unknown_id(self, clean_path_env, wiki):
        with pytest.raises(ValueError):
            companions.record_choice("not-a-companion", "accepted")


class TestReconcile:
    def test_pending_offers_excludes_installed_and_decided(self, clean_path_env, wiki, monkeypatch):
        monkeypatch.setattr(companions, "is_installed",
                            lambda c: c.cid == "markitdown")
        companions.record_choice("graphify", "declined")
        pending_ids = {o.companion.cid for o in companions.pending_offers()}
        assert "markitdown" not in pending_ids   # installed
        assert "graphify" not in pending_ids     # declined
        assert "superpowers" in pending_ids      # undecided + absent

    def test_reconcile_covers_full_registry(self, clean_path_env, wiki, monkeypatch):
        monkeypatch.setattr(companions, "is_installed", lambda c: False)
        offers = companions.reconcile()
        assert {o.companion.cid for o in offers} == {c.cid for c in companions.REGISTRY}


class TestDoctrineSync:
    def test_every_registry_id_appears_in_companions_doctrine(self):
        doc_path = Path(__file__).resolve().parents[2] / "doctrine" / "companions.md"
        doc = doc_path.read_text(encoding="utf-8").lower()
        for c in companions.REGISTRY:
            assert c.cid.lower() in doc, (
                f"{c.cid} is in lib.companions.REGISTRY but missing from "
                "doctrine/companions.md — the two must stay in sync"
            )
