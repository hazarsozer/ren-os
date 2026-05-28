"""
sf-wrap library — internal implementation for the /sf:wrap slash command.

Public entry point: `wrap(inputs: WrapInputs) -> WrapResult`.

The pipeline follows the 7 steps documented in skills/sf-wrap/SKILL.md:

    1. gather inputs (read-only)
    2. classifier — apply signal-threshold (LLM call)
    3. compose diff plan (signal → ADR-014 page mapping)
    4. user approval (TTY UX)
    5. atomic apply with git-restore rollback
    6. compose terse session-end summary + pre-validate
    7. feed.feed_write_entry(kind="end", ...) + handle result

Step 4-5 are interactive; this module exposes the pure logic and delegates
the UX surface to the host (Claude Code's normal user-facing rendering).

V1 status: types + format pre-validator are real; classifier / diff planner /
apply / approval are stubs to be filled in. The structure here is the contract
the rest of the skill develops against.
"""

from __future__ import annotations

# Local types — re-exported as the lib's public surface.
# Relative imports because the directory name `sf-wrap` contains a dash,
# which Python cannot use in absolute import paths.
from .types import (
    CandidateArtifact,
    ClassifierResult,
    DiffEntry,
    DiffKind,
    DiffPlan,
    FormatViolationReport,
    SignalLabel,
    WrapInputs,
    WrapResult,
)

# Validators — used by the pipeline + by host pre-feed-call
from .validate import (
    MAX_FILES_DISPLAYED,
    MAX_SUMMARY_CHARS,
    format_files_touched_for_summary,
    truncate_files_touched,
    validate_summary,
)

__all__ = [
    # types
    "CandidateArtifact",
    "ClassifierResult",
    "DiffEntry",
    "DiffKind",
    "DiffPlan",
    "FormatViolationReport",
    "SignalLabel",
    "WrapInputs",
    "WrapResult",
    # validators
    "MAX_FILES_DISPLAYED",
    "MAX_SUMMARY_CHARS",
    "format_files_touched_for_summary",
    "truncate_files_touched",
    "validate_summary",
    # pipeline entry (stubbed below; filled in subsequent turns)
    "wrap",
]


import time
from pathlib import Path
from typing import Callable

from .apply import ApplyResult, apply_diff_plan
from .classifier import classify as default_classify
from .diff_plan import compose_diff_plan
from .feed_call import FeedCallOutcome, do_feed_write
from .types import ClassifierResult, DiffEntry, DiffPlan


# Injection points (defaults raise NotImplementedError until LLM layer wired)
ClassifyCallable = Callable[[str, "str | None"], ClassifierResult]
ApprovalCallable = Callable[[DiffEntry], bool]
NextPointerComposer = Callable[[WrapInputs, ClassifierResult], str]
SummaryComposer = Callable[[WrapInputs, ClassifierResult], str]


def _default_classifier(transcript: str, project_name: "str | None") -> ClassifierResult:
    """Default delegates to lib.classifier.classify (currently stubbed)."""
    return default_classify(transcript, project_name=project_name)


def _default_approve_all(diff: DiffEntry) -> bool:
    """V1 default: approve every proposed diff. Host UX layer can inject
    an interactive approval callback per SKILL.md step 4."""
    return True


def _default_next_pointer(inputs: WrapInputs, classifier: ClassifierResult) -> str:
    """Compose a one-paragraph next-session pointer from classifier reasoning."""
    project = inputs.active_project or "unscoped"
    reasoning = classifier.reasoning or "Routine work; no signal threshold met."
    return f"Working in {project}. Last session: {reasoning}".strip()


def _default_summary(inputs: WrapInputs, classifier: ClassifierResult) -> str:
    """Compose a one-line summary for log entries."""
    if classifier.has_signal:
        primary = next((l for l in classifier.labels if l != "none"), "signal")
        return f"{primary}: {classifier.reasoning[:120]}".strip()
    return "routine"


def _gather_transcript(inputs: WrapInputs) -> str:
    """
    Read session transcript + any /sf:note pins. Returns combined text.

    Returns empty string if no transcript path is available (allows the
    classifier to still produce a 'none' label).
    """
    parts: list[str] = []
    if inputs.session_transcript_path:
        try:
            parts.append(Path(inputs.session_transcript_path).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            pass
    if inputs.session_notes:
        parts.append("\n\n## Pinned notes from /sf:note\n\n" + "\n\n".join(inputs.session_notes))
    return "\n".join(parts)


def wrap(
    inputs: WrapInputs,
    *,
    wiki_root: Path,
    cwd: Path,
    classifier_fn: ClassifyCallable | None = None,
    approve_fn: ApprovalCallable | None = None,
    pointer_composer: NextPointerComposer | None = None,
    summary_composer: SummaryComposer | None = None,
    feed_write_fn: Callable[..., FeedCallOutcome] | None = None,
) -> WrapResult:
    """
    Execute the /sf:wrap pipeline per SKILL.md §"The 7-step pipeline".

    Composes:
      1. gather session transcript + /sf:note pins
      2. classifier (LLM-dependent, injected — default raises NotImplementedError)
      3. compose_diff_plan (signal label → wiki page edits per ADR-014)
      4. user approval per diff (injected; default approves all — V1)
      5. apply_diff_plan (atomic; rolls back on any failure)
      6. compose summary + do_feed_write (skip-chain + format violation re-prompt)
      7. compose user-facing WrapResult

    Args:
        inputs: Gathered session context.
        wiki_root: Path to the wiki directory.
        cwd: Working directory for git commands.
        classifier_fn: Inject a classifier (default: lib.classifier.classify, stubbed).
        approve_fn: Inject a per-diff approval callback (default: approve all).
        pointer_composer: Inject a next-session-pointer composer (default: derive from classifier).
        summary_composer: Inject a one-line summary composer (default: derive from classifier).
        feed_write_fn: Inject a feed writer (default: lib.feed_call.do_feed_write).

    Returns:
        WrapResult.
    """
    start = time.monotonic()
    classifier_fn = classifier_fn or _default_classifier
    approve_fn = approve_fn or _default_approve_all
    pointer_composer = pointer_composer or _default_next_pointer
    summary_composer = summary_composer or _default_summary
    feed_write_fn = feed_write_fn or do_feed_write

    # --- Step 1: gather ---
    transcript = _gather_transcript(inputs)

    # --- Step 2: classify ---
    try:
        classifier_result = classifier_fn(transcript, inputs.active_project)
    except NotImplementedError:
        # Default classifier stubbed; degrade to 'none' so the rest of the
        # pipeline still runs (CONTEXT.md rewrite + feed entry).
        classifier_result = ClassifierResult(
            labels=("none",),
            reasoning="(classifier not yet wired)",
        )

    # --- Step 3: compose diff plan ---
    next_pointer = pointer_composer(inputs, classifier_result)
    summary_line = summary_composer(inputs, classifier_result)
    plan = compose_diff_plan(
        wiki_root=wiki_root,
        inputs=inputs,
        classifier_result=classifier_result,
        next_session_pointer=next_pointer,
        summary_line=summary_line,
    )

    # --- Step 4: filter by user approval ---
    approved_entries = tuple(e for e in plan.entries if approve_fn(e))
    rejected_paths = tuple(e.target_file for e in plan.entries if e not in approved_entries)
    approved_plan = DiffPlan(
        entries=approved_entries,
        context_md_rewrite=plan.context_md_rewrite,
    )

    # --- Step 5: apply approved diffs ---
    apply_result = apply_diff_plan(approved_plan, wiki_root=wiki_root, cwd=cwd)

    # If apply failed, abort feed write (consistency: wiki failed → no feed entry)
    if not apply_result.success:
        elapsed = time.monotonic() - start
        return WrapResult(
            wiki_pages_changed=(),
            wiki_pages_skipped=rejected_paths,
            feed_write_attempted=False,
            feed_write_success=False,
            feed_write_queued=False,
            feed_write_violation=None,
            feed_write_error=(
                f"wiki apply failed at entry {apply_result.failed_diff_index}: "
                f"{apply_result.failed_diff_reason}; feed deferred"
            ),
            context_md_path=str(wiki_root / "projects" / (inputs.active_project or "") / "CONTEXT.md"),
            next_session_pointer=next_pointer[:100],
            elapsed_seconds=elapsed,
        )

    # --- Step 6: feed write ---
    feed_outcome = feed_write_fn(
        task_brief=summary_line,
        project=inputs.active_project,
        files_touched=list(apply_result.files_changed),
        skip_feed_flag=inputs.skip_feed_flag,
    )

    elapsed = time.monotonic() - start
    return WrapResult(
        wiki_pages_changed=apply_result.files_changed,
        wiki_pages_skipped=rejected_paths,
        feed_write_attempted=not feed_outcome.skipped,
        feed_write_success=feed_outcome.written,
        feed_write_queued=feed_outcome.queued,
        feed_write_violation=feed_outcome.raw_violation,
        feed_write_error=None if feed_outcome.written or feed_outcome.skipped else feed_outcome.user_message,
        context_md_path=str(wiki_root / "projects" / (inputs.active_project or "") / "CONTEXT.md"),
        next_session_pointer=next_pointer[:100],
        elapsed_seconds=elapsed,
    )
