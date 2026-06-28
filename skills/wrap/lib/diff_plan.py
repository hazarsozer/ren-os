"""
sf-wrap diff planner — translate classifier signal labels into concrete
wiki-page edits.

Per references/wiki-page-mapping.md: each label maps to a set of files to
touch + the kind of change (create/edit/append) per ADR-014's taxonomy.

Pure-logic layer:
  - Reads the current wiki state (file existence; not contents)
  - Composes proposed unified-diff text for each affected page
  - Returns a DiffPlan that the apply layer applies atomically

No LLM calls here. No I/O beyond filesystem checks. Fully unit-testable.
"""

from __future__ import annotations

import difflib
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from .types import (
    CandidateArtifact,
    ClassifierResult,
    DiffEntry,
    DiffKind,
    DiffPlan,
    SignalLabel,
    WrapInputs,
)


# Always-touched files (regardless of signal label) per references/wiki-page-mapping.md
CONTEXT_FILENAME: Final[str] = "CONTEXT.md"
PROJECT_LOG_FILENAME: Final[str] = "log.md"
MASTER_LOG_FILENAME: Final[str] = "log.md"  # at wiki_root
STATE_FILENAME: Final[str] = "STATE.md"
ROADMAP_FILENAME: Final[str] = "ROADMAP.md"
REQUIREMENTS_FILENAME: Final[str] = "REQUIREMENTS.md"
PROJECT_FILENAME: Final[str] = "PROJECT.md"


# Per ADR-014 mapping table (see references/wiki-page-mapping.md):
# signal label → which files to touch
_LABEL_TARGETS: Final[dict[SignalLabel, frozenset[str]]] = {
    "none": frozenset(),  # CONTEXT.md + project log always; nothing else for none
    "decision": frozenset({"decisions", STATE_FILENAME, "index.md"}),
    "pattern": frozenset({"patterns", STATE_FILENAME, "index.md"}),
    "lesson": frozenset({STATE_FILENAME}),
    "stack_change": frozenset({STATE_FILENAME, REQUIREMENTS_FILENAME, ROADMAP_FILENAME}),
    "milestone": frozenset({ROADMAP_FILENAME, STATE_FILENAME}),
    "purpose_shift": frozenset({PROJECT_FILENAME, REQUIREMENTS_FILENAME, ROADMAP_FILENAME}),
}


def _framework_version() -> str:
    """Resolve framework version from the repo-root lib/sf_paths.py.

    Loaded by file path (not `import lib.sf_paths`) to avoid the name collision
    with this skill's own `lib/` package under the per-module test harness.
    Falls back to "0.1.0" if unreachable so frontmatter is never broken.
    """
    import importlib.util
    from pathlib import Path as _P
    try:
        root = _P(__file__).resolve().parents[3]
        spec = importlib.util.spec_from_file_location("_sf_paths_repo", root / "lib" / "sf_paths.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.framework_version()
    except Exception:
        return "0.1.0"  # mirrors lib/sf_paths.py FALLBACK_FRAMEWORK_VERSION — keep in sync


def _today_iso() -> str:
    """Return today's date in ISO-8601 YYYY-MM-DD UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now_log_prefix() -> str:
    """Return the log-entry prefix `## [YYYY-MM-DD HH:MM]` in UTC."""
    return datetime.now(timezone.utc).strftime("## [%Y-%m-%d %H:%M]")


def _read_or_empty(path: Path) -> str:
    """Read file or return empty string if missing/unreadable."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _slugify(title: str) -> str:
    """Convert a free-form title to a kebab-case slug for filenames."""
    import re
    slug = title.strip().lower()
    slug = re.sub(r"[^a-z0-9-]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "untitled"


def _frontmatter_for(page_type: str, title: str, today: str) -> str:
    """Compose the canonical YAML frontmatter triple for a new wiki page."""
    return (
        "---\n"
        f'title: "{title}"\n'
        f"type: {page_type}\n"
        f"schema_version: 1\n"
        f'framework_version: "{_framework_version()}"\n'
        f"date: {today}\n"
        f"status: accepted\n"
        "---\n\n"
    )


# ---------------------------------------------------------------------------
# Composition layer
# ---------------------------------------------------------------------------


def _project_root_for(wiki_root: Path, project_name: str | None) -> Path | None:
    """Return wiki_root/projects/<name>/ or None for unscoped."""
    if project_name is None:
        return None
    return wiki_root / "projects" / project_name


def _relpath_for_diff(absolute_path: Path, wiki_root: Path) -> str:
    """
    Compose the path used inside unified-diff headers (and as DiffEntry.target_file).

    Per ADR-026, the wiki IS its own git repo — so paths inside the diff must
    be relative to the wiki_root (which equals the repo root for git apply
    operations). This helper resolves an absolute path against wiki_root and
    returns the relative form. If absolute_path isn't under wiki_root, returns
    the absolute string (caller's git apply will fail loudly, which is the
    right outcome — a sign of misconfiguration).
    """
    try:
        return absolute_path.relative_to(wiki_root).as_posix()
    except ValueError:
        return str(absolute_path)


def _context_md_diff(
    wiki_root: Path,
    project_name: str | None,
    new_context_text: str,
) -> DiffEntry | None:
    """Build the always-rewrite CONTEXT.md diff. Returns None if unscoped."""
    project_root = _project_root_for(wiki_root, project_name)
    if project_root is None:
        return None
    target = project_root / CONTEXT_FILENAME
    rel_target = _relpath_for_diff(target, wiki_root)
    existing = _read_or_empty(target)

    today = _today_iso()
    new_content = (
        _frontmatter_for("project-context", f"Current focus — {project_name}", today)
        + new_context_text.strip() + "\n"
    )

    if existing:
        # Rewrite: full replacement diff
        existing_lines = existing.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff = "".join(
            difflib.unified_diff(
                existing_lines, new_lines,
                fromfile=f"a/{rel_target}", tofile=f"b/{rel_target}", n=3,
            )
        )
        return DiffEntry(
            target_file=rel_target,
            kind=DiffKind.EDIT,
            unified_diff=diff,
            rationale="CONTEXT.md is the next session's wake-up pointer; always refreshed.",
        )
    else:
        # Build CREATE diff with relative path in headers
        body_lines = new_content.splitlines(keepends=True)
        if body_lines and not body_lines[-1].endswith("\n"):
            body_lines[-1] = body_lines[-1] + "\n"
        diff_lines = [
            f"diff --git a/{rel_target} b/{rel_target}\n",
            "new file mode 100644\n",
            "--- /dev/null\n",
            f"+++ b/{rel_target}\n",
            f"@@ -0,0 +1,{len(body_lines)} @@\n",
        ]
        diff_lines.extend("+" + line for line in body_lines)
        return DiffEntry(
            target_file=rel_target,
            kind=DiffKind.CREATE,
            unified_diff="".join(diff_lines),
            rationale="CONTEXT.md doesn't exist yet; create with current session pointer.",
        )


def _log_append_diff(
    log_path: Path,
    label: SignalLabel,
    summary_line: str,
    *,
    wiki_root: Path,
) -> DiffEntry:
    """Build a one-line append diff for a log.md file (paths relative to wiki_root)."""
    rel_path = _relpath_for_diff(log_path, wiki_root)
    existing = _read_or_empty(log_path)
    line = f"{_now_log_prefix()} {label} | {summary_line.strip()}\n"

    if existing:
        existing_lines = existing.splitlines(keepends=True)
        if existing_lines and not existing_lines[-1].endswith("\n"):
            existing_lines[-1] = existing_lines[-1] + "\n"
        new_lines = existing_lines + [line]
        diff = "".join(
            difflib.unified_diff(
                existing_lines, new_lines,
                fromfile=f"a/{rel_path}", tofile=f"b/{rel_path}", n=3,
            )
        )
        return DiffEntry(
            target_file=rel_path,
            kind=DiffKind.APPEND,
            unified_diff=diff,
            rationale=f"Append chronological log entry for label={label}",
        )
    else:
        # Log file didn't exist — create with header + entry
        body = "# Log\n\n" + line
        body_lines = body.splitlines(keepends=True)
        if body_lines and not body_lines[-1].endswith("\n"):
            body_lines[-1] = body_lines[-1] + "\n"
        diff_lines = [
            f"diff --git a/{rel_path} b/{rel_path}\n",
            "new file mode 100644\n",
            "--- /dev/null\n",
            f"+++ b/{rel_path}\n",
            f"@@ -0,0 +1,{len(body_lines)} @@\n",
        ]
        diff_lines.extend("+" + l for l in body_lines)
        return DiffEntry(
            target_file=rel_path,
            kind=DiffKind.CREATE,
            unified_diff="".join(diff_lines),
            rationale="log.md doesn't exist; create with header + first entry.",
        )


def _decision_or_pattern_create_diff(
    wiki_root: Path,
    project_name: str | None,
    artifact: CandidateArtifact,
) -> DiffEntry | None:
    """
    Compose a CREATE diff for a new decisions/<slug>.md or patterns/<slug>.md
    file under the active project (or under master wiki for cross-project).

    Returns None if there's no sensible target location (e.g., decision-type
    artifact with no active project AND no master decisions/ dir).
    """
    if artifact.label not in ("decision", "pattern"):
        return None

    kind_dir = "decisions" if artifact.label == "decision" else "patterns"
    project_root = _project_root_for(wiki_root, project_name)

    if project_root is not None:
        target_dir = project_root / kind_dir
    else:
        # Cross-project: write to master wiki
        target_dir = wiki_root / kind_dir

    slug = _slugify(artifact.proposed_title)
    target = target_dir / f"{slug}.md"
    rel_target = _relpath_for_diff(target, wiki_root)

    today = _today_iso()
    page_type = "decision" if artifact.label == "decision" else "pattern"
    content = (
        _frontmatter_for(page_type, artifact.proposed_title, today)
        + f"# {artifact.proposed_title}\n\n"
        + artifact.proposed_summary.strip() + "\n"
    )

    # Build CREATE diff with relative path
    body_lines = content.splitlines(keepends=True)
    if body_lines and not body_lines[-1].endswith("\n"):
        body_lines[-1] = body_lines[-1] + "\n"
    diff_lines = [
        f"diff --git a/{rel_target} b/{rel_target}\n",
        "new file mode 100644\n",
        "--- /dev/null\n",
        f"+++ b/{rel_target}\n",
        f"@@ -0,0 +1,{len(body_lines)} @@\n",
    ]
    diff_lines.extend("+" + l for l in body_lines)

    return DiffEntry(
        target_file=rel_target,
        kind=DiffKind.CREATE,
        unified_diff="".join(diff_lines),
        rationale=f"New {artifact.label} page from session signal.",
    )


def compose_diff_plan(
    *,
    wiki_root: Path,
    inputs: WrapInputs,
    classifier_result: ClassifierResult,
    next_session_pointer: str,
    summary_line: str,
) -> DiffPlan:
    """
    Compose the full DiffPlan for a /ren:wrap invocation.

    Per references/wiki-page-mapping.md:
      - CONTEXT.md always rewritten (if active project)
      - Project log.md always appended (one line)
      - Master log.md appended ONLY if any non-`none` label fires
      - Per-label new pages (decisions/, patterns/) created as needed
      - STATE.md / ROADMAP.md / REQUIREMENTS.md / PROJECT.md edits are SCAFFOLDED
        in this function (placeholder appends pointing at the candidate artifact's
        title); deeper STATE.md section updates are deferred to v2 once we have
        section-aware editing primitives.

    Args:
        wiki_root: Path to the wiki root.
        inputs: The gathered WrapInputs (cwd, active project, etc.).
        classifier_result: Output of the classifier.
        next_session_pointer: The new CONTEXT.md body text.
        summary_line: Short one-line summary for log entries.

    Returns:
        DiffPlan with all entries to apply atomically. May be empty (except
        for CONTEXT.md if project-scoped) when label == ['none'].
    """
    entries: list[DiffEntry] = []

    # Always: rewrite CONTEXT.md (if project-scoped)
    ctx_diff = _context_md_diff(wiki_root, inputs.active_project, next_session_pointer)
    if ctx_diff:
        entries.append(ctx_diff)

    # Always: project log.md append (if project-scoped)
    project_root = _project_root_for(wiki_root, inputs.active_project)
    if project_root is not None:
        entries.append(
            _log_append_diff(
                project_root / PROJECT_LOG_FILENAME,
                _primary_label(classifier_result.labels),
                summary_line,
                wiki_root=wiki_root,
            )
        )

    # Master log: append ONLY if any non-`none` label fired
    if classifier_result.has_signal:
        entries.append(
            _log_append_diff(
                wiki_root / MASTER_LOG_FILENAME,
                _primary_label(classifier_result.labels),
                summary_line,
                wiki_root=wiki_root,
            )
        )

    # Per-label artifact creation (decisions, patterns)
    for artifact in classifier_result.candidate_artifacts:
        if artifact.label in ("decision", "pattern"):
            diff = _decision_or_pattern_create_diff(wiki_root, inputs.active_project, artifact)
            if diff is not None:
                entries.append(diff)

    return DiffPlan(
        entries=tuple(entries),
        context_md_rewrite=next_session_pointer,
    )


def _primary_label(labels: tuple[SignalLabel, ...]) -> SignalLabel:
    """Pick the highest-priority label from a multi-label set for log entries."""
    # Priority order per ADR-014 (highest first)
    priority = [
        "purpose_shift",
        "decision",
        "stack_change",
        "milestone",
        "pattern",
        "lesson",
        "none",
    ]
    for p in priority:
        if p in labels:
            return p  # type: ignore[return-value]
    return "none"


__all__ = [
    "compose_diff_plan",
    "_LABEL_TARGETS",
]
