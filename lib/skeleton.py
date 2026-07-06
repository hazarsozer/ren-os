"""lib.skeleton — manifest-driven wiki-skeleton stamping (additive-never-overwrite).

RenOS ships the wiki skeleton's templates + manifest as pure data under
`wiki-skeleton/` (see `wiki-skeleton/README.md`). This module is the one place
that reads `manifest.yaml` and stamps a profile's entries into a friend's wiki
root. Ported from startup-framework's wiki-skeleton, whose loader logic lived
only as a procedure description (`skills/install/references/stage-5-wiki-bootstrap.md`)
rather than shippable code — RenOS separates code from templates, so the
procedure is implemented here instead of re-described per skill.

The load-bearing contract, unchanged from the donor: `copy_if_missing` writes
a target file only if it does not already exist; `create_if_missing` makes a
target directory only if absent; `never_write` entries are always skipped.
Existing paths are NEVER overwritten and NEVER diffed for auto-merge — the
loader only reports them as already present.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


@dataclass(frozen=True)
class StampResult:
    """Outcome of one `stamp_skeleton` call."""

    written: list[str] = field(default_factory=list)
    """Manifest `path` values that were newly written this call."""

    skipped: list[str] = field(default_factory=list)
    """Manifest `path` values already present (files) or already existing
    (directories), or `never_write` entries — never touched."""

    warnings: list[str] = field(default_factory=list)
    """One entry per unresolved `{{placeholder}}` left in a written file,
    formatted as `"<path>: missing {{<placeholder>}}"`."""


def _substitute(text: str, placeholders: dict[str, str], path: str, warnings: list[str]) -> str:
    """Replace every `{{var}}` with its bound value. Missing bindings are left
    as the literal placeholder and recorded in `warnings` — never silently
    dropped to an empty string."""

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in placeholders:
            return placeholders[key]
        warnings.append(f"{path}: missing {{{{{key}}}}}")
        return match.group(0)

    return _PLACEHOLDER_RE.sub(repl, text)


def stamp_skeleton(
    *,
    skeleton_root: Path,
    target_root: Path,
    profile: str = "master",
    placeholders: dict[str, str] | None = None,
) -> StampResult:
    """Stamp one manifest profile's entries from `skeleton_root` into `target_root`.

    `skeleton_root` is a directory containing `manifest.yaml` plus the
    template files its entries reference (e.g. `wiki-skeleton/`).
    `target_root` is the friend's wiki root (e.g. `~/.renos/wiki`).

    Never overwrites an existing path — see module docstring for the
    per-write_rule contract. Directories are created with `parents=True` so a
    manifest entry can target a nested path without a preceding directory
    entry.
    """
    manifest = yaml.safe_load((skeleton_root / "manifest.yaml").read_text(encoding="utf-8"))
    try:
        entries = manifest["profiles"][profile]["entries"]
    except KeyError as exc:
        raise KeyError(f"unknown manifest profile {profile!r}") from exc

    bound: dict[str, str] = dict(placeholders or {})
    bound.setdefault("today", date.today().isoformat())

    result = StampResult()
    for entry in entries:
        path = entry["path"]
        rule = entry["write_rule"]
        target = target_root / path

        if rule == "never_write":
            result.skipped.append(path)
            continue

        if entry["type"] == "directory":
            if target.exists():
                result.skipped.append(path)
                continue
            target.mkdir(parents=True, exist_ok=True)
            result.written.append(path)
            continue

        # entry["type"] == "file", rule == "copy_if_missing"
        if target.exists():
            result.skipped.append(path)
            continue

        template_text = (skeleton_root / entry["template"]).read_text(encoding="utf-8")
        rendered = _substitute(template_text, bound, path, result.warnings)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
        result.written.append(path)

    return result


__all__ = ["StampResult", "stamp_skeleton"]
