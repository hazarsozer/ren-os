"""Unknown is an outcome — the "I could not look" channel (spec 2026-08-22).

A function that returns `[]` for *nothing found* and `[]` for *I could not
look* has destroyed the difference at the point where it was still known.
When something renders that value to the friend as a finding, the friend is
told the system is healthy on the strength of a check that never ran.

`Unknown` is deliberately NOT a subclass of the types it replaces. A caller
that forgets to handle it raises at first attribute access — loud, and
fixed once. An `Unknown` that quacked like an empty list would recreate the
exact defect this module exists to remove.

Stdlib only; imported by both `lib/` and `skills/`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Unknown:
    """Returned in place of a result when the check could not run.

    Not an error (nothing crashed) and not health (nothing was verified).
    `reason` is shown to the friend verbatim, so write it as a sentence
    fragment naming what could not be reached.
    """

    reason: str


@dataclass(frozen=True)
class Surface:
    """One registered reporting surface.

    `blind_when` documents the condition that makes it blind — read by a
    human, and by the audit test's failure message.
    """

    module: str
    function: str
    blind_when: str


# The closed list. See the spec's §1.5 for why this is not auto-derived:
# a SKILL.md-prose parser was prototyped and scored 4/8 recall, missing
# doctor — the reference implementation — entirely.
#
# Doctor's `check_*` functions are NOT here: `CheckResult.status == "skip"`
# is already this channel, and all 26 checks use it correctly.
REPORTING_SURFACES: tuple[Surface, ...] = (
    Surface(
        module="skills.wiki-health.lib",
        function="sweep",
        blind_when="wiki root is not a directory",
    ),
    Surface(
        module="skills.update.lib",
        function="gc_stale_envs",
        blind_when="plugin cache root unresolvable",
    ),
    Surface(
        module="skills.update.lib",
        function="rerender_all_project_claude_md",
        blind_when="project registry missing or unreadable",
    ),
    Surface(
        module="skills.update.lib",
        function="changelog_digest",
        blind_when="changelog missing or unparseable",
    ),
)
