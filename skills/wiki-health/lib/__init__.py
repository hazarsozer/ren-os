"""
skills.wiki-health library — the minimal coherence sweep (Task 9, RenOS 0.3
"the ungated brain"). With per-write human approval removed (v2.2's two-plane
pivot: the data plane auto-applies), this is the autonomous auditor that
replaces it — a periodic read-only sweep the live session runs, then fixes
what it can (through the existing write-safety substrate: `propose_and_apply`
/ `resolve_and_apply`) and interviews the friend only on genuine ambiguity.
See `SKILL.md` for the full behavior contract; this module is the sweep
mechanics only — it never writes anything itself.

`sweep()` returns seven findings + a timestamp:
  - `dangling_pointers` — every l2-map page's "## Decision map" pointer
    lines, target existence. Same question `skills.doctor.lib
    .check_dangling_pointers` answers, reimplemented here (not imported)
    because that check returns one joined `CheckResult.message` string —
    this needs one structured `{"page", "target"}` record per finding so a
    live session can act on each individually. Keep the two walks in sync if
    the L2 pointer-map schema (`## Decision map` / `- [x] → path#anchor`)
    ever changes.
  - `contradiction_pairs` — wiki-WIDE, not sibling-directory-only: every
    pair of pages whose body has a "## Knowledge" section is compared via
    `lib.memory.semantics.contradiction_evidence` (the pairwise core factored
    out of `detect`, so this can't drift from the write-time check's
    heuristic). `detect`'s own candidate set (target + same-directory
    siblings) is a sibling glob built for a single proposed write, not a
    wiki-wide auditor — this module builds its own all-pairs candidate set
    instead of calling `detect` directly. All-pairs is O(n^2); above
    `_CONTRADICTION_PAGE_CAP` pages, the scan narrows to pairs sharing a
    frontmatter `type` or a directory, and `contradiction_scan_note` in the
    returned dict records that the scan was capped (no silent truncation).
  - `duplicate_pairs` — the same wiki-wide candidate set, compared via
    `lib.memory.semantics.duplicate_evidence`: two applied pages whose
    bodies share ≥90% of their lines, a near-certain consolidation
    candidate rather than a contradiction.
  - `numeric_drift_pairs` — the same fact line appearing with different
    numbers, via `lib.memory.semantics.numeric_drift_evidence`. Checked both
    across pages AND within a single page (self-comparison), since two
    "## Knowledge" bullets in the same file can drift from each other just
    as easily as two separate pages can; for a within-page finding
    `page == with`.
  - `mass_deletions` — journal scan: more than 5 DELETE ops inside any
    rolling 24h window is an anomaly worth a friend's eyes, not proof of
    anything wrong on its own.
  - `quarantined_pages` — the unreviewed-content inventory
    (`lib.memory.quarantine.is_quarantined`): llm-auto writes still sitting
    behind the banner, never promoted or released.
  - `single_project_global_pages` — global-tier pages naming exactly one
    project (issue #18). The write-time gate (`lib.governance.tiers
    .INSTRUCTION_PLANE_PREFIXES`) stops NEW project-specific pages from
    landing in the global tier; this finds the ones already on disk,
    including hand-authored ones the queue never saw.
  - `hubless_knowledge_dirs` / `unlinked_knowledge_pages` — structural audit
    of the hierarchical `projects/<slug>/knowledge/` trees (issue #20
    amendment): a knowledge subdirectory must carry a hub `index.md`, and a
    leaf page in a subdirectory must be linked from some hub or project-root
    page. `projects/<slug>/raw/` (immutable source material) is skipped by
    the pairwise scans — sources, not claims.
"""

from __future__ import annotations

import re
import yaml
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Callable

from lib import ren_paths
from lib.evalkit.runner import run_retrieval_eval
from lib.governance.tiers import is_instruction_plane_page
from lib.instrument import collect
from lib.memory import journal, quarantine, semantics
from lib.memory.judge import (
    JUDGE_MAX_TEXT_CHARS,
    JUDGE_MIN_CONFIDENCE,
    JUDGE_PAIR_CAP,
    JudgeError,
    judge_pairs,
    parse_data_only_verdict,
)
from lib.ren_paths import PathTraversalError
from skills.recall.lib import rank as _recall_rank

from .lint import run_incremental_lint, walk_wiki_pages

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
_FM_TYPE_RE = re.compile(r"^type:\s*(.+)$", re.MULTILINE)
_POINTER_RE = re.compile(r"^-\s*\[[^\]]*\]\s*→\s*([^\s#]+)")
# External repository reference (issue #20): `repo:<name>:<path>`. Kept
# byte-identical with `skills.doctor.lib._REPO_REF_PREFIX` — the drift test
# `tests/skills/wiki_health/test_sweep.py` asserts the two agree.
_REPO_REF_PREFIX = "repo:"

_MASS_DELETION_WINDOW = timedelta(hours=24)
_MASS_DELETION_THRESHOLD = 5  # anomaly when a rolling window has MORE than this many


def _frontmatter_type(text: str) -> str | None:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    tm = _FM_TYPE_RE.search(m.group(1))
    return tm.group(1).strip().strip('"').strip("'") if tm else None


def _dangling_pointers(wiki_root: Path) -> list[dict]:
    """Reimplemented walk (see module docstring) — every l2-map page's
    "## Decision map" pointer lines whose target doesn't resolve."""
    dangling: list[dict] = []
    for md_path in sorted(wiki_root.rglob("*.md")):
        text = md_path.read_text(encoding="utf-8", errors="replace")
        if _frontmatter_type(text) != "l2-map":
            continue
        in_decision_map = False
        for line in text.splitlines():
            if line.startswith("## "):
                in_decision_map = line.strip() == "## Decision map"
                continue
            if not in_decision_map:
                continue
            m = _POINTER_RE.match(line.strip())
            if not m:
                continue
            target = m.group(1)
            page = str(md_path.relative_to(wiki_root))
            if target.startswith(_REPO_REF_PREFIX):
                # `repo:<name>:<path>` — an external repository reference
                # (issue #20). Not a wiki page, so not resolvable in-wiki and
                # never "dangling". Missing IN-WIKI targets are still flagged.
                continue
            if target.startswith("/"):
                dangling.append({"page": page, "target": target})
                continue
            try:
                target_path = ren_paths.safe_join(wiki_root, target)
            except PathTraversalError:
                dangling.append({"page": page, "target": target, "reason": "path-escaping"})
                continue
            if not target_path.is_file():
                dangling.append({"page": page, "target": target})
    return dangling


_CONTRADICTION_PAGE_CAP = 200  # above this many candidate pages, narrow the all-pairs scan


def _knowledge_pages(wiki_root: Path) -> list[tuple[str, str, str | None]]:
    """(rel_path, text, frontmatter_type) for every page with a "## Knowledge"
    section, skipping the `.ren/` metrics tree and quarantined pages (0.4.5:
    the producers-refuse-quarantined-sources contract — this scan feeds
    `wiki_health_critical`'s suggestion evidence, so unreviewed ingested
    content must be invisible to it)."""
    pages: list[tuple[str, str, str | None]] = []
    for rel in walk_wiki_pages(wiki_root, skip_raw=True):
        md_path = wiki_root / rel
        rel_path = Path(rel)
        text = md_path.read_text(encoding="utf-8", errors="replace")
        if "## Knowledge" not in text:
            continue
        if quarantine.is_quarantined(text):
            continue
        pages.append((str(rel_path), text, _frontmatter_type(text)))
    return pages


def _pair_findings(wiki_root: Path) -> tuple[list[dict], list[dict], list[dict], dict | None]:
    """Wiki-wide pairwise scans across every "## Knowledge" page: contradiction
    (negation heuristic), duplicate (shared-line ratio), and numeric drift
    (same line, different numbers — including WITHIN a single page via
    self-comparison). One loop, one candidate set, one cap (see module
    docstring). Returns `(contradictions, duplicates, drifts, cap_note)`."""
    pages = _knowledge_pages(wiki_root)
    n = len(pages)
    capped = n > _CONTRADICTION_PAGE_CAP

    contradictions: list[dict] = []
    duplicates: list[dict] = []
    drifts: list[dict] = []
    seen: set[frozenset] = set()
    pairs_checked = 0
    pairs_skipped = 0

    # Within-page drift: self-comparison finds two lines in ONE page that
    # share a masked template but differ in their numbers.
    for rel, text, _type in pages:
        drift = semantics.numeric_drift_evidence(text, text)
        if drift is not None:
            drifts.append({"page": rel, "with": rel, "evidence": f"{drift[0]}  ↔  {drift[1]}"})

    for i in range(n):
        rel_a, text_a, type_a = pages[i]
        dir_a = str(Path(rel_a).parent)
        for j in range(i + 1, n):
            rel_b, text_b, type_b = pages[j]
            if capped:
                same_type = type_a is not None and type_a == type_b
                same_dir = dir_a == str(Path(rel_b).parent)
                if not (same_type or same_dir):
                    pairs_skipped += 1
                    continue
            pairs_checked += 1

            evidence = semantics.contradiction_evidence(text_a, text_b)
            if evidence is not None:
                key = frozenset((rel_a, rel_b))
                if key not in seen:
                    seen.add(key)
                    contradictions.append({"page": rel_a, "with": rel_b, "evidence": evidence})

            dup = semantics.duplicate_evidence(text_a, text_b)
            if dup is not None:
                duplicates.append({"page": rel_a, "with": rel_b, "evidence": dup})

            drift = semantics.numeric_drift_evidence(text_a, text_b)
            if drift is not None:
                drifts.append({"page": rel_a, "with": rel_b, "evidence": f"{drift[0]}  ↔  {drift[1]}"})

    cap_note = None
    if capped:
        cap_note = {
            "page_count": n,
            "cap": _CONTRADICTION_PAGE_CAP,
            "pairs_checked": pairs_checked,
            "pairs_skipped": pairs_skipped,
            "reason": (
                f"{n} '## Knowledge' pages exceeds the {_CONTRADICTION_PAGE_CAP}-page "
                "all-pairs cap — pairwise scans (contradiction/duplicate/drift) narrowed "
                "to pairs sharing a frontmatter type or a directory; other pairs were "
                "not compared."
            ),
        }
    return contradictions, duplicates, drifts, cap_note


def _parse_journal_ts(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _mass_deletions() -> list[dict]:
    """Non-overlapping rolling-24h windows with MORE than
    `_MASS_DELETION_THRESHOLD` DELETE ops. Once a window is flagged, the
    scan resumes after it rather than re-flagging every overlapping
    sub-window of the same burst."""
    deletes = sorted(
        (e for e in journal.entries() if e.get("op") == "DELETE"),
        key=lambda e: e["ts"],
    )
    anomalies: list[dict] = []
    i, n = 0, len(deletes)
    while i < n:
        window_end = _parse_journal_ts(deletes[i]["ts"]) + _MASS_DELETION_WINDOW
        j = i
        while j < n and _parse_journal_ts(deletes[j]["ts"]) <= window_end:
            j += 1
        count = j - i
        if count > _MASS_DELETION_THRESHOLD:
            anomalies.append({
                "window_start": deletes[i]["ts"],
                "count": count,
                "pages": [e.get("page") for e in deletes[i:j]],
            })
            i = j
        else:
            i += 1
    return anomalies


def _quarantined_pages(wiki_root: Path) -> dict:
    pages = [
        str(md_path.relative_to(wiki_root))
        for md_path in sorted(wiki_root.rglob("*.md"))
        if ".ren" not in md_path.relative_to(wiki_root).parts
        and quarantine.is_quarantined(md_path.read_text(encoding="utf-8", errors="replace"))
    ]
    return {"count": len(pages), "pages": pages}


_PROJECT_REF_RE = re.compile(r"projects/([a-z0-9][a-z0-9._-]*)")
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9._-]*")


def _known_project_slugs(wiki_root: Path) -> set[str]:
    """The slug vocabulary: the repo-path↔slug registry plus every directory
    under `projects/`. Never raises — a missing/corrupt registry just
    narrows the vocabulary."""
    slugs = {s.lower() for s in ren_paths.load_project_registry()}
    projects_dir = wiki_root / "projects"
    if projects_dir.is_dir():
        slugs |= {p.name.lower() for p in projects_dir.iterdir() if p.is_dir()}
    return slugs


def _single_project_global_pages(wiki_root: Path) -> list[dict]:
    """Global-tier pages (`lib.governance.tiers.INSTRUCTION_PLANE_PREFIXES`)
    whose body names EXACTLY ONE project — the shape issue #18 caught live
    (a project-specific `decisions/flux-stack.md` written during ingest).

    Founder doctrine: the global tier is only for practices general enough
    to apply across projects; a page about one project belongs under
    `projects/<slug>/`. Deliberately cheap and word-based: an explicit
    `projects/<slug>` reference, or a bare word matching a known slug.
    Naming zero projects (genuinely general) or two-plus (a real
    cross-project comparison) is not a finding."""
    from lib.governance.tiers import INSTRUCTION_PLANE_PREFIXES

    slugs = _known_project_slugs(wiki_root)
    findings: list[dict] = []
    for prefix in INSTRUCTION_PLANE_PREFIXES:
        tier_dir = wiki_root / prefix.rstrip("/")
        if not tier_dir.is_dir():
            continue
        for md_path in sorted(tier_dir.rglob("*.md")):
            try:
                low = md_path.read_text(encoding="utf-8", errors="replace").lower()
            except OSError:  # pragma: no cover - unreadable page is not a finding
                continue
            named = {m.group(1) for m in _PROJECT_REF_RE.finditer(low)}
            words = set(_WORD_RE.findall(low))
            named |= {slug for slug in slugs if slug in words}
            if len(named) == 1:
                findings.append({
                    "page": md_path.relative_to(wiki_root).as_posix(),
                    "project": next(iter(named)),
                })
    return findings


def _knowledge_tree_findings(wiki_root: Path) -> tuple[list[str], list[str]]:
    """Structural audit of the hierarchical `projects/<slug>/knowledge/`
    trees (issue #20 amendment — Karpathy LLM-wiki pattern).

    Returns `(hubless_knowledge_dirs, unlinked_knowledge_pages)`:
      - every subdirectory (any depth) of a project's `knowledge/` without a
        hub `index.md`;
      - every leaf page (non-`index.md` `*.md` in a SUBDIRECTORY of
        `knowledge/`) whose filename appears in no hub page and no page
        directly under `projects/<slug>/` (map/overview/schema). Top-level
        `knowledge/*.md` pages are exempt — the map indexes them directly.

    Deliberately cheap and name-based (same spirit as
    `_single_project_global_pages`): a leaf counts as linked if its filename
    is mentioned anywhere in a hub or project-root page — forgiving over
    false positives."""
    hubless: list[str] = []
    unlinked: list[str] = []
    projects_dir = wiki_root / "projects"
    if not projects_dir.is_dir():
        return hubless, unlinked

    for project_dir in sorted(p for p in projects_dir.iterdir() if p.is_dir()):
        knowledge = project_dir / "knowledge"
        if not knowledge.is_dir():
            continue

        # Text that can legitimately link a leaf: every hub index.md in the
        # knowledge tree, plus every page directly under the project root
        # (map.md's Decision map, overview.md, schema.md).
        link_text: list[str] = []
        for page in sorted(project_dir.glob("*.md")):
            link_text.append(page.read_text(encoding="utf-8", errors="replace"))
        for hub in sorted(knowledge.rglob("index.md")):
            link_text.append(hub.read_text(encoding="utf-8", errors="replace"))
        joined = "\n".join(link_text)

        for sub in sorted(p for p in knowledge.rglob("*") if p.is_dir()):
            # Only dirs that actually organize markdown (any .md, direct or
            # deeper) need a hub — empty scaffold dirs and asset-only dirs
            # (knowledge/img/) have no children a hub could summarize.
            if next(sub.rglob("*.md"), None) is None:
                continue
            if not (sub / "index.md").is_file():
                hubless.append(sub.relative_to(wiki_root).as_posix())

        for leaf in sorted(knowledge.rglob("*.md")):
            if leaf.name == "index.md" or leaf.parent == knowledge:
                continue
            # Word-bounded filename match: a bare substring check let `a.md`
            # count as linked via `schema.md` and `map.md` via
            # `combat-map.md`. Preceding path separators (`/`, `(`, space…)
            # are fine; filename characters are not.
            name_re = re.compile(
                rf"(?<![A-Za-z0-9._-]){re.escape(leaf.name)}(?![A-Za-z0-9_])"
            )
            if not name_re.search(joined):
                unlinked.append(leaf.relative_to(wiki_root).as_posix())

    return hubless, unlinked


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Frozen retrieval-eval fixture + its own mini wiki (ships with the plugin
# under `lib/evalkit/fixtures/` — NOT `tests/`, which is never shipped).
# Scored against the shipped ranker (`skills.recall.lib.rank`), independent
# of whatever `wiki_root` this sweep was run against — this measures the
# ranker's fixed quality against known-answerable queries, not the friend's
# live wiki content.
_RETRIEVAL_FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "lib" / "evalkit" / "fixtures"
_RETRIEVAL_FIXTURE_PATH = _RETRIEVAL_FIXTURE_DIR / "retrieval_fixture.json"
_RETRIEVAL_MINI_WIKI = _RETRIEVAL_FIXTURE_DIR / "mini_wiki"


def _retrieval_eval() -> dict:
    """Score the shipped ranker against the frozen retrieval fixture and
    record the result to monthly metrics (`KIND_RETRIEVAL_EVAL`).

    Fail-closed like every other eval consumer in the sweep: any exception
    (missing fixture, ranker crash, malformed fixture) degrades to
    `{"hit_rate": None, "error": "<msg>"}` — the sweep itself never crashes
    because of this eval."""
    try:
        report = run_retrieval_eval(_recall_rank, _RETRIEVAL_FIXTURE_PATH, _RETRIEVAL_MINI_WIKI)
        result = {"hit_rate": report.hit_rate, "cases": report.total}
    except Exception as exc:  # noqa: BLE001 - deliberately broad: eval failures never crash the sweep
        result = {"hit_rate": None, "error": f"{type(exc).__name__}: {exc}"}

    collect.record(collect.KIND_RETRIEVAL_EVAL, dict(result))
    return result


def _judge_annotate(
    wiki_root: Path,
    contradiction_pairs: list[dict],
    duplicate_pairs: list[dict],
    numeric_drift_pairs: list[dict],
    llm_call: Callable[[str], str],
) -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict]]:
    """Judge (Task 4) the wiki-wide shortlist (Task 11, `focus_pages=None`)
    and layer verdicts onto the three heuristic pair lists.

    Operates on FRESH COPIES of the three input lists and only returns them
    on success — `sweep` commits the return value only inside a try/except,
    so a `shortlist_pairs`/`judge_pairs`/read exception here leaves the
    caller's already-computed no-llm result untouched (fail-closed, matching
    Task 12's wrap consumer).

    - A heuristic pair (`heuristic-contradiction` / `heuristic-duplicate` /
      `numeric-drift`) the judge confidently (>= `JUDGE_MIN_CONFIDENCE`)
      calls `unrelated` is REMOVED from its list and appended to the
      returned `judge_dismissed` list instead — its original `evidence` is
      preserved (anti-Goodhart: the judge filters visibility, never makes
      evidence disappear). Any other verdict is attached as a `"judge"` dict
      on the pair in place.
    - A `near-similar` shortlist pair (not one of the three heuristics)
      never silently vanishes once the judge has spoken confidently (0.5.2
      drill leg 2 — judged evidence must never vanish):
        - `duplicate` at >= `JUDGE_MIN_CONFIDENCE` joins `duplicate_pairs`
          with a synthetic evidence string and its `"judge"` dict.
        - `contradicts` at >= `JUDGE_MIN_CONFIDENCE` joins
          `contradiction_pairs` the same way — this is what flows to
          `wiki_health_critical` for `global/` pages, same as a
          heuristic-found contradiction.
        - `supersedes` at >= `JUDGE_MIN_CONFIDENCE` has no existing home in
          the three heuristic lists (supersedes is not a contradiction —
          don't shoehorn it in) — it's appended to the returned
          `judge_supersedes` list instead, kept visible like
          `judge_dismissed` but not automated on.
        - Sub-threshold or `unrelated` near-similar verdicts produce no
          finding — a near-similar pair was never a finding without the
          judge, so this isn't a silent drop of asserted evidence.
    - Verdicts of `None` (fail-closed per-pair or dropped by the cap) leave
      the corresponding pair exactly as the no-llm sweep produced it.
    """
    contradiction_pairs = [dict(p) for p in contradiction_pairs]
    duplicate_pairs = [dict(p) for p in duplicate_pairs]
    numeric_drift_pairs = [dict(p) for p in numeric_drift_pairs]
    judge_dismissed: list[dict] = []
    judge_supersedes: list[dict] = []

    pairs = semantics.shortlist_pairs(wiki_root, focus_pages=None)
    if not pairs:
        return contradiction_pairs, duplicate_pairs, numeric_drift_pairs, judge_dismissed, judge_supersedes

    texts = [
        (
            (wiki_root / p["page"]).read_text(encoding="utf-8", errors="replace"),
            (wiki_root / p["with"]).read_text(encoding="utf-8", errors="replace"),
        )
        for p in pairs
    ]
    verdicts = judge_pairs(texts, llm_call, cap=JUDGE_PAIR_CAP)

    lists_by_reason = {
        "heuristic-contradiction": contradiction_pairs,
        "heuristic-duplicate": duplicate_pairs,
        "numeric-drift": numeric_drift_pairs,
    }

    for pair, verdict in zip(pairs, verdicts):
        if verdict is None:
            continue
        judge_dict = {"verdict": verdict.kind, "confidence": verdict.confidence, "reason": verdict.reason}
        key = frozenset((pair["page"], pair["with"]))

        if pair["reason"] == "near-similar":
            if verdict.confidence < JUDGE_MIN_CONFIDENCE:
                continue
            if verdict.kind == "duplicate":
                duplicate_pairs.append({
                    "page": pair["page"],
                    "with": pair["with"],
                    "evidence": "near-similar (judge-confirmed)",
                    "judge": judge_dict,
                })
            elif verdict.kind == "contradicts":
                contradiction_pairs.append({
                    "page": pair["page"],
                    "with": pair["with"],
                    "evidence": "near-similar (judge-confirmed contradiction)",
                    "judge": judge_dict,
                })
            elif verdict.kind == "supersedes":
                judge_supersedes.append({
                    "page": pair["page"],
                    "with": pair["with"],
                    "evidence": "near-similar (judge-confirmed supersedes)",
                    "judge": judge_dict,
                })
            continue

        target = lists_by_reason.get(pair["reason"])
        if target is None:
            continue
        entry = next((e for e in target if frozenset((e["page"], e["with"])) == key), None)
        if entry is None:
            continue

        if verdict.kind == "unrelated" and verdict.confidence >= JUDGE_MIN_CONFIDENCE:
            target.remove(entry)
            dismissed = dict(entry)
            dismissed["judge"] = judge_dict
            judge_dismissed.append(dismissed)
        else:
            entry["judge"] = judge_dict

    return contradiction_pairs, duplicate_pairs, numeric_drift_pairs, judge_dismissed, judge_supersedes


def sweep(wiki_root: Path | None = None, llm_call: Callable[[str], str] | None = None) -> dict:
    """Run the full read-only coherence sweep. Never writes anything —
    fixing findings is the live session's job (see SKILL.md).

    Returns the 7 documented keys (`dangling_pointers`, `contradiction_pairs`,
    `duplicate_pairs`, `numeric_drift_pairs`, `mass_deletions`,
    `quarantined_pages`, `generated_at`) plus `contradiction_scan_note` —
    `None` unless the wiki-wide pairwise scan was capped (see
    `_pair_findings`), in which case it's a dict naming what was skipped and
    why — plus an 8th key, `judge_dismissed` (Task 13, 0.5.2): always
    present, `[]` unless `llm_call` is given and the judge confidently
    dismisses a heuristic pair as `unrelated` (see `_judge_annotate`) — and
    a 9th key, `judge_supersedes` (0.5.2 drill leg 2 fix): always present,
    `[]` unless the judge confidently calls a near-similar pair
    `supersedes` (kept visible, never automated on, same doctrine as
    `judge_dismissed`).

    `llm_call` (optional, Task 13): when given, the wiki-wide shortlist
    (`lib.memory.semantics.shortlist_pairs`, `focus_pages=None`) is judged
    and the verdicts are layered onto `contradiction_pairs`,
    `duplicate_pairs`, and `numeric_drift_pairs` (each judged pair gains a
    `"judge"` dict), with confidently-dismissed pairs moved to
    `judge_dismissed`, judge-confirmed near-similar duplicates joining
    `duplicate_pairs`, judge-confirmed near-similar contradictions joining
    `contradiction_pairs`, and judge-confirmed near-similar supersedes
    joining `judge_supersedes` — judged evidence never silently vanishes.
    Fail-closed like every other judge consumer: any exception during
    judging (shortlist scan, page read, `judge_pairs`) leaves the result
    exactly as the no-llm sweep would have produced it. Without `llm_call`
    (the default), behavior is byte-identical to before Task 13 plus the
    always-present empty `judge_dismissed`/`judge_supersedes` keys.

    A 10th key, `retrieval_eval` (Task 11, 0.6.1 E5b): `{"hit_rate", "cases"}`
    from scoring the shipped ranker against the frozen retrieval-eval
    fixture (independent of this call's `wiki_root`), or
    `{"hit_rate": None, "error": "<msg>"}` if the eval itself fails —
    fail-closed, never crashes the sweep. Also recorded to monthly metrics
    via `KIND_RETRIEVAL_EVAL`. This is exit criterion 2's instrument.

    An 11th key, `machine_released_total` (quarantine screen, spec
    2026-08-03-quarantine-screen-design.md): the count of
    `quarantine-screen-release` queue entries with `status == "applied"`,
    read via `lib.memory.queue.all_entries()` — the GLOBAL queue directory,
    not this call's `wiki_root` argument, so it counts the whole queue
    history regardless of which wiki root was swept. `0` when `wiki_root`
    doesn't exist (the early-return branch below never reads the queue)."""
    wiki_root = wiki_root or ren_paths.wiki_root()
    if not wiki_root.is_dir():
        return {
            "dangling_pointers": [],
            "contradiction_pairs": [],
            "duplicate_pairs": [],
            "numeric_drift_pairs": [],
            "contradiction_scan_note": None,
            "mass_deletions": _mass_deletions(),
            "quarantined_pages": {"count": 0, "pages": []},
            "single_project_global_pages": [],
            "hubless_knowledge_dirs": [],
            "unlinked_knowledge_pages": [],
            "judge_dismissed": [],
            "judge_supersedes": [],
            "retrieval_eval": _retrieval_eval(),
            "machine_released_total": 0,
            "generated_at": _now_iso(),
        }
    contradiction_pairs, duplicate_pairs, numeric_drift_pairs, contradiction_scan_note = _pair_findings(wiki_root)
    judge_dismissed: list[dict] = []
    judge_supersedes: list[dict] = []
    if llm_call is not None:
        try:
            (
                contradiction_pairs,
                duplicate_pairs,
                numeric_drift_pairs,
                judge_dismissed,
                judge_supersedes,
            ) = _judge_annotate(
                wiki_root, contradiction_pairs, duplicate_pairs, numeric_drift_pairs, llm_call
            )
        except Exception:  # noqa: BLE001 - fail-closed: keep the no-llm result already computed
            pass
    hubless_knowledge_dirs, unlinked_knowledge_pages = _knowledge_tree_findings(wiki_root)

    from lib.memory.queue import all_entries

    machine_released_total = sum(
        1
        for e in all_entries()
        if e.proposal.reason == "quarantine-screen-release" and e.status == "applied"
    )

    return {
        "dangling_pointers": _dangling_pointers(wiki_root),
        "contradiction_pairs": contradiction_pairs,
        "duplicate_pairs": duplicate_pairs,
        "numeric_drift_pairs": numeric_drift_pairs,
        "contradiction_scan_note": contradiction_scan_note,
        "mass_deletions": _mass_deletions(),
        "quarantined_pages": _quarantined_pages(wiki_root),
        "single_project_global_pages": _single_project_global_pages(wiki_root),
        "hubless_knowledge_dirs": hubless_knowledge_dirs,
        "unlinked_knowledge_pages": unlinked_knowledge_pages,
        "judge_dismissed": judge_dismissed,
        "judge_supersedes": judge_supersedes,
        "retrieval_eval": _retrieval_eval(),
        "machine_released_total": machine_released_total,
        "generated_at": _now_iso(),
    }


def render_report(findings: dict) -> str:
    """Render `sweep()`'s findings as the markdown a live session shows the
    friend — one section per finding kind, "none" when a section is empty
    (an explicit "checked, found nothing" beats a silently missing section)."""
    lines = [f"# Wiki health sweep — {findings.get('generated_at', '')}", ""]

    lines.append("## Dangling pointers")
    dangling = findings.get("dangling_pointers") or []
    if dangling:
        lines.extend(f"- {d['page']} → {d['target']}" for d in dangling)
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Contradiction pairs")
    pairs = findings.get("contradiction_pairs") or []
    if pairs:
        lines.extend(f"- {c['page']} ↔ {c['with']}: {c['evidence']}" for c in pairs)
    else:
        lines.append("- none")
    scan_note = findings.get("contradiction_scan_note")
    if scan_note:
        lines.append(f"- NOTE (scan capped): {scan_note['reason']}")
    lines.append("")

    lines.append("## Duplicate pairs")
    dups = findings.get("duplicate_pairs") or []
    if dups:
        lines.extend(f"- {d['page']} ↔ {d['with']}: {d['evidence']}" for d in dups)
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Numeric drift")
    drifts = findings.get("numeric_drift_pairs") or []
    if drifts:
        lines.extend(
            f"- {d['page']}" + ("" if d["page"] == d["with"] else f" ↔ {d['with']}") + f": {d['evidence']}"
            for d in drifts
        )
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Mass deletions")
    anomalies = findings.get("mass_deletions") or []
    if anomalies:
        lines.extend(
            f"- {a['count']} deletes starting {a['window_start']}: {', '.join(p for p in a['pages'] if p)}"
            for a in anomalies
        )
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Global-tier pages naming a single project")
    single = findings.get("single_project_global_pages") or []
    if single:
        lines.extend(
            f"- {s['page']}: names only {s['project']} — belongs under projects/{s['project']}/"
            for s in single
        )
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Knowledge dirs without a hub")
    hubless = findings.get("hubless_knowledge_dirs") or []
    if hubless:
        lines.extend(f"- {d}: missing index.md hub page" for d in hubless)
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Unlinked knowledge pages")
    unlinked = findings.get("unlinked_knowledge_pages") or []
    if unlinked:
        lines.extend(f"- {p}: linked from no hub and no map" for p in unlinked)
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Quarantined (unreviewed)")
    quarantined = findings.get("quarantined_pages") or {"count": 0, "pages": []}
    lines.append(f"- {quarantined['count']} page(s)")
    lines.extend(f"  - {p}" for p in quarantined.get("pages", []))

    lines.append("")
    lines.append("## Machine-released (quarantine screen)")
    lines.append(f"- {findings.get('machine_released_total', 0)} page(s) total")

    dismissed = findings.get("judge_dismissed") or []
    if dismissed:
        lines.append("")
        lines.append("## Judge-dismissed (for review)")
        for d in dismissed:
            judge = d.get("judge") or {}
            lines.append(
                f"- {d['page']} ↔ {d['with']}: judge={judge.get('verdict')} "
                f"(confidence {judge.get('confidence')}): {judge.get('reason')} "
                f"— heuristic evidence: {d['evidence']}"
            )

    supersedes = findings.get("judge_supersedes") or []
    if supersedes:
        lines.append("")
        lines.append("## Judge-flagged supersedes (for review)")
        for s in supersedes:
            judge = s.get("judge") or {}
            lines.append(
                f"- {s['page']} ↔ {s['with']}: judge={judge.get('verdict')} "
                f"(confidence {judge.get('confidence')}): {judge.get('reason')}"
            )

    return "\n".join(lines) + "\n"


def release_page(page: str, session: str) -> tuple:
    """Release `page` from quarantine — the ONLY product exit from the
    banner state, and it exists precisely because release is a HUMAN act:
    the live session calls this only after the friend explicitly says the
    page is fine (see SKILL.md; never auto-release from a sweep).

    Routes through the normal write substrate (writer="human",
    producer="retrospective" — this module isn't its own producer class, see
    SKILL.md "What this skill does NOT do") so the release is journaled,
    snapshotted, and revertible like every other write. Because release IS
    the human review, the write goes `propose` → `approve_and_apply`
    (0.6.2 review finding H3) rather than `propose_and_apply` — a
    quarantined instruction-plane page (`decisions/*` etc.) would otherwise
    pend forever, since `propose_and_apply` holds instruction-plane targets
    for exactly the human approval this call already represents.

    Returns `(QueueEntry, Provenance | None)` — `Provenance` is None only if
    the proposal was held on a `contradicts` conflict (the session resolves
    it like any other hold) or was a no-op.

    Raises `FileNotFoundError` if the page doesn't exist, `ValueError` if it
    isn't quarantined."""
    from lib.memory.queue import Proposal, approve_and_apply, get, propose

    path = ren_paths.safe_join(ren_paths.wiki_root(), page)
    if not path.is_file():
        raise FileNotFoundError(f"no such wiki page: {page!r}")
    text = path.read_text(encoding="utf-8")
    if not quarantine.is_quarantined(text):
        raise ValueError(f"{page!r} is not quarantined — nothing to release")

    entry = propose(
        Proposal(
            op="UPDATE",
            page=page,
            content=quarantine.release(text),
            reason="quarantine-release",
            producer="retrospective",
            writer="human",
            session=session,
        )
    )
    if entry.status != "pending":
        return entry, None
    if any(c.get("kind") == "contradicts" for c in entry.conflicts):
        return entry, None
    prov = approve_and_apply(entry.qid, who="human:quarantine-release")
    return get(entry.qid), prov


# --------------------------------------------------------------------------
# Quarantine screen (spec 2026-08-03-quarantine-screen-design.md): the
# bounded MACHINE exit from quarantine. Everything here fails closed — any
# doubt leaves the page quarantined. `release_page` above remains the human
# path; `release_page_auto` is reachable only through the screen's gate.

def _page_trust(md_text: str) -> str | None:
    """The page's `ren_trust` frontmatter stamp, or None when absent or the
    frontmatter is malformed (fail closed: None never screens as model)."""
    match = _FRONTMATTER_RE.match(md_text)
    if match is None:
        return None
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    trust = data.get("ren_trust")
    return trust if isinstance(trust, str) else None


def screen_ineligibility(rel: str, md_text: str) -> str | None:
    """Why `rel` may NOT be auto-released — or None when it is eligible.

    Reasons: "l1" (wrap's concern, skipped silently by the screen),
    "instruction-plane" (always a human decision), "non-model-trust"
    (foreign/unstamped/malformed — always a human decision)."""
    if "l1" in PurePosixPath(rel).parts:
        return "l1"
    if is_instruction_plane_page(rel):
        return "instruction-plane"
    if _page_trust(md_text) != "model":
        return "non-model-trust"
    return None


def release_page_auto(page: str, session: str, evidence: dict) -> tuple:
    """Machine release — same queue mechanics as `release_page`, different
    actor. `writer="retrospective"` deliberately: `writer="llm-auto"` content
    is banner-marked at the queue door (`_quarantined_content`), which would
    re-quarantine the very page being released. `producer="retrospective"`
    matches `release_page` (no wiki-health producer class exists).
    `trust_class("retrospective", ...)` derives "model", so the page's trust
    stamp is unchanged by the release.

    Returns `(QueueEntry, Provenance | None)` — Provenance is None if held
    on a `contradicts` conflict or a queue no-op, exactly like
    `release_page`. Raises FileNotFoundError / ValueError like it too.

    `evidence` (the judge verdict or ineligibility reason that justified the
    release) is recorded to the metrics stream (`KIND_QUARANTINE_RELEASE`)
    on a successful release — `approve_and_apply`/`apply` have no `extra`
    dict reachable without widening the queue's own contract, so this is the
    audit trail for WHY, alongside the journal's record of WHAT and WHO."""
    from lib.instrument import collect
    from lib.memory.queue import Proposal, approve_and_apply, get, propose

    path = ren_paths.safe_join(ren_paths.wiki_root(), page)
    if not path.is_file():
        raise FileNotFoundError(f"no such wiki page: {page!r}")
    text = path.read_text(encoding="utf-8")
    if not quarantine.is_quarantined(text):
        raise ValueError(f"{page!r} is not quarantined — nothing to release")

    entry = propose(
        Proposal(
            op="UPDATE",
            page=page,
            content=quarantine.release(text),
            reason="quarantine-screen-release",
            producer="retrospective",
            writer="retrospective",
            session=session,
        )
    )
    if entry.status != "pending":
        return entry, None
    if any(c.get("kind") == "contradicts" for c in entry.conflicts):
        return entry, None
    prov = approve_and_apply(entry.qid, who="agent:quarantine-screen")
    collect.record(
        collect.KIND_QUARANTINE_RELEASE,
        {"page": page, "session": session, "evidence": evidence},
    )
    return get(entry.qid), prov


def _record_release_suggestion(rel: str, why: str, evidence: dict) -> None:
    """File (fingerprint-deduped) 'release this page?' into the suggestions
    store. A page the friend already declined never re-nags (`record`
    returns None for known fingerprints — that is the dedup, not an error)."""
    from lib.suggestions import SuggestionSpec, record

    record(
        SuggestionSpec(
            producer="wiki-health",
            title=f"Release {rel} from quarantine?",
            rationale=f"quarantine screen routed this page to you: {why}",
            evidence=evidence,
            kind="structured_action",
            payload={"action": "quarantine_release", "page": rel, "evidence": evidence},
            fingerprint=f"quarantine:release:{rel}",
        )
    )


def run_quarantine_screen(session: str, cap: int = 20) -> dict:
    """Phase 1 of the quarantine screen: filter + deterministic scan.

    Walks every quarantined page (sorted, so runs are deterministic):
      - l1 pages: skipped silently (wrap's concern, not the screen's);
      - ineligible pages (non-model trust, instruction-plane): routed to the
        suggestions store, reported under `suggested`;
      - scanner hits (`detect_instruction_shaped`): routed to suggestions,
        never judged;
      - clean eligible pages: returned under `candidates`, each with a
        ready-built judge prompt for the agent (phase 2 applies verdicts).

    At most `cap` pages that would otherwise become CANDIDATES are screened
    per run; suggestion-routed pages (ineligible or scanner-hit) never
    consume the cap — fingerprint dedup already makes re-recording free, so
    routing them costs nothing, while letting them eat cap slots would let a
    sorted run of ineligible pages permanently starve every candidate that
    sorts after them. The remainder of would-be candidates is reported in
    `skipped_remaining` — never silently dropped. Unreadable pages land in
    `errors` and stay quarantined.

    A page whose full text exceeds the judge's truncation window
    (`lib.memory.judge.JUDGE_MAX_TEXT_CHARS`) is routed to suggestions with
    `why="too-long"` before either the scanner or the judge sees it: the
    judge prompt only ever carries the text's TAIL (see `_truncate`), so an
    unjudged head must never ride to release on a tail-only verdict — this
    check runs before the scanner so the routing reason names the real
    cause."""
    from lib.memory.judge import build_data_only_prompt

    root = ren_paths.wiki_root()
    result: dict = {
        "backlog_total": 0,
        "candidates": [],
        "suggested": [],
        "skipped_remaining": 0,
        "errors": [],
    }
    candidates_taken = 0
    for rel in sorted(quarantine.quarantined_rel_pages(root)):
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 - unreadable stays quarantined
            result["errors"].append(f"{rel}: unreadable ({exc})")
            continue
        why = screen_ineligibility(rel, text)
        if why == "l1":
            continue
        result["backlog_total"] += 1
        if why is not None:
            _record_release_suggestion(rel, why, {"ineligible": why})
            result["suggested"].append({"page": rel, "why": why})
            continue
        if len(text) > JUDGE_MAX_TEXT_CHARS:
            evidence = {"length": len(text), "limit": JUDGE_MAX_TEXT_CHARS}
            _record_release_suggestion(rel, "too-long", evidence)
            result["suggested"].append({"page": rel, "why": "too-long"})
            continue
        hits = quarantine.detect_instruction_shaped(text)
        if hits:
            _record_release_suggestion(rel, "instruction-shaped", {"scanner_hits": hits})
            result["suggested"].append({"page": rel, "why": "instruction-shaped"})
            continue
        if candidates_taken >= cap:
            result["skipped_remaining"] += 1
            continue
        candidates_taken += 1
        result["candidates"].append({"page": rel, "prompt": build_data_only_prompt(text)})
    return result


def apply_quarantine_verdicts(session: str, verdicts: dict) -> dict:
    """Phase 2 of the quarantine screen: apply the agent's per-page verdicts.

    Every page is RE-CHECKED before release (still quarantined, still
    eligible, still under the judge's text-length window, still
    scanner-clean) — phase 1's snapshot is advisory, the state at apply time
    is what counts. A page whose full text now exceeds
    `lib.memory.judge.JUDGE_MAX_TEXT_CHARS` is routed to suggestions with
    `why="too-long"` regardless of the verdict passed in — a verdict built
    from a tail-only judge prompt says nothing about an unjudged head.
    Fail-closed on every path: a malformed verdict, a failed re-check, or a
    queue hold leaves the page quarantined (`errors` / `suggested` / `held`
    respectively)."""
    root = ren_paths.wiki_root()
    result: dict = {"released": [], "held": [], "suggested": [], "errors": []}
    for rel, raw in sorted(verdicts.items()):
        try:
            text = ren_paths.safe_join(root, rel).read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 - missing/unreadable/traversal: fail closed
            result["errors"].append(f"{rel}: unreadable ({exc})")
            continue
        if not quarantine.is_quarantined(text):
            continue  # already released or never quarantined: clean no-op
        why = screen_ineligibility(rel, text)
        if why is not None:
            if why != "l1":
                _record_release_suggestion(rel, why, {"ineligible": why})
                result["suggested"].append({"page": rel, "why": why})
            continue
        if len(text) > JUDGE_MAX_TEXT_CHARS:
            evidence = {"length": len(text), "limit": JUDGE_MAX_TEXT_CHARS}
            _record_release_suggestion(rel, "too-long", evidence)
            result["suggested"].append({"page": rel, "why": "too-long"})
            continue
        hits = quarantine.detect_instruction_shaped(text)
        if hits:
            _record_release_suggestion(rel, "instruction-shaped", {"scanner_hits": hits})
            result["suggested"].append({"page": rel, "why": "instruction-shaped"})
            continue
        try:
            verdict = parse_data_only_verdict(raw)
        except JudgeError as exc:
            result["errors"].append(f"{rel}: invalid verdict ({exc})")
            continue
        if not (verdict.data_only and verdict.confidence >= JUDGE_MIN_CONFIDENCE):
            evidence = {
                "judge": {
                    "data_only": verdict.data_only,
                    "confidence": verdict.confidence,
                    "reason": verdict.reason,
                }
            }
            _record_release_suggestion(rel, "judge-objected", evidence)
            result["suggested"].append({"page": rel, "why": "judge-objected"})
            continue
        entry, prov = release_page_auto(
            rel, session, {"judge": {"confidence": verdict.confidence, "reason": verdict.reason}}
        )
        if prov is None:
            result["held"].append(rel)
        else:
            result["released"].append(rel)
    return result


__all__ = [
    "sweep",
    "render_report",
    "release_page",
    "run_incremental_lint",
    "walk_wiki_pages",
    "screen_ineligibility",
    "release_page_auto",
    "run_quarantine_screen",
    "apply_quarantine_verdicts",
]
