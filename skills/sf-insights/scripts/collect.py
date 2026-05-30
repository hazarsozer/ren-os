#!/usr/bin/env python3
"""
collect.py — read-only local-session fact collector for /sf:insights.

Walks two LOCAL on-disk sources, filters each by file mtime within a
look-back window, and emits a bounded, structured fact-block on stdout.
The LLM (per references/synthesis-prompt.md) turns those facts into the
four-section narrative; this script only collects facts.

Sources (per ADR-031 solo-first; both may be absent — parse tolerantly):
  ~/.claude/projects/<encoded-cwd>/*.jsonl  rich heterogeneous transcripts
  ~/.claude/session-data/*.tmp              narrative save-session summaries

INVARIANTS:
  - NO writes. Every file is opened read-only; nothing is created/modified/deleted.
  - NO network. Pure local filesystem reads, stdlib only.
  - Tolerant parsing. JSONL is read line-by-line; malformed lines are skipped,
    never fatal. .tmp files are treated as narrative text.
  - Bounded memory. Counters + capped snippet lists; never accumulates raw bodies.

Usage:
    python3 collect.py [--days N] [--project NAME] [--claude-dir PATH]

Exit codes:
    0 — collection succeeded (an empty window is still success)
    2 — invocation error (bad args)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

# --------------------------------------------------------------------------
# Constants / bounds (keep memory + output flat regardless of input size)
# --------------------------------------------------------------------------

DATA_BLOCK_HEADER = "=== SF-INSIGHTS COLLECTED DATA (v1) ==="
DATA_BLOCK_FOOTER = "=== END SF-INSIGHTS COLLECTED DATA ==="

DEFAULT_DAYS = 30
SECONDS_PER_DAY = 86400

MAX_SESSIONS_LISTED = 60        # cap per-session detail lines in the output
TOP_TOOLS_PER_SESSION = 10      # cap tools listed per session
TOP_TOPICS_PER_SESSION = 8      # cap topic keywords per session
TOP_TOOLS_AGGREGATE = 15
TOP_TOPICS_AGGREGATE = 20
MAX_SUMMARY_SNIPPET = 240       # chars of narrative .tmp snippet
MAX_TOPIC_SCAN_CHARS = 4000     # cap text scanned per message for topics

# Error/retry signal vocabulary (lower-cased substring scan, bounded).
ERROR_PHRASES = (
    "error", "failed", "failure", "exception", "traceback",
    "not found", "permission denied", "cannot ", "could not",
    "try again", "retry", "still failing", "does not exist",
)

# Topic-extraction stopwords (kept small + deliberate; topics are a hint, not NLP).
STOPWORDS = frozenset(
    """
    the a an and or but if then else for to of in on at by with from into
    this that these those it its is are was were be been being do does did
    done have has had will would shall should can could may might must not
    no yes you your yours we our ours i me my mine they them their he she
    him her his hers as so than too very just about over under again more
    most some any all each every both few other such only own same up down
    out off above below here there when where why how what which who whom
    let lets like get got make made use used using run running file files
    code now also need want please thanks thank ok okay sure going go
    """.split()
)

# Noise wrappers to strip before topic extraction (XML-ish CC plumbing tags).
_TAG_RE = re.compile(r"<[^>]+>")
_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_\-]{2,}")
# Encoded project dir like "-home-hsozer-Dev-startup-framework"
_PROJECT_DIR_PREFIX = "-"


# --------------------------------------------------------------------------
# Data shapes
# --------------------------------------------------------------------------


@dataclass
class SessionFacts:
    """Per-transcript extracted facts. Mutable during a single-file stream,
    frozen-by-convention once returned."""

    session_id: str = ""
    project: str = ""
    cwd: str = ""
    branch: str = ""
    versions: set = field(default_factory=set)
    first_ts: str = ""
    last_ts: str = ""
    message_count: int = 0
    tool_counts: Counter = field(default_factory=Counter)
    error_results: int = 0
    error_phrase_hits: int = 0
    tools_with_errors: set = field(default_factory=set)
    topic_counts: Counter = field(default_factory=Counter)
    kickoff: str = ""  # first user-text snippet (bounded)
    # tool_use id → tool name, so an errored tool_result can be tied back to
    # the tool that produced it (precise retry signal when ids are present).
    tool_use_ids: dict = field(default_factory=dict)

    @property
    def retry_suspected(self) -> bool:
        """A session shows a retry pattern if either:
        - PRECISE: a tool that errored (tied via tool_use_id) was used >1×, or
        - COARSE (fallback when ids are absent): there was at least one error
          result AND at least one tool was used more than once.
        """
        precise = any(self.tool_counts.get(t, 0) > 1 for t in self.tools_with_errors)
        coarse = self.error_results > 0 and any(
            c > 1 for c in self.tool_counts.values()
        )
        return precise or coarse


@dataclass
class SummaryDoc:
    """Parsed narrative save-session .tmp file (sparse, user-dependent)."""

    path: str = ""
    project: str = ""
    branch: str = ""
    date: str = ""
    snippet: str = ""


@dataclass
class CollectedData:
    days: int = DEFAULT_DAYS
    project_filter: str | None = None
    claude_dir: str = ""
    transcripts_scanned: int = 0
    summaries_scanned: int = 0
    sessions: list = field(default_factory=list)       # list[SessionFacts]
    summaries: list = field(default_factory=list)       # list[SummaryDoc]

    @property
    def sessions_found(self) -> int:
        return len(self.sessions)


# --------------------------------------------------------------------------
# Path resolution
# --------------------------------------------------------------------------


def resolve_claude_dir(claude_dir_arg: str | None) -> Path:
    """Resolve the ~/.claude base, honoring --claude-dir, then
    $CLAUDE_CONFIG_DIR, then $HOME/.claude."""
    if claude_dir_arg:
        return Path(claude_dir_arg).expanduser()
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".claude"


def decode_project_dir(name: str) -> str:
    """Best-effort decode of an encoded project dir name back to a cwd.

    Claude Code encodes the cwd by replacing path separators with '-', e.g.
    '/home/hsozer/Dev/startup-framework' -> '-home-hsozer-Dev-startup-framework'.
    The mapping is lossy (real '-' in a path is indistinguishable), so this is
    a hint only. We return a best-effort '/'-joined string.
    """
    if not name:
        return ""
    if name.startswith(_PROJECT_DIR_PREFIX):
        return "/" + name[1:].replace("-", "/")
    return name.replace("-", "/")


def _project_basename(cwd_or_dir: str) -> str:
    s = cwd_or_dir.rstrip("/")
    if not s:
        return ""
    return s.rsplit("/", 1)[-1]


def _matches_project(project: str, cwd: str, dir_name: str, needle: str | None) -> bool:
    if not needle:
        return True
    n = needle.lower()
    for hay in (project, cwd, dir_name, decode_project_dir(dir_name)):
        if hay and n in hay.lower():
            return True
    return False


# --------------------------------------------------------------------------
# Source enumeration (mtime filter applied BEFORE opening — cheap stat first)
# --------------------------------------------------------------------------


def _within_window(path: Path, cutoff_ts: float) -> bool:
    try:
        return path.stat().st_mtime >= cutoff_ts
    except OSError:
        return False


def iter_transcript_files(
    claude_dir: Path, cutoff_ts: float, project_filter: str | None
) -> Iterator[tuple[Path, str]]:
    """Yield (jsonl_path, encoded_dir_name) for transcripts within the window.

    Project filtering is applied at the directory level first (cheap), but a
    transcript's true project comes from its records, so a dir that doesn't
    match by name is still scanned only if no filter is set."""
    projects_root = claude_dir / "projects"
    if not projects_root.is_dir():
        return
    try:
        dir_entries = sorted(projects_root.iterdir())
    except OSError:
        return
    for proj_dir in dir_entries:
        if not proj_dir.is_dir():
            continue
        dir_name = proj_dir.name
        # Directory-level pre-filter: if a project filter is set and the dir
        # name can't match, skip the dir entirely (records would re-confirm,
        # but the dir name encodes the cwd so this is a safe cheap cut).
        if project_filter and not _matches_project("", "", dir_name, project_filter):
            continue
        try:
            files = sorted(proj_dir.glob("*.jsonl"))
        except OSError:
            continue
        for f in files:
            if _within_window(f, cutoff_ts):
                yield f, dir_name


def iter_summary_files(claude_dir: Path, cutoff_ts: float) -> Iterator[Path]:
    session_data = claude_dir / "session-data"
    if not session_data.is_dir():
        return
    try:
        files = sorted(session_data.glob("*.tmp"))
    except OSError:
        return
    for f in files:
        if _within_window(f, cutoff_ts):
            yield f


# --------------------------------------------------------------------------
# Transcript parsing (line-by-line, malformed lines skipped)
# --------------------------------------------------------------------------


def _extract_text_blocks(content) -> Iterator[str]:
    """Yield text strings from a message 'content' that may be a str or a
    list of blocks."""
    if isinstance(content, str):
        yield content
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                t = block.get("text")
                if isinstance(t, str):
                    yield t


def _scan_topics(text: str, counter: Counter) -> None:
    """Bounded keyword extraction from a chunk of user/assistant text."""
    if not text:
        return
    chunk = text[:MAX_TOPIC_SCAN_CHARS]
    chunk = _TAG_RE.sub(" ", chunk)  # strip XML-ish CC plumbing
    for m in _WORD_RE.finditer(chunk.lower()):
        w = m.group(0)
        if w in STOPWORDS:
            continue
        counter[w] += 1


def _count_error_phrases(text: str) -> int:
    if not text:
        return 0
    low = text[:MAX_TOPIC_SCAN_CHARS].lower()
    return sum(low.count(p) for p in ERROR_PHRASES)


def summarize_transcript(path: Path) -> SessionFacts | None:
    """Stream a single .jsonl transcript and return its facts.

    Returns None only if the file cannot be opened at all. Malformed JSON
    lines are skipped silently (tolerant parsing)."""
    facts = SessionFacts(session_id=path.stem)
    saw_any = False
    try:
        # errors="replace" so an odd byte never aborts the whole file.
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except (ValueError, TypeError):
                    continue  # malformed line — skip, never fatal
                if not isinstance(rec, dict):
                    continue
                saw_any = True
                _ingest_record(rec, facts)
    except OSError:
        return None
    if not saw_any:
        return None
    # Finalize project/cwd: prefer record-derived cwd basename.
    if facts.cwd and not facts.project:
        facts.project = _project_basename(facts.cwd)
    return facts


def _ingest_record(rec: dict, facts: SessionFacts) -> None:
    """Fold a single transcript record into the running facts."""
    # Metadata (any record type may carry these).
    if not facts.cwd:
        cwd = rec.get("cwd")
        if isinstance(cwd, str) and cwd:
            facts.cwd = cwd
            facts.project = _project_basename(cwd)
    if not facts.branch:
        gb = rec.get("gitBranch")
        if isinstance(gb, str) and gb:
            facts.branch = gb
    sid = rec.get("sessionId")
    if isinstance(sid, str) and sid:
        facts.session_id = sid
    ver = rec.get("version")
    if isinstance(ver, str) and ver:
        facts.versions.add(ver)
    ts = rec.get("timestamp")
    if isinstance(ts, str) and ts:
        if not facts.first_ts:
            facts.first_ts = ts
        facts.last_ts = ts

    rtype = rec.get("type")
    msg = rec.get("message")

    if rtype == "user":
        facts.message_count += 1
        if isinstance(msg, dict):
            for text in _extract_text_blocks(msg.get("content")):
                _scan_topics(text, facts.topic_counts)
                facts.error_phrase_hits += _count_error_phrases(text)
                if not facts.kickoff:
                    cleaned = _TAG_RE.sub(" ", text).strip()
                    if cleaned:
                        facts.kickoff = cleaned[:160]
            _ingest_tool_results(msg.get("content"), facts)

    elif rtype == "assistant":
        facts.message_count += 1
        if isinstance(msg, dict):
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    bt = block.get("type")
                    if bt == "tool_use":
                        name = block.get("name")
                        if isinstance(name, str) and name:
                            facts.tool_counts[name] += 1
                            tid = block.get("id")
                            if isinstance(tid, str) and tid:
                                facts.tool_use_ids[tid] = name
                    elif bt == "text":
                        t = block.get("text")
                        if isinstance(t, str):
                            _scan_topics(t, facts.topic_counts)


def _ingest_tool_results(content, facts: SessionFacts) -> None:
    """Tool results live in user-role messages as tool_result blocks."""
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            continue
        is_err = block.get("is_error")
        if is_err is True:
            facts.error_results += 1
            # Tie the error back to its originating tool when the id is present
            # (precise retry signal); aggregate error_results is the fallback.
            tid = block.get("tool_use_id")
            if isinstance(tid, str) and tid in facts.tool_use_ids:
                facts.tools_with_errors.add(facts.tool_use_ids[tid])
        # Some error results carry a name hint in content text.
        rc = block.get("content")
        if isinstance(rc, str):
            facts.error_phrase_hits += _count_error_phrases(rc)
        elif isinstance(rc, list):
            for sub in rc:
                if isinstance(sub, dict) and sub.get("type") == "text":
                    facts.error_phrase_hits += _count_error_phrases(sub.get("text") or "")


# --------------------------------------------------------------------------
# Narrative .tmp parsing
# --------------------------------------------------------------------------

_PROJECT_LINE_RE = re.compile(r"^\*\*Project:\*\*\s*(.+?)\s*$", re.MULTILINE)
_BRANCH_LINE_RE = re.compile(r"^\*\*Branch:\*\*\s*(.+?)\s*$", re.MULTILINE)
_DATE_LINE_RE = re.compile(r"^\*\*Date:\*\*\s*(.+?)\s*$", re.MULTILINE)


def parse_summary_tmp(path: Path) -> SummaryDoc | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    doc = SummaryDoc(path=str(path))
    m = _PROJECT_LINE_RE.search(text)
    if m:
        doc.project = m.group(1).strip()
    m = _BRANCH_LINE_RE.search(text)
    if m:
        doc.branch = m.group(1).strip()
    m = _DATE_LINE_RE.search(text)
    if m:
        doc.date = m.group(1).strip()
    # Snippet: first non-empty, non-header narrative line(s), bounded.
    snippet_lines: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("**") or s.startswith("---"):
            continue
        if s.startswith("<!--"):
            continue
        snippet_lines.append(_TAG_RE.sub(" ", s).strip())
        if sum(len(x) for x in snippet_lines) >= MAX_SUMMARY_SNIPPET:
            break
    doc.snippet = " ".join(snippet_lines)[:MAX_SUMMARY_SNIPPET]
    return doc


# --------------------------------------------------------------------------
# Collection orchestrator
# --------------------------------------------------------------------------


def collect(
    *,
    days: int = DEFAULT_DAYS,
    project: str | None = None,
    claude_dir: str | None = None,
    now: float | None = None,
) -> CollectedData:
    base = resolve_claude_dir(claude_dir)
    ref_now = now if now is not None else time.time()
    cutoff_ts = ref_now - max(0, days) * SECONDS_PER_DAY

    data = CollectedData(days=days, project_filter=project, claude_dir=str(base))

    for jsonl_path, dir_name in iter_transcript_files(base, cutoff_ts, project):
        data.transcripts_scanned += 1
        facts = summarize_transcript(jsonl_path)
        if facts is None:
            continue
        # Confirm project filter against record-derived project (more accurate
        # than the dir-name pre-filter).
        if not _matches_project(facts.project, facts.cwd, dir_name, project):
            continue
        if not facts.project:
            facts.project = _project_basename(decode_project_dir(dir_name)) or dir_name
        data.sessions.append(facts)

    for tmp_path in iter_summary_files(base, cutoff_ts):
        data.summaries_scanned += 1
        doc = parse_summary_tmp(tmp_path)
        if doc is None:
            continue
        if project and not _matches_project(doc.project, "", "", project):
            continue
        data.summaries.append(doc)

    return data


# --------------------------------------------------------------------------
# Rendering (stdout fact-block — stable contract consumed by synthesis-prompt)
# --------------------------------------------------------------------------


def render(data: CollectedData) -> str:
    lines: list[str] = []
    lines.append(DATA_BLOCK_HEADER)
    lines.append(f"window_days: {data.days}")
    lines.append(f"project_filter: {data.project_filter or '(all projects)'}")
    lines.append(f"claude_dir: {data.claude_dir}")
    lines.append(
        f"sources_scanned: transcripts={data.transcripts_scanned} "
        f"session_summaries={data.summaries_scanned}"
    )
    lines.append(f"sessions_found: {data.sessions_found}")
    lines.append("")

    if data.sessions_found == 0 and not data.summaries:
        lines.append(
            "NOTE: No local sessions found in this window. The window may be "
            "too narrow, the project filter too strict, or this machine has no "
            "recorded history yet. Synthesize the four sections noting the "
            "empty window; do NOT invent activity."
        )
        lines.append("")
        lines.append(DATA_BLOCK_FOOTER)
        return "\n".join(lines)

    # ----- Aggregates -----
    project_counts: Counter = Counter()
    tool_totals: Counter = Counter()
    topic_totals: Counter = Counter()
    versions: set[str] = set()
    total_errors = 0
    total_error_phrases = 0
    sessions_with_retry = 0

    for s in data.sessions:
        project_counts[s.project or "(unknown)"] += 1
        tool_totals.update(s.tool_counts)
        topic_totals.update(s.topic_counts)
        versions |= s.versions
        total_errors += s.error_results
        total_error_phrases += s.error_phrase_hits
        if s.retry_suspected:
            sessions_with_retry += 1

    projects_str = ", ".join(f"{p}={c}" for p, c in project_counts.most_common())
    tools_str = ", ".join(
        f"{t}×{c}" for t, c in tool_totals.most_common(TOP_TOOLS_AGGREGATE)
    )
    topics_str = ", ".join(
        f"{t}({c})" for t, c in topic_totals.most_common(TOP_TOPICS_AGGREGATE)
    )
    lines.append("## AGGREGATE")
    lines.append(f"projects: {projects_str or '(none)'}")
    lines.append(f"top_tools: {tools_str or '(none)'}")
    lines.append(f"top_topics: {topics_str or '(none)'}")
    lines.append(f"cc_versions_seen: {', '.join(sorted(versions)) or '(unknown)'}")
    lines.append(
        f"error_signals: tool_errors={total_errors} "
        f"error_phrase_hits={total_error_phrases} "
        f"sessions_with_retry_pattern={sessions_with_retry}"
    )
    lines.append("")

    # ----- Per-session detail (capped) -----
    lines.append("## SESSIONS")
    shown = data.sessions[:MAX_SESSIONS_LISTED]
    for s in shown:
        sid = (s.session_id or "")[:8]
        tools = ", ".join(
            f"{t}×{c}" for t, c in s.tool_counts.most_common(TOP_TOOLS_PER_SESSION)
        ) or "(none)"
        topics = ", ".join(
            t for t, _ in s.topic_counts.most_common(TOP_TOPICS_PER_SESSION)
        ) or "(none)"
        lines.append(
            f"### session {sid} | project={s.project or '(unknown)'} | "
            f"branch={s.branch or '(none)'}"
        )
        lines.append(f"- messages: {s.message_count}")
        lines.append(f"- window: {s.first_ts or '?'} → {s.last_ts or '?'}")
        lines.append(f"- tools_used: {tools}")
        lines.append(
            f"- error_signals: tool_errors={s.error_results} "
            f"error_phrase_hits={s.error_phrase_hits} "
            f"retry_suspected={'yes' if s.retry_suspected else 'no'}"
        )
        lines.append(f"- topics: {topics}")
        if s.kickoff:
            lines.append(f"- kickoff: {s.kickoff}")
    if len(data.sessions) > MAX_SESSIONS_LISTED:
        lines.append(
            f"... ({len(data.sessions) - MAX_SESSIONS_LISTED} more sessions "
            f"not listed; included in AGGREGATE)"
        )
    lines.append("")

    # ----- Narrative save-session summaries -----
    if data.summaries:
        lines.append("## SESSION_SUMMARIES (narrative save-session .tmp)")
        for d in data.summaries:
            lines.append(
                f"- {d.date or '?'} | project={d.project or '(unknown)'} | "
                f"branch={d.branch or '(none)'}: {d.snippet or '(no narrative)'}"
            )
        lines.append("")

    lines.append(DATA_BLOCK_FOOTER)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="collect.py",
        description="Read-only local-session fact collector for /sf:insights.",
    )
    p.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"look-back window in days (default {DEFAULT_DAYS})",
    )
    p.add_argument(
        "--project",
        type=str,
        default=None,
        help="restrict to sessions whose project matches (case-insensitive substring)",
    )
    p.add_argument(
        "--claude-dir",
        type=str,
        default=None,
        help="override the ~/.claude base (defaults to $CLAUDE_CONFIG_DIR or ~/.claude)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.days < 0:
        parser.error("--days must be >= 0")
    data = collect(days=args.days, project=args.project, claude_dir=args.claude_dir)
    try:
        sys.stdout.write(render(data) + "\n")
        sys.stdout.flush()
    except BrokenPipeError:
        # A downstream consumer (e.g. `| head`) closed the pipe early. This is
        # not an error for a read-only reporter — exit cleanly without a trace.
        try:
            sys.stdout.close()
        except OSError:
            pass
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
