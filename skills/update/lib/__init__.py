"""Update-skill Python helpers (0.3.5).

The update flow's bash scripts own snapshot/restore/semver; this lib holds
the post-update conveniences. ``changelog_digest`` powers the "what changed
in your RenOS" report — best-effort by design: it returns "" rather than
raising, because the digest is a courtesy, never a gate.
"""

from __future__ import annotations

import re
from pathlib import Path

_HEADER_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.MULTILINE)


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def changelog_digest(old: str, new: str, changelog_path: Path) -> str:
    """CHANGELOG.md sections for versions in (old, new], in file order.

    Returns "" when the range is empty, a bound is unparseable, or the
    file is missing/unreadable.
    """
    try:
        text = changelog_path.read_text(encoding="utf-8")
        old_key, new_key = _version_key(old), _version_key(new)
    except (OSError, ValueError):
        return ""
    matches = list(_HEADER_RE.finditer(text))
    sections: list[str] = []
    for i, match in enumerate(matches):
        try:
            key = _version_key(match.group(1))
        except ValueError:
            continue
        if old_key < key <= new_key:
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            sections.append(text[match.start():end].strip())
    return "\n\n".join(sections)
