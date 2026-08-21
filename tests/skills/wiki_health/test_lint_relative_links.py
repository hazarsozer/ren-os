"""
Tests for `../` wikilink resolution in the wiki-health lint (#79).

`_resolves` validated containment against the resolution base rather than the
wiki root, so every `../` link raised PathTraversalError into a swallowing
except and was judged dangling. The live hazard was not the noisy finding: on
a page with no code fence, `_link_findings` treats an unambiguous basename
match as a safe automatic repoint, so a VALID link could be silently rewritten.

Run with: uv run pytest tests/skills/wiki_health/test_lint_relative_links.py -v
"""

from __future__ import annotations

import importlib

import pytest

from lib.ren_paths import wiki_root

lint = importlib.import_module("skills.wiki-health.lib.lint")


@pytest.fixture
def wiki(monkeypatch, tmp_path):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_parent_relative_link_resolves(wiki):
    """A `../` link landing inside the wiki resolves. This is #79 itself."""
    _write(wiki, "projects/p/knowledge/experiment/experiment.md", "# Experiment\n")
    _write(wiki, "projects/p/knowledge/codebase/codebase.md", "# Codebase\n")

    assert lint._resolves(
        wiki, "projects/p/knowledge/codebase/codebase.md", "../experiment/experiment"
    )


def test_parent_relative_link_not_reported_on_fence_free_page(wiki):
    """The regression test MUST be fence-free.

    Both live false positives sat on pages containing a code fence, and the
    fence is the only reason they were reported rather than rewritten. A fenced
    fixture would pass while the actual hazard survived.
    """
    _write(wiki, "projects/p/knowledge/experiment/experiment.md", "# Experiment\n")
    text = "# Codebase\n\nSee [[../experiment/experiment]] for the setup.\n"
    page = "projects/p/knowledge/codebase/codebase.md"
    _write(wiki, page, text)

    all_pages = lint.walk_wiki_pages(wiki)
    new_text, fixes, judgments = lint._lint_page(wiki, page, text, all_pages, set())

    assert new_text == text, "a valid ../ link must never be rewritten"
    assert "dangling-link-repointed" not in fixes
    assert "dangling-link" not in {rule for rule, _ in judgments}


def test_link_escaping_the_wiki_is_still_refused(wiki):
    """The traversal guard must still guard — against the wiki root."""
    _write(wiki, "projects/p/knowledge/codebase/codebase.md", "# Codebase\n")

    assert not lint._resolves(
        wiki, "projects/p/knowledge/codebase/codebase.md", "../../../../../../etc/passwd"
    )


def test_same_directory_link_still_resolves(wiki):
    """The pre-existing behavior this fix must not disturb."""
    _write(wiki, "projects/p/knowledge/codebase/research-base.md", "# Research\n")
    _write(wiki, "projects/p/knowledge/codebase/codebase.md", "# Codebase\n")

    assert lint._resolves(
        wiki, "projects/p/knowledge/codebase/codebase.md", "research-base"
    )
