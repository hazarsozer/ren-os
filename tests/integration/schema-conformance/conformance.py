#!/usr/bin/env python3
"""
schema-conformance — load-bearing drift-catcher.

Walks the repo for files that claim a registered page-type in their YAML
frontmatter, then asserts they conform to the registry. Files without `type:`
are treated as free-form and reported informationally (NOT as failures) per
ADR-027's opt-in semantics.

Owned by sf-distribution. Catches:
- Templates claiming a `type:` not in schemas.json (typo or rename drift)
- Templates with schema_version > registry.current (forward drift)
- Templates with schema_version < supported_from (deprecated)
- Templates missing required frontmatter fields

Runs as a standalone script (`uv run` or `python3 conformance.py`) and also
under pytest. CI invokes it via `tests/integration/schema-conformance/`.

Exit codes:
  0 — all files conform OR are documented free-form
  1 — at least one file violates the contract
  2 — bad inputs (registry missing, malformed)
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]  # tests/integration/schema-conformance/ → repo root
SCHEMAS_JSON = REPO_ROOT / "skills" / "wiki-migration" / "schemas.json"

# framework_version must be a strict semver string (per schemas.schema.json's regex for the
# registry-level framework_version field). Page-level enforcement added 2026-05-28 per
# lifecycle-2 coord — catches values that would silently break the migration consumer
# (e.g., YAML parses `1.0.0` as float in some configs; an unquoted `1.0` becomes float 1.0;
# integers like `1` are not valid framework versions).
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.]+)?(\+[A-Za-z0-9.]+)?$")

# ──────────────────────────────────────────────────────────────────────
# Required-fields-per-type contract.
#
# This dict defines the MINIMUM frontmatter keys each registered page-type
# must declare. It is the conformance contract — peers' templates must satisfy
# it for v1. New page-types should add an entry here in the same PR that adds
# them to schemas.json (a v1.1 unification will move this into the registry).
# ──────────────────────────────────────────────────────────────────────
REQUIRED_FIELDS_BY_TYPE: dict[str, set[str]] = {
    # Universal triple — ADR-027's contract
    "_universal": {"type", "schema_version", "framework_version"},

    # Per-type additions (on top of universal)
    "identity": {"handle", "name", "phase"},
    "master-index": set(),
    "project-main": {"project_name"},
    "project-state": {"project_name"},
    "project-roadmap": {"project_name"},
    "project-requirements": {"project_name"},
    "project-context": {"project_name"},
    "project-index": {"project_name"},
    "research": set(),  # ingest pages have ad-hoc titles; only universal triple required
    "decision": set(),  # friend-authored ADRs; only universal required
    "pattern": set(),
    "log-entry": set(),
    "project-log-entry": set(),
    "skill": {"name", "description"},  # per ADR-011 SKILL.md frontmatter convention
    "licenses": set(),
    # C4 cadence (ADR-034): documents one live routine; surfaced by wake-up + doctor.
    "routine-spec": {"name", "trigger_type", "linked_repo", "network_tier"},
}

# ──────────────────────────────────────────────────────────────────────
# Where to look. Each tuple = (description, glob from repo root, mode).
# Mode is "strict" (must conform if type is claimed) or "informational" (report
# state but don't fail the harness).
# ──────────────────────────────────────────────────────────────────────
SCAN_TARGETS = [
    ("wiki-skeleton templates", "wiki-skeleton/templates/**/*.md.tmpl", "strict"),
    ("bootstrap-project templates", "skills/bootstrap-project/templates/**/*.md.tmpl", "strict"),
    ("routine-init wiki templates", "skills/routine-init/templates/wiki/**/*.md.tmpl", "strict"),
    # Framework-shipped SKILL.md files — declared `type: skill` get strict-scanned (per lifecycle-2
    # coord 2026-05-28). Files without `type:` declared are treated as free-form per ADR-027 opt-in
    # semantics; no failure penalty for not opting in.
    ("Framework-shipped SKILL.md", "skills/*/SKILL.md", "strict"),
    ("Framework dev wiki — research", "wiki/research/*.md", "informational"),
    ("Framework dev wiki — ADRs", "wiki/decisions/*.md", "informational"),
    ("Framework dev wiki — patterns", "wiki/patterns/*.md", "informational"),
    ("Framework dev wiki — top-level", "wiki/*.md", "informational"),
    ("Migration template", "skills/wiki-migration/migrations/_template/*.md", "informational"),
]

# Template placeholders we render with synthetic values so YAML parses cleanly.
TEMPLATE_PLACEHOLDERS = {
    "{{name}}": "Test User",
    "{{handle}}": "test-user",
    "{{today}}": "2026-05-28",
    "{{framework_version}}": "1.0.0",
    "{{project_name}}": "demo-project",
    "{{project_title}}": "Demo Project",
    # routine-spec v2 (C2/ADR-034) writes these bare (unquoted) to match migrate.sh's
    # output, so the synthetic values must themselves be valid YAML — a plain scalar for
    # the strategy enum and a sequence literal for the tools list.
    "{{verification_strategy}}": "manual",
    "{{verification_tools}}": "[]",
}


@dataclass
class CheckResult:
    path: str
    target_desc: str
    mode: str  # "strict" or "informational"
    status: str  # "pass" / "fail" / "skip" / "free-form"
    detail: str = ""
    type_claimed: str | None = None
    schema_version: int | None = None


@dataclass
class HarnessReport:
    by_status: dict[str, list[CheckResult]] = field(default_factory=lambda: {
        "pass": [], "fail": [], "skip": [], "free-form": []
    })
    type_coverage: dict[str, list[str]] = field(default_factory=dict)  # type → files

    def add(self, r: CheckResult) -> None:
        self.by_status[r.status].append(r)
        if r.type_claimed:
            self.type_coverage.setdefault(r.type_claimed, []).append(r.path)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def load_registry() -> dict:
    if not SCHEMAS_JSON.exists():
        raise SystemExit(f"FATAL: schemas.json not found at {SCHEMAS_JSON}")
    with open(SCHEMAS_JSON) as f:
        return json.load(f)


def render_placeholders(text: str) -> str:
    """Replace {{name}}, {{handle}}, etc. with synthetic values so YAML parses."""
    for ph, val in TEMPLATE_PLACEHOLDERS.items():
        text = text.replace(ph, val)
    return text


def parse_frontmatter(content: str) -> dict | None:
    """Return parsed YAML frontmatter as a dict, or None if not present/parse failure."""
    m = FRONTMATTER_RE.match(content)
    if not m:
        return None
    try:
        import yaml  # lazy import; harness runs under both pytest and direct invocation
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"YAML parse error: {e}") from e


def check_file(path: Path, target_desc: str, mode: str, registry: dict) -> CheckResult:
    """Apply the conformance contract to a single file."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        return CheckResult(str(path), target_desc, mode, "fail", f"read error: {e}")

    # Render template placeholders for .tmpl files
    if path.suffix == ".tmpl" or path.name.endswith(".md.tmpl"):
        raw = render_placeholders(raw)

    try:
        fm = parse_frontmatter(raw)
    except ValueError as e:
        return CheckResult(str(path), target_desc, mode, "fail", str(e))

    if fm is None:
        return CheckResult(str(path), target_desc, mode, "skip", "no YAML frontmatter")

    type_claimed = fm.get("type")

    # Files without `type:` are free-form. Per ADR-027's opt-in semantics, that's
    # legitimate — only files claiming a registered type are constrained.
    if not type_claimed:
        return CheckResult(str(path), target_desc, mode, "free-form", "no `type:` field", None, fm.get("schema_version"))

    page_types = registry["page_types"]
    if type_claimed not in page_types:
        return CheckResult(
            str(path), target_desc, mode, "fail",
            f"claims type='{type_claimed}' but no such page-type in registry. "
            f"Registered types: {sorted(page_types.keys())}",
            type_claimed=type_claimed,
        )

    meta = page_types[type_claimed]
    current = meta["current"]
    supported_from = meta["supported_from"]

    schema_version = fm.get("schema_version")
    sv_int: int | None = None
    if schema_version is None:
        # Per ADR-027 § Pages without schema_version: assume 1. But for templates we want explicit.
        return CheckResult(
            str(path), target_desc, mode, "fail",
            f"claims type='{type_claimed}' but missing schema_version field. "
            f"All typed pages MUST declare schema_version (per ADR-027).",
            type_claimed, None,
        )
    try:
        sv_int = int(schema_version)
    except (TypeError, ValueError):
        return CheckResult(
            str(path), target_desc, mode, "fail",
            f"schema_version='{schema_version}' is not an integer",
            type_claimed, None,
        )

    if sv_int < supported_from:
        return CheckResult(
            str(path), target_desc, mode, "fail",
            f"schema_version={sv_int} is below supported_from={supported_from} (deprecated, beyond N+3 window)",
            type_claimed, sv_int,
        )
    if sv_int > current:
        return CheckResult(
            str(path), target_desc, mode, "fail",
            f"schema_version={sv_int} is ahead of registry.current={current} (forward drift; this template ships a future schema)",
            type_claimed, sv_int,
        )

    # Required-fields check
    required = REQUIRED_FIELDS_BY_TYPE.get("_universal", set()) | REQUIRED_FIELDS_BY_TYPE.get(type_claimed, set())
    missing = sorted(required - set(fm.keys()))
    if missing:
        return CheckResult(
            str(path), target_desc, mode, "fail",
            f"missing required field(s): {missing}",
            type_claimed, sv_int,
        )

    # framework_version strict-semver check (page level). Per lifecycle-2 coord 2026-05-28:
    # the consumer side of framework_version (sf-update's migration driver, /ren:wrap's
    # consolidate) expects a valid semver string. A malformed value here would manifest
    # as a silent skip-bug downstream. Catch at write time.
    fv_raw = fm.get("framework_version", "")
    if fv_raw == "" or fv_raw is None:
        # framework_version is in the universal-required set; the missing-fields check above
        # already failed if it wasn't present. So this branch is unreachable for compliant
        # callers — defensive only.
        pass
    else:
        fv_str = str(fv_raw)
        if not SEMVER_RE.match(fv_str):
            return CheckResult(
                str(path), target_desc, mode, "fail",
                f"framework_version={fv_raw!r} is not valid semver (regex: ^MAJOR.MINOR.PATCH[-pre][+build]$). "
                f"Quote the value in YAML to prevent float-coercion (e.g. framework_version: \"1.0.0\").",
                type_claimed, sv_int,
            )

    return CheckResult(str(path), target_desc, mode, "pass", "", type_claimed, sv_int)


def walk_targets(registry: dict) -> HarnessReport:
    report = HarnessReport()
    for desc, glob_pattern, mode in SCAN_TARGETS:
        for path in REPO_ROOT.glob(glob_pattern):
            if not path.is_file():
                continue
            result = check_file(path, desc, mode, registry)
            report.add(result)
    return report


def render_text_report(report: HarnessReport, registry: dict) -> str:
    lines = []
    lines.append("schema-conformance harness")
    lines.append("=" * 60)
    lines.append("")

    total = sum(len(v) for v in report.by_status.values())
    lines.append(f"Total files scanned: {total}")
    for status in ("pass", "free-form", "skip", "fail"):
        count = len(report.by_status[status])
        symbol = {"pass": "✅", "free-form": "—", "skip": "⏭️", "fail": "❌"}[status]
        lines.append(f"  {symbol} {status:10}  {count}")
    lines.append("")

    if report.by_status["fail"]:
        lines.append("─" * 60)
        lines.append("FAILURES (strict-mode files that violated the contract):")
        lines.append("─" * 60)
        for r in report.by_status["fail"]:
            mode_indicator = "[strict]" if r.mode == "strict" else "[info]"
            lines.append(f"  {mode_indicator} {r.path}")
            lines.append(f"     type:           {r.type_claimed!r}")
            lines.append(f"     schema_version: {r.schema_version!r}")
            lines.append(f"     reason:         {r.detail}")
            lines.append("")

    # Type-coverage diagnostic — which registered types have ZERO conformant examples
    lines.append("─" * 60)
    lines.append("Type coverage:")
    lines.append("─" * 60)
    page_types = registry["page_types"]
    for ptype in sorted(page_types.keys()):
        files = report.type_coverage.get(ptype, [])
        if files:
            lines.append(f"  ✅ {ptype:25}  {len(files)} file(s)")
        else:
            # No conformant example anywhere. Surface as TODO so contributors know.
            lines.append(f"  ⚠️  {ptype:25}  no conformant example (TODO: add fixture or template)")
    lines.append("")

    if report.by_status["fail"]:
        # Distinguish strict fails (block) vs informational fails (report only)
        strict_fails = [r for r in report.by_status["fail"] if r.mode == "strict"]
        info_fails = [r for r in report.by_status["fail"] if r.mode == "informational"]
        lines.append(f"BLOCKERS (strict mode): {len(strict_fails)}")
        lines.append(f"INFORMATIONAL FAILS:    {len(info_fails)} (do not block CI)")
    else:
        lines.append("All files conform.")

    return "\n".join(lines)


def main() -> int:
    registry = load_registry()
    report = walk_targets(registry)

    print(render_text_report(report, registry))

    # Exit logic: only STRICT-mode fails are blockers.
    strict_fails = [r for r in report.by_status["fail"] if r.mode == "strict"]
    return 1 if strict_fails else 0


if __name__ == "__main__":
    sys.exit(main())
