"""
lib.memory.revert — G4 targeted revert (Task 2.3, RenOS 0.2 Phase 2).

Spec §3.10 "Memory Integrity & Recovery": "revert a single memory entry in one
step; downstream entries citing it get flagged." Built on the write-safety
substrate Task 1.2 already lands: `journal` (find what write_id touched),
`snapshot` (restore its prior bytes / delete if it was an ADD), and `locks`
(guard the restore with the same lease `write_apply` uses for writes).

Reverts are themselves journaled — never a silent rewrite. `revert()` appends a
NEW provenance record (op="NOOP", writer="human") carrying `revert_of` so the
journal shows exactly when and by what a prior write was undone, same as any
other write.

Citer detection is deliberately coarse (three cheap, explainable checks — see
`_find_citers`), matching the heuristic-first spirit of `lib.memory.semantics`:
this flags pages a human should re-check, it doesn't understand their content.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from lib import ren_paths
from lib.memory import journal, locks, snapshot
from lib.memory.provenance import new_provenance, read_frontmatter_provenance

_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


@dataclass(frozen=True)
class RevertResult:
    write_id: str
    page: str
    restored: bool          # True = bytes restored / ADD-deleted
    citers: list[str]       # wiki-relative paths of pages referencing the reverted write


def _find_journal_entry(write_id: str) -> dict:
    for entry in journal.entries():
        if entry.get("write_id") == write_id:
            return entry
    raise KeyError(f"no journal entry found for write_id={write_id!r}")


def _links_to_page(text: str, page: str) -> bool:
    page_name = Path(page).name
    for match in _MD_LINK_RE.finditer(text):
        target = match.group(1).split("#", 1)[0].strip()
        target = target[2:] if target.startswith("./") else target
        if target == page or target == page_name:
            return True
    return False


def _find_citers(write_id: str, page: str) -> list[str]:
    wiki_root = ren_paths.wiki_root()
    if not wiki_root.is_dir():
        return []

    citers: list[str] = []
    for md_path in sorted(wiki_root.rglob("*.md")):
        rel = str(md_path.relative_to(wiki_root))
        if rel == page:
            continue  # never cite the reverted page against itself

        text = md_path.read_text(encoding="utf-8")

        prov = read_frontmatter_provenance(text)
        cites_via_frontmatter = bool(prov) and prov.get("supersedes") == write_id
        cites_via_mention = write_id in text
        cites_via_link = _links_to_page(text, page)

        if cites_via_frontmatter or cites_via_mention or cites_via_link:
            citers.append(rel)

    return citers


def revert(write_id: str) -> RevertResult:
    """Undo the single write identified by `write_id`.

    Raises `KeyError` if no journal entry carries this `write_id`.

    Steps: locate the journal entry for `write_id` to learn its `page`; under
    that page's lease, `snapshot.restore` the prior bytes (or delete the page,
    if the write being reverted was an ADD); append a new NOOP provenance
    record journaling the revert itself; scan the wiki for citers.
    """
    entry = _find_journal_entry(write_id)
    page = entry["page"]

    with locks.lease(page):
        snapshot.restore(write_id, page)

    revert_prov = new_provenance(
        writer="human",
        session=os.environ.get(locks.SESSION_ID_ENV, "unknown"),
        op="NOOP",
        page=page,
    )
    journal.append(revert_prov, extra={"revert_of": write_id})

    citers = _find_citers(write_id, page)

    return RevertResult(write_id=write_id, page=page, restored=True, citers=citers)


__all__ = ["RevertResult", "revert"]
