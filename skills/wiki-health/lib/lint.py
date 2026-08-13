"""
skills.wiki-health.lib.lint — the incremental wiki lint (Task 3, RenOS 0.6.5
"shipped agents").

Where `sweep()` is a read-only wiki-WIDE audit a human reads, this is the
engine the `ren-wiki-lint` agent drives on every session: it looks only at
what CHANGED since the last pass (Task 2's watermark), and it acts.

Two dispositions, and the split is the whole point:

- **Mechanically safe fixes** — a hub `index.md` missing an entry for a page
  that sits right next to it; a `[[link]]` whose target moved and resolves
  unambiguously by filename; a `[[link]]` to a page the journal says was
  DELETED (commented out, never deleted — the line is evidence). These go
  through `lib.memory.queue.propose_and_apply` like every other data-plane
  write, so they are journaled, snapshotted and one-step revertible. The lint
  NEVER writes a page itself.
- **Judgment-shaped findings** — anything requiring a human's read (a page
  violating the schema, a dangling link with no unambiguous target) becomes a
  pending `lib.suggestions` entry. Suggestions are durable and never re-nag.

Nothing ever falls between the two: a fix class is reported only when the
page text actually changed, and anything intended-but-not-applied (aliased
form untouched, queue held it, page not writable) falls through to a
judgment.

Hard exclusions from the FIX path (a finding on such a page is still
reported, but as a suggestion — it is never written):
  - `projects/<slug>/raw/` — write-once source material, not claims;
  - `.ren/` — framework state, including the journal itself;
  - `log.md` — the chronology's settled days are frozen by doctrine;
  - the instruction plane (`global/`, `decisions/`, `patterns/`, `research/`)
    — promotion through a human is the only door from remembered to obeyed;
  - `_`-prefixed pseudo-pages (e.g. `_wrap-session`) — not wiki pages at all.

`run_incremental_lint` always stamps the watermark forward at the end, with
`clean=False` while ANY lint finding is still pending a human — so Task 5's
wake-up nudge can tell "nothing to look at" from "you have lint findings
waiting".
"""

from __future__ import annotations

import re
from pathlib import Path

from lib import ren_paths
from lib.governance.tiers import is_instruction_plane_page
from lib.memory import journal, quarantine
from lib.memory.queue import Proposal, propose_and_apply
from lib.suggestions import SuggestionSpec, pending_suggestions, record

from . import watermark

#: Queue producer for lint fixes. The brief sketched `producer="wiki-lint"`,
#: but `lib.memory.queue._PRODUCERS` is a closed enum (`wrap|pin|retrospective|
#: routine|promotion|ingest`) and a lint fix is an automated routine write, so
#: it reuses the existing `routine` class rather than widening the enum — the
#: `wiki-lint safe fix: <class>` reason string carries the finer identity.
PRODUCER = "routine"

_WIKILINK_RE = re.compile(r"\[\[([^\]\|\n]+?)(?:\|[^\]\n]*)?\]\]")
_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
_FM_TYPE_RE = re.compile(r"^type:\s*(.+)$", re.MULTILINE)
_FENCE_RE = re.compile(r"^\s*```", re.MULTILINE)

_HUB_SECTION = "## Pages"
_LINT_FINGERPRINT_PREFIX = "wiki-lint:"


# ------------------------------------------------------------------- walking


def walk_wiki_pages(wiki_root: Path, skip_raw: bool = False) -> list[str]:
    """Every markdown page under `wiki_root` as a sorted wiki-relative posix
    path, always skipping the `.ren/` framework tree and optionally
    `projects/<slug>/raw/`. THE page walker for this skill — `sweep`'s
    `_knowledge_pages` and the lint both use it so the two can't drift."""
    pages: list[str] = []
    for md_path in sorted(wiki_root.rglob("*.md")):
        parts = md_path.relative_to(wiki_root).parts
        if ".ren" in parts:
            continue
        if skip_raw and ren_paths.in_project_raw(parts):
            continue
        pages.append(md_path.relative_to(wiki_root).as_posix())
    return pages


def _is_pseudo(page: str) -> bool:
    return any(part.startswith("_") for part in Path(page).parts)


def is_fixable_page(page: str) -> bool:
    """True iff the lint may WRITE to `page` (see the module docstring's hard
    exclusions). A finding on a non-fixable page still surfaces — as a
    suggestion, never as a write."""
    parts = Path(page).parts
    if not parts or _is_pseudo(page):
        return False
    if ".ren" in parts:
        return False
    if ren_paths.in_project_raw(parts):
        return False
    if is_instruction_plane_page(page):
        return False
    if parts[-1] == "log.md":
        return False
    return True


# -------------------------------------------------------------------- rules


def _frontmatter_type(text: str) -> str | None:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    tm = _FM_TYPE_RE.search(m.group(1))
    return tm.group(1).strip().strip('"').strip("'") if tm else None


def _rejoin(lines: list[str], original: str) -> str:
    """Re-join split lines, preserving whether the original ended in a newline
    — a lint fix must never silently add or drop a trailing newline."""
    return "\n".join(lines) + ("\n" if original.endswith("\n") else "")


def _is_quarantined(path: Path) -> bool:
    try:
        return quarantine.is_quarantined(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:  # pragma: no cover - unreadable sibling isn't quarantined
        return False


def _name_mentioned(name: str, text: str) -> bool:
    """Word-bounded filename match — the same forgiving check
    `_knowledge_tree_findings` uses, so `a.md` isn't "linked" by `schema.md`."""
    return re.search(rf"(?<![A-Za-z0-9._-]){re.escape(name)}(?![A-Za-z0-9_])", text) is not None


def _title_of(path: Path) -> str:
    try:
        m = _H1_RE.search(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:  # pragma: no cover - unreadable sibling degrades to its stem
        m = None
    return m.group(1).strip() if m else path.stem


def _hub_candidates(directory: Path) -> tuple[Path, Path]:
    """The two paths that could be `directory`'s hub page: the folder-note
    convention (`<dir-name>.md`) first, the legacy `index.md` convention
    second. A directory's hub is the first of these that exists — dual-accept
    is deliberate; doctor's `check_hub_convention` is the single voice for
    "you haven't migrated", not this lint."""
    return (directory / f"{directory.name}.md", directory / "index.md")


def _is_hub_page(page: str) -> bool:
    p = Path(page)
    if p.name == "index.md":  # root index + legacy hubs
        return True
    return p.name == f"{p.parent.name}.md" and "knowledge" in p.parts


def _hub_missing_entries(wiki_root: Path, page: str, text: str) -> tuple[str, list[str]]:
    """For a hub page (folder-note or legacy `index.md`): append a bullet for
    every sibling page it doesn't already mention. Returns
    `(new_text, added_names)`."""
    directory = (wiki_root / page).parent
    hub_name = Path(page).name
    missing = [
        sib
        for sib in sorted(directory.glob("*.md"))
        if sib.name != hub_name
        and sib.name != "index.md"
        and sib.name != "log.md"  # the chronology is not a hub entry
        and not _is_pseudo(sib.name)
        and not _is_quarantined(sib)  # unreviewed content isn't advertised by a hub
        and not _name_mentioned(sib.name, text)
    ]
    if not missing:
        return text, []

    bullets = [f"- [{_title_of(sib)}]({sib.name})" for sib in missing]
    lines = text.splitlines()
    # EXACT heading line, not a substring: `## Pages (draft)`, a mention in
    # prose, or a line inside a fence must not be mistaken for the section
    # (and must never raise) — no match simply falls through to the append
    # branch below.
    start = next((i for i, line in enumerate(lines) if line.strip() == _HUB_SECTION), None)
    if start is not None:
        end = start + 1
        while end < len(lines) and not lines[end].startswith("## "):
            end += 1
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        new_text = _rejoin(lines[:end] + bullets + lines[end:], text)
    else:
        new_text = text.rstrip("\n") + "\n\n" + _HUB_SECTION + "\n" + "\n".join(bullets) + "\n"
    return new_text, [sib.name for sib in missing]


def _resolves(wiki_root: Path, page: str, target: str) -> bool:
    candidates = [target, target if target.endswith(".md") else target + ".md"]
    for cand in candidates:
        for base in (wiki_root, (wiki_root / page).parent):
            try:
                if ren_paths.safe_join(base, cand).is_file():
                    return True
            except ren_paths.PathTraversalError:
                continue
    return False


def _deleted_basenames() -> set[str]:
    """Filenames the journal says were DELETEd.

    Deliberately BASENAME-only, so a `[[gone.md]]` written without its full
    path still matches. The cost: a `notes.md` deleted under project A marks a
    dangling `[[notes.md]]` under project B as "deleted" too. Both dispositions
    are conservative (comment out, never delete), so the worst case is a
    commented line a human un-comments — but tighten this to full-path
    matching if a wiki ever grows many same-named pages."""
    return {
        Path(e["page"]).name
        for e in journal.entries()
        if e.get("op") == "DELETE" and e.get("page")
    }


def _link_re(target: str) -> re.Pattern:
    """Match `[[target]]` AND its aliased form `[[target|alias]]` — group(1)
    is the alias suffix (possibly empty), preserved by every rewrite."""
    return re.compile(rf"\[\[\s*{re.escape(target)}\s*(\|[^\]\n]*)?\]\]")


def _link_findings(
    wiki_root: Path,
    page: str,
    text: str,
    all_pages: list[str],
    deleted: set[str],
) -> tuple[str, list[str], list[tuple[str, str]]]:
    """Repoint / comment-out / report every unresolvable `[[link]]` in `text`.

    Returns `(new_text, applied_fix_classes, judgments)` where `judgments` is
    a list of `(rule, detail)` pairs for links this cannot safely act on.

    A fix class is reported ONLY when the text actually changed; anything this
    intended to fix but did not falls through to `judgments`, so a broken link
    can never vanish from both dispositions.

    A page containing a fenced code block is never link-REWRITTEN at all: the
    rewrite is a whole-page replace, and a `[[…]]` inside a fence is sample
    text, not a link. Such pages' dangling links become judgments instead —
    the finding still surfaces, it just isn't automated on."""
    fixes: list[str] = []
    judgments: list[tuple[str, str]] = []
    fenced = _FENCE_RE.search(text) is not None

    # Links on an already-commented-out line are settled business, not open
    # findings — re-flagging them would make every later run non-clean.
    targets = [
        m.group(1).strip()
        for line in text.splitlines()
        if not line.lstrip().startswith("<!--")
        for m in _WIKILINK_RE.finditer(line)
    ]
    for target in dict.fromkeys(targets):
        if not target or _resolves(wiki_root, page, target):
            continue
        pattern = _link_re(target)
        basename = Path(target).name
        if not basename.endswith(".md"):
            basename += ".md"
        matches = [p for p in all_pages if Path(p).name == basename and p != page]

        if fenced:
            judgments.append((
                "dangling-link",
                f"[[{target}]] does not resolve; page contains a code fence, "
                "so the lint will not rewrite it automatically",
            ))
            continue

        if len(matches) == 1:
            new_text = pattern.sub(lambda m: f"[[{matches[0]}{m.group(1) or ''}]]", text)
            if new_text != text:
                text = new_text
                fixes.append("dangling-link-repointed")
                continue
        elif basename in deleted:
            # Comment out, never delete: the line is the evidence that
            # something used to be there.
            lines = text.splitlines()
            new_lines = [
                (
                    f"<!-- stale link (target deleted): {line} -->"
                    if pattern.search(line) and not line.lstrip().startswith("<!--")
                    else line
                )
                for line in lines
            ]
            if new_lines != lines:
                text = _rejoin(new_lines, text)
                fixes.append("stale-link-commented")
                continue

        judgments.append((
            "dangling-link",
            f"[[{target}]] does not resolve and has no unambiguous replacement",
        ))
    return text, fixes, judgments


def _lint_page(
    wiki_root: Path,
    page: str,
    text: str,
    all_pages: list[str],
    deleted: set[str],
) -> tuple[str, list[str], list[tuple[str, str]]]:
    """All rules for one page. Returns `(new_text, fix_classes, judgments)`."""
    fixes: list[str] = []
    judgments: list[tuple[str, str]] = []

    if _frontmatter_type(text) is None:
        judgments.append((
            "missing-frontmatter-type",
            "page has no frontmatter `type:` — schema violation, needs a human's read",
        ))

    if _is_hub_page(page):
        text, added = _hub_missing_entries(wiki_root, page, text)
        if added:
            fixes.append("hub-missing-entry")

    text, link_fixes, link_judgments = _link_findings(wiki_root, page, text, all_pages, deleted)
    fixes.extend(link_fixes)
    judgments.extend(link_judgments)

    return text, fixes, judgments


# ---------------------------------------------------------------- the driver


def _suggest(page: str, rule: str, detail: str) -> bool:
    """Record one judgment finding. Returns True iff it was newly stored (a
    fingerprint already pending or decided is never re-nagged)."""
    spec = SuggestionSpec(
        producer="wiki-health",
        title=f"Wiki lint: {rule} in {page}",
        rationale=detail,
        evidence={"page": page, "rule": rule, "detail": detail},
        kind="structured_action",
        payload={"action": "review_lint_finding", "page": page, "rule": rule, "detail": detail},
        fingerprint=f"{_LINT_FINGERPRINT_PREFIX}{page}:{rule}",
    )
    return record(spec) is not None


def _pending_lint_findings() -> bool:
    """True iff ANY lint finding is still pending a human — the state
    `watermark(clean=...)` must reflect."""
    return any(
        str(s.get("fingerprint", "")).startswith(_LINT_FINGERPRINT_PREFIX)
        for s in pending_suggestions()
    )


def _incremental_scope(wiki_root: Path, touched: list[str]) -> list[str]:
    """The pages `unlinted()` named (that still exist), plus the hub page(s)
    of each one's directory — a page landing next to a hub is exactly what
    makes the hub stale. Both the folder-note and legacy `index.md`
    candidates are added if present, so a not-yet-migrated wiki's hub still
    gets re-checked."""
    scope: set[str] = set()
    for page in touched:
        if _is_pseudo(page) or not (wiki_root / page).is_file():
            continue
        scope.add(page)
        for candidate in _hub_candidates((wiki_root / page).parent):
            if candidate.is_file():
                scope.add(candidate.relative_to(wiki_root).as_posix())
    return sorted(scope)


def run_incremental_lint(session: str, full: bool = False) -> dict:
    """Lint what changed (or, with `full=True`, the whole wiki), fixing the
    mechanically safe classes through the write queue and routing judgment
    findings to the suggestion store. Always stamps the watermark forward.

    Returns `{"scope", "pages_checked", "fixed", "held", "queued_suggestions",
    "watermark_advanced"}`. See the module docstring for the disposition split
    and the hard exclusions.

    The watermark is stamped with the ABSOLUTE journal length read BEFORE the
    run — `unlinted()`'s first element is a DELTA ("how many are unlinted"),
    and stamping that as the absolute offset would walk the watermark
    backwards on every pass. Reading the total up front (rather than after)
    means the lint's own fix-writes stay unlinted and get re-checked next
    pass: self-healing, not self-blinding.
    """
    wiki_root = ren_paths.wiki_root()
    total_journal_lines = len(journal.entries())

    if not full and not watermark.watermark_exists():
        # FIRST RUN AFTER UPGRADE. No watermark means "seen 0 lines", which
        # would make this "incremental" pass expand to every page the journal
        # has EVER touched (plus their hubs) and auto-fix all of them — an
        # unattended full-wiki rewrite the friend never asked for, triggered
        # by the wake-up nudge on their first post-upgrade session. Seed the
        # watermark at the current journal length and do nothing else: steady
        # state starts clean from here, and `full=True` remains the deliberate
        # way to lint history. A CORRUPT-but-present watermark does NOT take
        # this path — that degrades to "lint everything" by design.
        watermark.advance_watermark(total_journal_lines, clean=not _pending_lint_findings())
        return {
            "scope": "seeded",
            "watermark_seeded": True,
            "pages_checked": [],
            "fixed": [],
            "held": [],
            "queued_suggestions": 0,
            "watermark_advanced": True,
        }

    _, touched = watermark.unlinted()

    if not wiki_root.is_dir():
        watermark.advance_watermark(total_journal_lines, clean=not _pending_lint_findings())
        return {
            "scope": "full" if full else "incremental",
            "watermark_seeded": False,
            "pages_checked": [],
            "fixed": [],
            "held": [],
            "queued_suggestions": 0,
            "watermark_advanced": True,
        }

    all_pages = walk_wiki_pages(wiki_root)
    pages = (
        [p for p in all_pages if not _is_pseudo(p)]
        if full
        else _incremental_scope(wiki_root, touched)
    )
    deleted = _deleted_basenames()

    fixed: list[dict] = []
    held: list[dict] = []
    queued = 0
    for page in pages:
        path = wiki_root / page
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover - vanished mid-run is not a finding
            continue

        new_text, fix_classes, judgments = _lint_page(wiki_root, page, text, all_pages, deleted)

        if fix_classes and not is_fixable_page(page):
            # Excluded page: the finding is real, but the lint may not write
            # it — surface it for a human instead of silently dropping it.
            judgments.extend(
                (f"blocked:{cls}", f"{cls} finding on a page the lint may not write")
                for cls in dict.fromkeys(fix_classes)
            )
            fix_classes = []

        if fix_classes and new_text != text:
            classes = list(dict.fromkeys(fix_classes))
            entry, prov = propose_and_apply(
                Proposal(
                    op="UPDATE",
                    page=page,
                    content=new_text,
                    reason=f"wiki-lint safe fix: {', '.join(classes)}",
                    producer=PRODUCER,
                    writer="routine",
                    session=session,
                )
            )
            if prov is None and getattr(entry, "status", None) == "noop-duplicate":
                # NOT a hold: `queue.propose` returns a SYNTHETIC, never-persisted
                # entry with this status when the rewrite normalizes equal to what
                # is already on the page (the `_rejoin` trailing-newline path is
                # the obvious way in). The page is already correct, so there is
                # nothing to fix and nothing to hold. Reporting it as a hold cited
                # a qid absent from `state_dir()/queue/` — telling the friend to
                # inspect something un-inspectable — and left a durable suggestion
                # that could never resolve, which also pinned `clean=False` and
                # the wake-up nudge on forever.
                pass
            elif prov is None:
                # The queue HELD it (instruction-plane target, or a
                # `contradicts` conflict the session must reason about). The
                # write did NOT land — never claim it did; surface it instead.
                qid = getattr(entry, "qid", None)
                held.extend({"page": page, "fix": cls, "qid": qid} for cls in classes)
                judgments.extend(
                    (f"held:{cls}", f"{cls} fix for {page} was held by the write queue (qid {qid})")
                    for cls in classes
                )
            else:
                fixed.extend({"page": page, "fix": cls} for cls in classes)

        for rule, detail in judgments:
            if _suggest(page, rule, detail):
                queued += 1

    # `clean` reflects OUTSTANDING findings, not just this run's new ones:
    # `record()` dedups an already-pending fingerprint, so counting only new
    # suggestions would let a later run over untouched pages declare the wiki
    # clean while a real finding still sits unread — and Task 5's wake-up
    # nudge, whose whole input is this flag, would go dark.
    watermark.advance_watermark(total_journal_lines, clean=not _pending_lint_findings())
    return {
        "scope": "full" if full else "incremental",
        "watermark_seeded": False,
        "pages_checked": pages,
        "fixed": fixed,
        "held": held,
        "queued_suggestions": queued,
        "watermark_advanced": True,
    }


__all__ = ["run_incremental_lint", "walk_wiki_pages", "is_fixable_page", "PRODUCER"]
