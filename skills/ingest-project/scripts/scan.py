#!/usr/bin/env python3
"""
scan.py — read-only project scanner for /ren:ingest-project.

Walks an existing project directory and emits a bounded, structured facts JSON
on stdout. The LLM (per references/page-mapping.md) turns those facts into a
populated ADR-014 sub-wiki; this script only collects facts.

INVARIANTS:
  - NO writes. Every file is opened read-only; nothing in the project is
    created, modified, or deleted.
  - NO network. Pure local filesystem + read-only git subprocess reads.
  - Bounded. Tree depth/entry caps, git summarized, code-skim capped, large
    and sensitive files never read.
  - Tolerant. A project with no git, no README, or no manifest still scans.

Usage:
    python3 scan.py [PATH] [--depth standard|light|deep]

Exit codes:
    0 — scan succeeded (a non-project path is still success: looks_like_project=false)
    2 — invocation error (bad args / path missing)
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path

SCHEMA_VERSION = 1

MAX_READ_BYTES = 256 * 1024  # never open a file larger than this

SKIP_DIRS = frozenset(
    {
        ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
        "target", "vendor", ".next", "coverage", ".idea", ".pytest_cache",
        ".mypy_cache", ".ruff_cache", ".gradle", ".tox", "site-packages",
    }
)

# Never read these (secret/credential/binary-ish), even if tracked.
NEVER_READ_GLOBS = (
    ".env", ".env.*", "*.pem", "*.key", "id_rsa", "id_rsa.*", "id_ed25519",
    "credentials", "credentials.*", "*.sqlite", "*.sqlite3", "*.db",
    "*.p12", "*.pfx", "*.keystore", "*.jks",
)


def _framework_version() -> str:
    """Best-effort framework version for page frontmatter. Imports lib.sf_paths
    from the plugin root; falls back to '1.0.0' in a bare checkout. Read-only."""
    try:
        plugin_root = Path(__file__).resolve().parents[3]  # scripts→ingest-project→skills→<plugin>
        if str(plugin_root) not in sys.path:
            sys.path.insert(0, str(plugin_root))
        from lib.sf_paths import framework_version
        return framework_version()
    except Exception:
        return "1.0.0"


def _is_never_read(name: str) -> bool:
    return any(fnmatch.fnmatch(name, g) for g in NEVER_READ_GLOBS)


def _safe_size(path: Path) -> bool:
    """Return True if path's size is within MAX_READ_BYTES; False on stat error."""
    try:
        return path.stat().st_size <= MAX_READ_BYTES
    except OSError:
        return False


def _git_tracked_files(root: Path) -> list[Path] | None:
    """Return tracked files via `git ls-files`, or None if not a git repo."""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=str(root), capture_output=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    out = proc.stdout.decode("utf-8", errors="replace")
    rels = [r for r in out.split("\0") if r]
    # A git repo with ZERO commits returns rc=0 + EMPTY stdout here. Return None
    # (→ enumerate_files falls back to _walk_files), NOT [] ("no files") — else a
    # freshly `git init`-ed, uncommitted project scans as empty.
    # Bare repos also return rc=0 + empty output -> None -> walk fallback; walking
    # a bare repo's object store is noisy but harmless (looks_like_project handles it).
    if not rels:
        return None
    return [root / r for r in rels]


def _walk_files(root: Path) -> list[Path]:
    """Fallback enumeration for non-git dirs: os.walk with skip-dir pruning."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            found.append(Path(dirpath) / fn)
    return found


def enumerate_files(root: Path) -> list[Path]:
    """Enumerate readable project files, respecting .gitignore (in git repos),
    skip-dirs, never-read globs, and the size cap. Read-only.
    """
    candidates = _git_tracked_files(root)
    if candidates is None:
        candidates = _walk_files(root)
    out: list[Path] = []
    for p in candidates:
        # Any path component in SKIP_DIRS → drop (covers git submodule edge cases).
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts[:-1]):
            continue
        if _is_never_read(p.name):
            continue
        if not p.is_file():
            continue
        if not _safe_size(p):
            continue
        out.append(p)
    return out


def scan(path: str, *, depth: str = "standard") -> dict:
    """Scan a project directory and return the facts dict.

    Never writes. Never raises on a readable-but-empty dir — returns
    looks_like_project=false instead.
    """
    root = Path(path).expanduser().resolve()
    facts: dict = {
        "schema_version": SCHEMA_VERSION,
        "scanned_path": str(root),
        "looks_like_project": False,
        "framework_version": _framework_version(),
        "warnings": [],
    }
    if not root.is_dir():
        facts["warnings"].append(f"path is not a directory: {root}")
        return facts
    # Remaining sections are filled by later tasks.
    return facts


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scan.py",
        description="Read-only project scanner for /ren:ingest-project.",
    )
    p.add_argument("path", nargs="?", default=".", help="project directory (default: cwd)")
    p.add_argument(
        "--depth",
        choices=["light", "standard", "deep"],
        default="standard",
        help="extraction depth (default: standard)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    target = Path(args.path).expanduser()
    if not target.exists():
        sys.stderr.write(f"scan.py: path does not exist: {target}\n")
        return 2
    facts = scan(str(target), depth=args.depth)
    try:
        sys.stdout.write(json.dumps(facts, indent=2) + "\n")
        sys.stdout.flush()
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except OSError:
            pass
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
