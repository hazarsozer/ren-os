"""Lifecycle fake — sf-lifecycle's doctor.report() surface as consumed by Stage 6.

Mirrors the proposed shape from plan §5.3 + stage-6-doctor-verification.md.
sf-lifecycle has not yet locked the shape; this fake encodes the *assumed*
shape and test_contract_drift.py is responsible for catching the drift if
lifecycle-2 picks a different one when they ship doctor.report().

TODO(lifecycle-2): replace assumed shape with real once locked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


CheckStatus = Literal["pass", "warn", "fail"]


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: CheckStatus
    detail: str = ""


@dataclass(frozen=True)
class DoctorResult:
    passed: bool
    checks: tuple[DoctorCheck, ...]
    warnings: tuple[str, ...] = ()
    remediation_hints: tuple[str, ...] = ()


def _all_green_checks(plugin_count: int = 6) -> tuple[DoctorCheck, ...]:
    """Sensible default: every standard check passes."""
    checks = [
        DoctorCheck(f"plugin: pin-{i}", "pass") for i in range(plugin_count)
    ]
    checks.extend([
        DoctorCheck("hooks ordering", "pass", "Context Mode → claude-mem → wake-up"),
        DoctorCheck("env: ANTHROPIC_API_KEY", "pass"),
        DoctorCheck("env: UPSTASH_CONTEXT7_API_KEY", "pass"),
        DoctorCheck("wiki: index.md", "pass"),
        DoctorCheck("wiki: log.md", "pass"),
        DoctorCheck("wiki: identity.md", "pass", "schema_version=1"),
        DoctorCheck("feed: status.sh", "pass", "push_ok=true"),
    ])
    return tuple(checks)


class LifecycleFake:
    """Pluggable fake for lifecycle's doctor.report() surface."""

    def __init__(self) -> None:
        self._report: DoctorResult = DoctorResult(
            passed=True,
            checks=_all_green_checks(),
        )
        self.calls: list[tuple] = []

    # ----- contract surface -----

    def doctor_report(self) -> DoctorResult:
        self.calls.append(("doctor_report",))
        return self._report

    # ----- injection helpers -----

    def inject_report(self, report: DoctorResult) -> None:
        self._report = report

    def inject_fail(
        self,
        *,
        failing_check_name: str = "wiki: identity.md",
        detail: str = "schema_version=0 (older than expected 1)",
        remediation: str = "Run /sf:update to migrate.",
    ) -> None:
        checks: list[DoctorCheck] = []
        for c in self._report.checks:
            if c.name == failing_check_name:
                checks.append(DoctorCheck(c.name, "fail", detail))
            else:
                checks.append(c)
        if not any(c.name == failing_check_name for c in self._report.checks):
            checks.append(DoctorCheck(failing_check_name, "fail", detail))
        self._report = DoctorResult(
            passed=False,
            checks=tuple(checks),
            warnings=(),
            remediation_hints=(remediation,),
        )

    def inject_warn(self, warning_text: str) -> None:
        self._report = DoctorResult(
            passed=self._report.passed,
            checks=self._report.checks,
            warnings=self._report.warnings + (warning_text,),
            remediation_hints=self._report.remediation_hints,
        )

    def call_names(self) -> list[str]:
        return [c[0] for c in self.calls]
