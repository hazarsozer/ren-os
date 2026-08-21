"""
Tests for lib.memory.page_types — the ONE path -> frontmatter `type:` table
(spec 2026-08-21 §2.4).

Run with: uv run pytest tests/lib/memory/test_page_types.py -v
"""

from __future__ import annotations

import pytest

from lib.memory.page_types import derive_type, ensure_type


class TestDeriveType:
    @pytest.mark.parametrize(
        "page,expected",
        [
            # Rule 1 — a project's own top-level files, direct children ONLY.
            ("projects/hallm/map.md", "l2-map"),
            ("projects/hallm/overview.md", "overview"),
            ("projects/hallm/schema.md", "project-schema"),
            ("projects/hallm/open-work.md", "open-work"),
            ("projects/hallm/instructions.md", "project-instructions"),
            # Rule 2 — folder-note hubs.
            ("projects/hallm/knowledge/lessons/lessons.md", "hub"),
            ("projects/hallm/knowledge/codebase/codebase.md", "hub"),
            # Rule 3 — lessons, global and project-scoped (kind wins).
            ("lessons/some-lesson.md", "lesson"),
            ("projects/flux/knowledge/lessons/some-lesson.md", "lesson"),
            # Rule 4 — session narratives, including archived.
            ("l1/session-x.md", "l1"),
            ("projects/ren-os/l1/session-y.md", "l1"),
            ("archive/l1/session-z.md", "l1"),
            # Rule 5 — everything else under a project knowledge tree.
            ("projects/hallm/knowledge/operations.md", "project-knowledge"),
            ("projects/ren-os/knowledge/architecture/obsidian.md", "project-knowledge"),
            ("projects/hallm/knowledge/pins/pin-2026-08-19.md", "project-knowledge"),
            # Rule 6 — the wiki root's own files.
            ("identity.md", "identity"),
            ("log.md", "log-entry"),
            ("LICENSES.md", "licenses"),
            ("index.md", "l2-map"),
        ],
    )
    def test_table(self, page, expected):
        assert derive_type(page) == expected

    def test_rule_1_depth_qualifier(self):
        """Rule 1 is direct-children-only (exactly 3 segments). A first pass
        at this table read it as 2 and silently dropped
        `projects/<slug>/schema.md` through to I2 — spec §2.4."""
        assert derive_type("projects/hallm/schema.md") == "project-schema"
        assert derive_type("projects/hallm/knowledge/schema.md") == "project-knowledge"

    def test_rule_2_precedes_rule_3(self):
        """A `lessons.md` folder note is a hub, not a lesson."""
        assert derive_type("projects/hallm/knowledge/lessons/lessons.md") == "hub"

    def test_rule_3_precedes_rule_5(self):
        """Kind wins over location for a project-scoped lesson."""
        assert derive_type("projects/flux/knowledge/lessons/x.md") == "lesson"

    def test_rule_4_anchored_to_immediate_parent(self):
        """Rule 4 matches spec §2.4's `**/l1/*.md` glob: `l1` must be the
        file's IMMEDIATE parent, the same fixed-position anchoring rules 3
        and 5 use. A first pass matched `"l1" in parts[:-1]` (anywhere in
        the path), which over-matched a nested path like
        `archive/l1/sub/session-z.md` — not a direct child of `l1/` — as
        `l1` instead of falling through to I2."""
        assert derive_type("l1/session-x.md") == "l1"
        assert derive_type("projects/ren-os/l1/session-y.md") == "l1"
        assert derive_type("archive/l1/session-z.md") == "l1"
        assert derive_type("archive/l1/sub/session-z.md") is None
        assert derive_type("l1/sub/session-z.md") is None

    def test_i2_unmapped_path_returns_none_without_raising(self):
        assert derive_type("some/novel/shape.md") is None
        assert derive_type("notes.md") is None
        assert derive_type("projects/x/fact.md") is None

    def test_hub_detection_excludes_raw_and_archive(self):
        assert derive_type("projects/h/knowledge/raw/raw.md") != "hub"
        assert derive_type("projects/h/knowledge/archive/archive.md") != "hub"

    def test_root_lessons_hub_derives_hub(self):
        """#76.3: the global lessons folder note is `hub` on disk but rule 3 said
        `lesson`. `_ensure_lessons_hub()`'s pre-stamp always won under I1, so the
        disagreement was unreachable — and the table was still wrong."""
        assert derive_type("lessons/lessons.md") == "hub"

    def test_root_lessons_leaf_still_derives_lesson(self):
        """Rule 2b must be narrow: only the folder note, not its siblings."""
        assert derive_type("lessons/some-durable-lesson.md") == "lesson"

    def test_project_lessons_unchanged_by_rule_2b(self):
        assert derive_type("projects/p/knowledge/lessons/lessons.md") == "hub"
        assert derive_type("projects/p/knowledge/lessons/a-lesson.md") == "lesson"


class TestEnsureType:
    def test_adds_frontmatter_when_absent(self):
        out = ensure_type("# Body\n", "lessons/x.md")
        assert out == "---\ntype: lesson\n---\n# Body\n"

    def test_inserts_into_existing_frontmatter(self):
        out = ensure_type('---\ntitle: "X"\n---\n# Body\n', "lessons/x.md")
        assert out == '---\ntype: lesson\ntitle: "X"\n---\n# Body\n'

    def test_i1_existing_type_is_never_overridden(self):
        text = "---\ntype: project-knowledge\n---\n# Body\n"
        assert ensure_type(text, "projects/h/knowledge/lessons/x.md") == text

    def test_i2_unmapped_path_returns_text_unchanged(self):
        text = "# Body\n"
        assert ensure_type(text, "some/novel/shape.md") == text

    def test_does_not_match_a_suffixed_key(self):
        """`content_type:` is not `type:` — the page still needs a stamp."""
        out = ensure_type("---\ncontent_type: x\n---\n# B\n", "lessons/x.md")
        assert out.startswith("---\ntype: lesson\ncontent_type: x\n---\n")

    def test_empty_frontmatter_fence_does_not_get_a_second_fence(self):
        """The bug the frontmatter regex comment warns about. `---\\n---\\n`
        has no newline before its closing fence, so a naive
        `\\A---\\n(.*?)\\n---\\n` misses it entirely and prepends a SECOND
        fence. Wrap's `_ensure_l1_type` shipped this bug once already."""
        out = ensure_type("---\n---\n\n# S\n", "l1/session-x.md")
        assert out == "---\ntype: l1\n---\n\n# S\n"

    def test_multi_key_frontmatter_keeps_its_order(self):
        out = ensure_type("---\na: 1\nb: 2\n---\nbody\n", "projects/h/knowledge/x/x.md")
        assert out == "---\ntype: hub\na: 1\nb: 2\n---\nbody\n"

    def test_is_idempotent(self):
        once = ensure_type("# Body\n", "lessons/x.md")
        assert ensure_type(once, "lessons/x.md") == once

    def test_trailing_space_after_closing_fence_returns_text_unchanged(self):
        """A space after the closing `---` defeats `_FRONTMATTER_RE` (it is
        deliberately stricter than provenance's/lint's, to correctly handle
        an empty fence). The fail-safe must leave the text alone rather than
        prepend a second fence on top of an already-typed page — this is the
        exact repro from the doctrine review."""
        text = "---\ntype: lesson\n--- \n# B\n"
        assert ensure_type(text, "lessons/a.md") == text

    def test_crlf_page_returns_text_unchanged(self):
        text = "---\r\ntype: lesson\r\n---\r\n# B\r\n"
        assert ensure_type(text, "lessons/a.md") == text

    def test_no_trailing_newline_after_closing_fence_returns_text_unchanged(self):
        text = "---\ntype: lesson\n---"
        assert ensure_type(text, "lessons/a.md") == text
