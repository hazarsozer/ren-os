"""
sf-recall library — internal implementation for /ren:recall.

Public entry: `recall(query, *, wiki_root, n_hits) -> RecallResult`.

Per references/grep-strategy.md (v1 deterministic grep heuristic).

Solo-first (ADR-031): recall greps the local wiki only. The former cross-friend
feed-tail surface was removed with the Activity Feed module.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)


# Stop-words removed from queries to focus the grep.
STOP_WORDS: Final[frozenset[str]] = frozenset(
    {"a", "an", "the", "of", "is", "we", "i", "to", "in", "on", "and", "or", "for", "do", "did", "what"}
)

# File-kind multipliers per references/grep-strategy.md
KIND_MULTIPLIERS: Final[dict[str, float]] = {
    "decisions": 1.5,
    "patterns": 1.3,
    ".session-notes": 0.8,
}
DEFAULT_KIND_MULTIPLIER: Final[float] = 1.0

# Score weights
TITLE_HIT_WEIGHT: Final[int] = 3
HEADING_HIT_WEIGHT: Final[int] = 2
BODY_HIT_WEIGHT: Final[int] = 1
RECENCY_BONUS: Final[float] = 0.5
RECENCY_DAYS: Final[int] = 30

DEFAULT_N_HITS: Final[int] = 10


@dataclass(frozen=True)
class RecallHit:
    """One wiki match returned by `recall()`."""

    path: Path                  # absolute path to the matching file
    relative_path: str          # path relative to wiki_root (for display)
    score: float
    line_number: int            # 1-indexed line of the first token hit
    snippet: str                # 3-line excerpt (prev + matching + next)


@dataclass(frozen=True)
class RecallResult:
    """Result returned to user-facing rendering."""

    query: str
    wiki_hits: tuple[RecallHit, ...]
    truncated: bool              # True if more wiki hits existed than n_hits cap

    @property
    def has_results(self) -> bool:
        return bool(self.wiki_hits)


def tokenize_query(query: str) -> list[str]:
    """
    Lowercase + split on non-word chars + strip stop-words.

    Returns:
        List of non-empty, lowercased, non-stop-word tokens.
    """
    if not isinstance(query, str):
        raise TypeError(f"query must be str, got {type(query).__name__}")
    raw = re.split(r"[^\w]+", query.lower())
    return [t for t in raw if t and t not in STOP_WORDS]


def _classify_kind(rel_path: str) -> float:
    """Map a relative path to its kind multiplier."""
    for prefix, mult in KIND_MULTIPLIERS.items():
        if f"/{prefix}/" in f"/{rel_path}/" or rel_path.startswith(prefix + "/"):
            return mult
    return DEFAULT_KIND_MULTIPLIER


_TITLE_RE = re.compile(r"^title:\s*[\"']?(.+?)[\"']?\s*$", re.MULTILINE)
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)


def _token_pattern(token: str) -> re.Pattern[str]:
    """
    Build a word-boundary regex for a single token.

    Word boundaries (`\\b`) ensure "not" does NOT match "notes" and "post"
    does NOT match "postgres" via accidental substring. This is the standard
    grep semantic: friends expect "find the word X," not "find the substring X."
    """
    return re.compile(r"\b" + re.escape(token) + r"\b", re.IGNORECASE)


def _score_file(content: str, tokens: list[str]) -> tuple[float, int | None]:
    """
    Score a file's content against the token list using word-boundary matching.

    Args:
        content: Full file content (str).
        tokens: Lowercased query tokens.

    Returns:
        (score, first_match_line_1indexed). first_match_line is None if no
        token hit (caller skips that file).
    """
    if not tokens:
        return 0.0, None

    # Extract title from frontmatter (between first --- block, if any)
    title_text = ""
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            fm = content[3:end]
            for match in _TITLE_RE.finditer(fm):
                title_text += " " + match.group(1)

    # Extract headings (anywhere)
    heading_text = " ".join(m.group(1) for m in _HEADING_RE.finditer(content))

    score = 0.0
    for token in tokens:
        pat = _token_pattern(token)
        # Title hits (highest weight)
        if pat.search(title_text):
            score += TITLE_HIT_WEIGHT
        # Heading hits
        if pat.search(heading_text):
            score += HEADING_HIT_WEIGHT
        # Body hits (count occurrences, but cap per-token contribution so one
        # keyword-stuffed file can't dominate)
        count = len(pat.findall(content))
        score += BODY_HIT_WEIGHT * min(count, 5)

    # Find first line with any token hit (word-boundary)
    first_match_line: int | None = None
    patterns = [_token_pattern(t) for t in tokens]
    for line_no, line in enumerate(content.splitlines(), start=1):
        if any(pat.search(line) for pat in patterns):
            first_match_line = line_no
            break

    return score, first_match_line


def _extract_snippet(content: str, match_line: int) -> str:
    """Return a 3-line excerpt centered on match_line (1-indexed)."""
    lines = content.splitlines()
    n = len(lines)
    if match_line < 1 or match_line > n:
        return ""

    prev_line = lines[match_line - 2] if match_line - 2 >= 0 else ""
    matched = lines[match_line - 1]
    next_line = lines[match_line] if match_line < n else ""
    return f"{prev_line}\n{matched}\n{next_line}"


def _recency_bonus(path: Path, *, now: datetime | None = None) -> float:
    """Return RECENCY_BONUS if file mtime is within RECENCY_DAYS, else 0.0."""
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return 0.0
    actual_now = now or datetime.now(timezone.utc)
    delta_days = (actual_now - mtime).total_seconds() / 86400.0
    return RECENCY_BONUS if delta_days <= RECENCY_DAYS else 0.0


def _safe_mtime(path: Path) -> float:
    """Return file mtime, or 0.0 if stat() fails. Mirrors _recency_bonus's guard."""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def grep_wiki(
    wiki_root: Path,
    query: str,
    *,
    n_hits: int = DEFAULT_N_HITS,
    now: datetime | None = None,
) -> tuple[tuple[RecallHit, ...], bool]:
    """
    Grep a wiki root for `query` per the v1 strategy.

    Args:
        wiki_root: Path to the wiki directory.
        query: User's free-text query.
        n_hits: Maximum hits to return.
        now: Override "now" for recency calculation (for tests).

    Returns:
        (hits, truncated) — hits sorted descending by score; truncated=True
        if more hits existed than n_hits.
    """
    tokens = tokenize_query(query)
    if not tokens or not wiki_root.is_dir():
        return (), False

    raw_hits: list[tuple[float, RecallHit]] = []
    for path in wiki_root.rglob("*.md"):
        # Skip hidden dirs like .git/
        if any(part.startswith(".") and part != ".session-notes" for part in path.parts):
            continue

        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Skipping unreadable file %s: %s", path, exc)
            continue

        score, match_line = _score_file(content, tokens)
        if score == 0 or match_line is None:
            continue

        rel = path.relative_to(wiki_root).as_posix()
        kind_mult = _classify_kind(rel)
        recency = _recency_bonus(path, now=now)
        final_score = score * kind_mult + recency

        snippet = _extract_snippet(content, match_line)

        raw_hits.append(
            (
                final_score,
                RecallHit(
                    path=path,
                    relative_path=rel,
                    score=final_score,
                    line_number=match_line,
                    snippet=snippet,
                ),
            )
        )

    # Sort by score desc, then by mtime desc (newer wins ties). _safe_mtime
    # guards stat() so a file deleted between rglob and sort can't crash the call.
    raw_hits.sort(key=lambda t: (t[0], _safe_mtime(t[1].path)), reverse=True)

    truncated = len(raw_hits) > n_hits
    hits = tuple(h[1] for h in raw_hits[:n_hits])
    return hits, truncated


def recall(
    query: str,
    *,
    wiki_root: Path,
    n_hits: int = DEFAULT_N_HITS,
    now: datetime | None = None,
) -> RecallResult:
    """
    Top-level entry point. Walks the wiki and returns ranked hits.

    Args:
        query: Free-text query.
        wiki_root: Path to the wiki directory.
        n_hits: Cap on wiki hits returned.
        now: Override "now" (for tests / determinism).

    Returns:
        RecallResult.

    Raises:
        ValueError: if the query is empty after whitespace strip.
    """
    if not query or not query.strip():
        raise ValueError("Empty query. Usage: /ren:recall <query>")

    wiki_hits, truncated = grep_wiki(wiki_root, query, n_hits=n_hits, now=now)

    return RecallResult(
        query=query.strip(),
        wiki_hits=wiki_hits,
        truncated=truncated,
    )


__all__ = [
    "STOP_WORDS",
    "KIND_MULTIPLIERS",
    "DEFAULT_N_HITS",
    "RecallHit",
    "RecallResult",
    "tokenize_query",
    "grep_wiki",
    "recall",
]
