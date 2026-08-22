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
  - `check_env` — git/python present. (Node/gh/claude-cli
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
  - `check_hub_convention` — legacy `index.md` knowledge hubs pending the
    folder-note-hubs-1 migration (#56).
  - `check_graphify_status` — `skills.code-map.lib.status()`.
  - `check_backup_configured` — `skills.backup.lib.backup_configured()`.
  - `check_global_drift` — `lib.memory.promotion.demote_check()`.
  - `check_harness_neutrality` — `lib.portability.agents_surface.
    lint_generated_surfaces_partitioned`, soft-wired (skips cleanly if that
    module is absent). Warns only on a coupled AGENTS.md; live l2-map content
    mentions are info; `wiki/.ren/` snapshots are excluded (issue #33).
"""

from __future__ import annotations

import importlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Final

from lib import ren_paths
from lib.instrument import collect
from lib.memory import promotion
from lib.pointer import REPO_REF_PREFIX as _REPO_REF_PREFIX, parse_pointer_line
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
    """git present, python present. Donor's Node/gh/claude-cli checks dropped
    (feed/marketplace-era, not applicable here). No API-key check — RenOS runs on
    subscription auth and ships with no keys, no services, no telemetry."""
    missing = []
    if shutil.which("git") is None:
        missing.append("git")
    if shutil.which("python3") is None and shutil.which("python") is None:
        missing.append("python3")
    if missing:
        return CheckResult("env", "warn", f"missing on PATH: {', '.join(missing)}")
    return CheckResult("env", "ok", "git, python3 all present")


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
        # projects/<slug>/raw/ is write-once source material — a source file
        # carrying registered-type frontmatter is not a page to migrate.
        if ren_paths.in_project_raw(md_path.relative_to(wiki_root).parts):
            continue
        text = md_path.read_text(encoding="utf-8", errors="replace")
        page_type = _frontmatter_field(text, "type")
        # Skip unregistered types (no migration path exists).
        if not page_type or page_type not in registry.get("page_types", {}):
            continue
        version_str = _frontmatter_field(text, "schema_version")
        # Unstamped pages predate schema-versioning (issue #20) — treat absent
        # version as 1, not as "skip me". This ensures they're visible to
        # migration discovery, not hidden from the upgrade path.
        if not version_str:
            version = 1
        else:
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
    (`- [topic](path#anchor) (write_id)`, legacy `→` form accepted) — do
    their targets exist?"""
    wiki_root = wiki_root or ren_paths.wiki_root()
    if not wiki_root.is_dir():
        return CheckResult("dangling_pointers", "skip", "no wiki to check")

    dangling: list[str] = []

    for md_path in sorted(wiki_root.rglob("*.md")):
        if ren_paths.under_ren_state(md_path, wiki_root):
            # `.ren/` is immutable framework state (incl. per-write snapshot
            # copies of maps) — its stale pointers are not live warns (#31).
            continue
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
            ptr = parse_pointer_line(line)
            if ptr is None:
                continue
            target = ptr.path
            rel = md_path.relative_to(wiki_root)
            if ptr.target.startswith(_REPO_REF_PREFIX):
                # `repo:<name>:<path>` external repo reference (issue #20) —
                # not an in-wiki page, so never dangling. Mirrors
                # `skills.wiki-health.lib._dangling_pointers`.
                continue
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


def check_hub_convention(wiki_root: Path | None = None) -> CheckResult:
    """Warn on knowledge hubs still named index.md (pre folder-note-hubs-1, #56)."""
    wiki_root = wiki_root or ren_paths.wiki_root()
    legacy = []
    for knowledge in sorted(wiki_root.glob("projects/*/knowledge")):
        for p in sorted(knowledge.rglob("index.md")):
            rel = p.relative_to(wiki_root)
            if any(part.startswith(".") or part in ("raw", "archive") for part in rel.parts):
                continue
            legacy.append(str(rel))
    if legacy:
        shown = ", ".join(legacy[:5])
        more = f" (+{len(legacy) - 5} more)" if len(legacy) > 5 else ""
        return CheckResult("hub_convention", "warn",
                           f"legacy index.md hubs pending folder-note-hubs-1: {shown}{more}")
    return CheckResult("hub_convention", "ok", "all knowledge hubs are folder notes")


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
    return CheckResult(
        "backup_configured",
        "warn",
        "no backup remote configured and no recent tarball — run /ren:backup --setup or /ren:backup "
        "(required before ingest-project/bootstrap-project can write to a populated wiki, per the 0.6.0 backup gate)",
    )


def check_orphaned_projects(wiki_root: Path | None = None) -> CheckResult:
    """Issue #19: every `projects/<slug>/` in the wiki should be reachable
    from a repo — either through a recorded repo-path↔slug mapping
    (`state_dir()/projects.json`, written at ingest/bootstrap time) or through
    a matching `<dev_root>/<slug>/` directory (the dir-name fallback
    `ren_paths.detect_project` uses).

    A slug with neither is memory nothing can ever inject: wake-up will never
    detect it from any cwd. Warn, naming the offenders."""
    root = Path(wiki_root) if wiki_root is not None else ren_paths.wiki_root()
    projects_dir = root / "projects"
    if not projects_dir.is_dir():
        return CheckResult("orphaned_projects", "skip", "no projects/ dir in the wiki yet")

    slugs = sorted(p.name for p in projects_dir.iterdir() if p.is_dir())
    if not slugs:
        return CheckResult("orphaned_projects", "skip", "no project subtrees yet")

    registry = ren_paths.load_project_registry()
    dev_root = ren_paths.resolve_dev_root()
    orphans = [
        slug for slug in slugs
        if slug not in registry and not (dev_root / slug).is_dir()
    ]
    if not orphans:
        return CheckResult(
            "orphaned_projects", "ok", f"{len(slugs)} project subtree(s) reachable from a repo"
        )
    return CheckResult(
        "orphaned_projects",
        "warn",
        f"{len(orphans)} project subtree(s) with no repo mapping and no {dev_root}/<slug> dir "
        f"(likely orphaned memory — re-run /ren:ingest-project from the repo to re-link): "
        + ", ".join(orphans),
    )


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
    checkout (it's Task 7.2, built in parallel) — skip cleanly if absent.

    Issue #33 "scope to scaffolding": only a coupled AGENTS.md (the generated
    scaffolding) warns; harness mentions inside live l2-map CONTENT are
    legitimate (log lines like "recalled via /ren:recall") and reported as
    info. Snapshot copies under `wiki/.ren/` are excluded by the lint."""
    wiki_root = wiki_root or ren_paths.wiki_root()
    repo_root = repo_root or _REPO_ROOT
    try:
        agents_surface = importlib.import_module("lib.portability.agents_surface")
    except ImportError:
        return CheckResult("harness_neutrality", "skip", "lib.portability.agents_surface not available")

    report = agents_surface.lint_generated_surfaces_partitioned(wiki_root, repo_root)
    agents_hits = report["agents_md"]
    map_hits = report["l2_maps"]
    if agents_hits:
        return CheckResult("harness_neutrality", "warn", f"AGENTS.md contains harness-coupling tokens: {', '.join(sorted(agents_hits))}")
    if map_hits:
        sample = ", ".join(sorted(map_hits)[:3])
        return CheckResult("harness_neutrality", "info", f"{len(map_hits)} l2-map(s) mention the harness in content (informational, not a violation): {sample}")
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


def check_suggestion_store(store_dir: Path | None = None) -> CheckResult:
    """0.4.5: the suggestion store degrades silently everywhere else (readers
    skip unparsable entry files by contract) — this check is where a corrupt
    or torn entry becomes VISIBLE instead of quietly shrinking the pending
    list. An absent/empty store is healthy (nothing suggested yet)."""
    store_dir = store_dir or (ren_paths.state_dir() / "suggestions")
    if not store_dir.is_dir():
        return CheckResult("suggestion_store", "ok", "no suggestion store yet")

    corrupt: list[str] = []
    total = 0
    for path in sorted(store_dir.glob("*.json")):
        total += 1
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            corrupt.append(path.name)

    if corrupt:
        return CheckResult(
            "suggestion_store", "warn",
            f"{len(corrupt)} unparsable suggestion entry file(s): {', '.join(corrupt[:5])}",
        )
    return CheckResult("suggestion_store", "ok", f"{total} suggestion entry file(s) parse cleanly")


# #67: sessions whose journal entries are orphaned BY DESIGN, not by the
# crash race check_apply_integrity exists to surface. Each key carries its
# in-code reason; adding an exemption is a deliberate code change here —
# there is no config/env override.
_APPLY_INTEGRITY_EXEMPT_SESSIONS: Final[dict[str, str]] = {
    "install": "Gate-0 skeleton stamp writes journal without queue entries by design",
    "f65b32a8-fixtrain-remediation": (
        "2026-08-04 L1 archive relocation: journal written, queue persist "
        "bypassed by the routine — accepted, not a crash window"
    ),
}


def check_apply_integrity() -> CheckResult:
    """codex D6 (visibility only): a write can leave a journal entry with no
    matching APPLIED queue entry if the process dies between
    `write_apply.apply_write`'s journal append and `queue.apply`/
    `apply_auto`'s `_persist(entry)` — the queue entry still reads
    pending/approved on restart even though the write already landed. Full
    idempotent-recovery is deferred to 0.6; this check only makes the gap
    VISIBLE.

    Scoped to journal entries with `op` in `ADD`/`UPDATE`/`DELETE` — every
    such entry is produced by `write_apply.apply_write` called from
    `queue.apply`/`apply_auto`/`resolve_and_apply`, each of which persists a
    matching `status="applied"` queue entry with that `write_id`. `NOOP`
    entries (revert records, metric-watch findings) are never queue-backed
    by design and are excluded from the scan entirely.

    Also excludes the sessions listed in `_APPLY_INTEGRITY_EXEMPT_SESSIONS` —
    entries orphaned by design, not by a crash race; the reason lives in the
    table next to each key, and adding an exemption is a deliberate code
    change (no config/env override). The `install` entry's long-form context
    (Gate-0 Finding 2): install's Stage-2 wiki-stamp
    (`lib.skeleton.stamp_skeleton`) calls `write_apply.apply_write` directly
    for the founding pages (index.md/log.md/identity.md/LICENSES.md),
    bypassing the queue entirely — they're orphaned by construction on every
    fresh install, not by a crash race, so flagging them is a false positive.
    The structural fix (routing install writes through `queue.apply` so a
    matching applied entry exists) is 0.6 backlog; this is the
    visibility-layer exclusion in the meantime."""
    from lib.memory import journal, queue

    applied_write_ids = {
        e.write_id for e in queue.all_entries() if e.status == "applied" and e.write_id
    }

    orphans: list[str] = []
    for entry in journal.entries():
        if entry.get("op") not in ("ADD", "UPDATE", "DELETE"):
            continue
        if entry.get("session") in _APPLY_INTEGRITY_EXEMPT_SESSIONS:
            continue
        write_id = entry.get("write_id")
        if write_id and write_id not in applied_write_ids:
            orphans.append(write_id)

    if orphans:
        return CheckResult(
            "apply_integrity", "warn",
            f"{len(orphans)} journal write_id(s) with no matching applied queue entry: "
            f"{', '.join(orphans[:5])}",
        )
    return CheckResult("apply_integrity", "ok", "every journaled write has a matching applied queue entry")


def check_judge_health() -> CheckResult:
    """Task 14 (0.5.2): make degraded semantic judging VISIBLE. Reads recent
    `judge_event` metrics (`lib.memory.judge.judge_pairs`'s fail-closed
    events). Any `fail_closed` event means at least one pair fell back to
    heuristics-only because the LLM judge call raised or returned something
    unparsable — that's a warn. `no_llm` (no `llm_call` configured at all)
    and `capped` (pairs beyond the batch cap, never even attempted) are both
    expected, non-degraded states, so their presence alone is `ok`."""
    events = collect.read(kind=collect.KIND_JUDGE_EVENT)
    fail_closed_count = sum(1 for e in events if e.get("event") == "fail_closed")
    if fail_closed_count:
        return CheckResult(
            "judge_health", "warn",
            f"semantic judging degraded — running heuristics-only ({fail_closed_count} fail_closed event(s))",
        )
    return CheckResult("judge_health", "ok", "no degraded judge events recorded")


def check_archive_integrity(wiki_root: Path | None = None) -> CheckResult:
    """Task 19 (0.5.3): make a broken archive tier VISIBLE. Every page under
    `archive/` must carry `archived_from` frontmatter AND have a matching
    journal entry proving how it got there — either the `ADD` write that
    created the archive copy (`entry["page"] == <archive rel>`) or the
    paired `DELETE`'s `archived_to` extra field pointing at it
    (`lib.memory.archive.archive_page` writes both). A page failing either
    check is an orphan: hand-dropped into `archive/`, or its journal entry
    was lost/pruned. Warn, listing offenders — never block."""
    from lib.memory import journal

    wiki_root = wiki_root or ren_paths.wiki_root()
    archive_dir = wiki_root / "archive"
    if not archive_dir.is_dir():
        return CheckResult("archive_integrity", "ok", "no archive tier yet")

    entries = journal.entries()
    journaled_archive_pages = {
        e.get("page") for e in entries if e.get("op") == "ADD"
    } | {
        e.get("archived_to") for e in entries if e.get("archived_to")
    }

    orphans: list[str] = []
    for path in sorted(archive_dir.rglob("*.md")):
        rel = path.relative_to(wiki_root).as_posix()
        text = path.read_text(encoding="utf-8")
        if not _frontmatter_field(text, "archived_from"):
            orphans.append(rel)
        elif rel not in journaled_archive_pages:
            orphans.append(rel)

    if orphans:
        return CheckResult(
            "archive_integrity", "warn",
            f"{len(orphans)} archive page(s) missing frontmatter or a matching journal entry: "
            f"{', '.join(orphans[:5])}",
        )
    return CheckResult("archive_integrity", "ok", "every archive page has frontmatter and a matching journal entry")


_MODEL_CLASSES_PATH = _REPO_ROOT / "doctrine" / "model-classes.md"
_MODEL_CLASS_ROW_RE = re.compile(r"^\|\s*([^|\s]+)\s*\|\s*([^|]*)\|", re.MULTILINE)
_MODEL_MAP_STAMP_RE = re.compile(r"<!--\s*renos:model-map-updated:\s*(\d{4}-\d{2}-\d{2})\s*-->")
_STALE_DAYS_THRESHOLD = 180
_ORCHESTRATOR_WARN_PCT = 0.30
_PARALLEL_PEAK_WARN_THRESHOLD = 5


def _model_class(model: str | None, table_text: str) -> str:
    """Classify `model` against `doctrine/model-classes.md`'s table:
    substring-match the model id against each row's "current models" cell.
    No match (including `model is None`, e.g. a spawn with no recorded
    override) → "unknown" — unknown models never count toward the
    orchestrator-percentage warn threshold and never independently warn."""
    if not model:
        return "unknown"
    for cls, models_cell in _MODEL_CLASS_ROW_RE.findall(table_text):
        if cls in ("class", "---"):
            continue
        if model in models_cell:
            return cls
    return "unknown"


def check_routing_audit() -> CheckResult:
    """0.6.1 E4, advisory-only: audits model-routing economics from harvested
    `subagent_spawn` metrics against `doctrine/model-classes.md`'s class
    table. `warn` when >30% of spawns used orchestrator-class models, OR any
    spawn recorded a `parallel_peak` > 5 (a fan-out wide enough to be worth a
    second look). Otherwise `info` with per-class counts. Never blocks —
    unknown models are excluded from the orchestrator-percentage denominator
    logic entirely (counted, but never trigger a warn on their own)."""
    spawns = collect.read(kind=collect.KIND_SUBAGENT_SPAWN)
    if not spawns:
        return CheckResult("routing_audit", "info", "no spawn data yet")

    table_text = ""
    if _MODEL_CLASSES_PATH.is_file():
        table_text = _MODEL_CLASSES_PATH.read_text(encoding="utf-8", errors="replace")

    counts: dict[str, int] = {}
    max_parallel_peak = 0
    for entry in spawns:
        cls = _model_class(entry.get("model"), table_text)
        counts[cls] = counts.get(cls, 0) + 1
        peak = entry.get("parallel_peak")
        if isinstance(peak, (int, float)) and peak > max_parallel_peak:
            max_parallel_peak = peak

    total = len(spawns)
    orchestrator_pct = counts.get("orchestrator", 0) / total
    summary = ", ".join(f"{n} {cls}" for cls, n in sorted(counts.items()))

    if max_parallel_peak > _PARALLEL_PEAK_WARN_THRESHOLD:
        return CheckResult(
            "routing_audit", "warn",
            f"parallel_peak {max_parallel_peak} exceeds {_PARALLEL_PEAK_WARN_THRESHOLD} "
            f"({total} spawn(s): {summary})",
        )
    if orchestrator_pct > _ORCHESTRATOR_WARN_PCT:
        return CheckResult(
            "routing_audit", "warn",
            f"{orchestrator_pct:.0%} of {total} spawn(s) used orchestrator-class models "
            f"(> {_ORCHESTRATOR_WARN_PCT:.0%} threshold): {summary}",
        )
    return CheckResult("routing_audit", "info", f"{total} spawn(s): {summary}")


def check_model_map_staleness() -> CheckResult:
    """0.6.1 E4, advisory-only: always `info` unless the `renos:model-map-
    updated` stamp in `doctrine/model-classes.md` is older than 180 days —
    then `warn` (the doctrine table may no longer reflect current model
    names). Missing file or missing/unparsable stamp is reported `info`
    (nothing to grade staleness against, not itself an error)."""
    if not _MODEL_CLASSES_PATH.is_file():
        return CheckResult("model_map_staleness", "info", f"no model-classes.md at {_MODEL_CLASSES_PATH}")

    text = _MODEL_CLASSES_PATH.read_text(encoding="utf-8", errors="replace")
    m = _MODEL_MAP_STAMP_RE.search(text)
    if not m:
        return CheckResult("model_map_staleness", "info", "no renos:model-map-updated stamp found")

    try:
        stamp_date = datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except ValueError:
        return CheckResult("model_map_staleness", "info", f"unparsable stamp: {m.group(1)}")

    age_days = (date.today() - stamp_date).days
    if age_days > _STALE_DAYS_THRESHOLD:
        return CheckResult(
            "model_map_staleness", "warn",
            f"model-classes.md stamp is {age_days} days old (> {_STALE_DAYS_THRESHOLD}) — "
            "review model names against current routing",
        )
    return CheckResult("model_map_staleness", "info", f"model-classes.md stamp is {age_days} days old")


def check_execution_doctrine() -> CheckResult:
    """RenOS 0.6.4: the wake-up hook now injects the doctrine card
    (`hooks.wake-up.wakeup.doctrine_card`), referencing `agents/ren-reviewer.md`.
    Missing agent → error (the doctrine card would reference a dead path).
    A manual pre-0.6.4 stopgap block left in `~/.claude/CLAUDE.md` is now
    redundant residue — warn, naming the marker to remove."""
    name = "execution_doctrine"
    agent = _REPO_ROOT / "agents" / "ren-reviewer.md"
    if not agent.is_file():
        return CheckResult(name, "error", "agents/ren-reviewer.md missing — doctrine card references it")

    claude_md_path = ren_paths.claude_user_dir() / "CLAUDE.md"
    if claude_md_path.is_file():
        from lib.adapter import claude_md as _cm

        if _cm.has_doctrine_stopgap(claude_md_path.read_text(encoding="utf-8", errors="replace")):
            return CheckResult(
                name, "warn",
                "manual doctrine stopgap block found in ~/.claude/CLAUDE.md — "
                "the wake-up hook injects the doctrine now; delete the "
                "<!-- renos:doctrine-stopgap --> block",
            )
    return CheckResult(name, "ok", "doctrine card wired; ren-reviewer shipped; no stopgap residue")


def check_standing_instructions_drift() -> CheckResult:
    """#63: for every registered project with an instructions.md, the repo's
    CLAUDE.md managed block must match a fresh render — a mismatch means a
    stale splice (re-render never fired), a hand-edit inside the markers, or
    a missing CLAUDE.md. Warn-not-block; remediation is a re-render
    (`lib.adapter.claude_md.write_project_claude_md`), never automatic."""
    from lib import ren_paths
    from lib.adapter import claude_md

    wiki = ren_paths.wiki_root()
    stale: list[str] = []
    seen = 0
    for slug, entry in sorted(ren_paths.load_project_registry().items()):
        if not (wiki / "projects" / slug / "instructions.md").is_file():
            continue
        seen += 1
        repo_md = Path(entry["repo_path"]) / "CLAUDE.md"
        try:
            current = repo_md.read_text(encoding="utf-8") if repo_md.is_file() else ""
        except OSError:
            stale.append(slug)
            continue
        expected = claude_md.render_project_block(slug, wiki_root=wiki)
        if claude_md.spliced_text(current, expected) != current:
            stale.append(slug)
    if not seen:
        return CheckResult("standing_instructions_drift", "skip", "no project has an instructions.md")
    if stale:
        return CheckResult(
            "standing_instructions_drift", "warn",
            f"stale CLAUDE.md block for: {', '.join(stale)} — re-render via write_project_claude_md",
        )
    return CheckResult("standing_instructions_drift", "ok", f"{seen} project block(s) in sync")


def _project_agents_dir() -> Path | None:
    """`.claude/agents/` of the repo the current cwd maps to, via the
    repo-path↔slug registry (`ren_paths.load_project_registry`) — same
    resolution `detect_project` uses, so this agrees with the wake-up hook
    and the wrap skill on which project "here" is. Returns None when no
    wiki, no mapped project, or no recorded repo path.

    Does NOT catch a failing `wiki_root()`: `None` means "no project here",
    and conflating that with "resolution failed" left the health checker
    unable to report its own blindness. A raise propagates to `_wrap`,
    which renders it as an `"error"` result (spec 2026-08-22 §5.1)."""
    wiki_root_ = ren_paths.wiki_root()
    if not wiki_root_.is_dir():
        return None
    project_slug = ren_paths.detect_project(Path.cwd(), wiki_root_)
    if project_slug is None:
        return None
    entry = ren_paths.load_project_registry().get(project_slug)
    if not entry or not entry.get("repo_path"):
        return None
    return Path(entry["repo_path"]) / ".claude" / "agents"


def check_agent_shadowing() -> CheckResult:
    """0.6.5: a user or project `.claude/agents/<name>.md` with the same
    filename as a shipped RenOS agent (`agents/*.md`) shadows the shipped
    behavior — Claude Code resolves agent names to whichever definition it
    finds, and the shipped one isn't guaranteed to win. Checks both
    `claude_user_dir()/agents` and, when the cwd resolves to a registered
    project (`_project_agents_dir`), that project's `.claude/agents/` too.
    Skips only when neither directory exists."""
    name = "agent_shadowing"
    shipped = {p.stem for p in (_REPO_ROOT / "agents").glob("*.md")}

    user_dir = ren_paths.claude_user_dir() / "agents"
    project_dir = _project_agents_dir()

    user_has_dir = user_dir.is_dir()
    project_has_dir = project_dir is not None and project_dir.is_dir()

    if not user_has_dir and not project_has_dir:
        return CheckResult(name, "skip", "no user or project agents directory")

    # Track clashes per origin
    clashes_by_origin: dict[str, set[str]] = {}
    if user_has_dir:
        user_clashes = shipped & {p.stem for p in user_dir.glob("*.md")}
        if user_clashes:
            clashes_by_origin["user"] = user_clashes
    if project_has_dir:
        project_clashes = shipped & {p.stem for p in project_dir.glob("*.md")}
        if project_clashes:
            clashes_by_origin["project"] = project_clashes

    if clashes_by_origin:
        messages = []
        for origin in ("user", "project"):
            if origin in clashes_by_origin:
                clashes = clashes_by_origin[origin]
                messages.append(
                    f"{origin} agent(s) shadow shipped RenOS agents: {', '.join(sorted(clashes))}"
                )
        return CheckResult(
            name, "warn",
            f"{'; '.join(messages)} — rename yours or the shipped behavior won't apply",
        )
    return CheckResult(name, "ok", f"{len(shipped)} shipped agent(s), no shadowing")


def check_cache_env_hygiene() -> CheckResult:
    """#40: a `.venv` inside a VERSIONED plugin cache dir
    (`~/.claude/plugins/cache/ren-os/ren/<version>/.venv`) is stale garbage
    the moment the next version lands — that directory is otherwise treated
    as an immutable installed artifact. Documented invocations set
    `UV_PROJECT_ENVIRONMENT` (see `ren_paths.envs_dir()`) instead of letting
    `uv run` create one there.

    EXEMPTION (review HIGH): the CURRENT version's `.venv` is not stale —
    `skills.install.lib.warm_environment` deliberately runs `uv sync
    --project $CLAUDE_PLUGIN_ROOT` with no `UV_PROJECT_ENVIRONMENT` redirect
    on every fresh install, and the interpreter path it records in
    `interpreter.json` points INSIDE that `.venv` — load-bearing for the
    wake-up hook's fast-path re-exec (#11 §4). Warning on it (and telling a
    friend to remove it) would degrade that first-session self-heal. So the
    version named by `ren_paths.current_plugin_cache_version()` — the SAME
    `$CLAUDE_PLUGIN_ROOT` resolution `plugin_cache_versions_root()` already
    uses, not a second mechanism — is excluded from the stale scan.

    Warns listing every OTHER (non-current) stale `.venv` found across all
    version dirs; `skip`s when the cache root is unresolvable (bare dev
    checkout, no installed plugin, `ren_paths.plugin_cache_versions_root()`
    returns None) — warn-not-block, never a false positive on a checkout
    that was never uv-run from the cache in the first place."""
    name = "cache_env_hygiene"
    cache_versions_root = ren_paths.plugin_cache_versions_root()
    if cache_versions_root is None or not cache_versions_root.is_dir():
        return CheckResult(name, "skip", "plugin cache root unresolvable")

    current_version = ren_paths.current_plugin_cache_version()
    stale = sorted(
        venv.parent.name
        for venv in cache_versions_root.glob("*/.venv")
        if venv.is_dir() and venv.parent.name != current_version
    )
    if stale:
        return CheckResult(
            name, "warn",
            f"stale venv inside versioned cache dir for: {', '.join(stale)} — "
            "remove it; invocations should set UV_PROJECT_ENVIRONMENT, see #40",
        )
    return CheckResult(
        name, "ok",
        "no stale .venv in versioned cache dirs "
        "(current version's .venv, if any, is expected — see warm_environment/#11 §4)",
    )


def _recorded_interpreter_version(recorded: str) -> str:
    """The plugin version a recorded interpreter path sits under, or 'unknown'.

    Two layouts are valid, and missing the second silently disabled the
    version-currency warn below. A venv inside the plugin cache dir gives
    `.../cache/ren-os/ren/<version>/.venv/bin/python3`. But `warm_environment`
    resolves the interpreter through `uv run`, which honors
    `UV_PROJECT_ENVIRONMENT` — and issue #40 has every skill invocation set
    that to `ren_paths.envs_dir()` precisely so uv does NOT write a `.venv`
    into the immutable cache dir. Under that (normal) path the interpreter is
    `~/.renos/.envs/<version>/bin/python3`, whose parents contain no `ren`
    directory at all, so this returned "unknown" and the currency comparison
    was skipped rather than performed.
    """
    parents = Path(recorded).parents
    version = next((p.name for p in parents if p.parent.name == "ren"), None)
    if version is None:
        version = next((p.name for p in parents if p.parent.name == ".envs"), None)
    return version or "unknown"


def check_interpreter_freshness() -> CheckResult:
    """The wake-up hook's fast-path re-exec target (spec 2026-08-21 (0.8.2) §8).

    `hooks/wake-up/ren-wake-up.py` re-execs under an interpreter recorded by
    `warm_environment()` to avoid a cold-`uv` cost that trips
    `_REEXEC_TIMEOUT_S` (#11 §4). When that record is unusable the hook
    silently falls through to `uv run` — every session paying the cost the
    fast path exists to avoid — so this check exists to make it visible.

    The accept/reject decision is NOT reimplemented here: it is
    `lib.interpreter.recorded_interpreter_status`, the same call the hook
    makes. Earlier rounds wrote the conditions out twice under a comment
    requiring them to "stay in step", and they drifted anyway — doctor
    reported `ok` for a record the hook rejected (a `.venv` that had lost its
    exec bit), the exact silent degrade this check is for. Any reason but
    "ok" is a `warn`: the consequence is the same degraded fast path and
    re-warming is the same correct advice.

    A valid-but-stale record (right machine, live interpreter, previous
    plugin version) stays a separate `warn` — with re-warm wired into
    `/ren:update` it should now be rare, but it is still the shape that hid
    for ten releases.

    0.8.3: no machine/platform reason exists any more. The record moved out
    of the synced wiki into `ren_paths.machine_state_dir()`, so it cannot
    arrive from another machine — retiring the `platform.node()` comparison
    that misfired whenever macOS reported an IP-derived node name.
    """
    from lib.interpreter import recorded_interpreter_status

    name = "interpreter_freshness"
    path, reason = recorded_interpreter_status()
    if reason == "never-warmed":
        return CheckResult(name, "info", "no recorded interpreter (never warmed)")

    if reason == "ok":
        version = _recorded_interpreter_version(str(path))
        current = ren_paths.current_plugin_cache_version()
        if current is not None and version not in ("unknown", current):
            return CheckResult(
                name, "warn",
                f"recorded interpreter is from {version}, current is {current} — "
                f"re-run /ren:update to re-warm",
            )
        return CheckResult(name, "ok", f"recorded interpreter valid ({version})")

    recorded = ""
    try:
        data = json.loads(ren_paths.interpreter_record_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            recorded = str(data.get("interpreter") or "")
    except (OSError, ValueError):
        pass
    version = _recorded_interpreter_version(recorded)
    detail = {
        "gone": "recorded interpreter is gone",
        "not-python": "recorded interpreter path is not a python binary",
        "not-executable": "recorded interpreter is not executable",
    }[reason]
    return CheckResult(
        name, "warn",
        f"{detail} (version {version}) — the wake-up fast path is degraded to "
        f"cold uv; re-run /ren:update to re-warm",
    )


_ALL_CHECK_NAMES: tuple[str, ...] = (
    "check_env",
    "check_wiki_structure",
    "check_frontmatter",
    "check_schema_versions",
    "check_budget_lint",
    "check_dangling_pointers",
    "check_hub_convention",
    "check_graphify_status",
    "check_companions",
    "check_backup_configured",
    "check_execution_tiers",
    "check_global_drift",
    "check_harness_neutrality",
    "check_guard_health",
    "check_suggestion_store",
    "check_apply_integrity",
    "check_judge_health",
    "check_archive_integrity",
    "check_routing_audit",
    "check_model_map_staleness",
    "check_orphaned_projects",
    "check_execution_doctrine",
    "check_standing_instructions_drift",
    "check_agent_shadowing",
    "check_cache_env_hygiene",
    "check_interpreter_freshness",
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
    "check_hub_convention",
    "check_graphify_status",
    "check_companions",
    "check_backup_configured",
    "check_execution_tiers",
    "check_global_drift",
    "check_harness_neutrality",
    "check_guard_health",
    "check_apply_integrity",
    "check_judge_health",
    "check_archive_integrity",
    "check_routing_audit",
    "check_model_map_staleness",
    "check_orphaned_projects",
    "check_execution_doctrine",
    "check_standing_instructions_drift",
    "check_agent_shadowing",
    "check_cache_env_hygiene",
    "check_interpreter_freshness",
    "run_checks",
]
