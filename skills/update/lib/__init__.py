"""Update-skill Python helpers (0.3.5).

The update flow's bash scripts own snapshot/restore/semver; this lib holds
the post-update conveniences. ``changelog_digest`` powers the "what changed
in your RenOS" report — best-effort by design: it returns "" rather than
raising, because the digest is a courtesy, never a gate.
"""

from __future__ import annotations

import re
from pathlib import Path

from lib.ren_paths import wiki_root

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


_PROJECT_KNOWLEDGE_GATE = "0.6.2"


def should_run_project_knowledge_1(old: str, new: str) -> bool:
    """True when an update crosses the 0.6.2 boundary (old < 0.6.2 <= new).

    Gates ``migrations/project-knowledge-1/migrate.py`` (see that migration's
    README) the same way ``should_run_trust_backfill`` gates its migration:
    a pure version-tuple comparison, no chain machinery, because
    project-knowledge-1 is a standalone global migration that walks whole
    ``projects/<slug>/`` directories rather than a schema_version-keyed
    page type.
    """
    try:
        old_key, new_key, gate_key = (
            _version_key(old),
            _version_key(new),
            _version_key(_PROJECT_KNOWLEDGE_GATE),
        )
    except ValueError:
        return False
    return old_key < gate_key <= new_key


_FOREIGN_REMINT_GATE = "0.6.3"


def should_run_foreign_remint_1(old: str, new: str) -> bool:
    """True when an update crosses the 0.6.3 boundary (old < 0.6.3 <= new).

    Gates ``migrations/foreign-remint-1/migrate.py`` (see that migration's
    README) the same way ``should_run_trust_backfill`` gates its migration:
    a pure version-tuple comparison, no chain machinery, because
    foreign-remint-1 is a standalone global migration (issue #22 — restamp
    mis-minted ``ren_trust: "foreign"`` ingest drafts to ``"model"``) that
    walks the whole wiki tree rather than a schema_version-keyed page type.
    """
    try:
        old_key, new_key, gate_key = (
            _version_key(old),
            _version_key(new),
            _version_key(_FOREIGN_REMINT_GATE),
        )
    except ValueError:
        return False
    return old_key < gate_key <= new_key


def should_run_folder_note_hubs_1(wiki_root_path: Path | None = None) -> bool:
    """True if any legacy knowledge-hub index.md remains (raw/, archive/, dot-dirs excluded).

    Unlike ``should_run_trust_backfill``/``should_run_project_knowledge_1``/
    ``should_run_foreign_remint_1``, this gate is idempotent-by-inspection
    rather than version-crossing: ``migrations/folder-note-hubs-1/migrate.py``
    (issue #56) renames `projects/*/knowledge/**/index.md` to
    `<parent-dir>.md`, so the gate just checks whether any such legacy hub
    still exists — same fail-safe reasoning as the migration's own verifier
    (`migrations/folder-note-hubs-1/verify.py`).
    """
    root = wiki_root_path or wiki_root()
    for knowledge in root.glob("projects/*/knowledge"):
        for p in knowledge.rglob("index.md"):
            rel = p.relative_to(root)
            if any(part.startswith(".") or part in ("raw", "archive") for part in rel.parts):
                continue
            return True
    return False
