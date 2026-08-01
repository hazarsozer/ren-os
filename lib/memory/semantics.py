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
backstop.

As of 0.5.2, these heuristics are no longer the end of the line for the
misses above: `shortlist_pairs` turns them into a SHORTLIST STAGE for an LLM
judge (`lib.memory.judge`, 0.5.0) rather than the final word. Pairs the
heuristics flag outright pass through with their reason; pairs they miss but
that still share high significant-token overlap ("near-similar") are handed
to the judge too, since that overlap band is exactly where paraphrased
duplicates and reworded contradictions hide. Pairs below the overlap
threshold are still never examined — the shortlist is deterministic and
capped, not an all-pairs judge sweep. This module still does NOT depend on
any fuzzy-matching/embeddings library to compute that overlap — it is a
plain significant-token Jaccard score, same cheap-and-explainable spirit as
the three heuristics above. Do not extend this module with a fuzzy-matching
dependency to "improve" recall here; that's the judge's job now.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from . import quarantine
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
_MIN_DUPLICATE_LINES = 3  # pages with fewer meaningful lines can't be judged duplicates
_MIN_SHARED_TOKENS_FOR_CONTRADICTION = 3
_MIN_SIGNIFICANT_TOKENS_TO_CONSIDER = 3

# issue #16: a negation marker plus >=3 shared topic tokens was too weak a
# signal — batch-ingested sibling pages restate each other's topics constantly,
# and any page carrying a "do not ..." line contradicted every sibling that
# merely TALKED about the same topic. A contradiction requires the SAME CLAIM,
# negated on one side: the negation-stripped line and the affirmative line must
# overlap on most of their significant tokens, not just three of them.
#
# 0.6.2 review finding H2: this gate is CONTAINMENT (shared / min side), not
# symmetric Jaccard. A genuine contradiction whose negated side carries an
# explanation ("Migrations do not run automatically on deploy; run them
# manually first." vs "Migrations run automatically on deploy.") dilutes a
# symmetric union below the threshold while fully containing the short
# side's claim — containment keeps it.
_MIN_NEGATED_CLAIM_OVERLAP = 0.6

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


def _same_claim(negated_toks: set[str], affirmative: str) -> bool:
    """Is the affirmative line the SAME claim the negated line negates?

    Two gates, both required (issue #16): at least
    `_MIN_SHARED_TOKENS_FOR_CONTRADICTION` significant tokens in common (the
    original topic gate), AND a significant-token CONTAINMENT — shared over
    the SMALLER side — of at least `_MIN_NEGATED_CLAIM_OVERLAP` between the
    negation-stripped line and the affirmative one (0.6.2 H2: containment,
    not symmetric Jaccard, so a negated side that also carries an
    explanation doesn't dilute a genuine same-claim match). The second gate
    is what separates "X is bad" vs "X is good" (same claim, one negated →
    contradiction) from "don't do X" vs "here is a long paragraph that also
    mentions X" (topic overlap only → restatement, NOT a contradiction)."""
    affirmative_toks = _significant_tokens(affirmative)
    shared = negated_toks & affirmative_toks
    if len(shared) < _MIN_SHARED_TOKENS_FOR_CONTRADICTION:
        return False
    smaller = min(len(negated_toks), len(affirmative_toks))
    if smaller == 0:
        return False
    return len(shared) / smaller >= _MIN_NEGATED_CLAIM_OVERLAP


def _detect_contradictions(
    proposed_lines: list[str], existing_lines: list[str]
) -> list[str]:
    """Return existing lines that contradict `proposed_lines` (either
    direction): a negated line on one side that states the SAME CLAIM
    (`_same_claim`) as an affirmative line on the other side. One entry per
    contradicting existing line, at most."""
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
            if _same_claim(toks, existing):
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
            if _same_claim(existing_toks, line):
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

    Returns the first shared line as evidence, or `None` below the threshold or
    if either page has fewer than _MIN_DUPLICATE_LINES meaningful lines (near-empty
    templated pages cannot be reliably judged duplicates)."""
    lines_a = _normalized_lines(_strip_frontmatter(text_a or ""))
    lines_b = _normalized_lines(_strip_frontmatter(text_b or ""))
    if min(len(lines_a), len(lines_b)) < _MIN_DUPLICATE_LINES:
        return None
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


def _numeric_divergence_lines(
    proposed_lines: list[str], existing_lines: list[str]
) -> list[str]:
    """Existing lines that state the same fact as a proposed line with ONE
    number changed ("timeout is 30 seconds" vs "timeout is 60 seconds").

    This is the second accepted contradiction signal (issue #16): with the
    negation gate tightened, a same-fact numeric divergence is the other case
    where overlap really is a contradiction rather than a restatement.

    Deliberately stricter than the report-only `numeric_drift_evidence`: both
    lines must carry the SAME COUNT of numbers and differ in EXACTLY ONE
    numeric position. Enumerated boilerplate ("line number 1 describes topic
    1." vs "line number 12 describes topic 12.") differs in two positions and
    is therefore not a contradiction — it is two different items."""
    hits: list[str] = []
    templates: dict[str, list[tuple[str, list[str]]]] = {}
    for line in proposed_lines:
        numbers = _NUMBER_RE.findall(line)
        if not numbers:
            continue
        template = _NUMBER_RE.sub(_NUMBER_MASK, line)
        if len(_significant_tokens(template)) < _MIN_SIGNIFICANT_TOKENS_TO_CONSIDER:
            continue
        templates.setdefault(template, []).append((line, numbers))

    for existing in existing_lines:
        numbers = _NUMBER_RE.findall(existing)
        if not numbers:
            continue
        template = _NUMBER_RE.sub(_NUMBER_MASK, existing)
        for line, line_numbers in templates.get(template, []):
            if len(line_numbers) != len(numbers):
                continue
            differing = sum(1 for a, b in zip(line_numbers, numbers) if a != b)
            if differing == 1:
                hits.append(existing)
                break

    return hits


def project_subtree(page: str) -> str | None:
    """`"projects/<slug>"` for a page under a project subtree, else None."""
    parts = str(page).replace("\\", "/").strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "projects" and parts[1]:
        return f"projects/{parts[1]}"
    return None


_L2_MAP_TYPE_RE = re.compile(r"^type:\s*[\"']?l2-map[\"']?\s*$", re.MULTILINE)


def is_l2_map(page: str, text: str | None = None) -> bool:
    """Is this page an L2 map — by path (`projects/<slug>/map.md`) or by
    `type: l2-map` frontmatter?"""
    normalized = str(page).replace("\\", "/").strip("/")
    subtree = project_subtree(normalized)
    if subtree is not None and normalized == f"{subtree}/map.md":
        return True
    if text:
        match = _FRONTMATTER_RE.match(text)
        if match and _L2_MAP_TYPE_RE.search(match.group(1)):
            return True
    return False


def _contradicts_exempt(
    page: str,
    content: str | None,
    candidate_rel: str,
    candidate_text: str,
    exempt_pages: set[str],
) -> bool:
    """Should the (proposed page, candidate page) pair skip the `contradicts`
    check entirely? (Duplicate/supersedes detection is never exempted.)

    Two exemptions, both from issue #16's batch-ingest false positives:

    1. SAME BATCH — `candidate_rel` is in `exempt_pages`: a page written by
       the same session into the same `projects/<slug>/` subtree. Sibling
       pages distilled from one source in one pass restate each other by
       construction; holding page 2 for "contradicting" page 1 of the same
       batch is never a real finding.
    2. L2 MAP — either side is the subtree's map and the other side lives in
       that same subtree. A map summarizes the pages it points to; overlap
       with its own children is its job.

    0.6.2 review finding H1: for the PROPOSED side, map detection is
    PATH-ONLY (`projects/<slug>/map.md`) — a proposal must not be able to
    self-exempt from contradiction checks by declaring `type: l2-map` in its
    own frontmatter. Frontmatter-based detection stays for the EXISTING
    candidate side, whose content is already on disk and trusted.
    """
    if candidate_rel in exempt_pages:
        return True
    subtree = project_subtree(page)
    if subtree is None or project_subtree(candidate_rel) != subtree:
        return False
    return is_l2_map(page) or is_l2_map(candidate_rel, candidate_text)


def detect(
    op: str,
    page: str,
    content: str | None,
    wiki_root: Path,
    exempt_pages: set[str] | list[str] | None = None,
) -> list[Conflict]:
    """Run the three deterministic conflict checks for a proposed write.

    Args:
        op: "ADD" | "UPDATE" | "DELETE" | "NOOP" (plain str — the queue's
            Proposal type doesn't exist yet, so this takes primitives).
        page: wiki-relative path of the write target, e.g. "projects/x/notes.md".
        content: the proposed page content (may include frontmatter; stripped
            before comparison), or None (e.g. a DELETE carries no content).
        wiki_root: root directory the wiki lives under.
        exempt_pages: wiki-relative pages this proposal must NOT be reported as
            contradicting — the same-batch sibling set (see
            `_contradicts_exempt`). Duplicate/supersedes detection ignores it.

    Returns a list of `Conflict`, checked in order: duplicate, supersedes,
    contradicts. All three may fire in the same call.
    """
    wiki_root = Path(wiki_root)
    exempt = set(exempt_pages or ())
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
        if min(len(proposed_lines), len(candidate_lines)) >= _MIN_DUPLICATE_LINES:
            ratio = _shared_line_ratio(proposed_lines, candidate_lines)
            if ratio >= _DUPLICATE_RATIO_THRESHOLD:
                evidence = _first_shared_line(proposed_lines, candidate_lines)
                conflicts.append(Conflict("duplicate", rel, write_id, evidence))

        # 3. contradicts (checked per-candidate; collected below with the others).
        # Two signals qualify: a negated restatement of the same claim, or a
        # same-fact numeric divergence. Pure topic overlap never does.
        if not _contradicts_exempt(page, content, rel, raw, exempt):
            evidence_lines = _detect_contradictions(proposed_lines, candidate_lines)
            evidence_lines += [
                line
                for line in _numeric_divergence_lines(proposed_lines, candidate_lines)
                if line not in evidence_lines
            ]
            for evidence_line in evidence_lines:
                conflicts.append(Conflict("contradicts", rel, write_id, evidence_line))

    # 2. supersedes — target page only, ADD/UPDATE only.
    if op in ("ADD", "UPDATE") and target_exists:
        raw = raw_by_path.get(target_path) or target_path.read_text(encoding="utf-8")
        write_id = _write_id_of(raw)
        existing_body_lines = _normalized_lines(_strip_frontmatter(raw))
        evidence = existing_body_lines[0] if existing_body_lines else ""
        conflicts.append(Conflict("supersedes", page, write_id, evidence))

    return conflicts


# Task 11 (0.5.2): shortlist stage feeding the LLM judge. `SHORTLIST_CAP` caps
# the judge's per-run workload; `_NEAR_SIMILAR_JACCARD` is the significant-token
# overlap floor below which two pages aren't worth the judge's attention.
SHORTLIST_CAP = 20
_NEAR_SIMILAR_JACCARD = 0.5

ShortlistReason = Literal[
    "heuristic-contradiction", "heuristic-duplicate", "numeric-drift", "near-similar"
]


def _shortlist_candidate_pages(
    wiki_root: Path, *, focus_pages: set[str] | None = None
) -> list[tuple[str, str]]:
    """(rel_path, text) for every page eligible for shortlist scanning.

    Mirrors `skills.wiki-health`'s `_knowledge_pages` candidate discipline:
    skip the `.ren/` metrics tree and (0.5.1 trust taxonomy) `ren_trust:
    foreign` pages — ingested content a human hasn't reviewed must stay
    invisible to automatic pairwise scans, the judge included. Foreign trust
    is untrusted provenance and is excluded unconditionally, focus or not.

    Quarantine is different: the quarantine banner means "unreviewed
    model-class write" — precisely the population the judge exists to judge.
    A page in `focus_pages` (the session's own write targets) BYPASSES the
    quarantine skip so wrap's judge can actually fire on it; a quarantined
    page NOT in focus_pages keeps the full skip (e.g. wiki-health's
    unrestricted sweep, or another session's still-quarantined write)."""
    focus_set = focus_pages or set()
    pages: list[tuple[str, str]] = []
    for md_path in sorted(wiki_root.rglob("*.md")):
        rel_path = md_path.relative_to(wiki_root)
        if ".ren" in rel_path.parts:
            continue
        text = md_path.read_text(encoding="utf-8", errors="replace")
        prov = read_frontmatter_provenance(text)
        if prov is not None and prov.get("trust") == "foreign":
            continue
        if quarantine.is_quarantined(text) and str(rel_path) not in focus_set:
            continue
        pages.append((str(rel_path), text))
    return pages


def _heuristic_reason(text_a: str, text_b: str) -> ShortlistReason | None:
    """First heuristic that fires for this pair, checked in a fixed priority
    order (contradiction, duplicate, numeric-drift) so a pair matching more
    than one heuristic still gets exactly one reason, deterministically."""
    if contradiction_evidence(text_a, text_b) is not None:
        return "heuristic-contradiction"
    if duplicate_evidence(text_a, text_b) is not None:
        return "heuristic-duplicate"
    if numeric_drift_evidence(text_a, text_b) is not None:
        return "numeric-drift"
    return None


def _jaccard(text_a: str, text_b: str) -> float:
    toks_a = _significant_tokens(_strip_frontmatter(text_a))
    toks_b = _significant_tokens(_strip_frontmatter(text_b))
    union = toks_a | toks_b
    if not union:
        return 0.0
    return len(toks_a & toks_b) / len(union)


def shortlist_pairs(
    wiki_root: Path, *, focus_pages: list[str] | None = None, cap: int = SHORTLIST_CAP
) -> list[dict]:
    """Deterministic candidate-pair generator for the LLM judge (Task 11,
    0.5.2). Runs the three cheap heuristics plus a near-similar (significant-
    token Jaccard >= `_NEAR_SIMILAR_JACCARD`) screen over every page pair from
    `_shortlist_candidate_pages`, and returns up to `cap` `{"page", "with",
    "reason"}` dicts — heuristic-flagged pairs first (in candidate order),
    then near-similar pairs by descending Jaccard (ties broken by path sort).

    `focus_pages`, when given, restricts consideration to pairs where at
    least one side is in that list (the write queue passes the session's new
    write targets; `skills.wiki-health`'s sweep passes `None` for a full scan).
    """
    wiki_root = Path(wiki_root)
    focus_set = set(focus_pages) if focus_pages is not None else None
    pages = _shortlist_candidate_pages(wiki_root, focus_pages=focus_set)

    heuristic_pairs: list[dict] = []
    near_similar_candidates: list[tuple[float, str, str]] = []

    n = len(pages)
    for i in range(n):
        rel_a, text_a = pages[i]
        for j in range(i + 1, n):
            rel_b, text_b = pages[j]
            if focus_set is not None and rel_a not in focus_set and rel_b not in focus_set:
                continue

            reason = _heuristic_reason(text_a, text_b)
            if reason is not None:
                heuristic_pairs.append({"page": rel_a, "with": rel_b, "reason": reason})
                continue

            jaccard = _jaccard(text_a, text_b)
            if jaccard >= _NEAR_SIMILAR_JACCARD:
                near_similar_candidates.append((jaccard, rel_a, rel_b))

    near_similar_candidates.sort(key=lambda t: (-t[0], t[1], t[2]))
    near_similar_pairs = [
        {"page": rel_a, "with": rel_b, "reason": "near-similar"}
        for _, rel_a, rel_b in near_similar_candidates
    ]

    return (heuristic_pairs + near_similar_pairs)[:cap]


__all__ = [
    "Conflict",
    "ConflictKind",
    "ShortlistReason",
    "SHORTLIST_CAP",
    "detect",
    "contradiction_evidence",
    "duplicate_evidence",
    "is_l2_map",
    "project_subtree",
    "numeric_drift_evidence",
    "shortlist_pairs",
]
