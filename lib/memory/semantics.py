"""
lib.memory.semantics — G3 contradiction / supersede / duplicate detection
(Task 2.2, RenOS 0.2 Phase 2).

Spec §3.1 "Memory semantics" (council A-1, load-bearing): at write time the
queue asks "does this contradict or replace an existing entry?" and surfaces it
in the diff the human already approves. This module answers that question with
THREE DETERMINISTIC HEURISTICS ONLY — no LLM call at the queue (unanimous
council). `write_apply`/the write queue (Task 2.1, not yet built) will import
`detect()` and route its `Conflict` list into the approval diff.

HONESTY ABOUT THE HEURISTIC (read before relying on this for anything): this is
a cheap, explainable, false-negative-tolerant screen — not semantic
understanding. It will MISS real contradictions phrased without the negation
markers below (including non-numeric fact swaps like "Postgres" -> "SQLite"),
MISS duplicates that reword every line, and it does not attempt synonymy,
negation scope, or discourse-level reasoning. Since v2.2 removed per-write
human approval, this screen is the ONLY automatic conflict check on
auto-applied data-plane writes — its misses land in the wiki and stay there
until an auditor finds them. That is why `skills.wiki-health`'s periodic sweep
(duplicate/drift/contradiction scans built on this module's pairwise helpers)
exists: write-time screening is best-effort, read-time auditing is the
backstop. Real semantic detection (embeddings or similar) is 0.4/0.5 ladder
work — do not extend this module with a fuzzy-matching dependency to "improve"
recall here.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .provenance import read_frontmatter_provenance

ConflictKind = Literal["supersedes", "contradicts", "duplicate"]

# Ordered longest-marker-first so a phrase like "do not" is stripped whole
# rather than leaving a dangling "do " after only "not " is removed.
_NEGATION_MARKERS: tuple[str, ...] = (
    "do not ",
    "don't ",
    "no longer ",
    "not ",
    "never ",
    "stop ",
    "avoid ",
)

# Word-boundary version of each marker (`\b` before the leading word char) so
# a marker can't match as a substring of a larger word — e.g. "never " must
# NOT match inside "whenever ", and "not " must NOT match inside "cannot ".
# The trailing space in each marker already guarantees a boundary on the
# right; only the left edge needs the explicit `\b`.
_NEGATION_MARKER_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(r"\b" + re.escape(marker)) for marker in _NEGATION_MARKERS
)

# Small, deliberate stopword list for the "significant token" overlap gate.
# Not exhaustive NLP — just enough that short connector words don't count
# toward the >=3 shared-token contradiction threshold.
_STOPWORDS = frozenset(
    """
    the a an and or but for to of in on at by with from into this that these
    those is are was were be been being do does did done will would can could
    should shall may might must use uses used using always never also just
    then than so if when where how what which who whom
    """.split()
)

_DUPLICATE_RATIO_THRESHOLD = 0.9
_MIN_SHARED_TOKENS_FOR_CONTRADICTION = 3
_MIN_SIGNIFICANT_TOKENS_TO_CONSIDER = 3

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)


@dataclass(frozen=True)
class Conflict:
    kind: ConflictKind
    page: str             # wiki-relative path of the existing page involved
    write_id: str | None  # ren_write_id of that page (from frontmatter), None if unstamped
    evidence: str         # the existing line/section that triggered the finding


def _strip_frontmatter(text: str) -> str:
    """Return `text` with a leading YAML frontmatter block removed, if present."""
    match = _FRONTMATTER_RE.match(text)
    return text[match.end():] if match else text


def _normalize_line(line: str) -> str:
    """Collapse internal whitespace and casefold, for line-level comparison."""
    return re.sub(r"\s+", " ", line.strip()).casefold()


def _normalized_lines(body: str) -> list[str]:
    """Non-empty, normalized lines of a page body, in order."""
    return [nl for line in body.splitlines() if (nl := _normalize_line(line))]


def _strip_negation(line: str) -> str | None:
    """If `line` contains a negation marker as a whole word (not merely a
    substring of a larger word — see `_NEGATION_MARKER_PATTERNS`), return the
    line with the FIRST matching marker removed. Returns None if no marker is
    present."""
    for pattern in _NEGATION_MARKER_PATTERNS:
        match = pattern.search(line)
        if match:
            return line[:match.start()] + line[match.end():]
    return None


def _significant_tokens(text: str) -> set[str]:
    """Casefolded word tokens longer than 3 chars, stopwords removed."""
    words = re.findall(r"[a-z0-9]+", text.casefold())
    return {w for w in words if len(w) > 3 and w not in _STOPWORDS}


def _write_id_of(raw_text: str) -> str | None:
    prov = read_frontmatter_provenance(raw_text)
    return prov["write_id"] if prov else None


def _shared_line_ratio(a_lines: list[str], b_lines: list[str]) -> float:
    """Multiset shared-line ratio: overlap count / longer document's line count."""
    if not a_lines or not b_lines:
        return 0.0
    shared = sum((Counter(a_lines) & Counter(b_lines)).values())
    total = max(len(a_lines), len(b_lines))
    return shared / total


def _first_shared_line(a_lines: list[str], b_lines: list[str]) -> str:
    b_set = set(b_lines)
    for line in a_lines:
        if line in b_set:
            return line
    return a_lines[0] if a_lines else ""


def _detect_contradictions(
    proposed_lines: list[str], existing_lines: list[str]
) -> list[str]:
    """Return existing lines that contradict `proposed_lines` (either direction):
    a negated line on one side sharing >=3 significant tokens with an affirmative
    line on the other side. One entry per contradicting existing line, at most."""
    hits: list[str] = []

    for line in proposed_lines:
        stripped = _strip_negation(line)
        if stripped is None:
            continue
        toks = _significant_tokens(stripped)
        if len(toks) < _MIN_SIGNIFICANT_TOKENS_TO_CONSIDER:
            continue
        for existing in existing_lines:
            if _strip_negation(existing) is not None:
                continue  # symmetric case handled by the loop below
            if len(toks & _significant_tokens(existing)) >= _MIN_SHARED_TOKENS_FOR_CONTRADICTION:
                hits.append(existing)

    for existing in existing_lines:
        existing_stripped = _strip_negation(existing)
        if existing_stripped is None:
            continue
        existing_toks = _significant_tokens(existing_stripped)
        if len(existing_toks) < _MIN_SIGNIFICANT_TOKENS_TO_CONSIDER:
            continue
        for line in proposed_lines:
            if _strip_negation(line) is not None:
                continue  # already covered above
            if len(existing_toks & _significant_tokens(line)) >= _MIN_SHARED_TOKENS_FOR_CONTRADICTION:
                hits.append(existing)

    return hits


def contradiction_evidence(text_a: str, text_b: str) -> str | None:
    """Direct pairwise contradiction check between two page bodies, for
    callers that need an all-pairs sweep rather than `detect`'s sibling-glob
    candidate set (e.g. `skills.wiki-health`'s wiki-wide scan). Shares the
    exact same core (`_detect_contradictions`) `detect` uses internally for
    its per-candidate contradiction check, so the two paths can't drift.

    Returns the first contradicting line found (from `text_b`'s side, by
    `_detect_contradictions`'s convention), or `None` if neither text
    contradicts the other."""
    lines_a = _normalized_lines(_strip_frontmatter(text_a or ""))
    lines_b = _normalized_lines(_strip_frontmatter(text_b or ""))
    hits = _detect_contradictions(lines_a, lines_b)
    return hits[0] if hits else None


_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_NUMBER_MASK = "#"


def duplicate_evidence(text_a: str, text_b: str) -> str | None:
    """Direct pairwise duplicate check between two page bodies, for callers
    that need an all-pairs sweep rather than `detect`'s sibling-glob candidate
    set (e.g. `skills.wiki-health`'s wiki-wide scan). Same threshold and
    ratio function as `detect`'s per-candidate duplicate check, so the two
    paths can't drift.

    Returns the first shared line as evidence, or `None` below the threshold."""
    lines_a = _normalized_lines(_strip_frontmatter(text_a or ""))
    lines_b = _normalized_lines(_strip_frontmatter(text_b or ""))
    if _shared_line_ratio(lines_a, lines_b) >= _DUPLICATE_RATIO_THRESHOLD:
        return _first_shared_line(lines_a, lines_b)
    return None


def numeric_drift_evidence(text_a: str, text_b: str) -> tuple[str, str] | None:
    """Cheap numeric-drift screen: two lines that are IDENTICAL except for
    their numbers ("uses port 8080" vs "uses port 9090") are almost always
    the same fact at two points in time — exactly the contradiction class the
    negation-marker heuristic (`_detect_contradictions`) is blind to.

    Masks every number to `#`, then looks for a masked-template collision
    between `text_a`'s lines and `text_b`'s lines where the ORIGINAL lines
    differ. Calling with `text_a is text_b` finds within-page drift (two
    lines in one page, same template, different numbers).

    Report-only signal for auditors (wiki-health). NOT semantic understanding:
    misses reworded facts and non-numeric swaps (Postgres vs SQLite) —
    those need the 0.4/0.5 semantics work, not a bigger regex.

    Returns `(line_from_a, line_from_b)` (normalized), or `None`."""
    lines_a = _normalized_lines(_strip_frontmatter(text_a or ""))
    lines_b = _normalized_lines(_strip_frontmatter(text_b or ""))

    templates_a: dict[str, str] = {}
    for line in lines_a:
        if not _NUMBER_RE.search(line):
            continue
        template = _NUMBER_RE.sub(_NUMBER_MASK, line)
        if len(_significant_tokens(template)) < _MIN_SIGNIFICANT_TOKENS_TO_CONSIDER:
            continue
        templates_a.setdefault(template, line)

    for line in lines_b:
        if not _NUMBER_RE.search(line):
            continue
        template = _NUMBER_RE.sub(_NUMBER_MASK, line)
        counterpart = templates_a.get(template)
        if counterpart is not None and counterpart != line:
            return (counterpart, line)
    return None


def detect(op: str, page: str, content: str | None, wiki_root: Path) -> list[Conflict]:
    """Run the three deterministic conflict checks for a proposed write.

    Args:
        op: "ADD" | "UPDATE" | "DELETE" | "NOOP" (plain str — the queue's
            Proposal type doesn't exist yet, so this takes primitives).
        page: wiki-relative path of the write target, e.g. "projects/x/notes.md".
        content: the proposed page content (may include frontmatter; stripped
            before comparison), or None (e.g. a DELETE carries no content).
        wiki_root: root directory the wiki lives under.

    Returns a list of `Conflict`, checked in order: duplicate, supersedes,
    contradicts. All three may fire in the same call.
    """
    wiki_root = Path(wiki_root)
    target_path = wiki_root / page
    target_exists = target_path.is_file()

    proposed_body = _strip_frontmatter(content or "")
    proposed_lines = _normalized_lines(proposed_body)

    candidates: list[Path] = []
    if target_exists:
        candidates.append(target_path)
    sibling_dir = target_path.parent
    if sibling_dir.is_dir():
        for candidate in sorted(sibling_dir.glob("*.md")):
            if candidate != target_path:
                candidates.append(candidate)

    conflicts: list[Conflict] = []
    raw_by_path: dict[Path, str] = {}

    for candidate in candidates:
        raw = candidate.read_text(encoding="utf-8")
        raw_by_path[candidate] = raw
        rel = str(candidate.relative_to(wiki_root))
        candidate_lines = _normalized_lines(_strip_frontmatter(raw))
        write_id = _write_id_of(raw)

        # 1. duplicate
        ratio = _shared_line_ratio(proposed_lines, candidate_lines)
        if ratio >= _DUPLICATE_RATIO_THRESHOLD:
            evidence = _first_shared_line(proposed_lines, candidate_lines)
            conflicts.append(Conflict("duplicate", rel, write_id, evidence))

        # 3. contradicts (checked per-candidate; collected below with the others)
        for evidence_line in _detect_contradictions(proposed_lines, candidate_lines):
            conflicts.append(Conflict("contradicts", rel, write_id, evidence_line))

    # 2. supersedes — target page only, ADD/UPDATE only.
    if op in ("ADD", "UPDATE") and target_exists:
        raw = raw_by_path.get(target_path) or target_path.read_text(encoding="utf-8")
        write_id = _write_id_of(raw)
        existing_body_lines = _normalized_lines(_strip_frontmatter(raw))
        evidence = existing_body_lines[0] if existing_body_lines else ""
        conflicts.append(Conflict("supersedes", page, write_id, evidence))

    return conflicts


__all__ = [
    "Conflict",
    "ConflictKind",
    "detect",
    "contradiction_evidence",
    "duplicate_evidence",
    "numeric_drift_evidence",
]
