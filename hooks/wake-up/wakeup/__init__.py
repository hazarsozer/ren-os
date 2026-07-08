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
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Final

from lib import ren_paths
from lib.instrument import collect, miss_log
from lib.memory import queue

logger = logging.getLogger(__name__)


DEFAULT_DEV_ROOT_REL: Final[str] = "Dev"
L1_DIRNAME: Final[str] = "l1"
L2_MAP_FILENAME: Final[str] = "map.md"
MASTER_ROUTINES_DIRNAME: Final[str] = "routines"

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


def resolve_dev_root() -> Path:
    """Projects root for cwd-based project detection. `CLAUDE_PLUGIN_OPTION_DEVROOT`
    → `~/Dev`."""
    val = os.environ.get("CLAUDE_PLUGIN_OPTION_DEVROOT", "").strip()
    if val:
        return Path(os.path.expanduser(os.path.expandvars(val)))
    return Path.home() / DEFAULT_DEV_ROOT_REL


def detect_project(cwd: Path, wiki_root: Path, dev_root: Path | None = None) -> str | None:
    """cwd matches `<dev_root>/<X>/...` AND `wiki_root/projects/<X>/` exists → X."""
    if dev_root is None:
        dev_root = resolve_dev_root()
    try:
        rel = cwd.resolve().relative_to(dev_root.resolve())
    except (ValueError, OSError):
        return None
    if not rel.parts:
        return None
    candidate = rel.parts[0]
    if (wiki_root / "projects" / candidate).is_dir():
        return candidate
    return None


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
    signal), or "" if there is no `l1/` dir or no `session-*.md` files."""
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
    return _read_text_safe(candidates[0])


def read_l2_map(project_dir: Path) -> str:
    """Return the project's L2 pointer-map content (`map.md`), or "" if absent."""
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
    """One line announcing pending queue entries (v2.2: suggestions are
    conversational, not a queue verb — Task 8). Returns "" when nothing is
    pending, so the payload gains nothing on the common case.

    Counts only suggestion-classified entries (a `global/` target, or
    produced by `"retrospective"`, WITHOUT a `contradicts` conflict) toward
    "N suggestion(s)" — a contradiction hold is not a suggestion (matches
    `skills.wrap.lib.render_wrap_screen`'s classification order: contradicts
    wins first). If any contradiction holds exist, appends a second count."""
    try:
        entries = queue.pending()
    except Exception:  # noqa: BLE001 - never let this abort the wake-up payload
        logger.debug("queue.pending() failed", exc_info=True)
        return ""
    if not entries:
        return ""

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
    if not parts:
        return ""
    return f"{' and '.join(parts)} waiting — I'll list them; answer in chat or ignore."


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


def _discover_extra_candidates(wiki_root: Path, exclude: set[str]) -> list[str]:
    """Every `*.md` under `wiki_root`, excluding dotdirs and `exclude` (the
    pages already surfaced as L1/L2, so they aren't offered twice)."""
    if not wiki_root.is_dir():
        return []
    candidates = []
    for path in wiki_root.rglob("*.md"):
        rel = path.relative_to(wiki_root).as_posix()
        if any(part.startswith(".") for part in path.relative_to(wiki_root).parts):
            continue
        if rel in exclude:
            continue
        candidates.append(rel)
    return candidates


def _salient_pages() -> set[str]:
    """Wiki-relative pages whose most recent APPLIED queue entry carried
    `proposal.salience=True` (Task 4.2's pin/correction verb sets this).

    Reads `state_dir()/"queue"/*.json` directly rather than adding a new
    public listing function to `lib.memory.queue` — the hook only needs two
    fields (`status`, `proposal.salience`/`proposal.page`) from otherwise-frozen
    queue-entry files, so it reads the raw JSON rather than reconstructing
    `QueueEntry`/`Proposal` dataclasses it has no other use for.
    """
    queue_dir = ren_paths.state_dir() / "queue"
    if not queue_dir.is_dir():
        return set()
    pages: set[str] = set()
    for path in queue_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("status") != "applied":
            continue
        proposal = data.get("proposal") or {}
        if proposal.get("salience") and proposal.get("page"):
            pages.add(proposal["page"])
    return pages


def rank_extras(
    query: str,
    wiki_root: Path,
    exclude: set[str],
    *,
    count: int = DEFAULT_EXTRAS_COUNT,
) -> list[str]:
    """Rank candidate pages (excluding `exclude`) via `skills.recall.lib.rank`,
    then move any salience-boosted page (Task 4.2 pins) to the front of its
    tier — i.e. all salient pages first (in their relative rank order among
    themselves), then the rest — and return the top `count`.

    `rank` is reached via `importlib.import_module("skills.recall.lib")`, the
    hyphen-safe pattern documented in Task 4.4 (kept here for consistency even
    though `recall` itself has no hyphen).
    """
    import importlib

    candidates = _discover_extra_candidates(wiki_root, exclude)
    if not candidates:
        return []

    recall_lib = importlib.import_module("skills.recall.lib")
    ranked = recall_lib.rank(query, candidates, wiki_root)

    salient = _salient_pages()
    boosted = [p for p in ranked if p in salient] + [p for p in ranked if p not in salient]
    return boosted[:count]


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

    Injects the active project's L1 (quarantine banner intact) + L2 map,
    live routines, and a small set of heuristically-ranked + salience-boosted
    extra pages — all within a hard token budget (oversized sections are
    truncated with a marker, never silently dropped). Records every surfaced
    page via `miss_log.log_surface` and the payload's byte size via
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

    project = None
    try:
        project = detect_project(cwd, wiki_root, dev_root=dev_root)
    except Exception:  # noqa: BLE001 - never let project detection abort the payload
        logger.debug("detect_project failed", exc_info=True)

    if project is not None:
        project_dir = wiki_root / "projects" / project

        l1_text = read_l1(project_dir)
        if l1_text:
            sections.append(f"### {project} — most recent session (L1)")
            sections.append(truncate_text_to_tokens(l1_text, L1_BUDGET))
            l1_files = sorted(
                (project_dir / L1_DIRNAME).glob("session-*.md"), key=_safe_mtime, reverse=True
            )
            if l1_files:
                surfaced_pages.append(str(l1_files[0].relative_to(wiki_root).as_posix()))

        l2_text = read_l2_map(project_dir)
        if l2_text:
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

    try:
        query = _build_rank_query(project, cwd)
        extras = rank_extras(query, wiki_root, exclude=set(surfaced_pages))
    except Exception:  # noqa: BLE001 - ranking failure degrades to no extras
        logger.debug("rank_extras failed", exc_info=True)
        extras = []

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
