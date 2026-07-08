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
  - `contradiction_pairs` — cheap reuse of `lib.memory.semantics.detect`:
    for every wiki page whose body has a "## Knowledge" section, run
    `detect(op="UPDATE", page=<page>, content=<its own text>, wiki_root=...)`
    and keep the `"contradicts"` hits against OTHER pages. Symmetric pairs
    (A-contradicts-B is found scanning both A and B) are deduped.
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
            target_path = ren_paths.safe_join(wiki_root, target) if not target.startswith("/") else None
            if target_path is None or not target_path.is_file():
                dangling.append({"page": str(md_path.relative_to(wiki_root)), "target": target})
    return dangling


def _contradiction_pairs(wiki_root: Path) -> list[dict]:
    """For each page with a "## Knowledge" section, run `semantics.detect`
    against its own content and keep `"contradicts"` hits against other
    pages. Deduped so an A<->B contradiction surfaces once, not twice."""
    pairs: list[dict] = []
    seen: set[frozenset] = set()
    for md_path in sorted(wiki_root.rglob("*.md")):
        text = md_path.read_text(encoding="utf-8", errors="replace")
        if "## Knowledge" not in text:
            continue
        rel = str(md_path.relative_to(wiki_root))
        conflicts = semantics.detect(op="UPDATE", page=rel, content=text, wiki_root=wiki_root)
        for c in conflicts:
            if c.kind != "contradicts" or c.page == rel:
                continue
            key = frozenset((rel, c.page))
            if key in seen:
                continue
            seen.add(key)
            pairs.append({"page": rel, "with": c.page, "evidence": c.evidence})
    return pairs


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
    fixing findings is the live session's job (see SKILL.md)."""
    wiki_root = wiki_root or ren_paths.wiki_root()
    if not wiki_root.is_dir():
        return {
            "dangling_pointers": [],
            "contradiction_pairs": [],
            "mass_deletions": _mass_deletions(),
            "quarantined_pages": {"count": 0, "pages": []},
            "generated_at": _now_iso(),
        }
    return {
        "dangling_pointers": _dangling_pointers(wiki_root),
        "contradiction_pairs": _contradiction_pairs(wiki_root),
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
