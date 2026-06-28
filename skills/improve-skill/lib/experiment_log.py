"""
sf-improve-skill experiment-log writer (B1, ADR-037/012).

Turns a finished Karpathy-loop `history` into an append-only, project-scoped
ledger at `wiki/projects/<name>/experiment-log.md` — the persistent record of
which improvement experiments ran and what they scored (the supervised-run audit
trail ADR-036 wants). Pure builders + a small append primitive; the SKILL.md
close-out resolves the wiki_root + active project and calls these. No change to
the orchestrator.
"""

from __future__ import annotations

from pathlib import Path

from .types import ExperimentEntry, IterationOutcome, IterationStatus

_FRONTMATTER = "---\ntype: experiment-log\nschema_version: 1\nscope: project\n---\n"


def build_experiment_entries(
    history: tuple[IterationOutcome, ...], *, ts: str
) -> tuple[ExperimentEntry, ...]:
    """
    Map a loop `history` to experiment-log entries (the forward-declared shape).

    `disposition` collapses the loop's status to the page-type's binary: a
    REVERTED iteration is `"reverted"`, anything kept (IMPROVED / NEUTRAL) is
    `"kept"`. `change` is the proposed change's one-line summary. `ts` (the run
    date) is stamped on every entry — `IterationOutcome` carries no per-iteration
    time, and a run happens at one moment.
    """
    return tuple(
        ExperimentEntry(
            iteration=o.iteration,
            change=o.proposed_change.summary,
            score_before=o.score_before,
            score_after=o.score_after,
            disposition="reverted" if o.status is IterationStatus.REVERTED else "kept",
            ts=ts,
        )
        for o in history
    )


def render_run_section(
    entries: tuple[ExperimentEntry, ...],
    *,
    skill_name: str,
    baseline: float,
    final: float,
    disposition: str,
    ts: str,
) -> str:
    """Render one dated run section: a header line + one bullet per entry. Pure."""
    header = f"## {ts} — improve({skill_name}): {baseline:.0%} → {final:.0%} ({disposition})"
    if not entries:
        return f"{header}\n\n_(no iterations)_\n"
    bullets = "\n".join(
        f"- iter {e.iteration} — [{e.disposition}] "
        f"{e.score_before:.3f} → {e.score_after:.3f} — {e.change}"
        for e in entries
    )
    return f"{header}\n\n{bullets}\n"


def append_experiment_log(path: Path | str, section: str, *, project: str | None = None) -> Path:
    """
    Append `section` to the experiment-log at `path`, creating it (with
    `type: experiment-log` frontmatter + a title) on first write. Append-only:
    re-runs add new sections in chronological order; the frontmatter is written
    once. Returns the path written.
    """
    path = Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        title = f"# Experiment Log — {project}" if project else "# Experiment Log"
        path.write_text(
            f"{_FRONTMATTER}\n{title}\n\n"
            "Append-only record of `/ren:improve-skill` runs (ADR-012/036). One section per run.\n",
            encoding="utf-8",
        )
    existing = path.read_text(encoding="utf-8")
    path.write_text(existing.rstrip("\n") + "\n\n" + section.rstrip("\n") + "\n", encoding="utf-8")
    return path


__all__ = ["build_experiment_entries", "render_run_section", "append_experiment_log"]
