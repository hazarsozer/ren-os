"""
skills.retrospective library — the G21 minimal retrospective engine + v2.1
D-2 skill-candidate mining (Task 8.3a, RenOS 0.2 Phase 8).

Spec §3.7: "a manually- or routine-triggered pass reading instrumentation +
journal + session history that PROPOSES behavior updates (instruction
tweaks, lessons) as diffs through the §3.1 queue." D-2: "skill-candidate
proposals — repeated tasks mined from session history that aren't skills
yet, proposed as candidates (task, observed frequency, proposed skill shape)
through the same queue." Explicitly NO eval-scored iteration — this is one
deterministic pass, not a tuning loop.

Three functions, each doing exactly one part of gather → analyze → propose:

  - `gather` — read-only: `lib.instrument.collect` metrics, the full
    journal, and BOUNDED session-transcript summaries (last 10 transcripts
    for the current project, per `~/.claude/projects/<encoded-cwd>/*.jsonl`
    — the SAME transcript family Task 3.1's `harvest_session_usage` reads,
    here mined for task-shape phrases instead of token counts. The
    topic-extraction pieces (STOPWORDS, word regex, secret guard) are
    adapted from donor `skills/insights/scripts/collect.py`, deliberately
    skipped in Task 3.1 and picked up here as instructed).
  - `analyze` — three DETERMINISTIC rules over `gather`'s output (no LLM
    call in this function; the SKILL.md layer is where a live session may
    ENRICH a finding with judgment before proposing it):
      1. "lesson" — a page corrected (journaled UPDATE with `supersedes`) at
         least `LESSON_MIN_CORRECTIONS` times.
      2. "instruction-tweak" — at least `INSTRUCTION_TWEAK_MIN_FAIL_CLOSED`
         classifier `fail_closed` events recorded.
      3. "skill-candidate" (D-2) — a task phrase recurring across at least
         `SKILL_CANDIDATE_MIN_SESSIONS` distinct sessions.
  - `propose_all` — queues each finding as a `Proposal(op="ADD", ...,
    producer="retrospective", writer="retrospective")`. Per the v2.2
    two-plane pivot, "lesson" and "instruction-tweak" findings are DATA-plane
    (descriptive: a stable fact worth remembering) — they go through
    `queue.propose_and_apply` and land `applied` immediately, one-step
    revertible. "skill-candidate" (D-2) findings are INSTRUCTION-plane by
    intent, not by page prefix: a skill-candidate is a suggestion that a
    human approves at wrap time (Promotion suggestions), so it always keeps
    the plain `queue.propose` door and stays `pending` regardless of which
    page it targets. `writer="retrospective"` is NOT `"llm-auto"`, so
    `queue.apply`'s auto-quarantine (Task 2.4) does not fire either way.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from lib.instrument import collect
from lib.memory import journal
from lib.memory.queue import Proposal, QueueEntry, propose, propose_and_apply

CLAUDE_CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"
MAX_SESSIONS_SCANNED = 10
MAX_TOPIC_SCAN_CHARS = 4000

LESSON_MIN_CORRECTIONS = 2
INSTRUCTION_TWEAK_MIN_FAIL_CLOSED = 3
SKILL_CANDIDATE_MIN_SESSIONS = 3

# Adapted from donor skills/insights/scripts/collect.py (deliberately skipped
# in Task 3.1; picked up here for the D-2 skill-candidate mining).
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

_TAG_RE = re.compile(r"<[^>]+>")
_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_\-]{2,}")

HARNESS_TURN_MARKERS: tuple[str, ...] = (
    "<command-name>",
    "<command-message>",
    "<local-command-caveat>",
    "<local-command-stdout>",
    "<system-reminder>",
)
"""Substrings that mark a "user" transcript turn as harness-injected
(slash-command invocations, local-command caveats, reminder blocks) rather
than something the friend actually typed. Mining these produced junk
skill-candidates like "resume-session-command" (dogfood finding F5,
2026-07-07); `isMeta: true` turns (expanded command/skill bodies) are the
same class — both are skipped in `_session_task_phrases`."""

_SECRET_TOKEN_MAX_LEN = 30
_SECRET_PREFIXES = ("sk-", "sk_", "ghp_", "gho_", "ghs_", "github_pat_", "xoxb-", "xoxp-")
_AWS_KEY_RE = re.compile(r"^(akia|asia)[a-z0-9]{16}$")


def _looks_like_secret(token: str) -> bool:
    return (
        len(token) > _SECRET_TOKEN_MAX_LEN
        or token.startswith(_SECRET_PREFIXES)
        or bool(_AWS_KEY_RE.match(token))
    )


def _resolve_claude_dir(claude_dir: Path | None = None) -> Path:
    if claude_dir is not None:
        return Path(claude_dir)
    env = os.environ.get(CLAUDE_CONFIG_DIR_ENV, "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / ".claude"


def _encode_project_dir(cwd: str) -> str:
    """Claude Code's cwd→project-dir encoding: replace path separators with
    `-` (e.g. `/home/x/y` → `-home-x-y`). Lossy for real `-` in a path;
    best-effort, same as donor's `decode_project_dir` in reverse."""
    return cwd.replace("/", "-")


def _significant_words(text: str) -> list[str]:
    """Lowercase, tag-stripped, stopword-filtered, secret-guarded word list."""
    chunk = _TAG_RE.sub(" ", text[:MAX_TOPIC_SCAN_CHARS])
    words = []
    for match in _WORD_RE.finditer(chunk.lower()):
        word = match.group(0)
        if word in STOPWORDS or _looks_like_secret(word):
            continue
        words.append(word)
    return words


def _task_phrase(text: str) -> str | None:
    """A crude, deterministic "task shape" key: the first 3 significant
    words of a user turn, joined by `-`. `None` if fewer than 2 significant
    words (too little signal to call it a repeatable task shape)."""
    words = _significant_words(text)
    if len(words) < 2:
        return None
    return "-".join(words[:3])


def _extract_user_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return " ".join(parts)
    return ""


def _session_task_phrases(transcript_path: Path) -> set[str]:
    """One deduped set of task phrases per session — tolerant of malformed
    lines (never raises), mirrors the discovery discipline Task 3.1's
    `harvest_session_usage` already established for this transcript family."""
    phrases: set[str] = set()
    try:
        with transcript_path.open("r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict) or obj.get("type") != "user":
                    continue
                if obj.get("isMeta"):
                    continue
                message = obj.get("message")
                if not isinstance(message, dict):
                    continue
                text = _extract_user_text(message)
                if not text.strip():
                    continue
                if any(marker in text for marker in HARNESS_TURN_MARKERS):
                    continue
                phrase = _task_phrase(text)
                if phrase:
                    phrases.add(phrase)
    except (OSError, UnicodeDecodeError):
        return phrases
    return phrases


def _recent_session_summaries(
    claude_dir: Path | None = None,
    cwd: str | None = None,
    max_sessions: int = MAX_SESSIONS_SCANNED,
) -> list[dict]:
    """Bounded (last `max_sessions`, newest-first by mtime) session
    summaries for the current project: `{"session": <transcript stem>,
    "task_phrases": [...]}`. `[]` if the project's transcript dir doesn't
    exist — never raises."""
    resolved_dir = _resolve_claude_dir(claude_dir)
    resolved_cwd = cwd or os.getcwd()
    project_dir = resolved_dir / "projects" / _encode_project_dir(resolved_cwd)
    if not project_dir.is_dir():
        return []

    try:
        files = sorted(project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []

    summaries = []
    for path in files[:max_sessions]:
        summaries.append({"session": path.stem, "task_phrases": sorted(_session_task_phrases(path))})
    return summaries


def gather(since: str | None = None, *, claude_dir: Path | None = None, cwd: str | None = None) -> dict:
    """Read-only: metrics (optionally since a timestamp), the full journal,
    and bounded session-transcript summaries for the current project."""
    return {
        "metrics": collect.read(since=since),
        "journal": journal.entries(),
        "sessions": _recent_session_summaries(claude_dir=claude_dir, cwd=cwd),
    }


def analyze(gathered: dict) -> list[dict]:
    """Three deterministic candidate-finding rules over `gather`'s output.
    No LLM call here — enrichment/judgment is the SKILL.md layer's job."""
    findings: list[dict] = []

    # 1. lesson: a page corrected (UPDATE + supersedes) >= LESSON_MIN_CORRECTIONS times.
    correction_counts: dict[str, int] = {}
    for entry in gathered.get("journal", []):
        if entry.get("op") == "UPDATE" and entry.get("supersedes"):
            page = entry.get("page")
            if page:
                correction_counts[page] = correction_counts.get(page, 0) + 1
    for page, count in sorted(correction_counts.items()):
        if count >= LESSON_MIN_CORRECTIONS:
            findings.append(
                {
                    "kind": "lesson",
                    "page": page,
                    "count": count,
                    "message": f"{page} keeps being corrected ({count}x) — capture the stable truth",
                }
            )

    # 2. instruction-tweak: >= INSTRUCTION_TWEAK_MIN_FAIL_CLOSED classifier fail_closed events.
    fail_closed = [
        e for e in gathered.get("metrics", [])
        if e.get("kind") == collect.KIND_CLASSIFIER_EVENT and e.get("event") == "fail_closed"
    ]
    if len(fail_closed) >= INSTRUCTION_TWEAK_MIN_FAIL_CLOSED:
        findings.append(
            {
                "kind": "instruction-tweak",
                "count": len(fail_closed),
                "message": "wrap gate failing often — check llm_call wiring",
            }
        )

    # 3. skill-candidate (D-2): a task phrase in >= SKILL_CANDIDATE_MIN_SESSIONS distinct sessions.
    phrase_sessions: dict[str, set[str]] = {}
    for summary in gathered.get("sessions", []):
        session_id = summary.get("session")
        for phrase in summary.get("task_phrases", []):
            phrase_sessions.setdefault(phrase, set()).add(session_id)
    for phrase, sessions in sorted(phrase_sessions.items()):
        if len(sessions) >= SKILL_CANDIDATE_MIN_SESSIONS:
            findings.append(
                {
                    "kind": "skill-candidate",
                    "task": phrase,
                    "frequency": len(sessions),
                    "proposed_shape": f"skill: {phrase}",
                    "proposed_scaffold": _script_scaffold(phrase),
                }
            )

    return findings


def _script_scaffold(phrase: str) -> str:
    """Finalize-v0.2 agenda item 5: a skill-candidate proposes an EXECUTABLE
    starting point, not just an idea — the reviewer approving the finding
    should be able to see exactly what would be built. Pure string assembly
    (deterministic, like everything else in this lib); pairs with 0.3's
    improve-skill loop, which would iterate on the generated skill."""
    slug = _slugify(phrase)
    return f"""\
# proposed layout
skills/{slug}/SKILL.md        # frontmatter: type: skill, execution_tier: <deterministic|worker|judgment>
skills/{slug}/lib/run.py      # the mechanical core — start here

# skills/{slug}/lib/run.py stub
def run(args: list[str]) -> int:
    \"\"\"TODO: the repeated task ('{phrase}') as a deterministic script.
    Return 0 on success; print human-readable progress to stdout.\"\"\"
    raise NotImplementedError
"""


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "finding"


def _slug_for(finding: dict) -> str:
    kind = finding["kind"]
    if kind == "lesson":
        return _slugify(finding["page"].rsplit(".", 1)[0])
    if kind == "instruction-tweak":
        return "wrap-gate-fail-closed"
    if kind == "skill-candidate":
        return _slugify(finding["task"])
    return _slugify(kind)


def _render_finding(finding: dict) -> str:
    lines = ["---", "type: retrospective-finding", f"kind: {finding['kind']}", "---", "", f"# Retrospective finding: {finding['kind']}", ""]
    for key, value in finding.items():
        if key in ("kind", "proposed_scaffold"):
            continue
        lines.append(f"- **{key}**: {value}")
    scaffold = finding.get("proposed_scaffold")
    if scaffold:
        lines += ["", "## Proposed scaffold", "", "```", scaffold.rstrip("\n"), "```"]
    return "\n".join(lines) + "\n"


def propose_all(findings: list[dict], session: str) -> list[QueueEntry]:
    """Queue each finding as an ADD proposal at
    `retrospective/<date>-<kind>-<slug>.md`, `producer="retrospective"`,
    `writer="retrospective"`.

    "lesson"/"instruction-tweak" findings are data-plane (descriptive) —
    they go through `propose_and_apply` and land `applied` immediately. A
    "skill-candidate" finding is an instruction-plane suggestion by intent
    (a human approves it at wrap time, not by page prefix), so it always
    stays on the plain `propose` door and lands `pending`."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entries = []
    for finding in findings:
        page = f"retrospective/{today}-{finding['kind']}-{_slug_for(finding)}.md"
        proposal = Proposal(
            op="ADD",
            page=page,
            content=_render_finding(finding),
            reason=f"retrospective: {finding['kind']}",
            producer="retrospective",
            writer="retrospective",
            session=session,
            salience=False,
        )
        if finding["kind"] == "skill-candidate":
            entry = propose(proposal)
        else:
            entry, _ = propose_and_apply(proposal)
        entries.append(entry)
    return entries


__all__ = [
    "LESSON_MIN_CORRECTIONS",
    "INSTRUCTION_TWEAK_MIN_FAIL_CLOSED",
    "SKILL_CANDIDATE_MIN_SESSIONS",
    "MAX_SESSIONS_SCANNED",
    "gather",
    "analyze",
    "propose_all",
]
