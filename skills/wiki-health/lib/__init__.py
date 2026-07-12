"""
skills.wiki-health library — the minimal coherence sweep (Task 9, RenOS 0.3
"the ungated brain"). With per-write human approval removed (v2.2's two-plane
pivot: the data plane auto-applies), this is the autonomous auditor that
replaces it — a periodic read-only sweep the live session runs, then fixes
what it can (through the existing write-safety substrate: `propose_and_apply`
/ `resolve_and_apply`) and interviews the friend only on genuine ambiguity.
See `SKILL.md` for the full behavior contract; this module is the sweep
mechanics only — it never writes anything itself.

`sweep()` returns six findings + a timestamp:
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
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from lib import ren_paths
from lib.memory import journal, quarantine, semantics
from lib.memory.judge import JUDGE_MIN_CONFIDENCE, JUDGE_PAIR_CAP, judge_pairs
from lib.ren_paths import PathTraversalError

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
_FM_TYPE_RE = re.compile(r"^type:\s*(.+)$", re.MULTILINE)
_POINTER_RE = re.compile(r"^-\s*\[[^\]]*\]\s*→\s*([^\s#]+)")

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
    for md_path in sorted(wiki_root.rglob("*.md")):
        rel_path = md_path.relative_to(wiki_root)
        if ".ren" in rel_path.parts:
            continue
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _judge_annotate(
    wiki_root: Path,
    contradiction_pairs: list[dict],
    duplicate_pairs: list[dict],
    numeric_drift_pairs: list[dict],
    llm_call: Callable[[str], str],
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
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
    - A `near-similar` shortlist pair (not one of the three heuristics) only
      surfaces at all if the judge confidently confirms `duplicate` — it is
      then appended to `duplicate_pairs` with a synthetic evidence string
      and its `"judge"` dict.
    - Verdicts of `None` (fail-closed per-pair or dropped by the cap) leave
      the corresponding pair exactly as the no-llm sweep produced it.
    """
    contradiction_pairs = [dict(p) for p in contradiction_pairs]
    duplicate_pairs = [dict(p) for p in duplicate_pairs]
    numeric_drift_pairs = [dict(p) for p in numeric_drift_pairs]
    judge_dismissed: list[dict] = []

    pairs = semantics.shortlist_pairs(wiki_root, focus_pages=None)
    if not pairs:
        return contradiction_pairs, duplicate_pairs, numeric_drift_pairs, judge_dismissed

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
            if verdict.kind == "duplicate" and verdict.confidence >= JUDGE_MIN_CONFIDENCE:
                duplicate_pairs.append({
                    "page": pair["page"],
                    "with": pair["with"],
                    "evidence": "near-similar (judge-confirmed)",
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

    return contradiction_pairs, duplicate_pairs, numeric_drift_pairs, judge_dismissed


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
    dismisses a heuristic pair as `unrelated` (see `_judge_annotate`).

    `llm_call` (optional, Task 13): when given, the wiki-wide shortlist
    (`lib.memory.semantics.shortlist_pairs`, `focus_pages=None`) is judged
    and the verdicts are layered onto `contradiction_pairs`,
    `duplicate_pairs`, and `numeric_drift_pairs` (each judged pair gains a
    `"judge"` dict), with confidently-dismissed pairs moved to
    `judge_dismissed` and judge-confirmed near-similar duplicates joining
    `duplicate_pairs`. Fail-closed like every other judge consumer: any
    exception during judging (shortlist scan, page read, `judge_pairs`)
    leaves the result exactly as the no-llm sweep would have produced it.
    Without `llm_call` (the default), behavior is byte-identical to before
    Task 13 plus the always-present empty `judge_dismissed` key."""
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
            "judge_dismissed": [],
            "generated_at": _now_iso(),
        }
    contradiction_pairs, duplicate_pairs, numeric_drift_pairs, contradiction_scan_note = _pair_findings(wiki_root)
    judge_dismissed: list[dict] = []
    if llm_call is not None:
        try:
            contradiction_pairs, duplicate_pairs, numeric_drift_pairs, judge_dismissed = _judge_annotate(
                wiki_root, contradiction_pairs, duplicate_pairs, numeric_drift_pairs, llm_call
            )
        except Exception:  # noqa: BLE001 - fail-closed: keep the no-llm result already computed
            pass
    return {
        "dangling_pointers": _dangling_pointers(wiki_root),
        "contradiction_pairs": contradiction_pairs,
        "duplicate_pairs": duplicate_pairs,
        "numeric_drift_pairs": numeric_drift_pairs,
        "contradiction_scan_note": contradiction_scan_note,
        "mass_deletions": _mass_deletions(),
        "quarantined_pages": _quarantined_pages(wiki_root),
        "judge_dismissed": judge_dismissed,
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

    lines.append("## Quarantined (unreviewed)")
    quarantined = findings.get("quarantined_pages") or {"count": 0, "pages": []}
    lines.append(f"- {quarantined['count']} page(s)")
    lines.extend(f"  - {p}" for p in quarantined.get("pages", []))

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

    return "\n".join(lines) + "\n"


def release_page(page: str, session: str) -> tuple:
    """Release `page` from quarantine — the ONLY product exit from the
    banner state, and it exists precisely because release is a HUMAN act:
    the live session calls this only after the friend explicitly says the
    page is fine (see SKILL.md; never auto-release from a sweep).

    Routes through the normal write substrate (`propose_and_apply`,
    writer="human", producer="retrospective" — this module isn't its own
    producer class, see SKILL.md "What this skill does NOT do") so the
    release is journaled, snapshotted, and revertible like every other
    write. Returns `(QueueEntry, Provenance | None)` — `Provenance` is None
    only if the proposal was held (e.g. a contradiction conflict), in which
    case the session resolves it like any other hold.

    Raises `FileNotFoundError` if the page doesn't exist, `ValueError` if it
    isn't quarantined."""
    from lib.memory.queue import Proposal, propose_and_apply

    path = ren_paths.safe_join(ren_paths.wiki_root(), page)
    if not path.is_file():
        raise FileNotFoundError(f"no such wiki page: {page!r}")
    text = path.read_text(encoding="utf-8")
    if not quarantine.is_quarantined(text):
        raise ValueError(f"{page!r} is not quarantined — nothing to release")

    return propose_and_apply(
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


__all__ = ["sweep", "render_report", "release_page"]
