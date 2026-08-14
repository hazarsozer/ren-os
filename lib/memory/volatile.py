"""lib.memory.volatile — the ren-volatile marker convention (#39, spec §3).

A fact that ages gets tagged inline where it lives:

    RenOS is currently at 0.7.2. <!-- ren-volatile: framework-version -->

The registry maps marker KINDS to mechanical ground-truth checkers. Kinds
without a checker are valid markers but only inventoried, never
auto-corrected — the sweep (wiki-health `stale_facts`) reports them as
"unverifiable" and moves on. Checkers return the current ground-truth value
as a string, or None when it cannot be established (no reachable git repo,
no resolvable framework version) — fail closed: no evidence, no correction.
Note "zero" is a value, not an absence: a real repo with no `v*` tags yields
`"0"`, never None.

Staleness test is deliberately dumb-mechanical: the marked LINE is stale
when it does not contain the ground-truth string. No NLP, no fuzzy match —
a false "stale" only queues a correction proposal, which the sweep renders
with the evidence for review.
"""

from __future__ import annotations

import re
import subprocess
from collections import namedtuple
from pathlib import Path
from typing import Callable, Final

from lib import ren_paths

MARKER_RE: Final[re.Pattern[str]] = re.compile(
    r"<!--\s*ren-volatile:\s*(?P<kind>[a-z0-9-]+)\s*-->"
)

Marker = namedtuple("Marker", "kind line_no line_text")

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

#: Project slug of the framework's own repo — the "ren-os repo" spec §3 names
#: as ground truth for `release-count`.
FRAMEWORK_PROJECT_SLUG: Final[str] = "ren-os"


def find_markers(md_text: str) -> list[Marker]:
    out: list[Marker] = []
    for i, line in enumerate(md_text.splitlines(), start=1):
        m = MARKER_RE.search(line)
        if m:
            out.append(Marker(kind=m.group("kind"), line_no=i, line_text=line))
    return out


def _framework_version(repo_root: Path) -> str | None:
    """Installed framework version via the canonical resolver
    (`ren_paths.framework_version()`: plugin-option env → plugin.json →
    shipped fallback). Fix round 2: the old direct `pyproject.toml` parse
    read a file that does not exist in an installed plugin cache, so the
    checker was dead everywhere except a dev checkout — and it could
    disagree with the version every other surface reports. `repo_root` is
    unused (kept for the `CHECKERS` callable shape); None only when the
    resolver itself can't produce a non-empty string."""
    del repo_root  # unused — the version is resolved canonically, not from disk
    try:
        version = ren_paths.framework_version()
    except Exception:  # noqa: BLE001 - fail closed: no evidence, no correction
        return None
    return version if isinstance(version, str) and version.strip() else None


def _repo_root_candidates(repo_root: Path | None) -> list[Path]:
    """Ordered candidates for "the ren-os repo" a git-backed checker reads.

    1. An explicit `repo_root` — when the caller names one, it is the ONLY
       candidate (tests, and any caller that already knows the repo).
    2. The dev checkout, if the friend's projects registry records one for
       this framework's own slug (`ren_paths.load_project_registry()`), else
       the conventional `<dev root>/ren-os` (`ren_paths.resolve_dev_root()`).
    3. `_REPO_ROOT` — this file's own package root, correct in a bare
       checkout and meaningless in an installed plugin cache (no `.git`).

    Fix round 2 (#I3): `_REPO_ROOT` alone made the release-count checker dead
    on an installed plugin, where the code lives in the plugin cache.
    """
    if repo_root is not None:
        return [repo_root]
    candidates: list[Path] = []
    try:
        registry = ren_paths.load_project_registry()
        recorded = registry.get(FRAMEWORK_PROJECT_SLUG, {}).get("repo_path")
        if isinstance(recorded, str) and recorded:
            candidates.append(Path(recorded))
    except Exception:  # noqa: BLE001 - a broken registry just means one fewer candidate
        pass
    try:
        candidates.append(ren_paths.resolve_dev_root() / FRAMEWORK_PROJECT_SLUG)
    except Exception:  # noqa: BLE001 - same
        pass
    candidates.append(_REPO_ROOT)
    # Preserve order, drop duplicates.
    seen: set[str] = set()
    out: list[Path] = []
    for cand in candidates:
        key = str(cand)
        if key not in seen:
            seen.add(key)
            out.append(cand)
    return out


def _release_count(repo_root: Path | None = None) -> str | None:
    """Count of `v*` tags in the ren-os repo, as a string.

    `"0"` — NOT None — for a real git repo that simply has no matching tags:
    zero releases is established ground truth, and returning None there made
    a genuinely-zero-tag repo indistinguishable from "no repo at all"
    (fix round 2, #I3). None is reserved for the case where git can't run or
    no candidate root is a git repo — no evidence, no correction.
    """
    for candidate in _repo_root_candidates(repo_root):
        try:
            proc = subprocess.run(
                ["git", "-C", str(candidate), "tag", "--list", "v*"],
                capture_output=True, text=True, timeout=10, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if proc.returncode != 0:
            continue  # not a repo (or git refused) — try the next candidate
        return str(len([t for t in proc.stdout.splitlines() if t.strip()]))
    return None


CHECKERS: Final[dict[str, Callable[[Path], str | None]]] = {
    "framework-version": _framework_version,
    "release-count": _release_count,
}


def check_marker(marker: Marker, repo_root: Path | None = None) -> tuple[str, str | None]:
    """(status, ground_truth): "ok" | "stale" | "unverifiable"."""
    checker = CHECKERS.get(marker.kind)
    if checker is None:
        return ("unverifiable", None)
    # `repo_root=None` is passed THROUGH (not defaulted to `_REPO_ROOT`
    # here) so a git-backed checker can walk its own candidate list —
    # `_REPO_ROOT` is only the last of those (fix round 2, #I3).
    truth = checker(repo_root)
    if truth is None:
        return ("unverifiable", None)
    return ("ok" if truth in marker.line_text else "stale", truth)


__all__ = ["MARKER_RE", "Marker", "find_markers", "CHECKERS", "check_marker"]
