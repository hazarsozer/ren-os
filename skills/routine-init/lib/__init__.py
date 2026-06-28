"""
routine-init library — internal implementation for /ren:routine-init.

Scaffolds a lean per-routine repo (ADR-034 cadence-as-glue) from templates.
Task 3 adds the routine-spec wiki-page write.

Public entry: `routine_init(name, *, dest_dir, wiki_root, trigger_type,
linked_repo, skill, ...) -> RoutineInitResult`.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

FRAMEWORK_VERSION: Final[str] = "0.1.0"
VALID_TRIGGERS: Final[frozenset[str]] = frozenset({"cron", "api", "github"})
VALID_TIERS: Final[frozenset[str]] = frozenset({"trusted", "full", "custom"})
VALID_VERIFICATION_STRATEGIES: Final[frozenset[str]] = frozenset(
    {"visual", "test-run", "lint", "llm-judge", "manual"}
)
SLUG_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

REPO_TEMPLATE_FILES: Final[tuple[str, ...]] = (
    "CLAUDE.md",
    "ROUTINE_PROMPT.md",
    "state.md",
    "run-log.md",
)


@dataclass(frozen=True)
class RoutineInitResult:
    success: bool
    repo_dir: Path | None = None
    spec_page: Path | None = None
    files_written: tuple[Path, ...] = ()
    error: str | None = None


def _render(text: str, placeholders: dict[str, str]) -> str:
    for ph, val in placeholders.items():
        text = text.replace(ph, val)
    return text


def _default_templates_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "templates"


def routine_init(
    name: str,
    *,
    dest_dir: Path,
    wiki_root: Path,
    trigger_type: str,
    linked_repo: str,
    skill: str,
    network_tier: str = "trusted",
    schedule: str = "",
    expected_output: str = "",
    env_secrets_ref: str = "",
    failure_email: str = "",
    verification_strategy: str = "manual",
    verification_tools: tuple[str, ...] = (),
    today: str | None = None,
    templates_dir: Path | None = None,
) -> RoutineInitResult:
    # ── validation ──────────────────────────────────────────────
    if not name or not SLUG_RE.match(name):
        return RoutineInitResult(False, error=f"Invalid routine name {name!r}. Use kebab-case (e.g. daily-digest).")
    if trigger_type not in VALID_TRIGGERS:
        return RoutineInitResult(False, error=f"Invalid trigger_type {trigger_type!r}. One of: {sorted(VALID_TRIGGERS)}.")
    if network_tier not in VALID_TIERS:
        return RoutineInitResult(False, error=f"Invalid network_tier {network_tier!r}. One of: {sorted(VALID_TIERS)}.")
    if not skill or not skill.strip():
        return RoutineInitResult(False, error="A target /ren: skill is required (the skill the routine runs).")
    if verification_strategy not in VALID_VERIFICATION_STRATEGIES:
        return RoutineInitResult(False, error=f"Invalid verification_strategy {verification_strategy!r}. One of: {sorted(VALID_VERIFICATION_STRATEGIES)}.")

    templates_dir = templates_dir or _default_templates_dir()
    repo_tmpl_dir = templates_dir / "repo"

    repo_dir = dest_dir / name
    if repo_dir.exists():
        return RoutineInitResult(False, error=f"Refusing to overwrite existing directory {repo_dir}.")
    spec_page = wiki_root / "routines" / f"{name}.md"
    if spec_page.exists():
        return RoutineInitResult(False, error=f"Refusing to overwrite existing routine-spec page {spec_page}.")

    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Render values for both the repo templates (this task) and the Task-3 wiki template (which reuses this dict).
    placeholders = {
        "{{routine_name}}": name,
        "{{trigger_type}}": trigger_type,
        "{{linked_repo}}": linked_repo,
        "{{network_tier}}": network_tier,
        "{{env_secrets_ref}}": env_secrets_ref or "(none declared)",
        "{{schedule}}": schedule,
        "{{expected_output}}": expected_output or "(describe what this routine produces)",
        "{{failure_handler}}": f"email {failure_email} via Resend MCP" if failure_email else "(set a failure email)",
        "{{failure_email}}": failure_email or "(set --failure-email)",
        "{{skill}}": skill.strip(),
        "{{verification_strategy}}": verification_strategy,
        "{{verification_tools}}": "[" + ", ".join(verification_tools) + "]",
        "{{today}}": today,
        "{{framework_version}}": FRAMEWORK_VERSION,
    }

    written: list[Path] = []

    # ── scaffold the lean repo ──────────────────────────────────
    repo_dir.mkdir(parents=True, exist_ok=False)
    try:
        for fname in REPO_TEMPLATE_FILES:
            src = repo_tmpl_dir / f"{fname}.tmpl"
            out = repo_dir / fname
            out.write_text(_render(src.read_text(encoding="utf-8"), placeholders), encoding="utf-8")
            written.append(out)
    except OSError as exc:
        import shutil
        shutil.rmtree(repo_dir, ignore_errors=True)
        logger.error("routine-init scaffold failed mid-write for %s: %s", name, exc)
        return RoutineInitResult(False, error=f"Scaffold failed mid-write: {exc}")

    # ── write the routine-spec wiki page (the "report home" record) ──
    try:
        wiki_tmpl = templates_dir / "wiki" / "routine-spec.md.tmpl"
        spec_page.parent.mkdir(parents=True, exist_ok=True)
        spec_page.write_text(_render(wiki_tmpl.read_text(encoding="utf-8"), placeholders), encoding="utf-8")
        written.append(spec_page)
    except OSError as exc:
        import shutil
        shutil.rmtree(repo_dir, ignore_errors=True)
        spec_page.unlink(missing_ok=True)
        logger.error("routine-init wiki-page write failed for %s: %s", name, exc)
        return RoutineInitResult(False, error=f"Wiki-page write failed: {exc}")

    return RoutineInitResult(
        success=True,
        repo_dir=repo_dir,
        spec_page=spec_page,
        files_written=tuple(written),
    )


__all__ = [
    "FRAMEWORK_VERSION",
    "VALID_TRIGGERS",
    "VALID_TIERS",
    "VALID_VERIFICATION_STRATEGIES",
    "RoutineInitResult",
    "routine_init",
]
