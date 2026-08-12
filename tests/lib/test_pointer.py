"""lib.pointer — the single home of the L2 decision-map pointer grammar (#53)."""
from __future__ import annotations

import pytest

from lib import pointer


class TestParseLinkForm:
    def test_basic(self):
        p = pointer.parse_pointer_line("- [Stack decisions](projects/flux/knowledge/stack.md) (w-01ABC)")
        assert p is not None
        assert p.topic == "Stack decisions"
        assert p.target == "projects/flux/knowledge/stack.md"
        assert p.path == "projects/flux/knowledge/stack.md"
        assert p.anchor is None
        assert p.write_id == "w-01ABC"
        assert p.form == "link"

    def test_anchor(self):
        p = pointer.parse_pointer_line("- [Schema](projects/ren-os/schema.md#naming-conventions) (w-01X)")
        assert p.path == "projects/ren-os/schema.md"
        assert p.anchor == "naming-conventions"
        assert p.target == "projects/ren-os/schema.md#naming-conventions"

    def test_unstamped(self):
        p = pointer.parse_pointer_line("- [Topic](projects/x/a.md) (unstamped)")
        assert p.write_id is None


class TestParseArrowForm:
    def test_legacy_wiki_path(self):
        p = pointer.parse_pointer_line("- [Architecture] → projects/ren-os/knowledge/architecture/index.md (w-01Y)")
        assert p.form == "arrow"
        assert p.path == "projects/ren-os/knowledge/architecture/index.md"
        assert p.write_id == "w-01Y"

    def test_arrow_anchor(self):
        p = pointer.parse_pointer_line("- [S] → projects/x/schema.md#conventions (unstamped)")
        assert p.path == "projects/x/schema.md"
        assert p.anchor == "conventions"
        assert p.write_id is None

    def test_repo_ref(self):
        p = pointer.parse_pointer_line("- [Specs] → repo:idea-generator:analyses/flux (w-01Z)")
        assert p.form == "arrow"
        assert p.target == "repo:idea-generator:analyses/flux"
        assert p.path == ""
        assert p.anchor is None


@pytest.mark.parametrize("line", [
    "",
    "- plain knowledge bullet",
    "## Decision map",
    "_All pointer paths are relative to the wiki root, not this file._",
    "- [unclosed](projects/x/a.md",
    "- [no target] →",
    "[not a bullet] → projects/x/a.md (w-01)",
    "- [T] → projects/x/a.md (w-1) — note",       # trailing prose
    "- [T] → projects/x/a.md (w-1) (extra)",      # double paren tail
    "- [T] → projects/my notes/a.md (w-1)",       # space in target
])
def test_non_pointer_lines_return_none(line):
    assert pointer.parse_pointer_line(line) is None


class TestRender:
    def test_wiki_target_renders_link_form(self):
        line = pointer.render_pointer_line("Stack", "projects/flux/knowledge/stack.md", "w-01ABC")
        assert line == "- [Stack](projects/flux/knowledge/stack.md) (w-01ABC)"

    def test_repo_ref_renders_arrow_form(self):
        line = pointer.render_pointer_line("Specs", "repo:idea-generator:analyses", None)
        assert line == "- [Specs] → repo:idea-generator:analyses (unstamped)"

    def test_none_write_id_renders_unstamped(self):
        line = pointer.render_pointer_line("T", "projects/x/a.md", None)
        assert line.endswith("(unstamped)")


def test_render_parse_round_trip():
    cases = [
        ("Topic", "projects/x/a.md", "w-01A"),
        ("With anchor", "projects/x/a.md#sec", None),
        ("Repo", "repo:name:some/path", "w-01B"),
    ]
    for topic, target, wid in cases:
        p = pointer.parse_pointer_line(pointer.render_pointer_line(topic, target, wid))
        assert p is not None
        assert (p.topic, p.target, p.write_id) == (topic, target, wid)
