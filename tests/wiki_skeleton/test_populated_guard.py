"""
tests.wiki_skeleton.test_populated_guard — unit tests for
`lib.skeleton.wiki_populated_reason` (Task 2, #58 remainder).

Two mechanical signals only, no content heuristics: a project map exists, or a
core page carries `ren_supersedes` (UPDATEd since its founding ADD).

Run with: uv run pytest tests/wiki_skeleton/test_populated_guard.py -v
"""

from pathlib import Path

from lib.skeleton import wiki_populated_reason


def _founding_page(text: str = "# page\n") -> str:
    # A founding page: stamped once, no ren_supersedes.
    return (
        '---\nren_write_id: "w-01TEST"\nren_ts: "2026-08-01T00:00:00Z"\n'
        'ren_writer: "human"\nren_op: "ADD"\nren_trust: "user"\n---\n' + text
    )


def _updated_page(text: str = "# page\n") -> str:
    # Updated since founding: carries ren_supersedes.
    return (
        '---\nren_write_id: "w-01TEST2"\nren_ts: "2026-08-12T00:00:00Z"\n'
        'ren_writer: "llm-auto"\nren_op: "UPDATE"\nren_trust: "model"\n'
        'ren_supersedes: "w-01TEST"\n---\n' + text
    )


def test_empty_root_is_not_populated(tmp_path):
    assert wiki_populated_reason(tmp_path) is None


def test_founding_pages_only_is_not_populated(tmp_path):
    (tmp_path / "identity.md").write_text(_founding_page(), encoding="utf-8")
    (tmp_path / "log.md").write_text(_founding_page(), encoding="utf-8")
    assert wiki_populated_reason(tmp_path) is None


def test_project_map_means_populated(tmp_path):
    (tmp_path / "projects" / "demo").mkdir(parents=True)
    (tmp_path / "projects" / "demo" / "map.md").write_text(_founding_page(), encoding="utf-8")
    reason = wiki_populated_reason(tmp_path)
    assert reason is not None and "projects/demo/map.md" in reason


def test_updated_core_page_means_populated(tmp_path):
    (tmp_path / "log.md").write_text(_updated_page(), encoding="utf-8")
    reason = wiki_populated_reason(tmp_path)
    assert reason is not None and "log.md" in reason


def test_unreadable_page_does_not_crash(tmp_path):
    (tmp_path / "identity.md").write_bytes(b"\xff\xfe garbage")
    assert wiki_populated_reason(tmp_path) is None
