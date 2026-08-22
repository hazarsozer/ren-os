"""
skills.install library — internal implementation for /ren:install (Task 8.1,
RenOS 0.2 Phase 8).

Spec §3.8: "idempotent guided install; first-session walkthrough." Donor
`skills/install/` implements idempotency via a 7-stage flow driven by an
`InstallSimulator` test harness (~1702 LOC, mostly the simulator). RenOS 0.2
keeps donor's CORE IDEA — idempotency by inspecting REAL on-disk state, so
re-running the guided flow just skips whatever's already done — without the
simulator: `install_state()` reads the actual wiki (skeleton markers, the
identity page, `skills.backup`'s own configured-check, the recorded install
version) directly, no fake filesystem needed. The 7-stage donor flow (env,
required plugins, conditional plugins, identity, wiki bootstrap, doctor
verify, walkthrough) also collapses to 6 stages here — RenOS ships as one
plugin, not several, so donor's "required/conditional plugins" negotiation
stages don't apply.

This module owns the state-inspection + three small write primitives the
SKILL.md flow calls; interview and identity-page RENDERING live in
`skills.interview.lib` (a separate producer, same as pin/wrap/promotion are
separate from each other).
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from lib import ren_paths
from lib.adapter.claude_md import MARKER_BEGIN, MARKER_END
from lib.companions import CHOICES_FILENAME
from lib.ren_paths import claude_user_dir
from lib.skeleton import (
    StampResult,
    stamp_skeleton,
    wiki_populated_reason,
    wiki_stamped as _wiki_stamped,
)
from skills.backup.lib import backup_configured

QUESTION_BUDGET = 10
"""Hard cap on interview questions (spec §3.8's "explicit question budget").
Owned here (not in skills.interview.lib) because install is what enforces
the "system must work with ZERO user-authored doctrine" guarantee end to
end — the budget is part of THAT guarantee, not interview's alone."""

INSTALL_STATE_FILENAME = "install.json"

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)


def _frontmatter_type(text: str) -> str | None:
    """Minimal frontmatter `type:` reader (same small local shape used
    across this codebase — see the running Phase-9-hygiene note in
    provenance.py/semantics.py/quarantine.py/promotion.py/lib.doctrine.loader/
    lib.portability.agents_surface)."""
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return None
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if stripped.startswith("type:"):
            value = stripped[len("type:"):].strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            return value or None
    return None


def _install_state_path() -> Path:
    return ren_paths.state_dir() / INSTALL_STATE_FILENAME


def install_state(wiki_root: Path | None = None) -> dict:
    """Read REAL on-disk install state — never raises; every field degrades
    to its "not done yet" value on any read error, so a corrupt/missing file
    never blocks the guided flow from re-running the affected stage.

    Returns `{"wiki_stamped", "identity_present", "backup_configured",
    "l2_maps", "installed_version", "global_claude_md", "companions_recorded"}`.
    """
    root = Path(wiki_root) if wiki_root is not None else ren_paths.wiki_root()

    wiki_stamped = _wiki_stamped(root)
    identity_present = (root / "identity.md").is_file()

    try:
        configured = backup_configured(root)
    except Exception:  # noqa: BLE001 - install_state must never raise
        configured = False

    # Only project maps count — the master index.md is itself `type: l2-map`
    # (it IS the wiki's own map) and must not read as "a project exists"
    # on a fresh install (dogfood finding F3, 2026-07-07).
    l2_maps = 0
    projects_dir = root / "projects"
    if projects_dir.is_dir():
        for md_path in projects_dir.rglob("*.md"):
            try:
                text = md_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if _frontmatter_type(text) == "l2-map":
                l2_maps += 1

    installed_version = None
    install_json = _install_state_path()
    if install_json.is_file():
        try:
            data = json.loads(install_json.read_text(encoding="utf-8"))
            installed_version = data.get("version")
        except (OSError, json.JSONDecodeError):
            installed_version = None

    global_claude_md = False
    try:
        global_md = claude_user_dir() / "CLAUDE.md"
        if global_md.is_file():
            text = global_md.read_text(encoding="utf-8")
            global_claude_md = MARKER_BEGIN in text and MARKER_END in text
    except (OSError, UnicodeDecodeError):
        global_claude_md = False

    return {
        "wiki_stamped": wiki_stamped,
        "identity_present": identity_present,
        "backup_configured": configured,
        "l2_maps": l2_maps,
        "installed_version": installed_version,
        "global_claude_md": global_claude_md,
        "companions_recorded": (ren_paths.state_dir() / CHOICES_FILENAME).exists(),
    }


class PopulatedWikiError(Exception):
    """Raised by `stamp_wiki` when the target wiki already holds real content.

    There is deliberately no force flag: `stamp_skeleton` already never
    overwrites, so nothing legitimate needs to stamp INTO a populated wiki —
    the only caller that hits this is a test-drive of /ren:install pointed
    at the real wiki (the 2026-08-12 incident)."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(
            f"wiki at {ren_paths.wiki_root()} already has real content ({reason}) — "
            "bootstrap refused. To test-drive install, point REN_WIKI_ROOT at a "
            "scratch directory."
        )


def stamp_wiki(profile: str = "master") -> StampResult:
    """Thin call into `lib.skeleton.stamp_skeleton` for the `profile` (default
    `"master"`) manifest against the real wiki root. Additive-only per that
    module's contract — a second call is a no-op (everything already present
    reports as `skipped`, nothing is overwritten).

    Raises `PopulatedWikiError` before stamping anything if the wiki already
    looks populated (`lib.skeleton.wiki_populated_reason`) — the flow-level
    guard in front of `stamp_skeleton`'s own never-overwrite door (the
    2026-08-12 incident: a test run of /ren:install re-ADDed skeleton pages
    over real content)."""
    reason = wiki_populated_reason(ren_paths.wiki_root())
    if reason is not None:
        raise PopulatedWikiError(reason)

    skeleton_root = Path(__file__).resolve().parents[3] / "wiki-skeleton"
    return stamp_skeleton(
        skeleton_root=skeleton_root,
        target_root=ren_paths.wiki_root(),
        profile=profile,
        placeholders={
            "name": "Friend",
            "handle": "friend",
            "framework_version": ren_paths.framework_version(),
        },
    )


# Okabe-Ito, colour-vision-safe; tier naming is the second signal (never colour alone).
# Group order matters: Obsidian applies the first matching group, so the
# quarantine content-match outranks the path-based tiers.
DEFAULT_GRAPH_CONFIG = {
    "search": "-path:raw -path:archive",
    "colorGroups": [
        {"query": '"ren-quarantine"', "color": {"a": 1, "rgb": 0xE69F00}},   # orange: quarantined
        {"query": "file:index.md OR file:map.md", "color": {"a": 1, "rgb": 0x0072B2}},  # blue: spine
        {"query": "path:knowledge", "color": {"a": 1, "rgb": 0x009E73}},     # green: knowledge
        {"query": "path:l1", "color": {"a": 1, "rgb": 0x56B4E9}},            # sky: session narratives
    ],
    "showTags": False,
    "showAttachments": False,
    "showOrphans": True,
}


def write_default_graph_config(wiki_root_path: Path | None = None) -> bool:
    """Write .obsidian/graph.json with the default tier view — only if absent."""
    root = wiki_root_path or ren_paths.wiki_root()
    dest = root / ".obsidian" / "graph.json"
    if dest.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(DEFAULT_GRAPH_CONFIG, indent=2) + "\n", encoding="utf-8")
    return True


def record_install(version: str) -> None:
    """Record that install completed at `version`, at
    `state_dir()/install.json` (atomic temp-file + `os.replace`)."""
    path = _install_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": version,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)


INTERPRETER_STATE_FILENAME = "interpreter.json"


def _interpreter_state_path() -> Path:
    """Machine-local (0.8.3), not `state_dir()`.

    This record names an absolute interpreter path on THIS filesystem.
    `state_dir()` is under the wiki, which `/ren:backup` pushes to a remote,
    so the record used to travel to other machines and was guarded by a
    `platform.node()` comparison — a guard that broke whenever macOS returned
    an IP-derived node name. `ren_paths.machine_state_dir()` is never backed
    up, so the record cannot travel and needs no such guard.
    """
    return ren_paths.interpreter_record_path()


def _repo_root() -> Path:
    """Resolve the repo/plugin root the same way `hooks/wake-up/ren-wake-up.py`'s
    `_plugin_root()` does: prefer `$CLAUDE_PLUGIN_ROOT`, else derive it from this
    file's location (`skills/install/lib/__init__.py` -> repo root)."""
    val = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    if val:
        return Path(os.path.expanduser(os.path.expandvars(val)))
    return Path(__file__).resolve().parents[3]


def warm_environment() -> dict:
    """Warm the venv (`uv sync --frozen`) and record its real interpreter path
    to `state_dir()/interpreter.json`, so the wake-up hook's self-heal can
    re-exec directly under it instead of paying `uv run`'s cold resolution
    cost — on a fresh machine that cold path is ~7s, which trips the hook's
    `_REEXEC_TIMEOUT_S` and degrades the very first session (issue #11 §4).

    Returns `{"interpreter": <abs path>, "warmed_at": <ISO 8601 UTC>,
    "machine": <platform.node()>, "platform": <sys.platform>}`. The
    `machine`/`platform` fields let the wake-up hook's
    `_recorded_interpreter_path()` reject a foreign record: `state_dir()`
    lives under the wiki root, which may be synced/backed up across
    machines, so two machines sharing a username could otherwise collide on
    an existing-but-foreign interpreter path (fix round 1, reviewer
    IMPORTANT).

    Raises `subprocess.CalledProcessError` if `uv sync`/`uv run` fail — stage
    1 of install is expected to surface that, not swallow it. Both
    subprocess calls carry generous timeouts (raises
    `subprocess.TimeoutExpired` rather than hanging install forever) —
    `uv sync` resolves+installs the full dependency set (slower, network-
    bound), `uv run`'s one-liner just needs the already-synced venv to spin
    up.
    """
    root_path = _repo_root()
    root = str(root_path)
    # `--frozen` requires a lockfile; an install whose plugin root lacks
    # uv.lock (issue #14 — it was gitignored, so it never shipped) would
    # otherwise fail unconditionally with "Unable to find lockfile". uv.lock
    # is tracked now, but degrade to a resolving sync rather than dying if a
    # future artifact loses it again.
    sync_cmd = ["uv", "sync", "--frozen", "--project", root]
    if not (root_path / "uv.lock").is_file():
        sync_cmd = ["uv", "sync", "--project", root]
    subprocess.run(
        sync_cmd,
        check=True, capture_output=True, text=True, timeout=120,
    )
    proc = subprocess.run(
        ["uv", "run", "--project", root, "python", "-c",
         "import sys; print(sys.executable)"],
        check=True, capture_output=True, text=True, timeout=30,
    )
    interpreter = proc.stdout.strip()
    # `machine`/`platform` are diagnostics only — recorded so a human reading
    # the file knows where it came from, never compared against this machine.
    # The record is machine-local now, so there is no foreign record to detect
    # (and `platform.node()` was too unstable to detect one with anyway).
    info = {
        "interpreter": interpreter,
        "warmed_at": datetime.now(timezone.utc).isoformat(),
        "machine": platform.node(),
        "platform": sys.platform,
    }
    path = _interpreter_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(info), encoding="utf-8")
    os.replace(tmp, path)
    return info


__all__ = [
    "QUESTION_BUDGET",
    "DEFAULT_GRAPH_CONFIG",
    "PopulatedWikiError",
    "install_state",
    "stamp_wiki",
    "write_default_graph_config",
    "record_install",
    "warm_environment",
]
