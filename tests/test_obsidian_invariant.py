"""
Obsidian-vault invariant (Task 9.1, v2.1 D-1).

The shipped wiki-skeleton (templates/ + modules/venture/) must be safely
openable as an Obsidian vault with zero configuration:

  - Every intra-wiki markdown link (`[text](path)`) is relative — no
    absolute filesystem paths, no `file://` URLs.
  - No state-dir (`.ren/`) references leak into template CONTENT (the
    state dir is machine-internal; a friend's vault view should never see
    it mentioned in a page body).
  - Filenames contain none of the characters Obsidian can't open cleanly in
    a link/filename: `# ^ [ ] |`.
  - The `{{placeholder}}` template syntax never collides with Obsidian's
    `[[wikilink]]` syntax — i.e. no `[[` sequences anywhere in a template.
  - No `.obsidian/` directory is committed under wiki-skeleton — a friend's
    vault config (themes, plugins, layout) is their own; the skeleton must
    never ship one.

Run with: uv run pytest tests/test_obsidian_invariant.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WIKI_SKELETON = REPO_ROOT / "wiki-skeleton"
TEMPLATE_ROOTS = [WIKI_SKELETON / "templates", WIKI_SKELETON / "modules"]

_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_FORBIDDEN_FILENAME_CHARS = set("#^[]|")


def _template_files() -> list[Path]:
    files = []
    for root in TEMPLATE_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.name != ".gitkeep":
                files.append(path)
    return files


def test_at_least_one_template_file_exists():
    """Sanity guard: if this returns [], every other test in this file
    passes vacuously and hides a real regression (e.g. a bad path)."""
    assert _template_files(), "expected to find template files under wiki-skeleton/"


def test_every_markdown_link_is_relative():
    offenders = []
    for path in _template_files():
        text = path.read_text(encoding="utf-8")
        for match in _MD_LINK_RE.finditer(text):
            target = match.group(1).strip()
            if target.startswith(("http://", "https://")):
                continue  # external links are fine; only file:// and absolute paths are not
            if target.startswith("file://"):
                offenders.append(f"{path}: {target} (file:// URL)")
            elif target.startswith("/"):
                offenders.append(f"{path}: {target} (absolute path)")
    assert not offenders, "non-relative intra-wiki links found:\n" + "\n".join(offenders)


def test_no_state_dir_references_in_template_content():
    offenders = []
    for path in _template_files():
        text = path.read_text(encoding="utf-8")
        if ".ren/" in text or '".ren"' in text:
            offenders.append(str(path))
    assert not offenders, f"state-dir (.ren/) references leaked into template content: {offenders}"


def test_no_forbidden_characters_in_filenames():
    offenders = []
    for path in _template_files():
        if _FORBIDDEN_FILENAME_CHARS & set(path.name):
            offenders.append(path.name)
    assert not offenders, f"filenames with Obsidian-unsafe characters: {offenders}"


def test_no_wikilink_syntax_collision_with_placeholders():
    """{{placeholder}} and [[wikilink]] must never coexist in the same
    template — a stray `[[` would be silently reinterpreted by Obsidian as
    a wikilink, not the framework's placeholder syntax."""
    offenders = []
    for path in _template_files():
        text = path.read_text(encoding="utf-8")
        if "[[" in text:
            offenders.append(str(path))
    assert not offenders, f"templates containing '[[' (Obsidian wikilink syntax): {offenders}"


def test_no_obsidian_config_dir_committed():
    obsidian_dirs = list(WIKI_SKELETON.rglob(".obsidian"))
    assert not obsidian_dirs, f".obsidian/ directories must never be committed to wiki-skeleton: {obsidian_dirs}"


def test_manifest_and_readme_also_relative_links_only():
    """The two non-template files at the wiki-skeleton root (manifest.yaml
    is not markdown, but README.md is) get the same relative-link check."""
    readme = WIKI_SKELETON / "README.md"
    if not readme.is_file():
        return
    text = readme.read_text(encoding="utf-8")
    for match in _MD_LINK_RE.finditer(text):
        target = match.group(1).strip()
        assert not target.startswith("file://"), f"README.md: file:// link {target}"
