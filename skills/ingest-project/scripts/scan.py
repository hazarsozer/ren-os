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
import json
import sys
from pathlib import Path

SCHEMA_VERSION = 1


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
