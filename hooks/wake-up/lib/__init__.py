"""
sf-wake-up lib — composition layer for the SessionStart wake-up hook.

Pure-logic functions for assembling the additionalContext payload:
  - detect_project(cwd, wiki_root) → project name or None
  - read_index_truncated(wiki_root) → master wiki index, truncated
  - read_log_tail(log_path, n) → last N log entries
  - read_context_md(project_dir) → CONTEXT.md content (the next-session pointer)
  - estimate_tokens(text) → rough token count (chars/4 heuristic; tiktoken-free)
  - truncate_to_budget(sections, max_tokens) → drop oldest signals to fit
  - compose_wake_up_context(...) → orchestrator

The feed-integration layer (read_friends_tails) is INJECTED via the
fetch_feed_tail callback so the orchestrator stays pure-testable without
feed module installed.

Per ADR-008: payload target is 3-5K tokens. Hard cap at 5K (~20K chars).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Final

logger = logging.getLogger(__name__)


# Locked path convention per team-lead 2026-05-28
DEFAULT_WIKI_ROOT_REL: Final[str] = ".startup-framework/wiki"
MASTER_INDEX_FILENAME: Final[str] = "index.md"
MASTER_LOG_FILENAME: Final[str] = "log.md"
PROJECT_CONTEXT_FILENAME: Final[str] = "CONTEXT.md"
PROJECT_INDEX_FILENAME: Final[str] = "index.md"
PROJECT_LOG_FILENAME: Final[str] = "log.md"

# Token budget per ADR-008 (3-5K target; 5K hard cap)
DEFAULT_MAX_TOKENS: Final[int] = 5_000
CHARS_PER_TOKEN: Final[float] = 4.0  # rough heuristic; tiktoken-free for hook latency

# Per-section token allocations (sum should not exceed DEFAULT_MAX_TOKENS)
MASTER_INDEX_BUDGET: Final[int] = 800
MASTER_LOG_BUDGET: Final[int] = 400
PROJECT_INDEX_BUDGET: Final[int] = 600
PROJECT_CONTEXT_BUDGET: Final[int] = 600
PROJECT_LOG_BUDGET: Final[int] = 800
FRIENDS_ACTIVITY_BUDGET: Final[int] = 1500


# Callback signature: returns rendered friends-activity block text + freshness header
# Returns "" if feed unavailable / not bootstrapped (silent degradation per feed-2 contract)
FetchFeedTail = Callable[[], str]


def estimate_tokens(text: str) -> int:
    """Rough token count via chars/4 heuristic (no tiktoken dep for hook latency)."""
    return int(len(text) / CHARS_PER_TOKEN)


def truncate_text_to_tokens(text: str, max_tokens: int) -> str:
    """
    Truncate text to fit within the token budget, preserving the tail.

    The wiki context-injection convention: tail (most recent / most relevant)
    wins over head. For log files, that's the recent entries. For index files
    where the title typically wins, the caller can pre-extract the head.

    Args:
        text: Source text.
        max_tokens: Token budget (chars/4 heuristic).

    Returns:
        Truncated text. If truncation happened, prefixed with a "[...truncated...]"
        marker so the LLM knows it's not seeing the full content.
    """
    if max_tokens <= 0:
        return ""
    max_chars = int(max_tokens * CHARS_PER_TOKEN)
    if len(text) <= max_chars:
        return text
    # Keep the tail; mark elided content
    return f"[...truncated; first {len(text) - max_chars} chars elided...]\n" + text[-max_chars:]


def detect_project(cwd: Path, wiki_root: Path) -> str | None:
    """
    Determine the active project from cwd, per ADR-008's CWD-aware loading.

    Heuristic: if cwd matches `~/Dev/<X>/` (or any subpath thereof) AND
    `wiki_root/projects/<X>/` exists → project = X. Else None.

    Args:
        cwd: Working directory the hook is running in.
        wiki_root: Path to the wiki root.

    Returns:
        Project name or None.
    """
    dev_root = Path.home() / "Dev"
    try:
        rel = cwd.resolve().relative_to(dev_root.resolve())
    except (ValueError, OSError):
        return None
    if not rel.parts:
        return None
    candidate = rel.parts[0]
    if (wiki_root / "projects" / candidate).is_dir():
        return candidate
    return None


def _read_text_safe(path: Path) -> str:
    """Read file safely; return empty string on any error."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("could not read %s: %s", path, exc)
        return ""


def read_log_tail(log_path: Path, n_entries: int) -> str:
    """
    Read the last N entries from a wiki log.md file.

    Per ADR-004 chronological-invariant format, entries look like:
        ## [YYYY-MM-DD HH:MM] type | description

    Returns the last N such entries, in chronological order (oldest of the
    tail first, newest last). Returns empty string if file missing/unreadable.
    """
    content = _read_text_safe(log_path)
    if not content:
        return ""

    # Split on entry-starting headers; preserve everything that follows each
    lines = content.splitlines()
    entries: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.startswith("## ["):
            if current:
                entries.append(current)
            current = [line]
        elif current:
            current.append(line)

    if current:
        entries.append(current)

    # Keep last N entries
    tail = entries[-n_entries:]
    return "\n".join("\n".join(e) for e in tail).strip()


def compose_wake_up_context(
    *,
    cwd: Path,
    wiki_root: Path,
    source: str = "startup",
    max_tokens: int = DEFAULT_MAX_TOKENS,
    fetch_feed_tail: FetchFeedTail | None = None,
) -> str:
    """
    Compose the additionalContext payload for the SessionStart hook.

    Reads master + project wiki sections, applies per-section truncation,
    optionally appends friends-activity tail. Returns "" if the wiki is
    inaccessible (graceful degradation; hook still exits 0).

    Args:
        cwd: Current working directory of the session.
        wiki_root: Wiki root (defaults inferred from env or convention).
        source: SessionStart matcher value ("startup", "compact", etc.).
        max_tokens: Hard token cap.
        fetch_feed_tail: Optional callable returning the friends-activity block.

    Returns:
        Composed text suitable for hookSpecificOutput.additionalContext.
        Empty string if wiki not accessible (graceful degradation).
    """
    if not wiki_root.is_dir():
        logger.info("wiki not found at %s; emitting empty context", wiki_root)
        return ""

    sections: list[str] = []
    sections.append(f"## Framework wake-up context (source={source})\n")

    # 1. Master wiki index
    master_index = _read_text_safe(wiki_root / MASTER_INDEX_FILENAME)
    if master_index:
        sections.append("### Master wiki index")
        sections.append(truncate_text_to_tokens(master_index, MASTER_INDEX_BUDGET))

    # 2. Master log tail (last 5 entries per ADR-008)
    master_log_tail = read_log_tail(wiki_root / MASTER_LOG_FILENAME, n_entries=5)
    if master_log_tail:
        sections.append("### Recent master log")
        sections.append(truncate_text_to_tokens(master_log_tail, MASTER_LOG_BUDGET))

    # 3. Project context (if in a project directory)
    project = detect_project(cwd, wiki_root)
    if project is not None:
        project_dir = wiki_root / "projects" / project

        project_index = _read_text_safe(project_dir / PROJECT_INDEX_FILENAME)
        if project_index:
            sections.append(f"### Project context: {project}")
            sections.append(truncate_text_to_tokens(project_index, PROJECT_INDEX_BUDGET))

        context_md = _read_text_safe(project_dir / PROJECT_CONTEXT_FILENAME)
        if context_md:
            sections.append("### Session pointer (CONTEXT.md from last /sf:wrap)")
            sections.append(truncate_text_to_tokens(context_md, PROJECT_CONTEXT_BUDGET))

        project_log_tail = read_log_tail(project_dir / PROJECT_LOG_FILENAME, n_entries=10)
        if project_log_tail:
            sections.append(f"### Recent {project} log")
            sections.append(truncate_text_to_tokens(project_log_tail, PROJECT_LOG_BUDGET))

    # 4. Friends activity (if feed integration available + bootstrapped)
    if fetch_feed_tail is not None:
        try:
            friends_block = fetch_feed_tail()
        except Exception:  # noqa: BLE001 — silent degradation
            logger.warning("fetch_feed_tail raised; skipping friends-activity block", exc_info=True)
            friends_block = ""
        if friends_block:
            sections.append(truncate_text_to_tokens(friends_block, FRIENDS_ACTIVITY_BUDGET))

    composed = "\n\n".join(s for s in sections if s.strip())

    # Final overall cap as a safety net (per-section budgets should sum below this)
    final_tokens = estimate_tokens(composed)
    if final_tokens > max_tokens:
        logger.info("composed %d tokens; truncating to %d", final_tokens, max_tokens)
        composed = truncate_text_to_tokens(composed, max_tokens)

    return composed


__all__ = [
    "DEFAULT_MAX_TOKENS",
    "CHARS_PER_TOKEN",
    "MASTER_INDEX_BUDGET",
    "MASTER_LOG_BUDGET",
    "PROJECT_CONTEXT_BUDGET",
    "PROJECT_LOG_BUDGET",
    "FRIENDS_ACTIVITY_BUDGET",
    "FetchFeedTail",
    "estimate_tokens",
    "truncate_text_to_tokens",
    "detect_project",
    "read_log_tail",
    "compose_wake_up_context",
]
