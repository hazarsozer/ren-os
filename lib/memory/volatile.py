"""lib.memory.volatile — the ren-volatile marker convention (#39, spec §3).

A fact that ages gets tagged inline where it lives:

    RenOS is currently at 0.7.2. <!-- ren-volatile: framework-version -->

The registry maps marker KINDS to mechanical ground-truth checkers. Kinds
without a checker are valid markers but only inventoried, never
auto-corrected — the sweep (wiki-health `stale_facts`) reports them as
"unverifiable" and moves on. Checkers return the current ground-truth value
as a string, or None when it cannot be established (missing repo,
unreadable pyproject) — fail closed: no evidence, no correction.

Staleness test is deliberately dumb-mechanical: the marked LINE is stale
when it does not contain the ground-truth string. No NLP, no fuzzy match —
a false "stale" only queues a correction proposal, which the sweep renders
with the evidence for review.
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from collections import namedtuple
from pathlib import Path
from typing import Callable, Final

MARKER_RE: Final[re.Pattern[str]] = re.compile(
    r"<!--\s*ren-volatile:\s*(?P<kind>[a-z0-9-]+)\s*-->"
)

Marker = namedtuple("Marker", "kind line_no line_text")

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]


def find_markers(md_text: str) -> list[Marker]:
    out: list[Marker] = []
    for i, line in enumerate(md_text.splitlines(), start=1):
        m = MARKER_RE.search(line)
        if m:
            out.append(Marker(kind=m.group("kind"), line_no=i, line_text=line))
    return out


def _framework_version(repo_root: Path) -> str | None:
    pyproject = repo_root / "pyproject.toml"
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        version = data.get("project", {}).get("version")
        return version if isinstance(version, str) else None
    except (OSError, tomllib.TOMLDecodeError):
        return None


def _release_count(repo_root: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "tag", "--list", "v*"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    tags = [t for t in proc.stdout.splitlines() if t.strip()]
    return str(len(tags)) if tags else None


CHECKERS: Final[dict[str, Callable[[Path], str | None]]] = {
    "framework-version": _framework_version,
    "release-count": _release_count,
}


def check_marker(marker: Marker, repo_root: Path | None = None) -> tuple[str, str | None]:
    """(status, ground_truth): "ok" | "stale" | "unverifiable"."""
    checker = CHECKERS.get(marker.kind)
    if checker is None:
        return ("unverifiable", None)
    truth = checker(repo_root or _REPO_ROOT)
    if truth is None:
        return ("unverifiable", None)
    return ("ok" if truth in marker.line_text else "stale", truth)


__all__ = ["MARKER_RE", "Marker", "find_markers", "CHECKERS", "check_marker"]
