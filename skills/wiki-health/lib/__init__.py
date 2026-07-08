"""
skills.wiki-health library — the minimal coherence sweep (Task 9, RenOS 0.3
"the ungated brain"). With per-write human approval removed (v2.2's two-plane
pivot: the data plane auto-applies), this is the autonomous auditor that
replaces it — a periodic read-only sweep the live session runs, then fixes
what it can (through the existing write-safety substrate: `propose_and_apply`
/ `resolve_and_apply`) and interviews the friend only on genuine ambiguity.
See `SKILL.md` for the full behavior contract; this module is the sweep
mechanics only — it never writes anything itself.

`sweep()` returns four findings + a timestamp:
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

from lib import ren_paths
from lib.memory import journal, quarantine, semantics
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
    section, skipping the `.ren/` metrics tree."""
    pages: list[tuple[str, str, str | None]] = []
    for md_path in sorted(wiki_root.rglob("*.md")):
        rel_path = md_path.relative_to(wiki_root)
        if ".ren" in rel_path.parts:
            continue
        text = md_path.read_text(encoding="utf-8", errors="replace")
        if "## Knowledge" not in text:
            continue
        pages.append((str(rel_path), text, _frontmatter_type(text)))
    return pages


def _contradiction_pairs(wiki_root: Path) -> tuple[list[dict], dict | None]:
    """Wiki-wide all-pairs contradiction scan across every "## Knowledge"
    page (see module docstring — NOT limited to `detect`'s sibling-directory
    candidate set). Returns `(pairs, cap_note)`; `cap_note` is `None` unless
    the page count exceeded `_CONTRADICTION_PAGE_CAP`, in which case pairs
    were narrowed to same-`type`-or-same-directory and the note records how
    many pairs that skipped."""
    pages = _knowledge_pages(wiki_root)
    n = len(pages)
    capped = n > _CONTRADICTION_PAGE_CAP

    pairs: list[dict] = []
    seen: set[frozenset] = set()
    pairs_checked = 0
    pairs_skipped = 0

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
            if evidence is None:
                continue
            key = frozenset((rel_a, rel_b))
            if key in seen:
                continue
            seen.add(key)
            pairs.append({"page": rel_a, "with": rel_b, "evidence": evidence})

    cap_note = None
    if capped:
        cap_note = {
            "page_count": n,
            "cap": _CONTRADICTION_PAGE_CAP,
            "pairs_checked": pairs_checked,
            "pairs_skipped": pairs_skipped,
            "reason": (
                f"{n} '## Knowledge' pages exceeds the {_CONTRADICTION_PAGE_CAP}-page "
                "all-pairs cap — scan narrowed to pairs sharing a frontmatter type "
                "or a directory; other pairs were not compared."
            ),
        }
    return pairs, cap_note


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
        if quarantine.is_quarantined(md_path.read_text(encoding="utf-8", errors="replace"))
    ]
    return {"count": len(pages), "pages": pages}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sweep(wiki_root: Path | None = None) -> dict:
    """Run the full read-only coherence sweep. Never writes anything —
    fixing findings is the live session's job (see SKILL.md).

    Returns the 5 documented keys (`dangling_pointers`, `contradiction_pairs`,
    `mass_deletions`, `quarantined_pages`, `generated_at`) plus
    `contradiction_scan_note` — `None` unless the wiki-wide contradiction
    scan was capped (see `_contradiction_pairs`), in which case it's a dict
    naming what was skipped and why."""
    wiki_root = wiki_root or ren_paths.wiki_root()
    if not wiki_root.is_dir():
        return {
            "dangling_pointers": [],
            "contradiction_pairs": [],
            "contradiction_scan_note": None,
            "mass_deletions": _mass_deletions(),
            "quarantined_pages": {"count": 0, "pages": []},
            "generated_at": _now_iso(),
        }
    contradiction_pairs, contradiction_scan_note = _contradiction_pairs(wiki_root)
    return {
        "dangling_pointers": _dangling_pointers(wiki_root),
        "contradiction_pairs": contradiction_pairs,
        "contradiction_scan_note": contradiction_scan_note,
        "mass_deletions": _mass_deletions(),
        "quarantined_pages": _quarantined_pages(wiki_root),
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

    return "\n".join(lines) + "\n"


__all__ = ["sweep", "render_report"]
