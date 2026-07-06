"""
skills.routine-init library — routine-spec v3 schema validation + allowlist
enforcement (Task 6.3, RenOS 0.2 Phase 6).

Spec §3.5: "pre-declared routines/loops: schedule, exit criterion, failure
handler, AND a per-routine capability/path allowlist — declaration must bound
WHAT IT MAY TOUCH, not just when it runs." This module is where that
declaration is checked, at two points:

  - `validate_routine_spec` — declaration time. A routine-spec dict (parsed
    frontmatter) must carry a non-empty `allowlist` (paths that never touch
    `global/`), a valid `failure_handler` (`"notify-journal"`, the only value
    0.2 implements), and a non-empty `exit_criterion`. `migrated=True` relaxes
    the non-empty-paths requirement to a warning (see
    `migrations/routine-spec-2-to-3/README.md` — a migrated spec may
    legitimately have nothing declared yet).
  - `check_proposal_against_allowlist` — runtime, called by a routine before
    `lib.memory.queue.propose`: does THIS specific proposal's target page
    actually fall within what the spec declared? Schema validation forbids
    `global/**` at declaration time; this function independently refuses any
    match against a `global/` page regardless of what the allowlist says
    (defense-in-depth — `lib.governance.tiers.tier_of` also refuses to
    `auto`-apply a routine write to `global/`, at the Task 6.1 apply-time
    layer; this is the earlier, declaration-adjacent layer).

Scope note: donor's `skills/routine-init/lib/__init__.py` scaffolds an entire
lean per-routine repo (CLAUDE.md, ROUTINE_PROMPT.md, state.md, run-log.md) from
templates — that repo-scaffolding machinery is NOT carried here. Task 6.3's
brief and required tests are specifically about the v3 schema fields and
allowlist enforcement; the full `routine_init()` scaffold function is a
separate, larger surface (ADR-034 cadence-as-glue) not exercised by anything
in this task's test list, so re-porting it would be scope creep against what's
actually tested. See the implementation report for this explicit call.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = 3

VALID_FAILURE_HANDLERS: tuple[str, ...] = ("notify-journal",)
"""The only failure_handler value 0.2 implements (spec §3.5: "failure =
notify + journal"). A tuple (not a bare constant) so a future schema version
can add values without changing this module's shape."""

GLOBAL_PREFIX = "global/"


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _touches_global(path: str) -> bool:
    return path == "global" or path.startswith(GLOBAL_PREFIX)


def validate_routine_spec(spec: dict[str, Any], *, migrated: bool = False) -> ValidationResult:
    """Validate a routine-spec dict (parsed frontmatter) against the v3 schema.

    `migrated=True` (used by the 2-to-3 migration's own validation pass, and
    by `/ren:doctor` auditing an already-migrated spec) downgrades an empty
    `allowlist.paths` from an error to a warning — a migrated spec may
    legitimately declare nothing yet. `migrated=False` (the default; a NEW
    spec authored via `/ren:routine-init`) requires non-empty paths: a
    routine that may touch anything is invalid by schema at declaration time.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if spec.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}, got {spec.get('schema_version')!r}")

    allowlist = spec.get("allowlist")
    if not isinstance(allowlist, dict):
        errors.append("allowlist is required and must be a mapping with 'paths' and 'capabilities'")
    else:
        paths = allowlist.get("paths")
        if not isinstance(paths, list):
            errors.append("allowlist.paths is required and must be a list")
        else:
            if not paths:
                if migrated:
                    warnings.append(
                        "allowlist.paths is empty — this routine can propose nothing until filled in"
                    )
                else:
                    errors.append("allowlist.paths must be non-empty for a new routine spec")
            for p in paths:
                if not isinstance(p, str) or _touches_global(p):
                    errors.append(
                        f"allowlist.paths entry {p!r} touches global/ — routines can never write global"
                    )

        capabilities = allowlist.get("capabilities")
        if not isinstance(capabilities, list):
            errors.append("allowlist.capabilities is required and must be a list")

    failure_handler = spec.get("failure_handler")
    if failure_handler not in VALID_FAILURE_HANDLERS:
        errors.append(
            f"failure_handler must be one of {VALID_FAILURE_HANDLERS}, got {failure_handler!r}"
        )

    exit_criterion = spec.get("exit_criterion")
    if not isinstance(exit_criterion, str) or not exit_criterion.strip():
        errors.append("exit_criterion is required and must be a non-empty string")

    return ValidationResult(valid=not errors, errors=errors, warnings=warnings)


def check_proposal_against_allowlist(routine_spec: dict[str, Any], proposal: Any) -> bool:
    """True iff `proposal`'s target page matches at least one glob in
    `routine_spec`'s `allowlist.paths` (fnmatch, wiki-relative) — AND the page
    doesn't touch `global/` regardless of what the allowlist says (see module
    docstring's defense-in-depth note).

    `proposal` may be a `lib.memory.queue.Proposal` (has a `.page` attribute)
    or a plain dict with a `"page"` key — both are accepted so this can be
    called before or after a `Proposal` object is actually constructed.
    """
    page = getattr(proposal, "page", None)
    if page is None and isinstance(proposal, dict):
        page = proposal.get("page")
    if not page:
        return False
    if _touches_global(page):
        return False

    allowlist = routine_spec.get("allowlist") or {}
    paths = allowlist.get("paths") or []
    return any(fnmatch.fnmatch(page, pattern) for pattern in paths)


__all__ = [
    "SCHEMA_VERSION",
    "VALID_FAILURE_HANDLERS",
    "GLOBAL_PREFIX",
    "ValidationResult",
    "validate_routine_spec",
    "check_proposal_against_allowlist",
]
