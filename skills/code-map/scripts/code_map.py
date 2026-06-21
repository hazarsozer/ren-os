#!/usr/bin/env python3
"""CLI entrypoint for /ren:code-map. Generates / refreshes / checks a project's code-map."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from lib import sf_paths  # noqa: E402
from lib.codemap import check_staleness, generate, load_cached, load_fresh  # noqa: E402
from lib.codemap.adapter_leanctx import EngineUnavailable  # noqa: E402

INSTALL_HINT = ("lean-ctx is not installed — the code-map needs it. "
                "Install it, then re-run /ren:code-map (see /ren:doctor).")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="code_map.py", description="Generate or check a project code-map.")
    ap.add_argument("path", nargs="?", default=".")
    ap.add_argument("--name", required=True, help="kebab project name (cache key)")
    ap.add_argument("--refresh", action="store_true", help="regenerate even if a cache exists")
    ap.add_argument("--deps", action="store_true",
                    help="show the module dependency graph (auto-refreshes if stale)")
    args = ap.parse_args(argv)
    project_root = Path(args.path)

    if args.deps:
        cm = load_fresh(args.name, project_root)
        if cm is None:
            print(INSTALL_HINT + " Run /ren:code-map first.")
            return 0
        edges = sum(len(v) for v in cm.dependencies.values())
        files = len(cm.dependencies)
        print(f"DEPENDENCIES ({edges} edges across {files} files) — auto-refreshed")
        for src in sorted(cm.dependencies):
            print(f"  {src} → {', '.join(sorted(cm.dependencies[src]))}")
        return 0

    # Cache exists and not refreshing -> surface staleness instead of regenerating.
    if not args.refresh and load_cached(args.name) is not None:
        report = check_staleness(args.name, project_root)
        if report and report.stale:
            print(f"⚠ STALE — code-map for '{args.name}' is out of date "
                  f"(changed={list(report.changed)} added={list(report.added)} "
                  f"deleted={list(report.deleted)}). Run /ren:code-map --refresh.")
        else:
            print(f"Code-map for '{args.name}' is fresh: {sf_paths.code_map_path(args.name)}")
        return 0

    try:
        cm = generate(project_root, project_name=args.name)
    except EngineUnavailable:
        print(INSTALL_HINT)
        return 0  # graceful: absence is not a failure
    print(f"Code-map written: {sf_paths.code_map_path(args.name)} ({len(cm.symbols)} symbols)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
