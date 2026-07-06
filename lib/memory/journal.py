"""
lib.memory.journal — append-only write journal (Task 1.2, G9 write-safety substrate).

Spec §3.10 "unified write-safety substrate": snapshot, auto-apply logging,
journal, and revert are one owned mechanism, not three fragments. This module
owns the journal piece: one JSON object per line, appended at
`ren_paths.state_dir()/"journal.jsonl"`.

`write_apply.apply_write` appends here LAST, after the page write and its
snapshot are both done — see that module's docstring for why the ordering
matters (it's what makes a crash mid-write detectable: a snapshot dir with no
matching journal entry).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from lib import ren_paths
from lib.memory.provenance import Provenance

JOURNAL_FILENAME = "journal.jsonl"


def _journal_path() -> Path:
    return ren_paths.state_dir() / JOURNAL_FILENAME


def append(prov: Provenance, extra: dict | None = None) -> None:
    """Append one JSON line for `prov` (merged with optional `extra` fields).

    `extra` keys override same-named `prov` fields if both are present (extra
    is spread last). Creates the state dir and journal file on first use.
    """
    path = _journal_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {**asdict(prov), **(extra or {})}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")


def entries(page: str | None = None) -> list[dict]:
    """Return journal entries in append order (newest-last), optionally
    filtered to a single `page`. Returns `[]` if the journal doesn't exist yet."""
    path = _journal_path()
    if not path.exists():
        return []

    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if page is not None and entry.get("page") != page:
            continue
        out.append(entry)
    return out


__all__ = ["append", "entries"]
