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

FIX (Task 9.3, holistic-review CRITICAL finding — one-door violation): every
stamped FILE now goes through `lib.memory.write_apply.apply_write`, not a raw
`Path.write_text`. Directories (`create_if_missing`) still get created
directly — they aren't pages, there's nothing to journal. The founding pages
(`index.md`, `log.md`, `identity.md`, ...) are no less "real wiki writes" than
anything `/ren:pin` produces; the invariant "every wiki write is journaled" has
to hold for them too, ESPECIALLY `log.md` — a friend's very first wiki event
belongs in the append-only log the same way every later one will.

Why this doesn't need queue diff-approval on top: the explicit human
`/ren:install` invocation (or `/ren:bootstrap-project`) IS the approval — a
friend running install is already saying "yes, set up my wiki." What's
missing without `write_apply` isn't consent, it's PROVENANCE: without it, the
founding pages have no `write_id`, no snapshot, no revert path, and no scrub
pass — exactly the gap the reviewer's failure scenario (`revert()` on
`index.md` raising `KeyError` because there was never a journal line for it)
demonstrated. So: `writer="human"`, `op="ADD"` (`copy_if_missing` never
overwrites, so it's always a fresh write from `write_apply`'s point of view),
synthetic provenance stamped via `new_provenance` per file.

One consequence worth calling out: `write_apply.apply_write` resolves its
target path against `ren_paths.wiki_root()` internally (never against an
arbitrary `target_root` argument) — so `target_root` passed to
`stamp_skeleton` MUST resolve to the same path as `ren_paths.wiki_root()` at
call time for the exists-check (which still uses `target_root`) and the
actual write (which now goes through `write_apply`, i.e. always
`wiki_root()`) to agree. Both real callers (`skills.install.lib.stamp_wiki`,
`skills.bootstrap-project.lib.bootstrap`) already pass
`target_root=ren_paths.wiki_root()` for exactly this reason; tests must set
`REN_FRAMEWORK_ROOT`/`REN_WIKI_ROOT` so `wiki_root()` resolves to the same
`tmp_path` they pass as `target_root`.

Also worth noting: `apply_write` stamps `ren_*` provenance keys onto every
written template — DESIRED, not a side effect to work around. The founding
pages get real `write_id`s like everything else; template-content tests that
assert exact byte-for-byte template output need to strip the `ren_*`
frontmatter lines before comparing (the additive-contract tests — "does an
existing file survive untouched" — are unaffected; they never re-render an
existing file in the first place).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from lib.memory import locks, write_apply
from lib.memory.provenance import new_provenance

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
    path_prefix: str = "",
) -> StampResult:
    """Stamp one manifest profile's entries from `skeleton_root` into `target_root`.

    `skeleton_root` is a directory containing `manifest.yaml` plus the
    template files its entries reference (e.g. `wiki-skeleton/`).
    `target_root` is the friend's wiki root (e.g. `~/.renos/wiki`).

    `path_prefix` (default `""`, i.e. no-op) is prepended to every entry's
    `path` when resolving the on-disk target and the page passed to
    `write_apply` — used by `skills.bootstrap-project` to stamp the `project`
    profile's manifest-relative paths (e.g. `"overview.md"`) under
    `projects/<slug>/` while `target_root` stays `ren_paths.wiki_root()`
    (see module docstring on why `target_root` must always agree with
    `wiki_root()`). `StampResult.written`/`.skipped` still report the
    manifest's un-prefixed `path`, matching the `master`/`venture` profiles'
    existing (unprefixed) behavior.

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
        rel_path = f"{path_prefix}{path}"
        rule = entry["write_rule"]
        target = target_root / rel_path

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
        rendered = _substitute(template_text, bound, rel_path, result.warnings)
        target.parent.mkdir(parents=True, exist_ok=True)
        # One-door invariant (Task 9.3 FIX 1): founding pages go through
        # write_apply so they carry provenance, a journal line, a snapshot,
        # and the scrub pass — /ren:install's explicit human invocation is
        # the approval; write_apply supplies everything else.
        prov = new_provenance(
            writer="human",
            session=os.environ.get(locks.SESSION_ID_ENV, "install"),
            op="ADD",
            page=rel_path,
        )
        write_apply.apply_write(rel_path, rendered, prov)
        result.written.append(path)

    return result


__all__ = ["StampResult", "stamp_skeleton"]
