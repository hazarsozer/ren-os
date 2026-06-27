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


# ---------------------------------------------------------------------------
# C3a — instincts hot tier (durable, hierarchically-routed memory)
# ---------------------------------------------------------------------------

INSTINCT_KINDS: Final = ("worked", "avoid", "dont-repeat")
INSTINCT_DATE_FORMAT: Final = "%Y-%m-%d"  # date-only; recall ranks by file mtime


@dataclass(frozen=True)
class InstinctResult:
    """Result of a /ren:note --instinct invocation."""

    success: bool
    path: Path | None
    scope: str               # "project" | "global" (the scope actually used)
    appended_line: str
    fell_back_to_global: bool = False  # True when project was requested but none was resolvable
    error: str | None = None


def instinct_scope(*, use_global: bool, project_slug: str | None) -> str:
    """Resolve the routing scope: global on the flag, or when no project is known."""
    return "global" if (use_global or not project_slug) else "project"


def resolve_instinct_path(*, scope: str, project_slug: str | None, wiki_root: Path) -> Path:
    """
    Resolve the instincts.md target.

    project + a slug → `<wiki_root>/projects/<slug>/instincts.md`
    otherwise        → `<wiki_root>/instincts.md` (master/global)
    """
    if scope == "project" and project_slug:
        return wiki_root / "projects" / project_slug / "instincts.md"
    return wiki_root / "instincts.md"


def format_instinct_bullet(kind: str, text: str, *, now: datetime | None = None) -> str:
    """Format one instinct entry: `- **[kind]** YYYY-MM-DD — text` (trailing newline)."""
    d = (now or datetime.now(timezone.utc)).strftime(INSTINCT_DATE_FORMAT)
    safe_text = text.replace("\n", "\\n").rstrip()
    return f"- **[{kind}]** {d} — {safe_text}\n"


def _instinct_template(
    *, scope: str, project_slug: str | None, framework_version: str, now: datetime | None = None
) -> str:
    """Frontmatter + header for a freshly-created instincts.md (page-type `instincts`, schema 1)."""
    d = (now or datetime.now(timezone.utc)).strftime(INSTINCT_DATE_FORMAT)
    title = f"Instincts — {project_slug}" if (scope == "project" and project_slug) else "Instincts — Global"
    return (
        "---\n"
        "type: instincts\n"
        "schema_version: 1\n"
        f'framework_version: "{framework_version}"\n'
        f"scope: {scope}\n"
        f"updated: {d}\n"
        "---\n\n"
        f"# {title}\n\n"
        "Append-only hot-tier memory. Each entry is **[kind]** date — text. "
        "Kinds: worked | avoid | dont-repeat.\n\n"
    )


def pin_instinct(
    kind: str,
    text: str,
    *,
    wiki_root: Path,
    project_slug: str | None,
    use_global: bool,
    framework_version: str,
    now: datetime | None = None,
) -> InstinctResult:
    """
    Append a typed instinct to the routed instincts.md (creating it from the
    template on first write). Pure-filesystem; the caller resolves wiki_root,
    project_slug, and framework_version (the SKILL.md layer, via lib.sf_paths).
    """
    if kind not in INSTINCT_KINDS:
        return InstinctResult(
            success=False, path=None, scope="", appended_line="",
            error=f"Invalid kind {kind!r}. Use one of: {', '.join(INSTINCT_KINDS)}",
        )
    stripped = text.strip()
    if not stripped:
        return InstinctResult(
            success=False, path=None, scope="", appended_line="",
            error="Empty text. Usage: /ren:note --instinct <kind> <text>",
        )

    scope = instinct_scope(use_global=use_global, project_slug=project_slug)
    fell_back = (not use_global) and (not project_slug)
    target = resolve_instinct_path(scope=scope, project_slug=project_slug, wiki_root=wiki_root)
    bullet = format_instinct_bullet(kind, stripped, now=now)

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            header = _instinct_template(
                scope=scope, project_slug=project_slug,
                framework_version=framework_version, now=now,
            )
            target.write_text(header + bullet, encoding="utf-8")
        else:
            with target.open("a", encoding="utf-8") as fh:
                fh.write(bullet)
    except OSError as exc:
        return InstinctResult(
            success=False, path=target, scope=scope, appended_line=bullet,
            fell_back_to_global=fell_back, error=f"Could not write to {target}: {exc}",
        )

    return InstinctResult(
        success=True, path=target, scope=scope, appended_line=bullet,
        fell_back_to_global=fell_back, error=None,
    )


__all__ = [
    "DEFAULT_NOTES_DIRNAME",
    "UNSESSIONED_FILENAME",
    "TIMESTAMP_FORMAT",
    "PinResult",
    "resolve_notes_path",
    "format_bullet",
    "pin_note",
    # C3a — instincts hot tier
    "INSTINCT_KINDS",
    "InstinctResult",
    "instinct_scope",
    "resolve_instinct_path",
    "format_instinct_bullet",
    "pin_instinct",
]
