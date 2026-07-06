"""
lib.memory.write_apply — THE only function that touches wiki pages
(Task 1.2, G9 unified write-safety substrate).

Spec §3.10: snapshot, auto-apply logging, journal, and revert are one owned
mechanism, not three fragments. `apply_write` is that mechanism's single entry
point — every writer in the framework (wrap gate, consolidate, routines,
promotion) is expected to call through here rather than touching a wiki page
directly, so the lease/snapshot/scrub/journal sequence below is never skipped.

Order, all INSIDE a `locks.lease(page)`:
  1. If `expect_token` is given: `locks.check_token` — raises `LostUpdate`
     before anything else happens if the page changed since the caller last
     read it.
  2. `snapshot.take` — captures the page's PRIOR bytes (or an ABSENT marker)
     under this write's `write_id`, so the write is revertible even if
     everything after this point fails.
  2.5. Scrub `new_content` (if a `lib.memory.scrub` module is importable) —
       refuses BEFORE any page write happens. `scrub` is being built in
       parallel (Task 1.4) and may not exist yet; the import is best-effort so
       this module works standalone until then.
  3. Dispatch by `prov.op`:
       ADD / UPDATE → write `provenance.stamp_frontmatter(new_content, prov)`
                       atomically (temp file + `os.replace`)
       DELETE        → unlink the page (`missing_ok=True`)
       NOOP          → touch nothing
  4. `journal.append(prov)` — written LAST. A crash between step 3 and step 4
     leaves a snapshot dir with no matching journal entry, which is exactly
     the detectable-crash invariant downstream recovery/doctor logic checks
     for: "was this write's snapshot ever followed by a journal line?"
"""

from __future__ import annotations

import os

from lib import ren_paths
from lib.memory import journal, locks, snapshot
from lib.memory.provenance import Provenance, stamp_frontmatter

try:
    from lib.memory import scrub as _scrub
except ImportError:  # pragma: no cover - exercised via monkeypatch until Task 1.4 lands
    _scrub = None


def apply_write(
    page: str,
    new_content: str | None,
    prov: Provenance,
    expect_token: str | None = None,
    journal_extra: dict | None = None,
) -> None:
    """Apply one provenance-stamped write to `page` under an exclusive lease.

    Raises `LeaseHeld` (from `lib.memory.locks`) if another writer already
    holds `page`'s lease, or `LostUpdate` if `expect_token` doesn't match the
    page's current content. See module docstring for the full write order.

    `journal_extra` (Task 6.1 addition): optional extra fields merged into the
    journal line for this write (e.g. `{"auto": True}` for the risk-tier
    model's auto-applied routine writes) — forwarded verbatim to
    `journal.append`'s own `extra` parameter. `None` (the default) preserves
    the original journal-line shape exactly for every pre-existing caller.
    """
    page_abs = ren_paths.safe_join(ren_paths.wiki_root(), page)

    with locks.lease(page):
        if expect_token is not None:
            locks.check_token(page_abs, expect_token)

        snapshot.take(page_abs, prov.write_id)

        if new_content is not None and _scrub is not None:
            _scrub.scrub_or_raise(new_content)

        if prov.op in ("ADD", "UPDATE"):
            if new_content is None:
                raise ValueError(f"op={prov.op!r} requires new_content")
            rendered = stamp_frontmatter(new_content, prov)
            page_abs.parent.mkdir(parents=True, exist_ok=True)
            tmp = page_abs.with_name(page_abs.name + ".tmp")
            tmp.write_text(rendered, encoding="utf-8")
            os.replace(tmp, page_abs)
        elif prov.op == "DELETE":
            page_abs.unlink(missing_ok=True)
        elif prov.op == "NOOP":
            pass
        else:  # pragma: no cover - Provenance.__post_init__ already validates op
            raise ValueError(f"unknown op {prov.op!r}")

        journal.append(prov, journal_extra)


__all__ = ["apply_write"]
