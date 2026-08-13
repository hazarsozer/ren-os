"""Tests for skills.doctor.lib.check_hub_convention (#56).

Warns when legacy knowledge-hub `index.md` pages remain (pending the
folder-note-hubs-1 migration) — mirrors check_dangling_pointers' shape:
a single warn-not-block check, wiki_root resolved via lib.ren_paths.wiki_root()
when no explicit root is passed.
"""

from __future__ import annotations

import importlib

doctor_lib = importlib.import_module("skills.doctor.lib")


def test_check_hub_convention_warns_on_legacy_hub(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    import lib.ren_paths as rp
    root = rp.wiki_root()
    hub = root / "projects/demo/knowledge/research/index.md"
    hub.parent.mkdir(parents=True)
    hub.write_text("---\nhub: true\n---\n", encoding="utf-8")
    result = doctor_lib.check_hub_convention()
    assert result.status == "warn"
    assert "projects/demo/knowledge/research/index.md" in result.message


def test_check_hub_convention_ok_on_migrated_wiki(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    import lib.ren_paths as rp
    root = rp.wiki_root()
    done = root / "projects/demo/knowledge/research/research.md"
    done.parent.mkdir(parents=True)
    done.write_text("---\nhub: true\n---\n", encoding="utf-8")
    result = doctor_lib.check_hub_convention()
    assert result.status == "ok"
