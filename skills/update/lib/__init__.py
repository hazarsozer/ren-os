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
_ANY_HEADER_RE = re.compile(r"^## \[", re.MULTILINE)


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

    # Compute boundaries from ALL headers (including prerelease ones).
    boundaries = sorted(m.start() for m in _ANY_HEADER_RE.finditer(text))

    matches = list(_HEADER_RE.finditer(text))
    sections: list[str] = []
    for match in matches:
        try:
            key = _version_key(match.group(1))
        except ValueError:
            continue
        if old_key < key <= new_key:
            # Find the next boundary strictly greater than match.start().
            end = next((b for b in boundaries if b > match.start()), len(text))
            sections.append(text[match.start():end].strip())
    return "\n\n".join(sections)


_TRUST_BACKFILL_GATE = "0.5.1"


def should_run_trust_backfill(old: str, new: str) -> bool:
    """True when an update crosses the 0.5.1 boundary (old < 0.5.1 <= new).

    Gates ``migrations/trust-backfill-1/migrate.py`` (see that migration's
    README) the same way `changelog_digest`'s range check gates the digest:
    a pure version-tuple comparison, no chain machinery involved, because
    trust-backfill-1 is a standalone global migration (not part of
    `skills/wiki-migration`'s page-type chain — see
    `skills/wiki-migration/schemas.json`'s `global_migrations` note).
    """
    try:
        old_key, new_key, gate_key = (
            _version_key(old),
            _version_key(new),
            _version_key(_TRUST_BACKFILL_GATE),
        )
    except ValueError:
        return False
    return old_key < gate_key <= new_key
