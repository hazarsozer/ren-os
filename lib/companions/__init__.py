"""Companion registry + reconciler (0.3.5 "companions on board").

SSOT for the recommended-companions list. ``doctrine/companions.md`` stays
the human-facing prose; a hygiene test keeps the two in sync. Detection is
best-effort and read-only. Choices persist at ``state_dir()/companions.json``
(.ren state, NOT a wiki page — direct atomic writes, same as install.json).

The reconciliation contract: a companion is offered iff it is not installed
AND has no recorded decision. Declines are durable — never re-nag.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from lib import ren_paths

CHOICES_FILENAME = "companions.json"
_DECISIONS = ("accepted", "declined")


@dataclass(frozen=True)
class Companion:
    cid: str           # stable id, e.g. "graphify"
    kind: str          # "tool" (uv/PATH binary) | "plugin" (Claude Code plugin)
    title: str
    pitch: str         # one line: why a friend would want it
    install_hint: str  # human-facing install command / instruction
    detect: str        # tool: binary name for shutil.which; plugin: cache dir name
    added_in: str      # framework version whose registry first listed it


REGISTRY: tuple[Companion, ...] = (
    Companion(
        cid="graphify",
        kind="tool",
        title="Graphify",
        pitch="structural code maps for /ren:code-map (pinned 0.9.x)",
        install_hint="uv tool install graphifyy",
        detect="graphify",
        added_in="0.3.5",
    ),
    Companion(
        cid="markitdown",
        kind="tool",
        title="markitdown",
        pitch="convert PDF/DOCX/PPTX/HTML sources to markdown for wiki ingest",
        install_hint='uv tool install "markitdown[all]"',
        detect="markitdown",
        added_in="0.3.5",
    ),
    Companion(
        cid="yt-dlp",
        kind="tool",
        title="yt-dlp",
        pitch="YouTube auto-captions for video ingest (markitdown's YouTube path is unreliable)",
        install_hint="uv tool install yt-dlp",
        detect="yt-dlp",
        added_in="0.3.5",
    ),
    Companion(
        cid="superpowers",
        kind="plugin",
        title="Superpowers",
        pitch="process skills for planning, TDD, and debugging (brainstorming, writing-plans)",
        install_hint="/plugin install superpowers@claude-plugins-official — then restart the session to activate",
        detect="superpowers",
        added_in="0.3.5",
    ),
)


def is_installed(companion: Companion) -> bool:
    """Best-effort presence check. Never raises."""
    if companion.kind == "tool":
        return shutil.which(companion.detect) is not None
    if companion.kind == "plugin":
        cache = ren_paths.claude_user_dir() / "plugins" / "cache"
        if not cache.is_dir():
            return False
        return any(p.is_dir() for p in cache.glob(f"*/{companion.detect}"))
    return False


def _choices_path() -> Path:
    return ren_paths.state_dir() / CHOICES_FILENAME


def load_choices() -> dict:
    """Recorded accept/decline choices; {} when absent or unreadable."""
    try:
        return json.loads(_choices_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def record_choice(cid: str, decision: str) -> None:
    """Durably record an in-chat accept/decline. Atomic write.

    Last-writer-wins under concurrent sessions (read-modify-write without a lock) —
    acceptable for a single-user tool; do not add locking without a demonstrated need.
    """
    if decision not in _DECISIONS:
        raise ValueError(f"decision must be one of {_DECISIONS}, got {decision!r}")
    if cid not in {c.cid for c in REGISTRY}:
        raise ValueError(f"unknown companion id: {cid!r}")
    choices = load_choices()
    choices[cid] = {
        "decision": decision,
        "offered_at_version": ren_paths.framework_version(),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    path = _choices_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(choices, indent=2), encoding="utf-8")
    os.replace(tmp, path)


@dataclass(frozen=True)
class Offer:
    companion: Companion
    installed: bool
    decision: str | None  # prior recorded decision, or None if never decided


def reconcile() -> list[Offer]:
    """Full registry state: (companion, installed?, prior decision)."""
    choices = load_choices()
    return [
        Offer(c, is_installed(c), choices.get(c.cid, {}).get("decision"))
        for c in REGISTRY
    ]


def pending_offers() -> list[Offer]:
    """The delta worth asking about: absent AND undecided."""
    return [o for o in reconcile() if not o.installed and o.decision is None]
