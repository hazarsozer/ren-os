"""Tests for skills.sf_note.lib."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ..__init__ import (
    UNSESSIONED_FILENAME,
    PinResult,
    format_bullet,
    pin_note,
    resolve_notes_path,
)


# ---------------------------------------------------------------------------
# resolve_notes_path
# ---------------------------------------------------------------------------


class TestResolveNotesPath:
    def test_with_session_id(self, tmp_path: Path):
        result = resolve_notes_path(session_id="abc-123_xyz", notes_root=tmp_path)
        assert result == tmp_path / "abc-123_xyz.md"

    def test_no_session_id_falls_back(self, tmp_path: Path):
        result = resolve_notes_path(session_id=None, notes_root=tmp_path)
        assert result == tmp_path / UNSESSIONED_FILENAME

    def test_empty_string_falls_back(self, tmp_path: Path):
        result = resolve_notes_path(session_id="", notes_root=tmp_path)
        assert result == tmp_path / UNSESSIONED_FILENAME

    def test_path_traversal_rejected(self, tmp_path: Path):
        """Defense-in-depth: a session_id with `/` or `..` falls back to unsessioned."""
        for hostile in ["../escape", "a/b", "a\\b", ".."]:
            result = resolve_notes_path(session_id=hostile, notes_root=tmp_path)
            assert result == tmp_path / UNSESSIONED_FILENAME, f"hostile {hostile!r} escaped"

    def test_dot_session_id_rejected(self, tmp_path: Path):
        """Session ids with dots (like 'sess.123') fall back since dots aren't in the safe set."""
        result = resolve_notes_path(session_id="sess.123", notes_root=tmp_path)
        assert result == tmp_path / UNSESSIONED_FILENAME


# ---------------------------------------------------------------------------
# format_bullet
# ---------------------------------------------------------------------------


class TestFormatBullet:
    def test_basic_bullet(self):
        line = format_bullet("hello world", now=datetime(2026, 5, 28, 14, 30, 0, tzinfo=timezone.utc))
        assert line == "- [2026-05-28T14:30:00Z] hello world\n"

    def test_trailing_whitespace_trimmed(self):
        line = format_bullet("text with trailing  ", now=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
        assert line == "- [2026-01-01T00:00:00Z] text with trailing\n"

    def test_internal_newlines_escaped(self):
        """Single-bullet invariant: \\n inside text becomes literal '\\n'."""
        line = format_bullet("line one\nline two", now=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
        # No raw newline in the middle (only the trailing one)
        assert line.count("\n") == 1
        assert "line one\\nline two" in line

    def test_iso_8601_format(self):
        line = format_bullet("x")
        # Match `- [YYYY-MM-DDTHH:MM:SSZ] x\n` shape
        assert re.match(r"^- \[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\] x\n$", line), line


# ---------------------------------------------------------------------------
# pin_note
# ---------------------------------------------------------------------------


class TestPinNote:
    def test_basic_pin_creates_file(self, tmp_path: Path):
        result = pin_note(
            "this is worth remembering",
            session_id="sess-1",
            notes_root=tmp_path,
            now=datetime(2026, 5, 28, 14, 30, 0, tzinfo=timezone.utc),
        )
        assert result.success
        assert result.error is None
        assert result.path == tmp_path / "sess-1.md"
        assert result.path.exists()

        content = result.path.read_text(encoding="utf-8")
        assert "# Session notes — sess-1" in content
        assert "- [2026-05-28T14:30:00Z] this is worth remembering" in content

    def test_second_pin_appends(self, tmp_path: Path):
        pin_note("first", session_id="s", notes_root=tmp_path,
                 now=datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc))
        pin_note("second", session_id="s", notes_root=tmp_path,
                 now=datetime(2026, 1, 1, 10, 5, 0, tzinfo=timezone.utc))

        content = (tmp_path / "s.md").read_text(encoding="utf-8")
        assert "first" in content
        assert "second" in content
        # Header appears only once
        assert content.count("# Session notes") == 1
        # Bullets are in chronological order (first appended first)
        idx_first = content.index("first")
        idx_second = content.index("second")
        assert idx_first < idx_second

    def test_no_session_id_uses_unsessioned(self, tmp_path: Path):
        result = pin_note(
            "no session", session_id=None, notes_root=tmp_path,
            now=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        )
        assert result.success
        assert result.path == tmp_path / UNSESSIONED_FILENAME
        content = result.path.read_text(encoding="utf-8")
        assert "# Unsessioned notes" in content
        assert "no session" in content

    def test_empty_text_refused(self, tmp_path: Path):
        result = pin_note("", session_id="s", notes_root=tmp_path)
        assert not result.success
        assert result.path is None
        assert "Empty text" in result.error

    def test_whitespace_only_refused(self, tmp_path: Path):
        result = pin_note("   \n\t  ", session_id="s", notes_root=tmp_path)
        assert not result.success
        assert "Empty text" in result.error

    def test_creates_parent_directory(self, tmp_path: Path):
        nested = tmp_path / "deep" / "nested" / "notes"
        assert not nested.exists()
        result = pin_note("x", session_id="s", notes_root=nested)
        assert result.success
        assert nested.is_dir()
        assert (nested / "s.md").exists()

    def test_multi_line_text_preserved_as_single_bullet(self, tmp_path: Path):
        result = pin_note("multi\nline\ntext", session_id="s", notes_root=tmp_path)
        assert result.success
        content = result.path.read_text(encoding="utf-8")
        # Single bullet line (escaped newlines)
        bullet_lines = [ln for ln in content.splitlines() if ln.startswith("- ")]
        assert len(bullet_lines) == 1
        assert "multi\\nline\\ntext" in bullet_lines[0]

    def test_unwritable_directory(self, tmp_path: Path, monkeypatch):
        """Simulate OSError on mkdir."""

        def boom(*args, **kwargs):
            raise OSError("simulated permission error")

        monkeypatch.setattr(Path, "mkdir", boom)
        result = pin_note("x", session_id="s", notes_root=tmp_path / "boom")
        assert not result.success
        assert "Could not create notes directory" in result.error

    def test_pin_result_immutable(self, tmp_path: Path):
        result = pin_note("x", session_id="s", notes_root=tmp_path)
        with pytest.raises(Exception):
            result.success = False  # type: ignore[misc]


class TestInstinctCapture:
    """C3a — /ren:note --instinct hot-tier capture (durable, hierarchically routed)."""

    def test_instinct_scope_project_default(self):
        from ..__init__ import instinct_scope
        assert instinct_scope(use_global=False, project_slug="dry") == "project"

    def test_instinct_scope_global_flag(self):
        from ..__init__ import instinct_scope
        assert instinct_scope(use_global=True, project_slug="dry") == "global"

    def test_instinct_scope_no_project_falls_back_to_global(self):
        from ..__init__ import instinct_scope
        assert instinct_scope(use_global=False, project_slug=None) == "global"

    def test_resolve_instinct_path_project(self, tmp_path: Path):
        from ..__init__ import resolve_instinct_path
        p = resolve_instinct_path(scope="project", project_slug="dry", wiki_root=tmp_path)
        assert p == tmp_path / "projects" / "dry" / "instincts.md"

    def test_resolve_instinct_path_global(self, tmp_path: Path):
        from ..__init__ import resolve_instinct_path
        p = resolve_instinct_path(scope="global", project_slug="dry", wiki_root=tmp_path)
        assert p == tmp_path / "instincts.md"

    def test_format_instinct_bullet(self):
        from ..__init__ import format_instinct_bullet
        line = format_instinct_bullet("worked", "do the thing",
                                      now=datetime(2026, 6, 28, tzinfo=timezone.utc))
        assert line == "- **[worked]** 2026-06-28 — do the thing\n"

    def test_pin_instinct_creates_file_with_frontmatter(self, tmp_path: Path):
        from ..__init__ import pin_instinct
        res = pin_instinct("worked", "first instinct", wiki_root=tmp_path,
                           project_slug="dry", use_global=False, framework_version="0.1.0")
        assert res.success and res.scope == "project"
        text = res.path.read_text(encoding="utf-8")
        assert "type: instincts" in text and "schema_version: 1" in text
        assert "scope: project" in text
        assert "- **[worked]**" in text and "first instinct" in text

    def test_pin_instinct_appends_to_existing_once_frontmatter(self, tmp_path: Path):
        from ..__init__ import pin_instinct
        pin_instinct("worked", "one", wiki_root=tmp_path, project_slug="dry",
                     use_global=False, framework_version="0.1.0")
        res = pin_instinct("avoid", "two", wiki_root=tmp_path, project_slug="dry",
                           use_global=False, framework_version="0.1.0")
        text = res.path.read_text(encoding="utf-8")
        assert "one" in text and "two" in text
        assert text.count("type: instincts") == 1  # frontmatter written once

    def test_pin_instinct_global_routes_to_master(self, tmp_path: Path):
        from ..__init__ import pin_instinct
        res = pin_instinct("worked", "g", wiki_root=tmp_path, project_slug="dry",
                           use_global=True, framework_version="0.1.0")
        assert res.path == tmp_path / "instincts.md" and res.scope == "global"

    def test_pin_instinct_no_project_falls_back_global(self, tmp_path: Path):
        from ..__init__ import pin_instinct
        res = pin_instinct("worked", "g", wiki_root=tmp_path, project_slug=None,
                           use_global=False, framework_version="0.1.0")
        assert res.path == tmp_path / "instincts.md"
        assert res.scope == "global" and res.fell_back_to_global is True

    def test_pin_instinct_rejects_bad_kind(self, tmp_path: Path):
        from ..__init__ import pin_instinct
        res = pin_instinct("banana", "x", wiki_root=tmp_path, project_slug="dry",
                           use_global=False, framework_version="0.1.0")
        assert not res.success and res.error and "worked" in res.error
        assert not (tmp_path / "projects" / "dry" / "instincts.md").exists()

    def test_pin_instinct_rejects_empty_text(self, tmp_path: Path):
        from ..__init__ import pin_instinct
        res = pin_instinct("worked", "   ", wiki_root=tmp_path, project_slug="dry",
                           use_global=False, framework_version="0.1.0")
        assert not res.success
