"""The real-renos isolation guard must ignore files the friend's editor
owns (Obsidian's `.obsidian/` state), which change while the suite runs
and are not RenOS-writable — a false isolation breach otherwise."""

from pathlib import Path

import conftest


def test_obsidian_state_is_editor_owned():
    assert conftest._is_editor_owned(Path("/h/.renos/wiki/.obsidian/workspace.json"))
    assert conftest._is_editor_owned(Path("/h/.renos/wiki/.obsidian/plugins/x/data.json"))


def test_wiki_pages_are_not_editor_owned():
    assert not conftest._is_editor_owned(Path("/h/.renos/wiki/index.md"))
    assert not conftest._is_editor_owned(Path("/h/.renos/wiki/.ren/metrics/x.json"))
