"""
lib.doctrine.loader — G11 instruction activation model (Task 7.1, RenOS 0.2
Phase 7).

Spec §3.3: "hierarchical instruction layer... with an activation model": each
doctrine file under `doctrine/` declares one of three activation modes in its
frontmatter so rules reliably fire instead of rotting in a flat, always-loaded
file (the Cursor paid-lesson the council cited):

  - `always-on` — always included (`active_for` always returns it).
  - `glob-scoped` — included only when at least one file in the current
    working set matches its `scope_glob` (fnmatch). REQUIRES a non-null
    `scope_glob`.
  - `agent-pulled` — never auto-included by `active_for`; only reachable via
    `pull(name)`, an explicit on-demand fetch (e.g. an agent decides it needs
    the cadence matrix only when actually doing loop/routine work).

Never raises on a malformed doctrine file: an unknown `activation` value, a
missing frontmatter block, or a `glob-scoped` file missing its required
`scope_glob` are all skipped with a warning on stderr rather than crashing
`load_all` for every other (valid) file.
"""

from __future__ import annotations

import fnmatch
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_VALID_ACTIVATIONS = frozenset({"always-on", "glob-scoped", "agent-pulled"})

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)


@dataclass(frozen=True)
class DoctrineFile:
    path: Path
    activation: str
    scope_glob: str | None
    body: str


def _default_doctrine_root() -> Path:
    """Resolve the plugin's `doctrine/` dir: `$CLAUDE_PLUGIN_ROOT/doctrine` if
    set, else `<repo root>/doctrine` (this file lives at
    `lib/doctrine/loader.py`, so `parents[2]` is the repo root — same depth
    convention `hooks/wake-up/ren-wake-up.py` uses for its own root lookup)."""
    val = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    if val:
        return Path(os.path.expanduser(os.path.expandvars(val))) / "doctrine"
    return Path(__file__).resolve().parents[2] / "doctrine"


def _split_frontmatter(text: str) -> tuple[str, str]:
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return "", text
    return match.group(1), text[match.end():]


def _frontmatter_field(frontmatter_content: str, field: str) -> str | None:
    """Minimal frontmatter field reader (same small local shape used
    elsewhere in this codebase — provenance.py/semantics.py/quarantine.py/
    promotion.py all have their own copy; on the Phase 9 hygiene list to
    collapse into one shared helper, per the team lead's note)."""
    prefix = f"{field}:"
    for line in frontmatter_content.splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            value = stripped[len(prefix):].strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            if value == "" or value.lower() == "null":
                return None
            return value
    return None


def _warn(path: Path, message: str) -> None:
    print(f"WARNING: doctrine loader skipping {path}: {message}", file=sys.stderr)


def load_all(doctrine_root: Path | None = None) -> list[DoctrineFile]:
    """Parse every `*.md` directly under `doctrine_root` (default: the
    plugin's `doctrine/` dir) into a `DoctrineFile`.

    Never raises. A file with no frontmatter, an unrecognized `activation`
    value, or `activation: glob-scoped` with no `scope_glob` is skipped with
    a warning on stderr — every other valid file still loads.
    """
    root = Path(doctrine_root) if doctrine_root is not None else _default_doctrine_root()
    if not root.is_dir():
        return []

    files: list[DoctrineFile] = []
    for path in sorted(root.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        frontmatter, body = _split_frontmatter(text)
        if not frontmatter:
            _warn(path, "no YAML frontmatter block")
            continue

        activation = _frontmatter_field(frontmatter, "activation")
        if activation not in _VALID_ACTIVATIONS:
            _warn(path, f"unknown activation {activation!r}; must be one of {sorted(_VALID_ACTIVATIONS)}")
            continue

        scope_glob = _frontmatter_field(frontmatter, "scope_glob")
        if activation == "glob-scoped" and scope_glob is None:
            _warn(path, "activation is 'glob-scoped' but scope_glob is missing/null")
            continue

        files.append(DoctrineFile(path=path, activation=activation, scope_glob=scope_glob, body=body))

    return files


def active_for(cwd_files: list[str], doctrine_root: Path | None = None) -> list[DoctrineFile]:
    """Return the doctrine files that should be active given `cwd_files` (a
    list of file paths/globs describing the current working set).

    `always-on` files are always included. `glob-scoped` files are included
    iff at least one entry in `cwd_files` fnmatches their `scope_glob`.
    `agent-pulled` files are NEVER auto-included — only `pull()` reaches them.
    """
    active: list[DoctrineFile] = []
    for doc in load_all(doctrine_root):
        if doc.activation == "always-on":
            active.append(doc)
        elif doc.activation == "glob-scoped":
            if any(fnmatch.fnmatch(cf, doc.scope_glob) for cf in cwd_files):
                active.append(doc)
        # agent-pulled: intentionally excluded
    return active


def pull(name: str, doctrine_root: Path | None = None) -> DoctrineFile:
    """Explicitly fetch one doctrine file by filename stem (e.g.
    `"cadence-matrix"` for `cadence-matrix.md`), regardless of its
    activation mode. Raises `KeyError` if no such file loads successfully."""
    for doc in load_all(doctrine_root):
        if doc.path.stem == name:
            return doc
    raise KeyError(name)


__all__ = ["DoctrineFile", "load_all", "active_for", "pull"]
