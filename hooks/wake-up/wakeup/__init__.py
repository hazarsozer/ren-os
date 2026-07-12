"""
ren-wake-up lib — composition layer for the SessionStart wake-up hook (Task 5.1,
RenOS 0.2 Phase 5).

Pure-logic functions for assembling the additionalContext payload:
  - detect_project(cwd, wiki_root) → project slug or None
  - read_l1(project_dir) → most recent L1 session page, quarantine banner intact
  - read_l2_map(project_dir) → the project's L2 pointer-map (projects/<slug>/map.md)
  - read_live_routines(wiki_root) → live-automations digest (carried from donor)
  - rank_extras(...) → heuristic-ranked additional pages, salience-boosted
  - estimate_tokens / truncate_text_to_tokens → the byte-budget mechanism
  - compose_wake_up_context(...) → orchestrator

Substrate CARRIED from donor `hooks/wake-up/wakeup/__init__.py` (per the harvest
map): the truncate-with-marker budget mechanism, project detection (cwd vs a
configurable dev root), and live-routine surfacing. What CHANGED (spec §3.1 +
§3.2):
  - Payload content: L1 (quarantine-bannered) + L2 map for the active project,
    NOT donor's master index + log-tail (that pair is dropped entirely).
  - Ranking: additional pages beyond L1/L2 are chosen by
    `skills.recall.lib.rank` (Task 4.3's heuristic — token overlap + recency +
    path-kind hints), reached via `importlib.import_module("skills.recall.lib")`
    per the hyphen-safe pattern noted in Task 4.4 (recall has no hyphen, but the
    pattern is used consistently everywhere the hook reaches into `skills/`).
  - Salience boost: pages behind an APPLIED queue entry whose proposal carried
    `salience=True` (Task 4.2's pin/correction verb) are moved to the front of
    the ranked extras.
  - Instrumentation: every composed payload calls
    `lib.instrument.miss_log.log_surface` (the pages actually surfaced) and
    `lib.instrument.collect.record(KIND_INJECTED_BYTES, ...)` — this is what
    makes G12's mechanical miss rate computable (Task 3.3).

Cache-line discipline (ADR-008, inviolable): this module only supplies TEXT for
`hookSpecificOutput.additionalContext` — it never touches the system-prompt
prefix. No LLM call anywhere in this module (verified by
`tests/hooks/test_wakeup.py`'s source-scan test).

RenOS 0.4.1 "trust hardening" (spec §4 L1-exemption amendment): extras (the
ranked "Related pages" section) AND the L2 knowledge map exclude every page
`lib.memory.quarantine` considers quarantined — that channel is where
foreign/ingested content travels, so it gets the read-time exclusion. L1 is
the ONLY exemption, and stays injected with its quarantine banner intact: L1
is RenOS's own summary of the user's own session, not foreign content, so the
banner alone (data-not-instruction) is the correct signal — dropping it from
context would break session continuity for no trust benefit. See `read_l1`'s
docstring for the same point at the call site. L2 maps do NOT get this
exemption: `ingest-project` writes them with `writer="llm-auto"` from a
repo scan, which is exactly the foreign/scan-derived content this exclusion
targets — a quarantined map is held out of `compose_wake_up_context` and
counted in the "N quarantined page(s) held out" line until a human releases
it (see `skills/ingest-project/SKILL.md`'s close-out step).
"""

from __future__ import annotations

import logging
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final

from lib.instrument import collect, miss_log
from lib.memory import queue, quarantine
from lib.memory.provenance import read_frontmatter_provenance
from lib.ren_paths import DEFAULT_DEV_ROOT_REL, detect_project, resolve_dev_root

logger = logging.getLogger(__name__)


L1_DIRNAME: Final[str] = "l1"
L2_MAP_FILENAME: Final[str] = "map.md"
MASTER_ROUTINES_DIRNAME: Final[str] = "routines"
_SUGGESTION_LIST_CAP: Final[int] = 5
SALIENCE_WINDOW_DAYS: Final[int] = 30

# Token budget (ADR-008 heritage: 3-5K target, 5K hard cap)
DEFAULT_MAX_TOKENS: Final[int] = 5_000
CHARS_PER_TOKEN: Final[float] = 4.0  # rough heuristic; tiktoken-free for hook latency

# Per-section token allocations.
L1_BUDGET: Final[int] = 1_200
L2_BUDGET: Final[int] = 1_200
ROUTINE_SPEC_BUDGET: Final[int] = 400
EXTRAS_BUDGET: Final[int] = 1_600   # ranked additional pages, split across however many fit
EXTRA_PAGE_BUDGET: Final[int] = 400  # per-page cap within the extras budget
DEFAULT_EXTRAS_COUNT: Final[int] = 3

_GIT_TIMEOUT_S: Final[float] = 3.0


def estimate_tokens(text: str) -> int:
    """Rough token count via chars/4 heuristic (no tiktoken dep for hook latency)."""
    return int(len(text) / CHARS_PER_TOKEN)


def truncate_text_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate `text` to fit within `max_tokens`, keeping the TAIL (most
    recent/relevant content) and prefixing a `[...truncated; N chars
    elided...]` marker when anything was cut — content is truncated, never
    silently dropped."""
    if max_tokens <= 0:
        return ""
    max_chars = int(max_tokens * CHARS_PER_TOKEN)
    if len(text) <= max_chars:
        return text
    return f"[...truncated; first {len(text) - max_chars} chars elided...]\n" + text[-max_chars:]


# `resolve_dev_root` and `detect_project` now live in `lib.ren_paths` (codex
# D4 wiring) — imported above, re-exported here so existing callers of
# `wakeup.resolve_dev_root` / `wakeup.detect_project` keep working. Shared
# with `skills/wrap/lib` so wrap's write path and wake-up's read path can
# never resolve a cwd to two different project slugs.


def _read_text_safe(path: Path) -> str:
    """Read a file as text; return "" on any error (missing, permissions,
    binary garbage that doesn't decode as UTF-8, ...). Never raises."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("could not read %s: %s", path, exc)
        return ""


def read_l1(project_dir: Path) -> str:
    """Return the most recent L1 session page's raw content (quarantine banner
    intact — it's data-not-instruction, and the hook must not strip that
    signal), or "" if there is no `l1/` dir or no `session-*.md` files, or the
    most recent page fails the stamp check below.

    L1 EXEMPTION (spec §4 amendment, 0.4.1): L1 pages are `llm-auto` and thus
    quarantined like any other unreviewed content, but they are deliberately
    exempt from the extras-side quarantine exclusion (`_discover_extra_candidates`)
    and are always injected here regardless. Rationale: L1 is RenOS's own
    summary of the user's OWN session — not foreign/ingested content — so the
    banner is sufficient signal (data-not-instruction) and the exclusion,
    which targets channels foreign content travels through, does not apply.

    Codex P5 hardening (0.5.1 Task 9): the exemption above previously trusted
    the L1 *path shape* alone — anything dropped at `l1/session-*.md` was
    injected raw, banner or not. That's no longer enough: this now verifies
    the page's OWN `ren_trust` stamp (Task 6) is `"model"` (a genuine RenOS
    write, not a foreign/human-planted file) before applying the exemption.
    A page that IS stamped `"model"` is injected raw regardless of the banner
    (the exemption, as before). A page that is unstamped OR stamped anything
    else (foreign, human, etc.) is held out (empty string) — never injected
    raw on path shape alone. Migration `trust-backfill-1` (Task 7) stamps
    `ren_trust` on every pre-0.5.1 page, so a legitimately old L1 page is
    stamped after migration; an unstamped file at this path post-migration
    has no legitimate explanation and gets the same held-out treatment as a
    foreign-stamped one.
    """
    l1_dir = project_dir / L1_DIRNAME
    if not l1_dir.is_dir():
        return ""
    try:
        candidates = sorted(l1_dir.glob("session-*.md"), key=lambda p: _safe_mtime(p), reverse=True)
    except OSError as exc:
        logger.debug("could not list %s: %s", l1_dir, exc)
        return ""
    if not candidates:
        return ""
    text = _read_text_safe(candidates[0])
    if not text:
        return ""

    prov = read_frontmatter_provenance(text)
    if prov and prov.get("trust") == "model":
        return text

    # Not a verified model-class RenOS write — held out, whether foreign-
    # stamped or entirely unstamped. Never injected raw on path shape alone.
    return ""


def read_l2_map(project_dir: Path) -> str:
    """Return the project's L2 pointer-map content (`map.md`), or "" if absent.

    Quarantine banner intact — this function only reads the file. The
    quarantine CHECK (and the decision to hold it out of the payload) happens
    in `compose_wake_up_context`, because L2 does NOT get L1's exemption: a
    map written by `ingest-project` carries `writer="llm-auto"` from a repo
    scan, which is foreign/scan-derived content, not the user's own session.
    """
    return _read_text_safe(project_dir / L2_MAP_FILENAME)


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


_ROUTINE_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_routine_fields(content: str) -> dict[str, str]:
    """Tiny dependency-free frontmatter field reader (no PyYAML at hook runtime)."""
    m = _ROUTINE_FM_RE.match(content)
    if not m:
        return {}
    fields: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        k, _, v = line.partition(":")
        fields[k.strip()] = v.strip().strip('"').strip("'")
    return fields


def read_live_routines(wiki_root: Path) -> str:
    """Scan `wiki/routines/` for routine-spec pages; one-line-per-routine
    digest. Returns "" if no routines/ dir or no routine-spec pages. Carried
    from donor (ADR-034 heritage)."""
    routines_dir = wiki_root / MASTER_ROUTINES_DIRNAME
    if not routines_dir.is_dir():
        return ""
    try:
        paths = sorted(routines_dir.glob("*.md"))
    except OSError as exc:
        logger.debug("could not scan routines dir %s: %s", routines_dir, exc)
        return ""
    rows: list[str] = []
    for path in paths:
        fm = _parse_routine_fields(_read_text_safe(path))
        if fm.get("type") != "routine-spec":
            continue
        name = fm.get("name", path.stem)
        trigger = fm.get("trigger_type", "?")
        repo = fm.get("linked_repo", "?")
        rows.append(f"- **{name}** · {trigger} · {repo}")
    return "\n".join(rows)


def suggestion_line() -> str:
    """Multi-line block announcing pending queue entries (v2.2: suggestions are
    conversational, not a queue verb — Task 8). Lists up to `_SUGGESTION_LIST_CAP`
    pending items with their page and reason; returns "" when nothing is pending,
    so the payload gains nothing on the common case.

    Counts only suggestion-classified entries (a `global/` target, or
    produced by `"retrospective"`, WITHOUT a `contradicts` conflict) toward
    "N suggestion(s)" — a contradiction hold is not a suggestion (matches
    `skills.wrap.lib.render_wrap_screen`'s classification order: contradicts
    wins first). If any contradiction holds exist, appends a second count.

    Returns a multi-line block with: count line + up to _SUGGESTION_LIST_CAP item
    lines (qid → page — reason) + overflow line if needed. This replaces the old
    bare count announcement so the user can see what they're answering without
    scrolling."""
    try:
        entries = queue.pending()
    except Exception:  # noqa: BLE001 - never let this abort the wake-up payload
        logger.debug("queue.pending() failed", exc_info=True)
        entries = []

    lines: list[str] = []

    if entries:
        held = 0
        suggested = 0
        for entry in entries:
            if any(c.get("kind") == "contradicts" for c in (entry.conflicts or [])):
                held += 1
            else:
                suggested += 1

        parts = []
        if suggested:
            plural = "" if suggested == 1 else "s"
            parts.append(f"{suggested} suggestion{plural}")
        if held:
            plural = "" if held == 1 else "s"
            parts.append(f"{held} contradiction hold{plural}")

        if parts:
            lines.append(f"{' and '.join(parts)} waiting — answer in chat or ignore:")
            for entry in entries[:_SUGGESTION_LIST_CAP]:
                reason = entry.proposal.reason or ""
                lines.append(f"- {entry.qid} → {entry.proposal.page} — {reason}")
            overflow = len(entries) - _SUGGESTION_LIST_CAP
            if overflow > 0:
                lines.append(f"- …and {overflow} more — ask me to list them")

    store_line = _suggestions_store_line()
    if store_line:
        lines.append(store_line)

    return "\n".join(lines)


def _suggestions_store_line() -> str:
    """Pointer line for `lib.suggestions` (Task 14's separate suggestion
    store, distinct from the queue) — announces its own pending count when
    non-empty. Never raises: any store-read failure degrades to ""."""
    try:
        from lib import suggestions

        entries = suggestions.pending_suggestions()
    except Exception:  # noqa: BLE001 - never let this abort the wake-up payload
        logger.debug("lib.suggestions.pending_suggestions() failed", exc_info=True)
        return ""
    if not entries:
        return ""
    n = len(entries)
    return f"{n} instruction suggestion(s) pending — run /ren:suggestions to review."


def _git(cwd: Path, args: list[str]) -> str:
    """Read-only, bounded git subprocess call. Returns "" on ANY failure
    (not a repo, git absent, timeout, non-zero exit) — never raises."""
    try:
        proc = subprocess.run(
            ["git"] + args, cwd=str(cwd), capture_output=True, timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.decode("utf-8", errors="replace").strip()


def _build_rank_query(project: str | None, cwd: Path) -> str:
    """Heuristic query for `rank`: project slug words + current git branch +
    recent commit subject words. Every source is best-effort; an empty query
    is a valid (if degraded) outcome — see `rank`'s own empty-query behavior."""
    parts: list[str] = []
    if project:
        parts.append(project.replace("-", " ").replace("_", " "))

    branch = _git(cwd, ["rev-parse", "--abbrev-ref", "HEAD"])
    if branch and branch != "HEAD":
        parts.append(branch.replace("-", " ").replace("_", " "))

    recent = _git(cwd, ["log", "-3", "--pretty=%s"])
    if recent:
        parts.append(recent.replace("\n", " "))

    return " ".join(parts).strip()


def _is_foreign_stamped(path: Path) -> bool:
    """True if `path`'s own `ren_trust` frontmatter stamp is `"foreign"` —
    Task 9b: the banner-only exclusion (`quarantine.quarantined_rel_pages`)
    misses a foreign-stamped page whose banner has since been released, so
    this checks the durable stamp (Task 6) independently of banner state.
    Unstamped pages are NOT foreign (deliberate scope decision — see module
    docstring / Task 9b brief: only the ingest door mints "foreign", and
    ordinary hand-written pages carry no `ren_*` stamps at all). Never
    raises: any read/parse failure degrades to "not foreign".
    """
    text = _read_text_safe(path)
    if not text:
        return False
    try:
        prov = read_frontmatter_provenance(text)
    except Exception:  # noqa: BLE001 - provenance parse failure must never abort wake-up
        logger.debug("read_frontmatter_provenance failed for %s", path, exc_info=True)
        return False
    return bool(prov and prov.get("trust") == "foreign")


def _discover_extra_candidates(wiki_root: Path, exclude: set[str]) -> tuple[list[str], int]:
    """Every `*.md` under `wiki_root`, excluding dotdirs, `exclude` (the pages
    already surfaced as L1/L2, so they aren't offered twice), quarantined
    pages (0.4.1 trust hardening — see module docstring for the L1 exemption,
    which does NOT apply here since L1 is never routed through this extras
    path), and `ren_trust: foreign`-stamped pages (Task 9b — closes the gap
    where a foreign page's released banner let it surface raw; unstamped
    pages remain included, per the deliberate scope decision in `_is_foreign_stamped`).

    Returns `(candidates, held_count)` where `held_count` is the number of
    otherwise-eligible pages dropped for being quarantined or foreign-stamped.
    Quarantine-scan failure degrades to no exclusion (never raises) — logged
    at debug level.
    """
    if not wiki_root.is_dir():
        return [], 0
    try:
        held_pages = quarantine.quarantined_rel_pages(wiki_root)
    except Exception:  # noqa: BLE001 - quarantine scan failure must never abort wake-up
        logger.debug("quarantined_rel_pages failed", exc_info=True)
        held_pages = set()

    candidates = []
    held_count = 0
    for path in wiki_root.rglob("*.md"):
        rel = path.relative_to(wiki_root).as_posix()
        if any(part.startswith(".") for part in path.relative_to(wiki_root).parts):
            continue
        if rel in exclude:
            continue
        if rel in held_pages:
            held_count += 1
            continue
        if _is_foreign_stamped(path):
            held_count += 1
            continue
        candidates.append(rel)
    return candidates, held_count


def _salient_pages() -> set[str]:
    """Wiki-relative pages with ANY applied queue entry that carried
    `proposal.salience=True` (Task 4.2's pin/correction verb sets this).
    Boosts expire after SALIENCE_WINDOW_DAYS — re-pin to refresh.
    Reads via `queue.all_entries()` (public read API, 0.4.0) instead of
    parsing `state_dir()/queue/*.json` raw."""
    try:
        entries = queue.all_entries()
    except Exception:  # noqa: BLE001 - never let this abort the wake-up payload
        logger.debug("queue.all_entries() failed", exc_info=True)
        return set()

    now = datetime.now(timezone.utc)
    result = set()
    for e in entries:
        if not (e.status == "applied" and e.proposal.salience and e.proposal.page):
            continue

        # Parse ts and check if within window. Unparsable ts → treat as fresh (never raise).
        try:
            entry_time = datetime.strptime(e.ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            age = now - entry_time
            if age <= timedelta(days=SALIENCE_WINDOW_DAYS):
                result.add(e.proposal.page)
        except (ValueError, TypeError):
            # Unparsable ts → treat as fresh, never raise
            logger.debug("could not parse ts %r; treating as fresh", e.ts)
            result.add(e.proposal.page)

    return result


def rank_extras(
    query: str,
    wiki_root: Path,
    exclude: set[str],
    *,
    count: int = DEFAULT_EXTRAS_COUNT,
) -> tuple[list[str], int]:
    """Rank candidate pages (excluding `exclude` and quarantined pages) via
    `skills.recall.lib.rank`, then move any salience-boosted page (Task 4.2
    pins) to the front of its tier — i.e. all salient pages first (in their
    relative rank order among themselves), then the rest — and return
    `(top count pages, held_count)`, where `held_count` is the number of
    quarantined pages excluded (see `_discover_extra_candidates`).

    `rank` is reached via `importlib.import_module("skills.recall.lib")`, the
    hyphen-safe pattern documented in Task 4.4 (kept here for consistency even
    though `recall` itself has no hyphen).
    """
    import importlib

    candidates, held_count = _discover_extra_candidates(wiki_root, exclude)
    if not candidates:
        return [], held_count

    recall_lib = importlib.import_module("skills.recall.lib")
    ranked = recall_lib.rank(query, candidates, wiki_root)

    salient = _salient_pages()
    boosted = [p for p in ranked if p in salient] + [p for p in ranked if p not in salient]
    return boosted[:count], held_count


def compose_wake_up_context(
    *,
    cwd: Path,
    wiki_root: Path,
    source: str = "startup",
    session: str = "unknown",
    max_tokens: int = DEFAULT_MAX_TOKENS,
    dev_root: Path | None = None,
) -> str:
    """Compose the additionalContext payload for the SessionStart hook.

    Injects the active project's L1 (quarantine banner intact, always
    injected — see module docstring for the L1 exemption) + L2 map (injected
    ONLY if not quarantined; a quarantined map is held out and counted in the
    "N quarantined page(s) held out" line instead), live routines, and a
    small set of heuristically-ranked + salience-boosted extra pages — all
    within a hard token budget (oversized sections are truncated with a
    marker, never silently dropped). Records every surfaced page via
    `miss_log.log_surface` and the payload's byte size via
    `collect.record(KIND_INJECTED_BYTES, ...)` — this instrumentation is
    unconditional, not optional.

    Returns "" if the wiki is inaccessible (graceful degradation; the hook
    still exits 0). NEVER raises — any per-section failure degrades that
    section to empty rather than aborting the whole payload.
    """
    if not wiki_root.is_dir():
        logger.info("wiki not found at %s; emitting empty context", wiki_root)
        return ""

    sections: list[str] = [f"## RenOS wake-up context (source={source})\n"]
    surfaced_pages: list[str] = []
    held_count = 0

    project = None
    try:
        project = detect_project(cwd, wiki_root, dev_root=dev_root)
    except Exception:  # noqa: BLE001 - never let project detection abort the payload
        logger.debug("detect_project failed", exc_info=True)

    if project is not None:
        project_dir = wiki_root / "projects" / project

        # Codex P5: whether or not read_l1 ultimately injects a given
        # candidate, its most recent file at EITHER the project-local or the
        # global fallback L1 path must not leak back in via the extras
        # ("Related pages") discovery path, which excludes only banner-
        # quarantined pages — a bannerless-but-unstamped hostile file that
        # read_l1 correctly held out would otherwise be offered raw there.
        for candidate_dir in (project_dir, wiki_root):
            candidate_files = sorted(
                (candidate_dir / L1_DIRNAME).glob("session-*.md"), key=_safe_mtime, reverse=True
            )
            if candidate_files:
                surfaced_pages.append(str(candidate_files[0].relative_to(wiki_root).as_posix()))

        l1_text = read_l1(project_dir)
        if not l1_text:
            # codex D4: project-local `l1/` has nothing (either no wrap has
            # ever written here, or this wiki predates the project-aware L1
            # path) — fall back to the global `l1/` dir so pre-fix pages
            # (and non-project-scoped wraps) stay reachable rather than the
            # project's most recent session silently vanishing from context.
            l1_text = read_l1(wiki_root)

        if l1_text:
            sections.append(f"### {project} — most recent session (L1)")
            sections.append(truncate_text_to_tokens(l1_text, L1_BUDGET))

        l2_text = read_l2_map(project_dir)
        if l2_text:
            l2_quarantined = False
            try:
                l2_quarantined = quarantine.is_quarantined(l2_text)
            except Exception:  # noqa: BLE001 - quarantine check failure must never abort wake-up
                logger.debug("quarantine.is_quarantined failed for L2 map", exc_info=True)
            l2_foreign = False
            try:
                l2_prov = read_frontmatter_provenance(l2_text)
                l2_foreign = bool(l2_prov and l2_prov.get("trust") == "foreign")
            except Exception:  # noqa: BLE001 - provenance parse failure must never abort wake-up
                logger.debug("read_frontmatter_provenance failed for L2 map", exc_info=True)
            if l2_quarantined or l2_foreign:
                # L2 maps are scan-derived (repo-ingest, `writer="llm-auto"`) —
                # foreign content, unlike L1's own-session summary. The L1
                # exemption does NOT apply here; hold it out and count it in
                # the held-out line until a human releases it from quarantine.
                # Task 9b: a released banner alone no longer clears a
                # `ren_trust: foreign` map — the stamp check catches that.
                held_count += 1
            else:
                sections.append(f"### {project} — knowledge map (L2)")
                sections.append(truncate_text_to_tokens(l2_text, L2_BUDGET))
                surfaced_pages.append(f"projects/{project}/{L2_MAP_FILENAME}")

    live_routines = read_live_routines(wiki_root)
    if live_routines:
        sections.append("### Live automations (routine-specs)")
        sections.append(truncate_text_to_tokens(live_routines, ROUTINE_SPEC_BUDGET))

    suggestion = suggestion_line()
    if suggestion:
        sections.append(suggestion)

    extras: list[str] = []
    try:
        query = _build_rank_query(project, cwd)
        extras, extras_held_count = rank_extras(query, wiki_root, exclude=set(surfaced_pages))
    except Exception:  # noqa: BLE001 - ranking failure degrades to no extras
        logger.debug("rank_extras failed", exc_info=True)
        extras, extras_held_count = [], 0
    held_count += extras_held_count

    if extras:
        sections.append("### Related pages")
        per_page_budget = max(EXTRA_PAGE_BUDGET, EXTRAS_BUDGET // max(len(extras), 1))
        for rel in extras:
            text = _read_text_safe(wiki_root / rel)
            if not text:
                continue
            sections.append(f"#### {rel}")
            sections.append(truncate_text_to_tokens(text, per_page_budget))
            surfaced_pages.append(rel)

    if held_count > 0:
        sections.append(
            f"{held_count} quarantined page(s) held out of this context — "
            "ask to see them explicitly."
        )

    composed = "\n\n".join(s for s in sections if s.strip())

    final_tokens = estimate_tokens(composed)
    if final_tokens > max_tokens:
        logger.info("composed %d tokens; truncating to %d", final_tokens, max_tokens)
        composed = truncate_text_to_tokens(composed, max_tokens)

    try:
        if surfaced_pages:
            miss_log.log_surface(surfaced_pages, session)
        collect.record(collect.KIND_INJECTED_BYTES, {"bytes": len(composed.encode("utf-8")), "session": session})
    except Exception:  # noqa: BLE001 - instrumentation failure must never break wake-up
        logger.debug("instrumentation recording failed", exc_info=True)

    return composed


__all__ = [
    "DEFAULT_MAX_TOKENS",
    "CHARS_PER_TOKEN",
    "DEFAULT_DEV_ROOT_REL",
    "L1_BUDGET",
    "L2_BUDGET",
    "ROUTINE_SPEC_BUDGET",
    "EXTRAS_BUDGET",
    "EXTRA_PAGE_BUDGET",
    "SALIENCE_WINDOW_DAYS",
    "estimate_tokens",
    "truncate_text_to_tokens",
    "resolve_dev_root",
    "detect_project",
    "read_l1",
    "read_l2_map",
    "read_live_routines",
    "suggestion_line",
    "rank_extras",
    "compose_wake_up_context",
]
