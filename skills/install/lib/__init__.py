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

This module owns the state-inspection + two small write primitives the
SKILL.md flow calls; interview and identity-page RENDERING live in
`skills.interview.lib` (a separate producer, same as pin/wrap/promotion are
separate from each other).
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from lib import ren_paths
from lib.adapter.claude_md import MARKER_BEGIN, MARKER_END
from lib.ren_paths import claude_user_dir
from lib.skeleton import StampResult, stamp_skeleton
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
    "l2_maps", "installed_version", "global_claude_md"}`.
    """
    root = Path(wiki_root) if wiki_root is not None else ren_paths.wiki_root()

    wiki_stamped = (root / "index.md").is_file()
    identity_present = (root / "identity.md").is_file()

    try:
        configured = backup_configured(root)
    except Exception:  # noqa: BLE001 - install_state must never raise
        configured = False

    l2_maps = 0
    if root.is_dir():
        for md_path in root.rglob("*.md"):
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
    }


def stamp_wiki(profile: str = "master") -> StampResult:
    """Thin call into `lib.skeleton.stamp_skeleton` for the `profile` (default
    `"master"`) manifest against the real wiki root. Additive-only per that
    module's contract — a second call is a no-op (everything already present
    reports as `skipped`, nothing is overwritten)."""
    skeleton_root = Path(__file__).resolve().parents[3] / "wiki-skeleton"
    return stamp_skeleton(
        skeleton_root=skeleton_root,
        target_root=ren_paths.wiki_root(),
        profile=profile,
        placeholders={"name": "Friend", "handle": "friend"},
    )


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


__all__ = ["QUESTION_BUDGET", "install_state", "stamp_wiki", "record_install"]
