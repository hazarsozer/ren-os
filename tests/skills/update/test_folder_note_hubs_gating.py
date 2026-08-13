"""Tests for skills/update/lib should_run_folder_note_hubs_1 (#56).

Unlike the version-crossing gates (trust-backfill-1, project-knowledge-1,
foreign-remint-1), folder-note-hubs-1 is idempotent-by-inspection: the
migration renames `projects/*/knowledge/**/index.md` to `<parent-dir>.md`,
so the gate simply checks whether any legacy `index.md` hub remains
(raw/, archive/, and dot-dirs excluded — those are never migrated).
"""

from __future__ import annotations

from skills.update import lib as update_lib


def test_should_run_folder_note_hubs_1_true_when_legacy_hub_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    import lib.ren_paths as rp
    root = rp.wiki_root()
    hub = root / "projects/demo/knowledge/research/index.md"
    hub.parent.mkdir(parents=True)
    hub.write_text("---\ntype: project-knowledge\nhub: true\n---\n# R\n", encoding="utf-8")
    assert update_lib.should_run_folder_note_hubs_1() is True


def test_should_run_folder_note_hubs_1_false_when_migrated_or_only_raw(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    import lib.ren_paths as rp
    root = rp.wiki_root()
    done = root / "projects/demo/knowledge/research/research.md"
    done.parent.mkdir(parents=True)
    done.write_text("---\nhub: true\n---\n", encoding="utf-8")
    raw = root / "projects/demo/raw/knowledge/x/index.md"
    raw.parent.mkdir(parents=True)
    raw.write_text("raw", encoding="utf-8")
    assert update_lib.should_run_folder_note_hubs_1() is False
