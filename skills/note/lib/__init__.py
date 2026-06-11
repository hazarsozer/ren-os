"""
sf-note library — internal implementation for /ren:note.

Single public entry: `pin_note(text, *, session_id, notes_root) -> PinResult`.

Pure-filesystem skill — no LLM calls, no subprocess. Fully testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final


# Locked path convention per team-lead (framework root: ~/.startup-framework/)
DEFAULT_NOTES_DIRNAME: Final[str] = ".session-notes"
UNSESSIONED_FILENAME: Final[str] = "unsessioned-notes.md"
TIMESTAMP_FORMAT: Final[str] = "%Y-%m-%dT%H:%M:%SZ"  # ISO-8601 UTC


@dataclass(frozen=True)
class PinResult:
    """Result of a /ren:note invocation."""

    success: bool
    path: Path | None        # the file written to (None on failure)
    appended_line: str       # the bullet that was appended (for confirmation rendering)
    error: str | None = None # error message on failure


def resolve_notes_path(
    *,
    session_id: str | None,
    notes_root: Path,
) -> Path:
    """
    Resolve which .session-notes/ file the pin goes to.

    Args:
        session_id: Active session id, or None if not resolvable.
        notes_root: Path to the .session-notes/ directory (created if missing
            by the writer; this function doesn't side-effect the filesystem).

    Returns:
        Absolute path to the target file. Either:
          - `<notes_root>/<session_id>.md` if session_id is a non-empty,
            safe filename component
          - `<notes_root>/unsessioned-notes.md` otherwise

    Note: session_id is sanitized — only [a-zA-Z0-9_-] allowed. If the
    session_id contains other characters (e.g., path separators), we fall
    back to unsessioned to avoid path-traversal.
    """
    if not session_id:
        return notes_root / UNSESSIONED_FILENAME

    # Defensive sanitization against accidental or hostile session ids
    safe = "".join(c for c in session_id if c.isalnum() or c in "_-")
    if not safe or safe != session_id:
        return notes_root / UNSESSIONED_FILENAME

    return notes_root / f"{safe}.md"


def format_bullet(text: str, *, now: datetime | None = None) -> str:
    """
    Format a single note bullet:

        - [YYYY-MM-DDTHH:MM:SSZ] <text>

    Args:
        text: The user-supplied text. Newlines inside are replaced with `\\n`
            (literal escape) to preserve the single-bullet invariant.
        now: Override the timestamp (for tests).

    Returns:
        The formatted line (with trailing newline).
    """
    ts = (now or datetime.now(timezone.utc)).strftime(TIMESTAMP_FORMAT)
    safe_text = text.replace("\n", "\\n").rstrip()
    return f"- [{ts}] {safe_text}\n"


def _header_for(session_id: str | None) -> str:
    if session_id:
        return f"# Session notes — {session_id}\n\n"
    return "# Unsessioned notes\n\n"


def pin_note(
    text: str,
    *,
    session_id: str | None,
    notes_root: Path,
    now: datetime | None = None,
) -> PinResult:
    """
    Append a single note bullet to the appropriate session-notes file.

    Args:
        text: The user-supplied text. Must be non-empty (whitespace-only counts as empty).
        session_id: Active session id, or None to use unsessioned-notes.md.
        notes_root: Path to the .session-notes/ directory. Created if missing.
        now: Override the timestamp (for tests).

    Returns:
        PinResult with success=True + the path written, or success=False + error message.
    """
    stripped = text.strip()
    if not stripped:
        return PinResult(
            success=False,
            path=None,
            appended_line="",
            error="Empty text. Usage: /ren:note <text>",
        )

    try:
        notes_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return PinResult(
            success=False,
            path=None,
            appended_line="",
            error=f"Could not create notes directory {notes_root}: {exc}",
        )

    target = resolve_notes_path(session_id=session_id, notes_root=notes_root)
    bullet = format_bullet(stripped, now=now)

    try:
        if not target.exists():
            target.write_text(_header_for(session_id) + bullet, encoding="utf-8")
        else:
            with target.open("a", encoding="utf-8") as fh:
                fh.write(bullet)
    except OSError as exc:
        return PinResult(
            success=False,
            path=target,
            appended_line=bullet,
            error=f"Could not write to {target}: {exc}",
        )

    return PinResult(success=True, path=target, appended_line=bullet, error=None)


__all__ = [
    "DEFAULT_NOTES_DIRNAME",
    "UNSESSIONED_FILENAME",
    "TIMESTAMP_FORMAT",
    "PinResult",
    "resolve_notes_path",
    "format_bullet",
    "pin_note",
]
