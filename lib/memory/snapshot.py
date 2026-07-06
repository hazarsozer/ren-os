"""
lib.memory.snapshot — per-write page snapshots (Task 1.2, G9 write-safety substrate).

Spec §3.10 "unified write-safety substrate" + "targeted revert": every write
gets a snapshot of the page's PRIOR state, keyed by that write's `write_id`
(a ULID, so lexicographic sort == chronological order). `write_apply.apply_write`
calls `take()` before touching the page; downstream revert/doctor tooling calls
`restore()` to undo a single write.

Layout: `ren_paths.state_dir()/"snapshots"/<write_id>/<wiki-relative-page-path>`.
A page that doesn't exist yet (this write is an ADD) has no prior bytes to
snapshot — instead an ABSENT marker file (`<page-path>.absent`, sibling to
where the bytes would have gone) records that fact, so `restore()` knows the
correct revert action is "delete the page", not "restore empty bytes" (which
would leave a spurious zero-byte file behind).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from lib import ren_paths

SNAPSHOTS_DIRNAME = "snapshots"
ABSENT_SUFFIX = ".absent"


def _snapshots_root() -> Path:
    return ren_paths.state_dir() / SNAPSHOTS_DIRNAME


def _write_dir(write_id: str) -> Path:
    return _snapshots_root() / write_id


def _paths_for(write_id: str, rel: Path) -> tuple[Path, Path]:
    """Return (snapshot_path, marker_path) for `rel` under `write_id`'s snapshot dir."""
    snapshot_path = _write_dir(write_id) / rel
    marker_path = snapshot_path.with_name(snapshot_path.name + ABSENT_SUFFIX)
    return snapshot_path, marker_path


def take(page_abs: Path, write_id: str) -> Path:
    """Snapshot `page_abs`'s current bytes (or record an ABSENT marker) under
    `write_id`'s snapshot directory. Returns the path written (bytes copy or
    marker file).

    `page_abs` must live under `ren_paths.wiki_root()` — the relative path is
    what keys the snapshot so `restore()` can map back to the same page.
    """
    page_abs = Path(page_abs)
    rel = page_abs.relative_to(ren_paths.wiki_root())
    snapshot_path, marker_path = _paths_for(write_id, rel)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)

    if not page_abs.exists():
        marker_path.write_text("", encoding="utf-8")
        return marker_path

    snapshot_path.write_bytes(page_abs.read_bytes())
    return snapshot_path


def restore(write_id: str, page: str) -> None:
    """Restore `page` (wiki-relative path) from `write_id`'s snapshot.

    If the snapshot recorded an ABSENT marker, the current page is deleted
    (the page didn't exist before that write). Otherwise the snapshot's bytes
    are written back atomically (temp file + `os.replace`).

    Raises `FileNotFoundError` if neither a byte snapshot nor an ABSENT marker
    exists for this `write_id`/`page` pair.
    """
    page_abs = ren_paths.safe_join(ren_paths.wiki_root(), page)
    rel = Path(page)
    snapshot_path, marker_path = _paths_for(write_id, rel)

    if marker_path.exists():
        page_abs.unlink(missing_ok=True)
        return

    if not snapshot_path.exists():
        raise FileNotFoundError(
            f"no snapshot found for write_id={write_id!r} page={page!r}"
        )

    page_abs.parent.mkdir(parents=True, exist_ok=True)
    tmp = page_abs.with_name(page_abs.name + ".tmp")
    tmp.write_bytes(snapshot_path.read_bytes())
    os.replace(tmp, page_abs)


def prune(retain: int) -> None:
    """Keep only the `retain` most-recent write_id snapshot dirs; delete the rest.

    write_id dirs are named `w-<ULID>` — ULIDs are lexicographically sortable
    by creation time, so a plain string sort on the directory name gives
    chronological order without parsing timestamps. `retain <= 0` removes every
    snapshot dir; `retain` at or above the current count is a no-op.
    """
    root = _snapshots_root()
    if not root.is_dir():
        return

    write_dirs = sorted((d for d in root.iterdir() if d.is_dir()), key=lambda d: d.name)
    to_remove = write_dirs[:-retain] if retain > 0 else write_dirs
    for d in to_remove:
        shutil.rmtree(d, ignore_errors=True)


__all__ = ["take", "restore", "prune"]
