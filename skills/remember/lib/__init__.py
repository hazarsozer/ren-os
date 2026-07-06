"""
skills.remember library — internal implementation for /ren:remember
(Task 8.2, RenOS 0.2 Phase 8).

Spec §3.8 A-10: "the first session produces a visible artifact... and a
'show me what you remember about this project' command renders the L2 map
in human form. The cheapest trust-builder in the scope." This module is that
command: it reads the L2 map (a project's `projects/<slug>/map.md`, or the
master `index.md` when unscoped) and renders it as PROSE, not a raw markdown
dump — the frozen schema's `## Knowledge`/`## Decision map`/`## Log` sections
become a title line, human-readable bullets (decision-map pointers drop
their `(write_id)` parenthetical — that's provenance plumbing, not something
a friend reading this needs to see), the last 3 log lines, and a footer with
counts. Read-only: never writes, never raises.

If the map is quarantined (an `ingest`-produced map is always `writer=
"llm-auto"`, auto-quarantined per Task 2.4's wiring, until a human reviews
it), that's surfaced prominently — the whole point of showing memory back to
a friend is trust, and an unreviewed auto-generated map is exactly the case
where trust needs a caveat, not silent confidence.
"""

from __future__ import annotations

import re
from pathlib import Path

from lib import ren_paths
from lib.memory.quarantine import is_quarantined

_KNOWLEDGE_HEADER = "## Knowledge"
_DECISION_HEADER = "## Decision map"
_LOG_HEADER = "## Log"
_KNOWN_HEADERS = (_KNOWLEDGE_HEADER, _DECISION_HEADER, _LOG_HEADER)

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
_POINTER_RE = re.compile(r"^\[(?P<topic>[^\]]*)\]\s*→\s*(?P<path>.+)$")
_TRAILING_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*$")


def _strip_frontmatter(text: str) -> str:
    match = _FRONTMATTER_RE.match(text)
    return text[match.end():] if match else text


def _sections(body: str) -> dict[str, list[str]]:
    """Split `body` into `{header: [non-empty stripped lines under it]}` for
    the three known L2 headers. A line under an UNRECOGNIZED `## ` header
    stops being attributed to the prior known section."""
    result: dict[str, list[str]] = {h: [] for h in _KNOWN_HEADERS}
    current: str | None = None
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line in _KNOWN_HEADERS:
            current = line
            continue
        if line.startswith("## "):
            current = None
            continue
        if current is not None and line:
            result[current].append(line)
    return result


def _bullets(lines: list[str]) -> list[str]:
    return [line[1:].strip() for line in lines if line.startswith("-")]


def _humanize_pointer(bullet: str) -> str:
    """`"[topic] → path#anchor (write_id)"` -> `"topic — see path#anchor"` —
    drops the write_id parenthetical entirely; that's provenance plumbing."""
    without_paren = _TRAILING_PAREN_RE.sub("", bullet).strip()
    match = _POINTER_RE.match(without_paren)
    if match:
        return f"{match.group('topic')} — see {match.group('path')}"
    return without_paren


def _resolve_map_path(project_slug: str | None) -> Path:
    root = ren_paths.wiki_root()
    if project_slug:
        return root / "projects" / project_slug / "map.md"
    return root / "index.md"


def _no_memory_fallback() -> str:
    """No slug given AND no maps exist at all: list what IS known instead of
    just saying "nothing.\""""
    root = ren_paths.wiki_root()
    identity_present = (root / "identity.md").is_file()
    global_dir = root / "global"
    global_count = len(list(global_dir.glob("*.md"))) if global_dir.is_dir() else 0

    lines = [
        "I don't have any project memory yet.",
        "",
        f"- identity profile: {'set up' if identity_present else 'not set up yet'}",
        f"- global doctrine/preference pages: {global_count}",
        "",
        "To get started: run /ren:install, or /ren:ingest-project <path> for an "
        "existing repo, or /ren:bootstrap-project <name> for a fresh idea.",
    ]
    return "\n".join(lines) + "\n"


def remember(project_slug: str | None = None) -> str:
    """Render the L2 map for `project_slug` (or the master index when
    `None`) in human-readable prose. Never raises:
      - unknown `project_slug` (no map on disk) -> a friendly one-line
        pointer to `/ren:ingest-project`/`/ren:bootstrap-project`.
      - no slug AND nothing to show at all -> `_no_memory_fallback()`.
    """
    map_path = _resolve_map_path(project_slug)

    if not map_path.is_file():
        if project_slug:
            return (
                f"I don't have memory for {project_slug} yet — run "
                "/ren:ingest-project (an existing repo) or /ren:bootstrap-project "
                "(a fresh idea) to set it up.\n"
            )
        return _no_memory_fallback()

    text = map_path.read_text(encoding="utf-8")
    body = _strip_frontmatter(text)
    sections = _sections(body)

    knowledge = _bullets(sections[_KNOWLEDGE_HEADER])
    pointer_bullets = _bullets(sections[_DECISION_HEADER])
    pointers = [_humanize_pointer(b) for b in pointer_bullets]
    log_bullets = _bullets(sections[_LOG_HEADER])[-3:]

    quarantined = is_quarantined(text)
    label = project_slug or "this wiki"

    lines = [f"Here's what I remember about {label}:", ""]

    if quarantined:
        lines.append(
            "⚠ this map was auto-generated and hasn't been reviewed — approve it via the queue"
        )
        lines.append("")

    if knowledge:
        lines.append("Knowledge:")
        lines.extend(f"- {fact}" for fact in knowledge)
        lines.append("")

    if pointers:
        lines.append("Decision map:")
        lines.extend(f"- {pointer}" for pointer in pointers)
        lines.append("")

    if log_bullets:
        lines.append("Recent log:")
        lines.extend(f"- {entry}" for entry in log_bullets)
        lines.append("")

    lines.append(
        f"{len(knowledge)} facts · {len(pointers)} decision pointers · "
        f"quarantined: {'yes' if quarantined else 'no'}"
    )
    return "\n".join(lines) + "\n"


__all__ = ["remember"]
