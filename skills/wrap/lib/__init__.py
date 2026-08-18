"""
skills.wrap library — internal implementation for /ren:wrap (Task 4.1, RenOS
0.2 Phase 4).

Public entry: `wrap_session(narrative_md, durable_items, session, llm_call=None,
project=None, cwd=None) -> dict`.

Per spec §3.1 producer 1 (L1 session continuity) + §3.8 (unified wrap
surface) + §3.10 (quarantine): the live Claude session (SKILL.md) writes the
narrative and proposes candidate durable items; this module is the part that
actually touches the single write-queue (Task 2.1) and the classifier gate
(`.classifier.gate`).

Per the v2.2 two-plane governance pivot (data plane auto-applies), both the
L1 narrative and gated-durable items go through the single data-plane door,
`lib.memory.queue.propose_and_apply`, tagged `writer="llm-auto"`, which the
queue's auto-quarantine wiring quarantines on write — it is data, not
instruction, until a human reviews it. One-step revert is what makes
"auto-apply" safe here. `propose_and_apply` itself holds an entry pending
(rather than applying) when the target is instruction-plane (`global/`) or a
`contradicts` conflict was detected — those cases surface in this module's
`held` list for a human to reason about; items gated out as non-durable, or
refused for a planted secret, never reach the queue at all.

Donor `skills/wrap/lib/{classifier.py,types.py,diff_plan.py}` is NOT ported
wholesale — its CONTEXT.md-rewrite / diff_plan machinery assumed direct wiki
writes, which 0.2's single write-queue makes obsolete (every write, including
L1, goes through `lib.memory.queue` now). Only the classifier's prompt/parse
DISCIPLINE was adapted (see `.classifier`), reshaped for the different
question this module asks per item ("is this durable?") rather than donor's
whole-session multi-label classification.
"""

from __future__ import annotations

import re
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path, PurePosixPath
from typing import Callable

import yaml

from lib import ren_paths
from lib.adapter.worker import parse_worker_json
from lib.instrument import calibration, collect
from lib.memory import journal, queue
from lib.memory import quarantine
from lib.memory.judge import JUDGE_MIN_CONFIDENCE, JUDGE_PAIR_CAP, judge_pairs
from lib.memory.lifecycle import consolidate_duplicates, run_decay
from lib.memory.provenance import new_provenance, read_frontmatter_provenance
from lib.memory.queue import Proposal, propose_and_apply
from lib.memory.scrub import SecretsFound
from lib.memory.semantics import shortlist_pairs
from lib.suggestions import expire_stale_pending, prune_decided
from lib.suggestions import record as record_suggestion
from lib.suggestions import SuggestionSpec
from lib.suggestions.producers import (
    doctrine_shaping,
    promotion_candidates,
    wiki_health_critical,
)

from .classifier import gate
from .merge import merge_update, MergeError

_SLUG_WORD_RE = re.compile(r"[a-z0-9]+")
_PREVIEW_MAX_CHARS = 100
_PREVIEW_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n?", re.DOTALL)

_L1_TYPE_RE = re.compile(r"^type:\s*\S", re.MULTILINE)


def _ensure_l1_type(narrative_md: str) -> str:
    """#43: wiki-lint requires a frontmatter `type:`; the live session authors
    the narrative and reliably forgets it. Normalize at the write door."""
    if not narrative_md.startswith("---\n"):
        return f"---\ntype: l1\n---\n\n{narrative_md}"
    end = narrative_md.find("\n---", 3)
    if end == -1:
        return narrative_md  # malformed frontmatter — leave for lint to flag
    fm = narrative_md[4:end]
    if _L1_TYPE_RE.search(fm):
        return narrative_md
    return f"---\ntype: l1\n{fm}\n---{narrative_md[end + 4:]}"


def _content_preview(content: str | None) -> str:
    """First meaningful body line of a proposal's content — what the friend
    is actually saying yes/no to. Skips frontmatter and the quarantine
    banner; truncates to keep the wrap screen one legible screen."""
    if not content:
        return ""
    body = _PREVIEW_FRONTMATTER_RE.sub("", content, count=1)
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("> [!ren-quarantine]"):
            continue
        if len(line) > _PREVIEW_MAX_CHARS:
            return line[:_PREVIEW_MAX_CHARS] + "…"
        return line
    return ""


def _slugify(text: str, *, max_words: int = 8) -> str:
    """Kebab-case slug derived from `text`'s first few significant words.
    Falls back to "item" if nothing alphanumeric is found (e.g. all-emoji or
    all-punctuation input) so a durable item never fails to queue purely
    because it produced an empty page name."""
    words = _SLUG_WORD_RE.findall(text.lower())
    return "-".join(words[:max_words]) or "item"


def _judge_semantic_findings(
    focus_pages: list[str], llm_call: Callable[[str], str] | None
) -> list[dict]:
    """Judge (Task 4) the shortlist (Task 11) restricted to `focus_pages` —
    this session's applied writes — and return informational findings for
    the wrap screen only (0.5.3's consolidation is the future apply
    consumer; nothing here writes anything).

    Fail-closed like every other wrap sub-step: `focus_pages` empty means
    nothing was written this session, so there's nothing to compare and
    `llm_call` is never invoked; any exception anywhere in this path
    (shortlist scan, page read, judging) degrades to `[]` rather than
    raising — `judge_pairs` itself is already fail-closed per pair, but the
    shortlist scan and page reads are plain filesystem code with no such
    guarantee, so the whole function is wrapped for the same "wrap must
    never crash" discipline as the rest of this module.
    """
    if not focus_pages:
        return []

    try:
        root = ren_paths.wiki_root()
        pairs = shortlist_pairs(root, focus_pages=focus_pages)
        if not pairs:
            return []

        texts = [
            (
                (root / pair["page"]).read_text(encoding="utf-8", errors="replace"),
                (root / pair["with"]).read_text(encoding="utf-8", errors="replace"),
            )
            for pair in pairs
        ]
        verdicts = judge_pairs(texts, llm_call, cap=JUDGE_PAIR_CAP)

        findings: list[dict] = []
        for pair, verdict in zip(pairs, verdicts):
            if verdict is None or verdict.kind == "unrelated":
                continue
            if verdict.confidence < JUDGE_MIN_CONFIDENCE:
                continue
            findings.append(
                {
                    "page": pair["page"],
                    "with": pair["with"],
                    "verdict": verdict.kind,
                    "confidence": verdict.confidence,
                    "reason": verdict.reason,
                }
            )
        return findings
    except Exception:  # noqa: BLE001 - semantic findings are informational, must never break wrap
        return []


_OVERVIEW_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
_OVERVIEW_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

_OVERVIEW_PROMPT_TEMPLATE: str = """\
You maintain a project's overview page across sessions. Decide whether this
session's narrative represents a MATERIAL change to the project's stage,
direction, or key facts — not routine chatter, not a restatement of what the
overview already says.

Current overview body (may be empty/placeholder if none exists yet):
---
{current_overview}
---

This session's narrative:
---
{narrative}
---

If material_change is true, write a full replacement overview body: what the
project is, its current stage, and 3-5 load-bearing facts. Target <=600
tokens - a thesis, not a novel. If material_change is false, "overview" is
ignored and may be empty.

Output JSON ONLY (no surrounding prose, no code fence). Schema:

{{"material_change": true | false, "overview": "<full replacement body>"}}
"""


def _split_overview_frontmatter(text: str) -> tuple[dict, str]:
    """Return `(frontmatter_dict, body)` for `text`. Any parse failure (bad
    YAML, no frontmatter) degrades to an empty dict rather than raising —
    frontmatter here is only used to carry a few cosmetic fields (title,
    created date) forward across overview UPDATEs, never load-bearing."""
    match = _OVERVIEW_FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        data = None
    return (data if isinstance(data, dict) else {}), text[match.end():]


def _is_skeleton_or_empty_body(body: str) -> bool:
    """True if `body` (frontmatter already stripped) carries no real content
    of its own — i.e. it's the shipped skeleton (a heading plus an HTML
    comment) or genuinely empty/whitespace. Same idea as `read_identity`'s
    skeleton check (Task 1), adapted for overview's comment-only body shape
    rather than a byte-for-byte template match."""
    without_comments = _OVERVIEW_HTML_COMMENT_RE.sub("", body)
    lines = [line.strip() for line in without_comments.splitlines() if line.strip()]
    if not lines:
        return True
    return len(lines) == 1 and lines[0].startswith("#")


def _yaml_double_quoted(value: object) -> str:
    """Escape `value` for embedding in a double-quoted YAML scalar: backslash
    first (so a source backslash isn't double-escaped by the next replace),
    then double-quote. Without this, a hand-edited overview `title` carrying
    a `"` would malform the frontmatter fence it's interpolated into."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _build_overview_content(existing_text: str, overview_body: str) -> str:
    """Build the full page content (frontmatter + body) for an overview
    ADD/UPDATE. Carries `title`/`created`/`framework_version` forward from
    the existing page's frontmatter when present (a fresh CREATE falls back
    to the skeleton template's defaults); `updated` is always today.
    `ren_*` provenance keys are stamped downstream by `write_apply`, not
    here."""
    fm, _ = _split_overview_frontmatter(existing_text)
    today = date.today().isoformat()
    lines = [
        "---",
        f'title: "{_yaml_double_quoted(fm.get("title", "Project Overview"))}"',
        "type: overview",
        "schema_version: 1",
        f'framework_version: "{fm.get("framework_version") or ren_paths.framework_version()}"',
        f"created: {fm.get('created', today)}",
        f"updated: {today}",
        "---",
        "",
    ]
    return "\n".join(lines) + overview_body.strip() + "\n"


# --- open-work ledger (0.6.5 Task 6) ----------------------------------------

OPEN_WORK_LINE_RE = re.compile(
    r"^- \[( |x)\] (?P<desc>.+?) — ptr:(?P<ptr>\S+) "
    r"\(opened (?P<opened>\d{4}-\d{2}-\d{2})(?:, closed (?P<closed>\d{4}-\d{2}-\d{2}))?\)$"
)
OPEN_WORK_ARCHIVE_DAYS = 14
_OPEN_HEADER = "## Open"
_ARCHIVE_HEADER = "## Archive"


def _ptr_parts(ptr: str) -> tuple[str, bool]:
    """`(target, has_fragment)` for a `ptr:` value: the path it points at with
    the scheme prefix and any `#task-N` / `§section` fragment stripped, plus
    whether a fragment was present. `spec:projects/x/map.md§2` →
    `("projects/x/map.md", True)`; `issue:#7` → `("", True)`, because an issue
    pointer is ALL fragment and has no file target at all.

    Both halves are load-bearing (fix round 1). Matching on the target alone
    collapsed `plan:docs/p.md#task-3` and `#task-9` into the same key, and
    made every `issue:#N` line share the empty-string key — so closing one
    item silently closed its siblings. Callers must therefore never match on
    a target that is empty or that came from a fragment-bearing pointer."""
    body = ptr.split(":", 1)[1] if ":" in ptr else ptr
    target = body
    has_fragment = False
    for sep in ("#", "§"):
        if sep in target:
            has_fragment = True
            target = target.split(sep, 1)[0]
    return target.strip(), has_fragment


def _split_ledger_sections(body: str) -> tuple[list[str], list[str], list[str]]:
    """Split a ledger body into `(preamble, open_lines, archive_lines)`.

    EVERY line lands in exactly one bucket — the ledger's core invariant is
    that nothing is ever dropped, including lines this module cannot parse.
    Only the two KNOWN headers (`## Open`, `## Archive`) are consumed here and
    re-emitted by `_render_ledger_body`. Any other header line is not special
    to this parser: it is appended verbatim like any other line, along with
    everything under it, into whichever bucket was current — so a hand-added
    section survives a reconcile heading and all."""
    preamble: list[str] = []
    open_lines: list[str] = []
    archive_lines: list[str] = []
    current = preamble
    for line in body.splitlines():
        stripped = line.strip()
        if stripped == _OPEN_HEADER:
            current = open_lines
            continue
        if stripped == _ARCHIVE_HEADER:
            current = archive_lines
            continue
        current.append(line)
    return preamble, open_lines, archive_lines


def _render_ledger_body(
    project: str, preamble: list[str], open_lines: list[str], archive_lines: list[str]
) -> str:
    """Re-emit the ledger body with both section headers always present."""
    head = "\n".join(preamble).strip()
    if not head:
        head = (
            f"# Open work — {project}\n\n"
            "<!-- One line per item: `- [ ] <desc> — ptr:<target> (opened YYYY-MM-DD)`.\n"
            "     Lines are NEVER deleted; closed lines older than "
            f"{OPEN_WORK_ARCHIVE_DAYS} days move to the archive section below. -->"
        )
    parts = [
        head,
        "",
        _OPEN_HEADER,
        "",
        "\n".join(line for line in open_lines).strip("\n"),
        "",
        _ARCHIVE_HEADER,
        "",
        "\n".join(line for line in archive_lines).strip("\n"),
    ]
    return "\n".join(parts).rstrip() + "\n"


def _build_open_work_content(existing_text: str, project: str, body: str) -> str:
    """Frontmatter + body for an open-work ADD/UPDATE, carrying cosmetic
    fields forward exactly like `_build_overview_content` does."""
    fm, _ = _split_overview_frontmatter(existing_text)
    today = date.today().isoformat()
    lines = [
        "---",
        f'title: "{_yaml_double_quoted(fm.get("title", "Open Work"))}"',
        "type: open-work",
        "schema_version: 1",
        f"project: {project}",
        f'framework_version: "{fm.get("framework_version") or ren_paths.framework_version()}"',
        f"created: {fm.get('created', today)}",
        f"updated: {today}",
        "---",
        "",
    ]
    return "\n".join(lines) + body


#: Wrap's own bookkeeping artifacts. Wrap rewrites these on EVERY session as
#: a side effect of wrapping up — they are never evidence that a human's
#: open-work line about them is done.
_WRAP_INTERNAL_BASENAMES = ("overview.md", "open-work.md")


def _is_session_work_write(proposal: dict) -> bool:
    """True iff this queue entry is genuine SESSION work, i.e. may close a
    fragment-less open-work pointer.

    0.6.5 added two UNCONDITIONAL automated writers to every session — the
    `ren-wiki-lint` pass (`producer="routine"`) and wrap's own
    `maintain_overview` / L1 narrative. Before this guard, either of them
    touching a page ticked its ledger box, so the ledger closed lines while
    nothing about the actual work had changed. The ledger exists to remember
    open threads; an automated writer must never be what closes one.
    """
    if proposal.get("producer") == "routine":
        return False
    page = PurePosixPath(str(proposal.get("page", "")))
    if page.name in _WRAP_INTERNAL_BASENAMES:
        return False
    # `projects/<slug>/l1/session-*.md` (and the project-less `l1/…` form) —
    # wrap writes one every session.
    if "l1" in page.parts and page.name.startswith("session-"):
        return False
    return True


def reconcile_open_work(
    session: str,
    project: str,
    cwd: Path | None = None,
    *,
    open_threads: list | None = None,
    completed_ptrs: list | None = None,
) -> dict:
    """Reconcile `projects/<project>/open-work.md` — the open-thread ledger
    (0.6.5, M3 pointer/cursor shape). Returns
    `{"closed": [ptr, ...], "opened": [ptr, ...], "carried": int}`.

    Deterministic bookkeeping, NOT a judgment call. A line closes when either
    (a) the caller passed its exact `ptr` in `completed_ptrs` — the only
    channel that can close a FRAGMENT-bearing pointer (`issue:#7`,
    `plan:p.md#task-3`) — or (b) the pointer has no fragment and its target
    file is either a bare path in `completed_ptrs` or a page this `session`'s
    GENUINE work wrote (`_is_session_work_write` — the routine lint and wrap's
    own overview/L1/ledger writes are excluded, since they touch pages on
    every session regardless of what the human did). Nothing here asks a model
    anything.

    `carried` counts pre-existing OPEN lines left untouched this run: it
    excludes lines closed on this run, already-closed lines, and lines the
    regex could not parse (those are carried on disk, just not counted).

    THE INVARIANT: no line is ever deleted. Closed lines older than
    `OPEN_WORK_ARCHIVE_DAYS` MOVE to `## Archive` intact; a line the regex
    cannot parse is carried through verbatim in whichever section it was in.
    A ledger the reconciler silently eats is worse than no ledger.

    `cwd` is accepted for signature symmetry with the rest of wrap's write
    path and is unused: the page path is derived from `project` alone.
    """
    del cwd  # unused — see docstring

    page = f"projects/{project}/open-work.md"
    path = ren_paths.safe_join(ren_paths.wiki_root(), page)

    existing_text = ""
    exists = path.is_file()
    if exists:
        try:
            existing_text = path.read_text(encoding="utf-8")
        except OSError:
            existing_text = ""

    _, existing_body = _split_overview_frontmatter(existing_text)
    preamble, open_lines, archive_lines = _split_ledger_sections(existing_body)

    # Closure sets (fix round 1 — the fragment is load-bearing):
    #   * `explicit_full` matches a ledger line's pointer STRING exactly. This
    #     is the only channel that can close a fragment-bearing pointer
    #     (`issue:#7`, `plan:p.md#task-3`), so completing one task can never
    #     close its siblings in the same file.
    #   * `explicit_targets` holds bare targets from FRAGMENT-LESS explicit
    #     pointers only, so a caller may pass a plain path.
    #   * `written_pages` (this session's GENUINE queue writes — see
    #     `_is_session_work_write`; automated writers are filtered out) may
    #     only close a fragment-less pointer: writing a file is not evidence
    #     that a specific task inside it is done.
    # An empty target is never a match key — it is the shape every `issue:#N`
    # pointer degrades to.
    explicit_full = {str(p) for p in (completed_ptrs or [])}
    explicit_targets: set[str] = set()
    for raw in completed_ptrs or []:
        cand_target, cand_fragment = _ptr_parts(str(raw))
        if cand_target and not cand_fragment:
            explicit_targets.add(cand_target)
    try:
        written_pages = {
            e["proposal"]["page"]
            for e in _session_queue_entries(session)
            if _is_session_work_write(e["proposal"])
        }
    except Exception:  # noqa: BLE001 - a broken queue must not break the ledger
        written_pages = set()

    today = date.today().isoformat()
    cutoff = date.today() - timedelta(days=OPEN_WORK_ARCHIVE_DAYS)

    closed: list[str] = []
    carried = 0
    kept_open: list[str] = []
    open_ptrs: set[str] = set()

    for line in open_lines:
        match = OPEN_WORK_LINE_RE.match(line.strip())
        if match is None:
            # Unparseable (or blank, or a human's freeform note) — verbatim.
            kept_open.append(line)
            continue
        ptr = match.group("ptr")
        open_ptrs.add(ptr)
        closed_on = match.group("closed")
        if closed_on is None:
            target, has_fragment = _ptr_parts(ptr)
            fragmentless_hit = bool(target) and not has_fragment and (
                target in explicit_targets or target in written_pages
            )
            if ptr in explicit_full or fragmentless_hit:
                closed.append(ptr)
                kept_open.append(
                    f"- [x] {match.group('desc')} — ptr:{ptr} "
                    f"(opened {match.group('opened')}, closed {today})"
                )
                continue
            carried += 1
            kept_open.append(line)
            continue
        # Already closed: archive it once it ages past the window — MOVED,
        # never dropped.
        try:
            aged_out = date.fromisoformat(closed_on) < cutoff
        except ValueError:  # pragma: no cover - regex already pins the shape
            aged_out = False
        if aged_out:
            archive_lines.append(line)
        else:
            kept_open.append(line)

    opened: list[str] = []
    for thread in open_threads or []:
        if not isinstance(thread, dict):
            continue
        desc = str(thread.get("desc", "")).strip()
        ptr = str(thread.get("ptr", "")).strip()
        if not desc or not ptr or ptr in open_ptrs:
            continue
        open_ptrs.add(ptr)
        opened.append(ptr)
        kept_open.append(f"- [ ] {desc} — ptr:{ptr} (opened {today})")

    content = _build_open_work_content(
        existing_text, project, _render_ledger_body(project, preamble, kept_open, archive_lines)
    )
    propose_and_apply(
        Proposal(
            op="UPDATE" if exists else "ADD",
            page=page,
            content=content,
            reason="open-work reconcile",
            producer="wrap",
            writer="llm-auto",
            session=session,
        )
    )
    return {"closed": closed, "opened": opened, "carried": carried}


def maintain_overview(
    project: str,
    session: str,
    narrative: str,
    llm_call: Callable[[str], str] | None,
) -> dict | None:
    """Maintain `projects/<project>/overview.md`: CREATE it when absent or
    still skeleton-only, UPDATE it when the LLM judges this session's
    narrative a material change to stage/direction/key facts. Never writes
    on a merely-session-only narrative, and never writes at all if the LLM
    call or its output can't be trusted (fail-closed, per anti-Goodhart
    doctrine — an LLM error must never silently produce no write AND no
    signal; a `KIND_OVERVIEW_EVENT` "skipped" event is recorded so
    `wrap_session` can surface it on the wrap report rather than the
    outcome vanishing into an indistinguishable no-op).

    Returns the queue-apply result (`{"qid", "write_id", "page"}`) when a
    write actually landed; `None` when nothing changed (no material change)
    or the LLM path failed. `propose_and_apply` holding the entry pending
    instead of auto-applying (shouldn't happen for a data-plane `projects/`
    target, but treated the same as "not written" if it ever does) also
    returns `None`.
    """
    page = f"projects/{project}/overview.md"
    path = ren_paths.safe_join(ren_paths.wiki_root(), page)

    existing_text = ""
    exists = path.is_file()
    if exists:
        try:
            existing_text = path.read_text(encoding="utf-8")
        except OSError:
            existing_text = ""

    _, existing_body = _split_overview_frontmatter(existing_text)
    # Task 3b (spec §4.5): the current overview may carry a quarantine
    # banner (routine for an llm-auto write, per the wake-up exemption) —
    # strip it before embedding the body in the LLM prompt so the banner
    # text itself never becomes part of what the model reads as "current
    # overview". Pure string strip only; the on-disk page's release is a
    # separate, human-gated act (/ren:wiki-health) and this must never do
    # file I/O to release it.
    existing_body = quarantine.release(existing_body)
    prompt = _OVERVIEW_PROMPT_TEMPLATE.format(
        current_overview=existing_body.strip() if not _is_skeleton_or_empty_body(existing_body) else "(none yet)",
        narrative=narrative,
    )

    if llm_call is None:
        collect.record(
            collect.KIND_OVERVIEW_EVENT,
            {"event": "skipped", "reason": "no llm_call available"},
        )
        return None

    try:
        raw = llm_call(prompt)
        if not isinstance(raw, str):
            raise ValueError(f"llm_call must return str, got {type(raw).__name__}")
        data = parse_worker_json(raw)
        if not isinstance(data, dict):
            raise ValueError(f"overview output must be a JSON object, got {type(data).__name__}")
        material_change = data.get("material_change")
        if not isinstance(material_change, bool):
            raise ValueError(f"'material_change' must be a bool, got {material_change!r}")
        overview_body = data.get("overview")
        if material_change and (not isinstance(overview_body, str) or not overview_body.strip()):
            raise ValueError("'overview' must be a non-empty string when material_change is true")
    except Exception as exc:  # noqa: BLE001 - fail-closed: never write, never stay silent
        collect.record(
            collect.KIND_OVERVIEW_EVENT,
            {"event": "skipped", "reason": str(exc)},
        )
        return None

    if not material_change:
        return None

    content = _build_overview_content(existing_text, overview_body)
    entry, prov = propose_and_apply(
        Proposal(
            op="UPDATE" if exists else "ADD",
            page=page,
            content=content,
            reason="overview maintenance (material change)",
            producer="wrap",
            writer="llm-auto",
            session=session,
        )
    )
    if prov is None:
        return None
    return {"qid": entry.qid, "write_id": prov.write_id, "page": page}


def _target_trust(page: str) -> str | None:
    """`ren_trust` frontmatter of a wiki page, or None (unreadable/unstamped).
    Mirrors skills/wiki-health/lib `_page_trust` — None is deliberately
    treated as NOT user-trust: an unstamped page was never human-released,
    so it takes the auto path."""
    try:
        text = ren_paths.safe_join(ren_paths.wiki_root(), page).read_text(encoding="utf-8")
    except OSError:
        return None
    data = _split_overview_frontmatter(text)[0]  # existing frontmatter parser
    trust = data.get("ren_trust")
    return trust if isinstance(trust, str) else None


def _durable_create_page(item: str, scope: str, project: str | None) -> str:
    """Placement for a durable CREATE (spec §2): project-scoped when the
    classifier said so AND a project is in scope; global lessons/ otherwise."""
    if scope == "project" and project:
        return f"projects/{project}/knowledge/lessons/{_slugify(item)}.md"
    return f"lessons/{_slugify(item)}.md"


_HUB_LINK_RE = re.compile(r"^- \[[^\]]+\]\(([^)]+)\)$", re.MULTILINE)


def _hub_links(text: str) -> list[str]:
    """The link TARGETS of the `- [name](file.md)` lines carried by a hub
    body — what the hub already advertises. Used to decide which entries a
    hub is missing: the write door stamps `ren_*` provenance frontmatter onto
    every applied page, so the on-disk file never byte-equals a freshly
    rendered body; comparing advertised targets is what makes
    `_ensure_lessons_hub` idempotent."""
    return _HUB_LINK_RE.findall(text)


def _ensure_lessons_hub(dir_rel: str, session: str, project: str | None) -> bool:
    """Folder-note hub for a lessons/ directory (spec §2, 0.7.2 hub
    convention: `<dir>/<dirname>.md`, `hub: true`).

    Two distinct paths (fix round 2, #I2 — the old code re-rendered the whole
    body and UPDATEd it, silently deleting any prose a human had written on
    the hub):

      * **Hub absent** — write the full template (frontmatter + heading +
        one link per lesson page, backfilling every pre-existing one).
      * **Hub present** — APPEND ONLY the link lines it is missing to the
        body it already has (same shape as
        `skills/wiki-health/lib/lint.py::_hub_missing_entries`), never a
        re-render. Nothing missing → no write at all (idempotent).

    A hub whose `ren_trust` is `user` is a human-owned page: skipped
    entirely (returns False), same hold rule the durable-update path applies
    to trust-user targets.

    Isolated-duty posture: never raises; returns False on any failure (caller
    appends a warning)."""
    try:
        wiki = ren_paths.wiki_root()
        dirname = PurePosixPath(dir_rel).name
        hub_rel = f"{dir_rel}/{dirname}.md"
        hub_path = ren_paths.safe_join(wiki, hub_rel)
        dir_path = ren_paths.safe_join(wiki, dir_rel)

        entries = sorted(
            p.name for p in dir_path.glob("*.md")
            if p.is_file() and p.name != f"{dirname}.md"
        ) if dir_path.is_dir() else []

        if hub_path.is_file():
            # Human-authored hub: never auto-edited (see docstring).
            if _target_trust(hub_rel) == "user":
                return False
            existing_text = hub_path.read_text(encoding="utf-8")
            advertised = set(_hub_links(existing_text))
            missing = [n for n in entries if n not in advertised]
            if not missing:
                return False
            appended = "\n".join(f"- [{PurePosixPath(n).stem}]({n})" for n in missing)
            content = existing_text.rstrip("\n") + "\n" + appended + "\n"
            op = "UPDATE"
        else:
            links = "\n".join(f"- [{PurePosixPath(n).stem}]({n})" for n in entries)
            if project:
                fm = (f"---\ntype: project-knowledge\nschema_version: 1\n"
                      f"project: {project}\nhub: true\ntitle: \"Lessons Hub\"\n---\n")
            else:
                # #I6: wiki-lint files a `missing-frontmatter-type` judgment
                # on any page without a frontmatter `type:` — wrap's own hub
                # was tripping it. `hub` is the honest minimal stamp: lint
                # accepts ANY non-empty type string, and `hub` is NOT in
                # `skills/wiki-migration/schemas.json`'s `page_types`, so
                # doctor's schema check skips it rather than demanding a
                # schema_version chain that doesn't exist for this shape.
                fm = "---\ntype: hub\nhub: true\ntitle: \"Lessons\"\n---\n"
            content = f"{fm}\n# Lessons\n\nDurable lessons in this folder:\n\n{links}\n"
            op = "ADD"

        _, prov = propose_and_apply(
            Proposal(
                op=op,
                page=hub_rel, content=content,
                reason="lessons folder-note hub (spec 2026-08-14 §2)",
                producer="wrap", writer="routine", session=session,
            )
        )
        return prov is not None
    except Exception:  # noqa: BLE001 - hub upkeep must never fail wrap close-out
        return False


def wrap_session(
    narrative_md: str,
    durable_items: list[str],
    session: str,
    llm_call: Callable[[str], str] | None = None,
    project: str | None = None,
    cwd: Path | None = None,
    *,
    open_threads: list | None = None,
    completed_ptrs: list | None = None,
) -> dict:
    """Run the wrap write path for one session close-out.

    Returns a dict:
      - "l1_qid": qid of the (already applied + quarantined) L1 entry
      - "project": the resolved project slug the L1 was scoped under, or
        `None` for the global fallback (#45) — `render_wrap_screen` shouts
        when this is `None`, since a global misfile from an unrecognized
        `cwd` is silent otherwise.
      - "wrap_cwd": `str(cwd or Path.cwd())` — the cwd project detection
        actually ran from, surfaced so the fallback warning can name it.
      - "applied": [{"qid", "write_id", "page"}] for items gated "durable"
        that auto-applied through the data-plane door
      - "held": [{"qid", "page", "conflicts"}] for items gated "durable" that
        `propose_and_apply` held pending instead of applying (instruction-
        plane target, or a detected `contradicts` conflict — a human/the live
        session needs to reason about these)
      - "gated_out": [{"item", "verdict", "reason"}] for non-durable items
      - "refused": [{"item", "reason"}] for durable items the queue itself
        refused (currently: a planted secret — `SecretsFound` propagates from
        `lib.memory.scrub` via `queue.propose`'s door-side scrub, and is
        caught here so ONE bad item doesn't crash the whole wrap)
      - "fail_closed": True if the classifier gate fell back to the
        deterministic path (due to an LLM error) for at least one durable
        candidate during this call
      - "semantic_findings": [{"page", "with", "verdict", "confidence",
        "reason"}] — LLM-judged (Task 4) verdicts over the shortlist (Task
        11) restricted to this session's applied writes (`applied`'s pages).
        INFORMATIONAL ONLY — rendered on the wrap screen, nothing here
        writes or applies anything; that's 0.5.3's consolidation. `[]` when
        nothing was applied this session, `llm_call` is `None`, or judging
        fails for any reason (fail-closed, never raises)
      - "decayed": [{"archive_page", "add_write_id", "delete_write_id"}] —
        `lib.memory.lifecycle.run_decay`'s moves for this wrap's close-out
        (Task 17): up to `DECAY_MAX_PER_WRAP` stale, unrecalled, non-salient
        data-plane pages archived (never deleted, revertible). Isolated like
        `semantic_findings` — any exception anywhere in the decay path
        degrades to `[]` rather than raising; wrap must never fail to close
        out a session because of a housekeeping sweep.
      - "consolidated": [{"status": "merged", "archived", "archive_page",
        "merged_into", "write_id"} | {"status": "partial", "archived",
        "archive_page", "update_failed", "error"}] —
        `lib.memory.lifecycle.consolidate_duplicates`'s moves for this
        wrap's close-out (Task 18): up to `CONSOLIDATE_MAX_PER_WRAP`
        judge-confirmed (`semantic_findings`, this same call) duplicate
        pairs auto-merged on the data plane — the older page archives, the
        newer carries a `Merged from [[...]]` provenance line. A `"partial"`
        entry means the older page archived but the newer-page UPDATE then
        failed (concurrent write); it is not silently dropped. Isolated
        like `decayed`; degrades to `[]` rather than raising.
      - "overview": one of "created" | "updated" | "unchanged" | "skipped" —
        `maintain_overview`'s (Task 3, 0.5.5) outcome for
        `projects/<project>/overview.md`, called right after the L1 write.
        "created"/"updated" mean a write landed (page was absent/skeleton vs.
        already had real content); "unchanged" means the LLM judged this
        session's narrative not a material change; "skipped" means either no
        `project` is in scope for this wrap, or the LLM call/output failed
        and `maintain_overview` fail-closed (never silent — always one of
        these four values, never omitted).
      - "open_work": `{"closed": [...], "opened": [...], "carried": int}` —
        `reconcile_open_work`'s (0.6.5 Task 6) bookkeeping over
        `projects/<project>/open-work.md`, driven by the keyword-only
        `open_threads` / `completed_ptrs` the live session passes and by this
        session's own queue writes. The zero-value dict when no project is in
        scope or the reconcile failed (isolated like the sweeps above).

    `project` (codex D4): when the wrap is scoped to a project, the L1 page
    is written to `projects/<project>/l1/session-<id>.md`, the EXACT path
    `hooks.wake-up.wakeup.read_l1` reads for that project (`project_dir /
    "l1"`, where `project_dir = wiki_root / "projects" / project`) — mirrors
    that resolution exactly rather than reimplementing it. `None` (the
    default) preserves the original global `l1/session-<id>.md` path.

    `cwd` (codex D4 live wiring): the live `/ren:wrap` invocation has no
    reason to know its own project slug — SKILL.md's instructions call
    `wrap_session(narrative_md, durable_items, session, llm_call=...)` with
    no `project=` kwarg at all, same as every other caller. So when
    `project` is not given explicitly, this derives it from `cwd` (defaults
    to `Path.cwd()`, the real process cwd at wrap time — the live session
    IS running with its cwd inside the project directory, exactly the signal
    `hooks/wake-up/ren-wake-up.py` falls back to via `event.get("cwd") or
    os.getcwd()`) via `lib.ren_paths.detect_project` — the SAME shared
    helper `hooks.wake-up.wakeup.compose_wake_up_context` uses to resolve
    its read-side project. Write and read paths can now never drift onto
    different project slugs for the same cwd. An explicit `project=` kwarg
    (as tests use) still overrides detection entirely.
    """
    if project is None:
        project = ren_paths.detect_project(cwd or Path.cwd(), ren_paths.wiki_root())

    l1_page = (
        f"projects/{project}/l1/session-{session}.md"
        if project
        else f"l1/session-{session}.md"
    )
    l1_path = ren_paths.safe_join(ren_paths.wiki_root(), l1_page)
    l1_entry, _ = propose_and_apply(
        Proposal(
            op="UPDATE" if l1_path.is_file() else "ADD",
            page=l1_page,
            content=_ensure_l1_type(narrative_md),
            reason="end-of-session L1 narrative summary",
            producer="wrap",
            writer="llm-auto",
            session=session,
        )
    )

    overview_status = "skipped"
    if project:
        overview_path = ren_paths.safe_join(
            ren_paths.wiki_root(), f"projects/{project}/overview.md"
        )
        overview_had_real_content = False
        if overview_path.is_file():
            try:
                _, existing_body = _split_overview_frontmatter(
                    overview_path.read_text(encoding="utf-8")
                )
                overview_had_real_content = not _is_skeleton_or_empty_body(existing_body)
            except OSError:
                overview_had_real_content = False

        ov_events_before = collect.read(kind=collect.KIND_OVERVIEW_EVENT)
        overview_result = maintain_overview(project, session, narrative_md, llm_call)
        ov_events_after = collect.read(kind=collect.KIND_OVERVIEW_EVENT)
        new_ov_events = ov_events_after[len(ov_events_before):]
        overview_skipped = any(e.get("event") == "skipped" for e in new_ov_events)

        if overview_result is not None:
            overview_status = "updated" if overview_had_real_content else "created"
        elif overview_skipped:
            overview_status = "skipped"
        else:
            overview_status = "unchanged"

    events_before = collect.read(kind=collect.KIND_CLASSIFIER_EVENT)

    applied: list[dict] = []
    held: list[dict] = []
    gated_out: list[dict] = []
    refused: list[dict] = []
    updated: list[dict] = []
    suggested: list[dict] = []

    eligible = _eligible_update_targets(session)

    for item in durable_items:
        decision = gate(item, llm_call, eligible_targets=eligible, project=project)

        if decision.verdict != "durable":
            gated_out.append(
                {"item": item, "verdict": decision.verdict, "reason": decision.reason}
            )
            continue

        if decision.action == "update":
            target = decision.target_page
            try:
                current = ren_paths.safe_join(
                    ren_paths.wiki_root(), target
                ).read_text(encoding="utf-8")
                merged = merge_update(current, item, llm_call)
            except (OSError, MergeError) as exc:
                gated_out.append(
                    {"item": item, "verdict": "durable",
                     "reason": f"update to {target} gated out (merge): {exc}"}
                )
                continue

            proposal_kwargs = dict(
                op="UPDATE", page=target, content=merged,
                reason=decision.reason, producer="wrap",
                writer="llm-auto", session=session,
            )
            if _target_trust(target) == "user":
                entry = record_suggestion(
                    SuggestionSpec(
                        producer="wrap",
                        title=f"Update human-authored page: {target}",
                        rationale=decision.reason,
                        evidence={"item": item, "session": session, "page": target},
                        kind="page_write",
                        payload=proposal_kwargs,
                        fingerprint=f"wrap-update:{session}:{target}",
                    )
                )
                suggested.append({"page": target, "sid": entry["sid"] if entry else None})
                continue
            try:
                entry, prov = propose_and_apply(Proposal(**proposal_kwargs))
            except SecretsFound as exc:
                refused.append({"item": item, "reason": str(exc)})
                continue
            if prov is not None:
                updated.append({"qid": entry.qid, "write_id": prov.write_id,
                                "page": target, "op": prov.op})
            else:
                held.append({"qid": entry.qid, "page": target,
                             "conflicts": entry.conflicts})
            continue

        page = _durable_create_page(item, decision.scope, project)
        try:
            entry, prov = propose_and_apply(
                Proposal(
                    op="ADD",
                    page=page,
                    content=item,
                    reason=decision.reason,
                    producer="wrap",
                    writer="llm-auto",
                    session=session,
                )
            )
        except SecretsFound as exc:
            refused.append({"item": item, "reason": str(exc)})
            continue

        if prov is not None:
            applied.append(
                {"qid": entry.qid, "write_id": prov.write_id, "page": page, "op": prov.op}
            )
            hub_dir = str(PurePosixPath(page).parent)
            _ensure_lessons_hub(
                hub_dir, session, project if page.startswith("projects/") else None
            )
        else:
            held.append({"qid": entry.qid, "page": page, "conflicts": entry.conflicts})

    events_after = collect.read(kind=collect.KIND_CLASSIFIER_EVENT)
    new_events = events_after[len(events_before):]
    fail_closed = any(e.get("event") == "fail_closed" for e in new_events)

    # Spec §4 — the measurement the #60 distiller decision is made on. `seen`
    # (candidates offered) and the project/global split of creates are what
    # make "creates still starve" distinguishable from "nothing was ever
    # proposed" and from "everything lands globally"; the original four
    # counters could not tell those apart (fix round 2, #I5). Existing keys
    # are unchanged — `created` stays the TOTAL.
    created_project = sum(1 for a in applied if a["page"].startswith("projects/"))
    collect.record(
        collect.KIND_DURABLE_OUTCOME,
        {"session": session, "seen": len(durable_items),
         "created": len(applied),
         "created_project": created_project,
         "created_global": len(applied) - created_project,
         "updated": len(updated),
         "gated_out": len(gated_out), "suggested": len(suggested),
         "held": len(held), "refused": len(refused)},
    )

    semantic_findings = _judge_semantic_findings(
        [a["page"] for a in applied], llm_call
    )

    try:
        decayed = run_decay(session)
    except Exception:  # noqa: BLE001 - a housekeeping sweep must never fail wrap close-out
        decayed = []

    try:
        consolidated = consolidate_duplicates(semantic_findings, session)
    except Exception:  # noqa: BLE001 - a housekeeping sweep must never fail wrap close-out
        consolidated = []

    # 0.6.1 E5a: close the estimator loop. This is also the FIRST production
    # caller of `collect.harvest_session_usage` — it records this session's
    # real token usage and its subagent spawns (the input 0.6.1 E4's routing
    # audit reads), then folds measured (text, tokens) pairs into the stored
    # chars-per-token ratio wake-up's cheap estimator reads back. Isolated
    # like the sweeps above: instrumentation must never fail a close-out.
    #
    # `session` here is a MODEL-supplied label, so it is passed for logging
    # only — the harvest resolves the transcript from the harness `session_id`
    # the wake-up hook stamped into the pairing file. Fix round 1: relying on
    # the label meant the loop never fired in production.
    try:
        calibration.harvest_and_calibrate(session=session, cwd=cwd or Path.cwd())
    except Exception:  # noqa: BLE001 - instrumentation must never fail wrap close-out
        pass

    wrap_cwd = str(cwd or Path.cwd())

    result = {
        "l1_qid": l1_entry.qid,
        "l1_status": l1_entry.status,
        "project": project,
        "wrap_cwd": wrap_cwd,
        "applied": applied,
        "held": held,
        "gated_out": gated_out,
        "refused": refused,
        "updated": updated,
        "suggested": suggested,
        "fail_closed": fail_closed,
        "semantic_findings": semantic_findings,
        "decayed": decayed,
        "consolidated": consolidated,
        "overview": overview_status,
        "open_work": {"closed": [], "opened": [], "carried": 0},
        "links": {
            "l1_touched": 0, "log_entry": False, "sessions_entry": False,
            "auto_pointers": [], "warnings": [],
        },
    }

    try:
        _append_session_summary(session, project, result)
    except Exception:  # noqa: BLE001 - the session journal line must never break wrap close-out
        pass

    # 0.6.5 Task 6: reconcile the project's open-work ledger. Isolated like
    # every other close-out sub-step — a ledger failure must never break
    # wrap; the result stays the zero-value dict above.
    if project:
        try:
            result["open_work"] = reconcile_open_work(
                session,
                project,
                open_threads=open_threads,
                completed_ptrs=completed_ptrs,
            )
        except Exception:  # noqa: BLE001 - the ledger must never break wrap close-out
            pass

    # #54: the link duties (D1-D4) — L1 gains a "## Touched pages" section
    # over this session's OWN queue writes (D1), log.md gets a session entry
    # (D2), the project map's "## Sessions" section gets this session (D3),
    # and every newly-ADDed durable page under this project gets an
    # auto-pointer from the map plus a spine pointer from index.md (D4). Runs
    # LAST (after open-work, so its own writes don't chase their tail) and is
    # isolated exactly like decay/consolidate above — link bookkeeping must
    # never fail a session's close-out. "links" is ALWAYS present on the
    # result (seeded into the dict literal above), so a total failure here
    # still leaves callers a well-shaped, all-zero/warned value.
    try:
        result["links"] = _run_link_duties(
            session=session,
            project=project,
            l1_page=l1_page,
            l1_path=l1_path,
            applied=applied,
            wiki_root=ren_paths.wiki_root(),
        )
    except Exception as exc:  # noqa: BLE001 - link bookkeeping must never break wrap close-out
        result["links"]["warnings"].append(f"link duties failed: {exc}")

    return result


def _run_link_duties(
    *, session: str, project: str | None, l1_page: str, l1_path: Path,
    applied: list[dict], wiki_root: Path,
) -> dict:
    """#54's link duties, run at the very end of `wrap_session`'s close-out —
    the queue plumbing (building/queuing `Proposal`s) lives HERE, keeping
    `skills.wrap.lib.links` a pure text-transform module tests can hammer
    directly. Each duty is isolated in its own try/except so one duty's
    failure never starves the others; the whole call is ALSO wrapped by its
    caller, so a bug in THIS function's own control flow (not just inside a
    duty) still degrades to a warning rather than failing wrap.

    Returns `{"l1_touched": int, "log_entry": bool, "sessions_entry": bool,
    "auto_pointers": list[str], "warnings": list[str]}` — never raises.
    """
    from skills.wrap.lib import links as _links

    out = {
        "l1_touched": 0, "log_entry": False, "sessions_entry": False,
        "auto_pointers": [], "warnings": [],
    }
    today = date.today().isoformat()

    def _queue_update(page: str, content: str, reason: str, *, writer: str = "routine") -> bool:
        """Queue an UPDATE and report whether it actually APPLIED.

        `propose_and_apply` returns `(entry, None)` when it HOLDS instead of
        applying (instruction-plane target, or a detected `contradicts`
        conflict — see its docstring) — same shape `wrap_session`'s own
        `applied`/`held` split already reads (`prov is not None` there means
        applied). Mirrored here so a held link-duty write can never be
        reported as a success.

        `writer="routine"` by default (D2/D3/D4): these are mechanical,
        wrap's-own-bookkeeping edits to pages a human may already own
        (log.md, a project map, index.md) — `writer="llm-auto"` would
        banner-mark the whole page `> [!ren-quarantine]` at the queue door
        (`lib.memory.queue._quarantined_content`), quarantining pages that
        were never LLM-authored data in the first place (and re-quarantining
        a map a human already released). Both tiers resolve to the "auto"
        risk tier on these non-global pages either way
        (`lib.governance.tiers.tier_of`), so switching away from
        `llm-auto` costs nothing on the apply path — same precedent as
        `skills/wiki-health/lib/__init__.py`'s `release_page_auto`. D1 is
        the one call site that passes `writer="llm-auto"` explicitly: it
        edits the L1 page itself, which is quarantined by design."""
        _, prov = propose_and_apply(
            Proposal(
                op="UPDATE", page=page, content=content, reason=reason,
                producer="wrap", writer=writer, session=session,
            )
        )
        return prov is not None

    # D1 — touched pages: every OTHER page this session's own queue writes
    # landed on (excluding the L1 page itself and `_`-prefixed pseudo-pages
    # such as the "_wrap-session" journal marker), appended to the L1 as a
    # "## Touched pages" section. Read via `_session_queue_entries` — by this
    # point in `wrap_session`, `applied`/overview/open-work have ALL already
    # run, so this reflects the full session, not just the durable-items
    # loop. Ordering fix vs. the naive approach: `applied` alone is
    # incomplete (overview/open-work pages wouldn't show), and running this
    # BEFORE the D2-D4 writes below means log.md/the map itself never show up
    # in "pages this session's WORK touched" (they're wrap's own bookkeeping,
    # not narrative content).
    try:
        touched_pages = sorted(
            {
                e["proposal"]["page"]
                for e in _session_queue_entries(session)
                # Only pages this session actually WROTE — a held/pending
                # entry (instruction-plane target, or a detected conflict)
                # never landed, so linking it from the L1 would dangle.
                if e["status"] == "applied"
                and e["proposal"]["page"] != l1_page
                and not e["proposal"]["page"].startswith("_")
            }
        )
        if touched_pages:
            section = _links.touched_section(wiki_root, touched_pages)
            if section and l1_path.is_file():
                current_l1 = l1_path.read_text(encoding="utf-8")
                write_applied = _queue_update(
                    l1_page,
                    current_l1.rstrip("\n") + "\n\n" + section,
                    "touched-pages section (link duty D1)",
                    # L1 pages are quarantined by design (unreviewed narrative
                    # data) — unlike D2/D3/D4's default, this UPDATE keeps
                    # `writer="llm-auto"` so the banner semantics don't change.
                    writer="llm-auto",
                )
                if write_applied:
                    out["l1_touched"] = len(touched_pages)
                else:
                    out["warnings"].append(
                        f"touched-pages section for {l1_page} not applied (held or already current)"
                    )
    except Exception as exc:  # noqa: BLE001
        out["warnings"].append(f"touched-pages section failed: {exc}")

    # D2 — log.md session entry
    try:
        log_path = wiki_root / "log.md"
        if log_path.is_file():
            entry = _links.log_entry_line(today, project, l1_page, session)
            write_applied = _queue_update(
                "log.md",
                _links.append_log_entry(log_path.read_text(encoding="utf-8"), entry),
                "session log entry (link duty D2)",
            )
            if write_applied:
                out["log_entry"] = True
            else:
                out["warnings"].append("log.md entry not applied (held or already current)")
        else:
            out["warnings"].append("log.md missing — session entry skipped")
    except Exception as exc:  # noqa: BLE001
        out["warnings"].append(f"log entry failed: {exc}")

    # D3 — map "## Sessions" + D4 — auto-pointers + spine (project scope only)
    if project:
        map_page = f"projects/{project}/map.md"
        map_path = wiki_root / map_page
        try:
            if map_path.is_file():
                new_text = _links.upsert_sessions_section(
                    map_path.read_text(encoding="utf-8"), l1_page, session
                )
                if new_text is None:
                    out["sessions_entry"] = True  # already recorded — nothing to write
                elif _queue_update(map_page, new_text, "map Sessions entry (link duty D3)"):
                    out["sessions_entry"] = True
                else:
                    out["warnings"].append(
                        f"{map_page} Sessions entry not applied (held or already current)"
                    )
            else:
                out["warnings"].append(f"{map_page} missing — Sessions entry skipped")
        except Exception as exc:  # noqa: BLE001
            out["warnings"].append(f"Sessions entry failed: {exc}")

        _EXCLUDE_NAMES = {"map.md", "overview.md", "open-work.md"}
        _EXCLUDE_PARTS = {"l1", "raw", "archive"}
        for item in applied:
            page = item.get("page", "")
            parts = PurePosixPath(page).parts
            if (
                not page.startswith(f"projects/{project}/")
                or PurePosixPath(page).name in _EXCLUDE_NAMES
                or _EXCLUDE_PARTS & set(parts)
                or item.get("op", "ADD") != "ADD"
            ):
                continue
            try:
                current = (wiki_root / map_page).read_text(encoding="utf-8")
                new_text = _links.add_map_pointer(
                    current, _links.page_title(wiki_root, page), page, item.get("write_id")
                )
                if new_text is not None:
                    if _queue_update(
                        map_page, new_text, "auto-pointer for new durable page (link duty D4)"
                    ):
                        out["auto_pointers"].append(page)
                    else:
                        out["warnings"].append(
                            f"auto-pointer for {page} not applied (held or already current)"
                        )
            except Exception as exc:  # noqa: BLE001
                out["warnings"].append(f"auto-pointer for {page} failed: {exc}")

        # spine: index.md links this project's map. write_id = the map's
        # OWN current `ren_write_id` frontmatter stamp when readable (per
        # spec: "the map's current ren_write_id if readable"), read AFTER
        # the D3/D4 writes above so it reflects the map's latest apply —
        # `render_pointer_line`/`ensure_index_spine` fall back to the
        # "(unstamped)" literal on `None`, e.g. a brand-new/unreadable map.
        try:
            index_path = wiki_root / "index.md"
            if index_path.is_file():
                map_write_id = None
                try:
                    map_prov = read_frontmatter_provenance(
                        (wiki_root / map_page).read_text(encoding="utf-8")
                    )
                    map_write_id = map_prov.get("write_id") if map_prov else None
                except OSError:
                    map_write_id = None
                new_text = _links.ensure_index_spine(
                    index_path.read_text(encoding="utf-8"), project, map_page, map_write_id
                )
                if new_text is not None and not _queue_update(
                    "index.md", new_text, "index spine pointer (link duty D4)"
                ):
                    out["warnings"].append(
                        "index.md spine pointer not applied (held or already current)"
                    )
        except Exception as exc:  # noqa: BLE001
            out["warnings"].append(f"index spine failed: {exc}")
    else:
        out["warnings"].append("no project in scope — map/pointer duties skipped")

    return out


def _run_wiki_health_sweep() -> dict:
    """Run `skills.wiki_health.lib.sweep()` (imported via importlib for the
    hyphen in `skills/wiki-health`, same pattern as
    `hooks/wake-up/wakeup/__init__.py::rank_extras`).

    Wrap's close-out does NOT otherwise run the wiki-health sweep (it's
    normally a live-session-invoked auditor per `skills/wiki-health/SKILL.md`)
    — this is the one place `wiki_health_critical`'s input gets produced at
    wrap time. Left as its own function so `harvest_suggestions` can isolate
    a sweep failure from the three producer calls.

    READ-ONLY on purpose: `apply_corrections` is left at its default False,
    so this unattended, every-session call reports stale facts without
    queuing a single write (fix round 2, #C2). Only `/ren:wiki-health`'s
    explicit apply step — with a human looking at the report — passes True."""
    import importlib

    wiki_health_lib = importlib.import_module("skills.wiki-health.lib")
    return wiki_health_lib.sweep()


def harvest_suggestions(session: str, cwd: str | None = None) -> int:
    """Run the three wrap-time suggestion producers (Task 17's
    `promotion_candidates`, `doctrine_shaping`, `wiki_health_critical`) and
    record each `SuggestionSpec` via `lib.suggestions.record`. The
    retrospective producer runs inside `/ren:retrospective` (Task 16), not
    here.

    Each producer call (and the wiki-health sweep it depends on) is isolated
    in its own try/except — one producer failing must never starve the
    others. Never raises.

    Returns the count of `record()` calls that returned non-None (a spec
    whose fingerprint was already pending/decided returns None and doesn't
    count — see `lib.suggestions.record`'s never-re-nag contract).

    `cwd` is accepted for interface symmetry with other wrap-time hooks but
    unused: none of the three producers are cwd-scoped (wiki state is
    process-global via `lib.ren_paths`, not per-directory).
    """
    del cwd  # unused — see docstring

    try:
        prune_decided()
    except Exception:  # noqa: BLE001 - store maintenance must not starve the producers
        pass

    try:
        expire_stale_pending()
    except Exception:  # noqa: BLE001 - store maintenance must not starve the producers
        pass

    specs: list = []

    try:
        specs.extend(promotion_candidates())
    except Exception:  # noqa: BLE001 - one producer's failure must not starve the others
        pass

    try:
        specs.extend(doctrine_shaping())
    except Exception:  # noqa: BLE001 - one producer's failure must not starve the others
        pass

    try:
        sweep_result = _run_wiki_health_sweep()
    except Exception:  # noqa: BLE001 - sweep failure must not starve the other producers
        sweep_result = None

    if sweep_result is not None:
        try:
            specs.extend(wiki_health_critical(sweep_result))
        except Exception:  # noqa: BLE001 - one producer's failure must not starve the others
            pass

    count = 0
    for spec in specs:
        if record_suggestion(spec) is not None:
            count += 1
    return count


def _append_session_summary(session: str, project: str | None, result: dict) -> None:
    """One append-only journal line summarizing this wrap (0.6.5 session
    journal): a `routine`-writer NOOP entry on the pseudo-page
    `"_wrap-session"`, same page-less-journal-marker pattern as
    `skills.metric-watch.lib`'s `"_metric-watch"` NOOP entries — this is a
    journal notification, never a wiki page. `ren-wiki-lint` (a later
    0.6.5 task) reads these lines to select which pages changed since its
    last incremental run, via `pages_touched`."""
    touched = sorted({e["proposal"]["page"] for e in _session_queue_entries(session)})
    journal.append(
        new_provenance(writer="routine", session=session, op="NOOP", page="_wrap-session"),
        extra={
            "wrap_summary": {
                "session": session,
                "project": project,
                "pages_touched": touched,
                "counts": {
                    "applied": len(result.get("applied", [])),
                    "held": len(result.get("held", [])),
                    "refused": len(result.get("refused", [])),
                },
            }
        },
    )


def _session_id_candidates(session: str) -> set[str]:
    """Every id this wrap's session may be logged under.

    Wrap's `session` argument is a MODEL-supplied label, but the wake-up hook
    logs `KIND_WAKEUP_SURFACE` under the HARNESS `session_id` it was handed
    (`hooks/wake-up/ren-wake-up.py` → `compose_wake_up_context(session=...)`).
    Matching on the label alone therefore found zero wake-up surfaces in
    production, which silently emptied the eligibility set and made the whole
    update path inert (fix round 2, #C1). The harness id is recovered from the
    pairing file the same hook stamps — `calibration.harness_session_id()`,
    the only authority for it; unresolvable (no stamp, degraded wake-up) just
    means the label stands alone, never an error."""
    candidates = {session}
    try:
        harness = calibration.harness_session_id()
    except Exception:  # noqa: BLE001 - a broken stamp must never break wrap
        harness = None
    if harness:
        candidates.add(harness)
    return candidates


def _eligible_update_targets(session: str) -> tuple[str, ...]:
    """The mechanical eligibility set for update-action durable items (spec
    §1): pages THIS session actually surfaced — wake-up injections
    (`KIND_WAKEUP_SURFACE`) plus on-demand recalls (`KIND_L3_FETCH`) — that
    still exist on disk. Assembled from the instrumentation logs, re-checked
    in code after the classifier call; a target outside this set is treated
    as malformed classifier output (fail-closed), never written.

    Entries match on ANY of this session's ids (`_session_id_candidates`):
    the wrap label the model supplied, plus the harness `session_id` the
    wake-up hook logged its surfaces under."""
    sessions = _session_id_candidates(session)
    pages: set[str] = set()
    for entry in collect.read(kind=collect.KIND_WAKEUP_SURFACE):
        if entry.get("session") in sessions:
            pages.update(p for p in entry.get("pages", []) if isinstance(p, str))
    for entry in collect.read(kind=collect.KIND_L3_FETCH):
        if entry.get("session") in sessions and isinstance(entry.get("page"), str):
            pages.add(entry["page"])
    wiki = ren_paths.wiki_root()
    return tuple(sorted(p for p in pages if (wiki / p).is_file()))


def _session_queue_entries(session: str) -> list[dict]:
    """Every queue entry for `session`, regardless of status (the wrap screen
    needs BOTH pending and already-applied entries, incl. auto-tier applies).

    Reads via `queue.all_entries()` (public read API, 0.4.0) instead of
    parsing `state_dir()/queue/*.json` raw, then converts to dict so the
    presentation code below (`e["qid"]`, `e["proposal"]["page"]`, etc.) keeps
    its existing shape. Read-only; never mutates a queue entry."""
    return [
        asdict(entry)
        for entry in sorted(queue.all_entries(), key=lambda e: e.qid)
        if entry.proposal.session == session
    ]


def _conflict_flags(conflicts: list[dict]) -> list[str]:
    flags: list[str] = []
    for conflict in conflicts:
        kind = conflict.get("kind")
        if kind == "supersedes":
            flags.append(f"supersedes {conflict.get('write_id')}")
        elif kind == "contradicts":
            evidence = (conflict.get("evidence") or "")[:60]
            flags.append(f"contradicts: {evidence}")
        elif kind == "duplicate":
            flags.append("duplicate")
    return flags


def live_pin_pages() -> list[dict]:
    """Applied `producer="pin"` queue entries whose page still exists on disk
    and isn't archived — deduped by page (newest entry wins), newest-first
    (issue #25's wrap-side cleanup gate, mechanical half).

    Cross-session by design: stale pins from EARLIER sessions are exactly the
    ones needing cleanup. Purely mechanical detection — judging whether a pin
    looks acted-on is model-work for the live session (see SKILL.md), never a
    heuristic here. UPDATE entries never introduce a listing (issue #62): a
    pin UPDATE is a restoration/correction of an existing page, not a note
    with a keep/expand/delete lifecycle — one may only refresh a page an
    earlier pin ADD already listed. Returns `[{"page": <rel>, "qid": <qid>,
    "preview": <one-line content preview>}]`. Read-only; never raises — any
    queue-read failure degrades to `[]`."""
    from lib.memory import archive

    try:
        entries = queue.all_entries()
    except Exception:  # noqa: BLE001 - a broken queue must not break wrap
        return []

    root = ren_paths.wiki_root()
    by_page: dict[str, dict] = {}
    # qids are ULIDs — lexicographic order IS chronological order, so sorting
    # ascending and overwriting leaves the newest entry per page.
    for entry in sorted(entries, key=lambda e: e.qid):
        if not (entry.status == "applied" and entry.proposal.producer == "pin"):
            continue
        page = entry.proposal.page
        if not page or archive.is_archived(page):
            continue
        # #62: a pin UPDATE is a restoration/correction of an existing page
        # (e.g. the two #58 restoration writes, q-01KZXD2H37WW05W73QZ8RRFSM9
        # → log.md and q-01KZXD2H2VM0KF1218EQ78K4YA → identity.md), not a
        # note with a keep/expand/delete lifecycle — it never introduces a
        # live-pin listing. It may only refresh a page an earlier pin ADD
        # already listed (a re-pin of the same note).
        if entry.proposal.op == "UPDATE" and page not in by_page:
            continue
        try:
            if not ren_paths.safe_join(root, page).is_file():
                continue
        except Exception:  # noqa: BLE001 - a hostile/odd path is simply not live
            continue
        by_page[page] = {
            "page": page,
            "qid": entry.qid,
            "preview": _content_preview(entry.proposal.content),
        }
    return sorted(by_page.values(), key=lambda p: p["qid"], reverse=True)


def render_pending_list() -> str:
    """Every pending queue entry, ALL sessions, oldest first — the
    deterministic backing for wake-up's 'ask me to list them'. Read-only."""
    entries = queue.pending()
    if not entries:
        return "No pending suggestions."
    lines = [f"{len(entries)} pending entr{'y' if len(entries) == 1 else 'ies'} (all sessions, oldest first):"]
    for entry in entries:
        reason = entry.proposal.reason or ""
        lines.append(f"- {entry.qid} → {entry.proposal.page} — {reason}")
        preview = _content_preview(entry.proposal.content)
        if preview:
            lines.append(f"  > {preview}")
    return "\n".join(lines)


def render_wrap_screen(wrap_result: dict, session: str) -> str:
    """Render the unified end-of-wrap screen (spec §3.8 A-10 / G15): one
    legible screen naming what happened this session even though risk tiers
    fragment the underlying writes across auto-applied and pending entries.

    PURE PRESENTATION: reads queue state on disk via `_session_queue_entries`
    and the given `wrap_result` (the return value of `wrap_session`); writes
    NOTHING. Per the v2.2 two-plane pivot's conversational gate (no
    slash-command hints anywhere on this screen):
      - "What I learned" — the L1 entry's qid + one-line status ("unchanged
        (already saved)" when the L1 propose deduped to the never-persisted
        noop-duplicate entry, per #49), plus a loud
        ⚠ line (#45) when `wrap_result["project"]` is `None`: the L1 filed
        under the GLOBAL `l1/` because `cwd` matched no project, and that
        misfile is otherwise silent.
      - "Saved this session (revertible)" — this session's entries with
        `status == "applied"` and `approved_by in ("auto-tier",
        "model-resolved")`, each with its write_id and a spoken revert hint
        ("say ... to revert" — never a slash command).
      - "Held — contradictions to resolve" — still-PENDING entries with a
        detected `contradicts` conflict; the section is OMITTED entirely
        when there are none (nothing to resolve, nothing to show). Each item
        carries a one-line content preview (`  > …`) showing what the friend
        is approving.
      - "Suggestions" — still-PENDING entries targeting an instruction-plane
        `global/` page, plus any other pending residue that isn't a
        contradiction hold; renders "- (none)" when empty. Each item carries
        a one-line content preview (`  > …`) showing what the friend is
        approving. These are resolved by asking the friend in chat (see
        SKILL.md), never by a slash command.
    """
    entries = _session_queue_entries(session)
    by_qid = {e["qid"]: e for e in entries}

    lines: list[str] = ["# Wrap summary", ""]

    # --- What I learned ---
    lines.append("## What I learned")
    l1_entry = by_qid.get(wrap_result.get("l1_qid"))
    if l1_entry is not None:
        status = l1_entry.get("status")
        status_label = "applied (quarantined, unreviewed)" if status == "applied" else status
        lines.append(f"- session summary ({l1_entry['qid']}): {status_label}")
    elif wrap_result.get("l1_status") == "noop-duplicate":
        # #49: an unchanged re-run dedups the L1 propose to a synthetic,
        # never-persisted noop-duplicate entry — the qid is absent from disk
        # by design, so "(not found)" would be a false alarm.
        lines.append("- session summary: unchanged (already saved)")
    else:
        lines.append("- session summary: (not found)")
    if not wrap_result.get("project"):
        lines.append(
            f"- ⚠ session summary filed under GLOBAL l1/ — no project detected "
            f"from {wrap_result.get('wrap_cwd', 'unknown cwd')}; pass cwd= or register "
            f"the project in projects.json"
        )
    lines.append(f"- project overview: {wrap_result.get('overview', 'skipped')}")
    lines.append("")

    # --- Saved this session (revertible) ---
    lines.append("## Saved this session (revertible)")
    reverted = {j["revert_of"] for j in journal.entries() if j.get("revert_of")}
    saved_entries = [
        e for e in entries
        if e.get("status") == "applied"
        and e.get("approved_by") in ("auto-tier", "model-resolved")
        and e.get("write_id") not in reverted
    ]
    if saved_entries:
        for entry in saved_entries:
            write_id = entry.get("write_id")
            page = entry["proposal"]["page"]
            lines.append(f'- {page} (write_id={write_id}) — say "undo {write_id}" to revert')
    else:
        lines.append("- (none this session)")
    updated = wrap_result.get("updated") or []
    if updated:
        n = len(updated)
        lines.append(f"- {n} page{'s' if n != 1 else ''} updated (durable item merged)")
    suggested = wrap_result.get("suggested") or []
    if suggested:
        n = len(suggested)
        lines.append(
            f"- {n} update{'s' if n != 1 else ''} to a human-authored page held as a suggestion"
        )
    decayed = wrap_result.get("decayed") or []
    if decayed:
        n = len(decayed)
        lines.append(f"- {n} stale page{'s' if n != 1 else ''} archived — revertible")
    consolidated = wrap_result.get("consolidated") or []
    merged = [m for m in consolidated if m.get("status") != "partial"]
    partial = [m for m in consolidated if m.get("status") == "partial"]
    if merged:
        n = len(merged)
        lines.append(f"- {n} duplicate{'s' if n != 1 else ''} consolidated — revertible")
    if partial:
        n = len(partial)
        lines.append(f"- {n} consolidation{'s' if n != 1 else ''} partial — see journal")
    lines.append("")

    # --- Link duties (#54) — one clean line, or the details when something
    # was skipped/failed. `links` is always present on `wrap_result` per
    # `wrap_session`'s contract, but `.get`/`or {}` keeps this screen honest
    # for hand-built result dicts in tests too.
    links = wrap_result.get("links") or {}
    lines.append(
        "links: L1 ✥{l1} · log {log} · sessions {sess} · pointers {ptrs}".format(
            l1=links.get("l1_touched", 0),
            log="✓" if links.get("log_entry") else "✗",
            sess="✓" if links.get("sessions_entry") else "✗",
            ptrs=len(links.get("auto_pointers") or []),
        )
    )
    for warning in links.get("warnings") or []:
        lines.append(f"⚠ {warning}")
    lines.append("")

    # --- Live pins (#25) — omitted entirely when none ---
    # Cross-session: stale pins from earlier sessions are exactly the ones
    # needing cleanup. The live session judges which look acted-on and asks
    # the friend (see SKILL.md); a confirmed delete goes through the queue
    # via the normal correction path. Nothing here auto-deletes.
    pins = live_pin_pages()
    if pins:
        lines.append("## Live pins")
        for pin_info in pins:
            lines.append(f"- {pin_info['page']} ({pin_info['qid']})")
            if pin_info["preview"]:
                lines.append(f"  > {pin_info['preview']}")
        lines.append("")

    # --- Classify this session's still-pending entries into held/suggestions ---
    # A pending entry is a *hold* iff any conflict is a `contradicts` —
    # checked FIRST, so a contradiction-held candidate never renders as a
    # "yes"-able suggestion (that path skips recording a
    # contradiction_resolution). Every other pending entry (instruction-plane
    # global/ targets, or any other residue such as a plain pin awaiting a
    # human) lists under suggestions.
    pending_entries = [e for e in entries if e.get("status") == "pending"]
    held_entries: list[dict] = []
    suggestion_entries: list[dict] = []
    for entry in pending_entries:
        if any(c.get("kind") == "contradicts" for c in (entry.get("conflicts") or [])):
            held_entries.append(entry)
        else:
            suggestion_entries.append(entry)

    # --- Held — contradictions to resolve (omitted entirely when empty) ---
    if held_entries:
        lines.append("## Held — contradictions to resolve")
        for entry in held_entries:
            page = entry["proposal"]["page"]
            reason = entry["proposal"].get("reason", "")
            flags = _conflict_flags(entry.get("conflicts") or [])
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            lines.append(f"- {entry['qid']} → {page} — {reason}{flag_str}")
            preview = _content_preview(entry["proposal"].get("content"))
            if preview:
                lines.append(f"  > {preview}")
        lines.append("")

    # --- Suggestions ---
    lines.append("## Suggestions")
    if suggestion_entries:
        for entry in suggestion_entries:
            page = entry["proposal"]["page"]
            reason = entry["proposal"].get("reason", "")
            flags = _conflict_flags(entry.get("conflicts") or [])
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            lines.append(f"- {entry['qid']} → {page} — {reason}{flag_str}")
            preview = _content_preview(entry["proposal"].get("content"))
            if preview:
                lines.append(f"  > {preview}")
    else:
        lines.append("- (none)")
    lines.append("")

    # --- Possible connections (informational, judge-sourced) ---
    # Task 12: LLM-judged verdicts over this session's applied writes vs. the
    # rest of the wiki. Purely informational — omitted entirely when empty,
    # never a slash-command hint; acting on one is 0.5.3's job.
    semantic_findings = wrap_result.get("semantic_findings") or []
    if semantic_findings:
        lines.append("## Possible connections (unverified)")
        for finding in semantic_findings:
            lines.append(
                f"- {finding['page']} ↔ {finding['with']}: {finding['verdict']} "
                f"(confidence {finding['confidence']:.2f}) — {finding['reason']}"
            )
        lines.append("")

    # --- Refused (never queued) ---
    refused = wrap_result.get("refused") or []
    if refused:
        lines.append("## Refused (not queued)")
        for item in refused:
            # Deliberately do NOT render `item["item"]` — that's the raw
            # candidate text, which is exactly what got refused for
            # containing a secret. `reason` is `lib.memory.scrub.SecretsFound`'s
            # message, which names kinds + counts only, never secret content.
            lines.append(f"- refused: {item.get('reason', '')}")
        lines.append("")

    lines.append("Answers to the suggestions above happen in chat — just tell me what to do.")
    return "\n".join(lines) + "\n"


__all__ = [
    "wrap_session",
    "maintain_overview",
    "render_wrap_screen",
    "render_pending_list",
    "harvest_suggestions",
]
