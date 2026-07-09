"""
skills.doctor library — the framework health-check harness (Task 7.3, RenOS
0.2 Phase 7). ADAPTED from donor `skills/doctor/scripts/check-*.sh` (bash,
one script per section) into a single Python check-harness: one small named
function per check, all returning the same `CheckResult` shape, all run
through `run_checks()` with per-check isolation (a crashing check becomes an
`"error"`-status result, never kills the harness — same discipline as
`skills.metric-watch.lib.watch`, Task 6.3).

CARRIED (logic ported from donor's bash, not the bash itself — Python
integrates directly with this repo's lib modules, which the new checks below
need anyway):
  - `check_env` — git/python present, ANTHROPIC_API_KEY set. (Node/gh/claude-cli
    checks from donor's check-env.sh are DROPPED — feed-era/marketplace-era
    concerns that don't apply to a bare Python+git framework.)
  - `check_wiki_structure` — wiki root exists, `identity.md`/`log.md` present.
  - `check_frontmatter` — runs `scripts/lint-yaml-frontmatter.py` against the wiki.
  - `check_schema_versions` — every page vs. `skills.wiki-migration.lib`'s
    registry; behind-current pages get a `warn` naming the pending migration chain.

DROPPED entirely (feed-era, per task brief): activity-feed/RC-channel/fleet
checks (donor's check-permissions.sh, check-plugins.sh, check-code-map.sh's
OLD feed-sync meaning, check-context.sh, check-update.sh's marketplace-version
half, check-routines.sh's feed-registration half). Donor's check-wiki-health.sh
(dead links/stale/heavy pages) is also dropped — its wikilink-graph concern is
superseded by the NEW dangling-L2-pointer check below, which checks the same
"does this reference resolve" question but against the L2 pointer-map schema
this repo actually uses, not donor's freeform wikilink convention.

NEW (Task 7.3, all warn-not-block):
  - `check_budget_lint` — SKILL.md `budgets:` declarations vs. measured
    `capability_tokens` data (`lib.instrument.collect`).
  - `check_dangling_pointers` — every l2-map page's "## Decision map" lines,
    target existence.
  - `check_graphify_status` — `skills.code-map.lib.status()`.
  - `check_backup_configured` — `skills.backup.lib.backup_configured()`.
  - `check_global_drift` — `lib.memory.promotion.demote_check()`.
  - `check_harness_neutrality` — `lib.portability.agents_surface.lint_generated_surfaces`,
    soft-wired (skips cleanly if that module is absent).
"""

from __future__ import annotations

import importlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from lib import ren_paths
from lib.instrument import collect
from lib.memory import promotion
from lib.ren_paths import PathTraversalError

_REPO_ROOT = Path(__file__).resolve().parents[3]  # lib -> doctor -> skills -> repo root


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str      # "ok" | "warn" | "info" | "skip" | "error"
    message: str


def _wrap(name: str, fn) -> CheckResult:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - one crashing check must never kill the harness
        return CheckResult(name=name, status="error", message=f"check crashed: {exc}")


# --------------------------------------------------------------- carried checks


def check_env() -> CheckResult:
    """git present, python present, ANTHROPIC_API_KEY set. Donor's Node/gh/
    claude-cli checks dropped (feed/marketplace-era, not applicable here)."""
    missing = []
    if shutil.which("git") is None:
        missing.append("git")
    if shutil.which("python3") is None and shutil.which("python") is None:
        missing.append("python3")
    if missing:
        return CheckResult("env", "warn", f"missing on PATH: {', '.join(missing)}")
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return CheckResult("env", "warn", "ANTHROPIC_API_KEY not set")
    return CheckResult("env", "ok", "git, python3, ANTHROPIC_API_KEY all present")


def check_wiki_structure(wiki_root: Path | None = None) -> CheckResult:
    wiki_root = wiki_root or ren_paths.wiki_root()
    if not wiki_root.is_dir():
        return CheckResult("wiki_structure", "warn", f"no wiki at {wiki_root} — run /ren:install")
    missing = [f for f in ("identity.md", "log.md") if not (wiki_root / f).is_file()]
    if missing:
        return CheckResult("wiki_structure", "warn", f"missing: {', '.join(missing)}")
    return CheckResult("wiki_structure", "ok", "wiki root, identity.md, log.md all present")


def check_frontmatter(wiki_root: Path | None = None) -> CheckResult:
    """Runs `scripts/lint-yaml-frontmatter.py` against the wiki root."""
    wiki_root = wiki_root or ren_paths.wiki_root()
    if not wiki_root.is_dir():
        return CheckResult("frontmatter", "skip", "no wiki to lint")
    script = _REPO_ROOT / "scripts" / "lint-yaml-frontmatter.py"
    proc = subprocess.run(
        ["python3", str(script), str(wiki_root)],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode == 0:
        return CheckResult("frontmatter", "ok", "all frontmatter blocks parse cleanly")
    return CheckResult("frontmatter", "warn", proc.stdout.strip() or proc.stderr.strip() or "lint failed")


_FM_FIELD_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _frontmatter_field(text: str, field: str) -> str | None:
    fm_match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not fm_match:
        return None
    pattern = _FM_FIELD_RE_CACHE.setdefault(field, re.compile(rf"^{field}:\s*(.+)$", re.MULTILINE))
    m = pattern.search(fm_match.group(1))
    if not m:
        return None
    return m.group(1).strip().strip('"').strip("'")


def check_schema_versions(wiki_root: Path | None = None) -> CheckResult:
    """Every wiki page vs. `skills.wiki-migration.lib`'s registry — behind-
    current pages get a warn naming the pending migration chain."""
    wiki_root = wiki_root or ren_paths.wiki_root()
    if not wiki_root.is_dir():
        return CheckResult("schema_versions", "skip", "no wiki to check")

    wiki_migration = importlib.import_module("skills.wiki-migration.lib")
    registry = wiki_migration.load_registry()
    behind: list[str] = []

    for md_path in sorted(wiki_root.rglob("*.md")):
        text = md_path.read_text(encoding="utf-8", errors="replace")
        page_type = _frontmatter_field(text, "type")
        version_str = _frontmatter_field(text, "schema_version")
        if not page_type or page_type not in registry.get("page_types", {}) or not version_str:
            continue
        try:
            version = int(version_str)
        except ValueError:
            continue
        chain = wiki_migration.migration_chain(page_type, version, registry)
        if chain:
            rel = md_path.relative_to(wiki_root)
            behind.append(f"{rel} ({page_type} v{version}, pending: {', '.join(chain)})")

    if behind:
        return CheckResult("schema_versions", "warn", f"{len(behind)} page(s) behind current schema: {'; '.join(behind[:5])}")
    return CheckResult("schema_versions", "ok", "all typed pages at current schema")


# ------------------------------------------------------------------- new checks


_DECLARED_TOKENS_RE = re.compile(r"^\s*tokens:\s*(\d+)\s*$", re.MULTILINE)


def check_budget_lint(wiki_root: Path | None = None) -> CheckResult:
    """Declared SKILL.md `budgets:` blocks vs. measured `capability_tokens`
    data (`lib.instrument.collect`). Skips silently when no measured data
    exists yet. A SKILL.md's `budgets:` block in this repo currently declares
    `turns`/`files_written`/`duration_seconds` — none of them a token
    ceiling — so until a skill actually declares a `tokens:` field, every
    measured capability is reported `info` (there and awaiting a
    declared-budget to grade against) rather than invented a threshold to
    compare against. Any skill that DOES declare `tokens:` gets a real
    over/under-budget verdict."""
    entries = collect.read(kind=collect.KIND_CAPABILITY_TOKENS)
    if not entries:
        return CheckResult("budget_lint", "skip", "no capability_tokens data yet")

    skills_dir = _REPO_ROOT / "skills"
    over_budget: list[str] = []
    undeclared: list[str] = []
    for entry in entries:
        capability = entry.get("capability")
        measured = entry.get("tokens")
        if not capability or measured is None:
            continue
        skill_md = skills_dir / capability / "SKILL.md"
        if not skill_md.is_file():
            continue
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        declared_match = _DECLARED_TOKENS_RE.search(text)
        if declared_match is None:
            undeclared.append(capability)
            continue
        if measured > int(declared_match.group(1)):
            over_budget.append(f"{capability} ({measured} > {declared_match.group(1)})")

    if over_budget:
        return CheckResult("budget_lint", "warn", f"{len(over_budget)} capability(ies) over declared budget: {', '.join(over_budget[:5])}")
    if undeclared:
        return CheckResult("budget_lint", "info", f"{len(undeclared)} capability(ies) measured but no declared token ceiling in their SKILL.md")
    return CheckResult("budget_lint", "ok", "all measured capabilities within declared token budgets")


def check_dangling_pointers(wiki_root: Path | None = None) -> CheckResult:
    """Every l2-map page's "## Decision map" pointer lines
    (`- [topic] → path#anchor (write_id)`) — do their targets exist?"""
    wiki_root = wiki_root or ren_paths.wiki_root()
    if not wiki_root.is_dir():
        return CheckResult("dangling_pointers", "skip", "no wiki to check")

    pointer_re = re.compile(r"^-\s*\[[^\]]*\]\s*→\s*([^\s#]+)")
    dangling: list[str] = []

    for md_path in sorted(wiki_root.rglob("*.md")):
        text = md_path.read_text(encoding="utf-8", errors="replace")
        if _frontmatter_field(text, "type") != "l2-map":
            continue
        in_decision_map = False
        for line in text.splitlines():
            if line.startswith("## "):
                in_decision_map = line.strip() == "## Decision map"
                continue
            if not in_decision_map:
                continue
            m = pointer_re.match(line.strip())
            if not m:
                continue
            target = m.group(1)
            rel = md_path.relative_to(wiki_root)
            if target.startswith("/"):
                dangling.append(f"{rel} → {target}")
                continue
            try:
                target_path = ren_paths.safe_join(wiki_root, target)
            except PathTraversalError:
                dangling.append(f"{rel} → {target} (path-escaping)")
                continue
            if not target_path.is_file():
                dangling.append(f"{rel} → {target}")

    if dangling:
        return CheckResult("dangling_pointers", "warn", f"{len(dangling)} dangling pointer(s): {'; '.join(dangling[:5])}")
    return CheckResult("dangling_pointers", "ok", "no dangling L2 pointers")


def check_graphify_status(repo_root: Path | None = None) -> CheckResult:
    repo_root = repo_root or _REPO_ROOT
    code_map = importlib.import_module("skills.code-map.lib")
    status = code_map.status(repo_root)

    if not status.installed:
        return CheckResult("graphify_status", "info", "graphify not installed — see companions.md for setup")
    if not status.pinned_ok:
        return CheckResult("graphify_status", "warn", f"graphify version {status.version} outside the pinned range")
    if status.stale:
        return CheckResult("graphify_status", "info", "graph is stale (source changed since last build)")
    return CheckResult("graphify_status", "ok", f"graphify {status.version}, graph fresh")


def check_companions() -> CheckResult:
    """Companion choices vs reality: accepted-but-missing is drift (warn);
    undecided-and-absent is a pointer (info). Warn-not-block, like every check."""
    from lib import companions

    missing = [
        o.companion.cid
        for o in companions.reconcile()
        if o.decision == "accepted" and not o.installed
    ]
    if missing:
        return CheckResult(
            "companions",
            "warn",
            f"accepted but not installed: {', '.join(missing)} — "
            "re-run the install hint from doctrine/companions.md",
        )
    undecided = [o.companion.cid for o in companions.pending_offers()]
    if undecided:
        return CheckResult(
            "companions",
            "info",
            f"companions not yet decided: {', '.join(undecided)} — "
            "/ren:install or /ren:update will offer them",
        )
    return CheckResult("companions", "ok", "no companion drift")


def check_backup_configured(wiki_root: Path | None = None) -> CheckResult:
    backup_lib = importlib.import_module("skills.backup.lib")
    if backup_lib.backup_configured(wiki_root):
        return CheckResult("backup_configured", "ok", "backup remote or recent tarball present")
    return CheckResult("backup_configured", "warn", "no backup remote configured and no recent tarball — run /ren:backup --setup or /ren:backup")


_VALID_EXECUTION_TIERS = frozenset({"deterministic", "worker", "judgment"})


def check_execution_tiers(skills_dir: Path | None = None) -> CheckResult:
    """Finalize-v0.2 agenda item 3: every shipped SKILL.md must declare
    `execution_tier: deterministic | worker | judgment` in its frontmatter —
    the routing contract for WHO executes the skill's reasoning (lib scripts /
    a cheap worker subagent / the main model only). Missing or invalid
    declarations are a warn listing the offenders."""
    skills_dir = skills_dir or (_REPO_ROOT / "skills")
    if not skills_dir.is_dir():
        return CheckResult("execution_tiers", "skip", "no skills dir to lint")

    missing: list[str] = []
    invalid: list[str] = []
    counts: dict[str, int] = {}
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        tier = _frontmatter_field(text, "execution_tier")
        name = skill_md.parent.name
        if tier is None:
            missing.append(name)
        elif tier not in _VALID_EXECUTION_TIERS:
            invalid.append(f"{name} ({tier!r})")
        else:
            counts[tier] = counts.get(tier, 0) + 1

    problems = []
    if missing:
        problems.append(f"{len(missing)} skill(s) missing execution_tier: {', '.join(missing[:5])}")
    if invalid:
        problems.append(f"{len(invalid)} skill(s) with invalid execution_tier: {', '.join(invalid[:5])}")
    if problems:
        return CheckResult("execution_tiers", "warn", "; ".join(problems))
    summary = ", ".join(f"{n} {tier}" for tier, n in sorted(counts.items()))
    return CheckResult("execution_tiers", "ok", f"all skills declare a valid tier ({summary})")


def check_global_drift() -> CheckResult:
    violations = promotion.demote_check()
    if violations:
        return CheckResult("global_drift", "warn", f"{len(violations)} page(s) in global/ not typed doctrine/preference: {', '.join(violations[:5])}")
    return CheckResult("global_drift", "ok", "global tier clean")


def check_harness_neutrality(wiki_root: Path | None = None, repo_root: Path | None = None) -> CheckResult:
    """Soft-wired: `lib.portability.agents_surface` may not exist in every
    checkout (it's Task 7.2, built in parallel) — skip cleanly if absent."""
    wiki_root = wiki_root or ren_paths.wiki_root()
    repo_root = repo_root or _REPO_ROOT
    try:
        agents_surface = importlib.import_module("lib.portability.agents_surface")
    except ImportError:
        return CheckResult("harness_neutrality", "skip", "lib.portability.agents_surface not available")

    report = agents_surface.lint_generated_surfaces(wiki_root, repo_root)
    if report:
        return CheckResult("harness_neutrality", "warn", f"{len(report)} generated surface(s) with harness-coupling tokens")
    return CheckResult("harness_neutrality", "ok", "generated surfaces are harness-neutral")


def check_guard_health(guards_dir: Path | None = None) -> CheckResult:
    """Task 9.3 doc-note-3 compensating control: the PreToolUse guards fail
    OPEN on internal error by design (a broken guard must not brick the
    harness for a non-technical friend — see docs/data-flow.md "Guard failure
    posture"). This check makes a degraded guard VISIBLE: run each guard
    script with a trivially-safe synthetic payload; a crash, non-zero exit, or
    internal-error warning on stderr means enforcement is degraded."""
    guards_dir = guards_dir or (_REPO_ROOT / "hooks" / "guards")
    scripts = sorted(guards_dir.glob("*.py")) if guards_dir.is_dir() else []
    scripts = [s for s in scripts if s.name != "__init__.py"]
    if not scripts:
        return CheckResult("guard_health", "warn", f"no guard scripts found under {guards_dir}")

    safe_payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo ok"}})
    degraded = []
    for script in scripts:
        proc = subprocess.run(
            [sys.executable, str(script)],
            input=safe_payload, capture_output=True, text=True, timeout=30,
            cwd=str(_REPO_ROOT),
        )
        if proc.returncode != 0 or "WARNING" in proc.stderr:
            degraded.append(script.name)
    if degraded:
        return CheckResult(
            "guard_health", "warn",
            f"guard degraded — investigate before relying on enforcement: {', '.join(degraded)}",
        )
    return CheckResult("guard_health", "ok", f"{len(scripts)} guard(s) healthy on a safe synthetic payload")


_ALL_CHECK_NAMES: tuple[str, ...] = (
    "check_env",
    "check_wiki_structure",
    "check_frontmatter",
    "check_schema_versions",
    "check_budget_lint",
    "check_dangling_pointers",
    "check_graphify_status",
    "check_companions",
    "check_backup_configured",
    "check_execution_tiers",
    "check_global_drift",
    "check_harness_neutrality",
    "check_guard_health",
)


def run_checks() -> list[CheckResult]:
    """Run every check, isolated (a crashing check produces an `"error"`
    result, never kills the harness). Returns results in declaration order.

    Looks up each check function by name in this module's globals() AT CALL
    TIME (not a bound-reference tuple) — so a test that does
    `monkeypatch.setattr(doctor, "check_env", fake)` is honored here, the
    same reasoning `skills.metric-watch.lib.watch` uses for its own checks.
    """
    results = []
    for fn_name in _ALL_CHECK_NAMES:
        fn = globals()[fn_name]
        short_name = fn_name.removeprefix("check_")
        results.append(_wrap(short_name, fn))
    return results


__all__ = [
    "CheckResult",
    "check_env",
    "check_wiki_structure",
    "check_frontmatter",
    "check_schema_versions",
    "check_budget_lint",
    "check_dangling_pointers",
    "check_graphify_status",
    "check_companions",
    "check_backup_configured",
    "check_execution_tiers",
    "check_global_drift",
    "check_harness_neutrality",
    "check_guard_health",
    "run_checks",
]
