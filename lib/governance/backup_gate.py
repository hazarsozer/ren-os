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

"Populated" is deliberately CONTENT-BEARING-ONLY (fix round 1, direction (b)).
The first cut scanned every `*.md` under the wiki root for a "not just a
heading and/or HTML comments" body — which false-positived on the REAL
skeleton: the shipped `wiki-skeleton/templates/*.tmpl` pages (`index.md`,
`identity.md`, `log.md`, `LICENSES.md`) all carry guidance prose, so a
pristine post-`/ren:install` wiki looked populated and a friend's FIRST
ingest-project (or SECOND bootstrap-project) tripped the gate with nothing of
theirs actually at risk.

So the scan now only looks where the friend's OWN content can land:
`_CONTENT_DIRS` (`research/`, `decisions/`, `alternatives/`, `patterns/`,
`maps/`, `projects/`) plus `log.md` having entries beyond the single stamped
`init` one. Inside those dirs the heading/HTML-comment-only check still
applies, which is exactly right for the one template stamped there
(`projects/<slug>/overview.md`, whose skeleton body IS heading + comment).

Tradeoff, stated: a filled-in `identity.md` or `venture/*.md` alone does not
trip the gate. Those are onboarding profile pages, cheap to re-run
(`/ren:interview`), and not the destructive write target this gate protects
(bootstrap/ingest meeting an existing project page). Any real session that
grows them also writes a `log.md` entry, which does trip it.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from skills.backup.lib import backup_configured

OVERRIDE_ENV_VAR = "RENOS_ALLOW_NO_BACKUP"

_CONTENT_DIRS = ("research", "decisions", "alternatives", "patterns", "maps", "projects")
"""Wiki subtrees where the friend's OWN knowledge lands. Root-level skeleton
pages (`index.md`, `identity.md`, `LICENSES.md`) are intentionally excluded —
their shipped templates carry guidance prose, see module docstring."""

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


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def _log_has_entries_beyond_init(wiki_root: Path) -> bool:
    """The stamped `log.md` holds exactly one `## [<date>] init | ...` entry;
    anything more means the friend has real history worth backing up."""
    text = _read(wiki_root / "log.md")
    if text is None:
        return False
    body = _FRONTMATTER_RE.sub("", text, count=1)
    entries = [line for line in body.splitlines() if line.startswith("## [")]
    return len(entries) > 1


def _wiki_is_populated(wiki_root: Path) -> bool:
    if not wiki_root.is_dir():
        return False
    for content_dir in _CONTENT_DIRS:
        for path in (wiki_root / content_dir).rglob("*.md"):
            text = _read(path)
            if text is not None and _is_grown_page(text):
                return True
    return _log_has_entries_beyond_init(wiki_root)


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
