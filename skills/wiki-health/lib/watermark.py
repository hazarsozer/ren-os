"""
skills.wiki-health.lib.watermark — lint watermark + incremental journal
selection (Task 2, RenOS 0.6.5 "shipped agents" train).

Task 1 made `wrap_session` append one `_wrap-session` journal line per session
carrying a `wrap_summary` (pages touched, apply/hold/refuse counts). This
module lets a lint pass track how far it has gotten through the append-only
journal so it only re-checks pages that changed since the last pass, instead
of re-walking the whole wiki every time:

- `read_watermark()` / `advance_watermark()` persist a small stamp —
  `{journal_lines_seen, clean, stamped_at}` — at
  `ren_paths.state_dir()/wiki_lint_watermark.json`. Framework bookkeeping, not
  user knowledge (see `docs/audits/2026-07-destructive-writes.md`), so a
  corrupt or missing stamp just degrades to "lint everything" rather than
  raising.
- `unlinted()` reads the journal, slices off everything at/after the stamped
  offset, and returns how many lines are new plus the sorted distinct pages
  they touched — pulled from ordinary per-write lines' `page` field and from
  `_wrap-session` lines' `wrap_summary.pages_touched`. Pseudo-pages (any name
  starting with `_`, e.g. `_wrap-session` itself) are excluded since they
  aren't lintable wiki pages.

Tasks 3 and 5 are the consumers: Task 3 runs the incremental lint over
`unlinted()`'s pages and then calls `advance_watermark`; Task 5 uses
`unlinted()` to decide whether to nudge the friend at wake-up.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from lib import ren_paths
from lib.memory import journal

WATERMARK_FILENAME = "wiki_lint_watermark.json"


def _path():
    return ren_paths.state_dir() / WATERMARK_FILENAME


def read_watermark() -> dict:
    """Return the stamped watermark, or `{}` if missing/corrupt."""
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def advance_watermark(lines_seen: int, clean: bool) -> None:
    """Atomically stamp the watermark at `lines_seen` journal lines."""
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps({
            "journal_lines_seen": lines_seen,
            "clean": clean,
            "stamped_at": datetime.now(timezone.utc).isoformat(),
        }),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def unlinted() -> tuple[int, list[str]]:
    """Return (count of journal lines past the watermark, sorted distinct
    pages they touched), excluding `_`-prefixed pseudo-pages."""
    entries = journal.entries()
    seen = int(read_watermark().get("journal_lines_seen", 0))
    fresh = entries[seen:]

    pages: set[str] = set()
    for entry in fresh:
        summary = entry.get("wrap_summary")
        if summary:
            pages.update(p for p in summary.get("pages_touched", []) if not p.startswith("_"))
        else:
            page = entry.get("page", "")
            if page and not page.startswith("_"):
                pages.add(page)

    return len(fresh), sorted(pages)


__all__ = ["read_watermark", "advance_watermark", "unlinted", "WATERMARK_FILENAME"]
