"""
sf-consolidate link repair — C3c dead-link housekeeping sweep.

A faithful Python port of doctor's `check-wiki-health.sh` dead-link DETECTION,
extended with a deterministic, conservative REPAIR proposer. Pure logic over a
`{repo_relpath: text}` mapping — no disk, no LLM; the diff it builds is verified
by `git apply`. The prompt layer orchestrates scan → propose → gate → apply.
"""

from __future__ import annotations

import difflib
import posixpath
import re

from .diffs import unified_diff
from .types import DeadLink, LinkRepair, PromotionDiff

# Wikilink: [[target]] or [[target|alias]]. group(1)=target, group(2)=alias.
_WIKILINK_RE = re.compile(r"\[\[([^\]\|]+?)(?:\|([^\]]*))?\]\]")
# Markdown link to a .md file: ](path.md) or ](path.md#anchor). group(1)=path.
_MDLINK_RE = re.compile(r"\]\(([^)]+?\.md)(?:#[^)]*)?\)")

_FUZZY_CUTOFF = 0.8


def _slug(relpath: str) -> str:
    return posixpath.splitext(posixpath.basename(relpath))[0]


def build_slug_index(pages: dict[str, str]) -> dict[str, str]:
    """basename-without-ext → relpath (first wins, mirroring check-wiki-health.sh)."""
    index: dict[str, str] = {}
    for relpath in pages:
        index.setdefault(_slug(relpath), relpath)
    return index


def build_basename_index(pages: dict[str, str]) -> dict[str, list[str]]:
    """basename.md → [relpaths] (for mdlink relocation; >1 ⇒ ambiguous)."""
    index: dict[str, list[str]] = {}
    for relpath in pages:
        index.setdefault(posixpath.basename(relpath), []).append(relpath)
    return index


def find_dead_links(pages: dict[str, str]) -> tuple[DeadLink, ...]:
    """
    Scan every page for dead `[[wikilinks]]` and `](file.md)` links.

    A wikilink is dead if its target slug is not a known page slug. A markdown
    link is dead if it doesn't resolve (relative to the source page) to a known
    page; `http(s)` targets are ignored. One record per dead occurrence, in page
    then line then column order.
    """
    slug_index = build_slug_index(pages)
    dead: list[DeadLink] = []
    for relpath, text in pages.items():
        src_dir = posixpath.dirname(relpath)
        for line_no, line in enumerate(text.split("\n")):
            for m in _WIKILINK_RE.finditer(line):
                target = m.group(1).strip()
                if target not in slug_index:
                    dead.append(DeadLink(
                        source_relpath=relpath, form="wikilink", raw_target=target,
                        alias=m.group(2), old_literal=m.group(0),
                        line_no=line_no, raw_line=line,
                    ))
            for m in _MDLINK_RE.finditer(line):
                target = m.group(1)
                if target.startswith(("http://", "https://")):
                    continue
                resolved = posixpath.normpath(posixpath.join(src_dir, target))
                if resolved not in pages:
                    dead.append(DeadLink(
                        source_relpath=relpath, form="mdlink", raw_target=target,
                        alias=None, old_literal=m.group(0),
                        line_no=line_no, raw_line=line,
                    ))
    return tuple(dead)


def propose_link_repair(
    dead: DeadLink,
    slug_index: dict[str, str],
    basename_index: dict[str, list[str]],
) -> LinkRepair | None:
    """
    Propose a deterministic, conservative fix for one dead link.

    Returns `None` when there is no confident candidate — the sweep reports those
    for manual fixing rather than guessing (it never removes a link or invents a
    target). Wikilinks fuzzy-match the slug pool (cutoff 0.8); markdown links
    relocate only on an unambiguous basename match.
    """
    if dead.form == "wikilink":
        match = difflib.get_close_matches(
            dead.raw_target, list(slug_index), n=1, cutoff=_FUZZY_CUTOFF
        )
        if not match:
            return None
        new_target = match[0]
        new_literal = dead.old_literal.replace(dead.raw_target, new_target, 1)
        return LinkRepair(
            dead=dead, new_target=new_target, new_literal=new_literal,
            rationale=f"fuzzy-match dead [[{dead.raw_target}]] → [[{new_target}]]",
        )

    # mdlink — relocate only on an exact, unambiguous basename match.
    candidates = basename_index.get(posixpath.basename(dead.raw_target), [])
    if len(candidates) != 1:
        return None
    new_rel = posixpath.relpath(candidates[0], posixpath.dirname(dead.source_relpath))
    new_literal = dead.old_literal.replace(dead.raw_target, new_rel, 1)
    return LinkRepair(
        dead=dead, new_target=new_rel, new_literal=new_literal,
        rationale=f"relocate dead link {dead.raw_target} → {new_rel}",
    )


def build_link_repair_diffs(
    page_relpath: str,
    page_text: str,
    repairs: tuple[LinkRepair, ...],
) -> PromotionDiff:
    """
    Compose all `repairs` for ONE page into a single git-apply-compatible diff.

    Repairs are grouped by line so multiple links on one line — or across several
    lines — coalesce into one `PromotionDiff(kind="link-fix")`. Applying N
    independent same-file diffs would fail the 2nd `git apply` (apply.py applies
    in order against the working tree), so one diff per page is the safe unit.
    """
    lines = page_text.split("\n")
    by_line: dict[int, list[LinkRepair]] = {}
    for repair in repairs:
        by_line.setdefault(repair.dead.line_no, []).append(repair)
    for line_no, line_repairs in by_line.items():
        line = lines[line_no]
        for repair in line_repairs:
            line = line.replace(repair.dead.old_literal, repair.new_literal, 1)
        lines[line_no] = line
    new_text = "\n".join(lines)
    return PromotionDiff(
        target_file=page_relpath,
        unified_diff=unified_diff(page_relpath, page_text, new_text),
        kind="link-fix",
        rationale=f"fix {len(repairs)} dead link(s) in {page_relpath}",
    )


__all__ = [
    "build_slug_index",
    "build_basename_index",
    "find_dead_links",
    "propose_link_repair",
    "build_link_repair_diffs",
]
