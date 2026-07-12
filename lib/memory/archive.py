"""
lib.memory.archive — the archive tier (Task 16, RenOS 0.5.3 "learning brain").

Spec: archive-never-delete. A page that's no longer live isn't deleted — it's
moved to `archive/<rel>` (the archive copy carries the FULL prior content plus
`archived_from`/`archive_reason` frontmatter stamps), and the original is then
journaled-DELETEd. Both writes go through `write_apply.apply_write`, the
single write door (Task 1.2) — never a raw file move.

Recovery does NOT depend on snapshot retention (Codex R7 amendment):
snapshots prune to `snapshot.retain_setting()` (default 50), but the archive
copy itself is the durable, full-content recovery path — a page can be
restored by reading `archive/<rel>` and writing it back, long after the
DELETE write's own snapshot has been pruned away. `unarchive_page` is
deliberately NOT built here — restoration goes through the existing journal
revert (`lib.memory.revert.revert`, called on both write_ids) or a plain
write of the archive copy's content back to the original page.

Both writes are stamped `writer="routine"` — a non-`global/` memory write
from any writer class resolves to the "auto" tier
(`lib.governance.tiers.tier_of`), so this is safe to call unattended.
"""

from __future__ import annotations

import re

from lib import ren_paths
from lib.memory import write_apply
from lib.memory.provenance import new_provenance

ARCHIVE_PREFIX = "archive/"
GLOBAL_PREFIX = "global/"

_ARCHIVE_KEY_RE = re.compile(r"^(archived_from|archive_reason):")
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)


def is_archived(rel: str) -> bool:
    """True if `rel` is already under the archive prefix."""
    return rel.startswith(ARCHIVE_PREFIX)


def _upsert_archive_frontmatter(md_text: str, archived_from: str, archive_reason: str) -> str:
    """Upsert `archived_from`/`archive_reason` into `md_text`'s frontmatter,
    same targeted line-level rewrite strategy as
    `provenance.stamp_frontmatter` — every other key and the body are left
    untouched, byte-for-byte."""
    new_lines = [
        f'archived_from: "{archived_from}"',
        f'archive_reason: "{archive_reason}"',
    ]
    match = _FRONTMATTER_RE.match(md_text)
    if match is None:
        fence = "---\n" + "\n".join(new_lines) + "\n---\n"
        return fence + md_text

    fm_content = match.group(1)
    body = md_text[match.end():]
    kept_lines = [line for line in fm_content.split("\n") if not _ARCHIVE_KEY_RE.match(line)]
    if kept_lines and kept_lines[-1] == "":
        kept_lines.pop()

    rebuilt_content = "\n".join(kept_lines + new_lines)
    return f"---\n{rebuilt_content}\n---\n{body}"


def archive_page(rel: str, session: str, *, reason: str) -> dict:
    """Move `rel` to `archive/<rel>`: a journaled ADD of the archive copy
    (original content, `archived_from`/`archive_reason` stamped), then a
    journaled DELETE of the original (`journal_extra={"archived_to": ...}`).

    Raises `ValueError` for a `global/` page (instruction plane, never
    archived this way) or a page that's already under `archive/`.

    Returns `{"archive_page": <archive rel path>, "add_write_id": ...,
    "delete_write_id": ...}`.
    """
    if rel == "global" or rel.startswith(GLOBAL_PREFIX):
        raise ValueError(f"cannot archive global page {rel!r}")
    if is_archived(rel):
        raise ValueError(f"page {rel!r} is already archived")

    page_abs = ren_paths.safe_join(ren_paths.wiki_root(), rel)
    original_content = page_abs.read_text(encoding="utf-8")

    archive_rel = ARCHIVE_PREFIX + rel
    archived_content = _upsert_archive_frontmatter(original_content, rel, reason)

    add_prov = new_provenance("routine", session, "ADD", archive_rel)
    write_apply.apply_write(archive_rel, archived_content, add_prov)

    delete_prov = new_provenance("routine", session, "DELETE", rel)
    write_apply.apply_write(
        rel, None, delete_prov, journal_extra={"archived_to": archive_rel}
    )

    return {
        "archive_page": archive_rel,
        "add_write_id": add_prov.write_id,
        "delete_write_id": delete_prov.write_id,
    }


__all__ = ["ARCHIVE_PREFIX", "is_archived", "archive_page"]
