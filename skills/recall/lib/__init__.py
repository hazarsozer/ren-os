"""
skills.recall library — internal implementation for /ren:recall (Task 4.3,
RenOS 0.2 Phase 4).

Public entries:
  `rank(query, candidate_pages, wiki_root) -> list[str]` — pure ranking
    function, no I/O beyond reading the candidate files. Signature matches
    the Phase 5 wake-up ranker contract AND the retrieval-eval harness's
    `ranker_fn: (query, candidate_pages, wiki_root) -> ordered list` so the
    exact same function can be scored against
    `tests/fixtures/retrieval_fixture.json` (builder-0-2, in flight) without
    an adapter shim.
  `fetch(query, session, k=3) -> list[dict]` — the L3 fetch verb: ranks every
    `*.md` page under the wiki root, returns the top-k as
    `{"page": ..., "content": ...}`, and logs EVERY returned page via
    `lib.instrument.miss_log.log_fetch` — per spec §3.2, every L3 fetch is
    logged; that log is the mechanical miss-measurement substrate (Task 3.3),
    not a surveillance feature.

Scoring heuristic carried from donor `skills/recall/lib/__init__.py`: token
overlap (title/heading/body weighted hits, word-boundary matched) + a
recency bonus (mtime within 30 days) + a path-kind multiplier (decisions/
and patterns/ pages score higher, .session-notes/ lower). Dropped entirely:
`--instincts` mode (`instincts_only`, `_is_instincts_page`) and the
`read_routine_state` routine-state reader — both out of scope for 0.2's
recall verb.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from lib import ren_paths
from lib.instrument import miss_log

# Stop-words removed from queries to focus the token-overlap score.
STOP_WORDS: Final[frozenset[str]] = frozenset(
    {"a", "an", "the", "of", "is", "we", "i", "to", "in", "on", "and", "or", "for", "do", "did", "what"}
)

# Path-kind multipliers (path hints) — carried verbatim from the donor heuristic.
KIND_MULTIPLIERS: Final[dict[str, float]] = {
    "decisions": 1.5,
    "patterns": 1.3,
    ".session-notes": 0.8,
}
DEFAULT_KIND_MULTIPLIER: Final[float] = 1.0

TITLE_HIT_WEIGHT: Final[int] = 3
HEADING_HIT_WEIGHT: Final[int] = 2
BODY_HIT_WEIGHT: Final[int] = 1
RECENCY_BONUS: Final[float] = 0.5
RECENCY_DAYS: Final[int] = 30

DEFAULT_K: Final[int] = 3

_TITLE_RE = re.compile(r"^title:\s*[\"']?(.+?)[\"']?\s*$", re.MULTILINE)
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)


def tokenize_query(query: str) -> list[str]:
    """Lowercase + split on non-word chars + strip stop-words."""
    if not isinstance(query, str):
        raise TypeError(f"query must be str, got {type(query).__name__}")
    raw = re.split(r"[^\w]+", query.lower())
    return [t for t in raw if t and t not in STOP_WORDS]


def _classify_kind(rel_path: str) -> float:
    """Map a wiki-relative path to its kind multiplier (path hint)."""
    for prefix, mult in KIND_MULTIPLIERS.items():
        if f"/{prefix}/" in f"/{rel_path}/" or rel_path.startswith(prefix + "/"):
            return mult
    return DEFAULT_KIND_MULTIPLIER


def _token_pattern(token: str) -> re.Pattern[str]:
    """Word-boundary regex for one token (so "not" doesn't match "notes")."""
    return re.compile(r"\b" + re.escape(token) + r"\b", re.IGNORECASE)


def _score_content(content: str, tokens: list[str]) -> float:
    """Token-overlap score: title hits > heading hits > body hits (capped per token)."""
    if not tokens:
        return 0.0

    title_text = ""
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            fm = content[3:end]
            for match in _TITLE_RE.finditer(fm):
                title_text += " " + match.group(1)

    heading_text = " ".join(m.group(1) for m in _HEADING_RE.finditer(content))

    score = 0.0
    for token in tokens:
        pat = _token_pattern(token)
        if pat.search(title_text):
            score += TITLE_HIT_WEIGHT
        if pat.search(heading_text):
            score += HEADING_HIT_WEIGHT
        count = len(pat.findall(content))
        score += BODY_HIT_WEIGHT * min(count, 5)
    return score


def _recency_bonus(path: Path, *, now: datetime | None = None) -> float:
    """RECENCY_BONUS if mtime is within RECENCY_DAYS, else 0.0. Never raises
    (a stat() failure — e.g. the file vanished mid-scan — scores 0 bonus)."""
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return 0.0
    actual_now = now or datetime.now(timezone.utc)
    delta_days = (actual_now - mtime).total_seconds() / 86400.0
    return RECENCY_BONUS if delta_days <= RECENCY_DAYS else 0.0


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def rank(query: str, candidate_pages: list[str], wiki_root: Path) -> list[str]:
    """Rank `candidate_pages` (wiki-relative path strings) against `query`.

    Returns an ordered list (best match first) of the SAME strings passed in
    `candidate_pages` — no filesystem walking beyond reading each candidate's
    content to score it. An unreadable candidate scores 0 rather than being
    dropped, so the output is always a permutation of the input (this matters
    for the retrieval-eval harness, which expects a full ranking, not a
    filtered subset). Ties break by file mtime (newer first); an unreadable
    file's mtime is treated as 0 (oldest).
    """
    wiki_root = Path(wiki_root)
    tokens = tokenize_query(query)

    scored: list[tuple[float, str]] = []
    for rel in candidate_pages:
        path = wiki_root / rel
        content = _safe_read(path)
        token_score = _score_content(content, tokens) if tokens else 0.0
        kind_mult = _classify_kind(rel)
        recency = _recency_bonus(path)
        final_score = token_score * kind_mult + recency
        scored.append((final_score, rel))

    scored.sort(key=lambda t: (t[0], _safe_mtime(wiki_root / t[1])), reverse=True)
    return [rel for _, rel in scored]


def _discover_candidates(wiki_root: Path) -> list[str]:
    """Every `*.md` page under `wiki_root`, excluding dotdirs (`.git/`, the
    `.ren/` state dir, etc.) — mirrors the donor heuristic's hidden-dir skip."""
    if not wiki_root.is_dir():
        return []
    candidates = []
    for path in wiki_root.rglob("*.md"):
        if any(part.startswith(".") for part in path.relative_to(wiki_root).parts):
            continue
        candidates.append(path.relative_to(wiki_root).as_posix())
    return candidates


def fetch(query: str, session: str, k: int = DEFAULT_K) -> list[dict]:
    """The L3 fetch verb: rank every wiki page against `query`, return the
    top-`k` as `{"page": <wiki-relative path>, "content": <file text>}`, and
    log every returned page via `miss_log.log_fetch` (per spec §3.2, every L3
    fetch is logged — this IS the mechanical miss-measurement substrate).

    Returns `[]` on an empty (or absent) wiki — never raises.
    """
    root = ren_paths.wiki_root()
    candidates = _discover_candidates(root)
    ranked = rank(query, candidates, root)

    results: list[dict] = []
    for rel in ranked[:k]:
        content = _safe_read(root / rel)
        results.append({"page": rel, "content": content})
        miss_log.log_fetch(rel, query, session)
    return results


__all__ = [
    "STOP_WORDS",
    "KIND_MULTIPLIERS",
    "DEFAULT_K",
    "tokenize_query",
    "rank",
    "fetch",
]
