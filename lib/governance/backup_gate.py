"""
lib.governance.backup_gate — backup precondition before the first
ingest-project/bootstrap-project write on a POPULATED wiki (0.6.0 Task 4,
issue #11 §2).

Two of the last four releases fixed data-destroying bugs (docs/audits/
2026-07-destructive-writes.md flags bootstrap/ingest's destructive-meeting-
existing-file class as exactly the write path this protects). A configured
backup (`skills.backup.lib.backup_configured`) is the only real mitigation,
and until now it's been a skippable install-time offer, not a precondition.

`require_backup` is the gate: no-op on a fresh/empty wiki (nothing grown yet
to lose — the very first bootstrap must be able to run before there's
anything to back up, or friend #1 can never get started), and raises
`BackupRequired` when the wiki already holds grown content AND no backup is
configured. `RENOS_ALLOW_NO_BACKUP=1` downgrades the raise to a loud stderr
warning so an unattended/CI run (or a friend who's made an informed choice)
can still proceed.

"Populated" reuses the same idea as `skills.wrap.lib._is_skeleton_or_empty_body`
(a page with only a heading and/or HTML comments carries no real content) —
generalized here across every markdown page under the wiki root rather than
one page's specific shape, since the brief's contract is "any non-skeleton
page exists", not "the overview page specifically."
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from skills.backup.lib import backup_configured

OVERRIDE_ENV_VAR = "RENOS_ALLOW_NO_BACKUP"

_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n?", re.DOTALL)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


class BackupRequired(Exception):
    """Raised by `require_backup` when `operation` would touch a populated
    wiki and no backup is configured, without the override env var set."""


def _is_grown_page(text: str) -> bool:
    """True if `text` (a whole markdown file, frontmatter included) carries
    real content beyond a bare skeleton page — a heading and/or HTML
    comments only, or nothing at all, doesn't count."""
    body = _FRONTMATTER_RE.sub("", text, count=1)
    body = _HTML_COMMENT_RE.sub("", body)
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines:
        return False
    return not all(line.startswith("#") for line in lines)


def _wiki_is_populated(wiki_root: Path) -> bool:
    if not wiki_root.is_dir():
        return False
    for path in wiki_root.rglob("*.md"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if _is_grown_page(text):
            return True
    return False


def require_backup(wiki_root: Path, *, operation: str) -> None:
    """Gate `operation` (e.g. `"ingest-project"`, `"bootstrap-project"`) on a
    configured backup, but only once the wiki holds grown content. No-op on
    a fresh/empty wiki. Raises `BackupRequired` unless `RENOS_ALLOW_NO_BACKUP=1`
    is set, in which case it prints a loud stderr warning and returns."""
    if not _wiki_is_populated(wiki_root):
        return
    if backup_configured(wiki_root):
        return

    message = (
        f"{operation} can overwrite grown wiki content and no backup is "
        f"configured. Run /ren:backup once, or set {OVERRIDE_ENV_VAR}=1 to "
        "proceed at your own risk."
    )
    if os.environ.get(OVERRIDE_ENV_VAR) == "1":
        print(f"WARNING: no backup configured — proceeding anyway ({operation}, {OVERRIDE_ENV_VAR}=1 set)", file=sys.stderr)
        return
    raise BackupRequired(message)


__all__ = ["BackupRequired", "require_backup"]
