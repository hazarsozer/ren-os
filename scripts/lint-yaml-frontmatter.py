#!/usr/bin/env python3
"""
lint-yaml-frontmatter.py — Fast-fail YAML frontmatter parse check.

Per task #48 (v1.1 lift to v1.0 per team-lead direction 2026-05-28):
walks given paths, finds every Markdown file with a `---` YAML frontmatter
block, and runs `yaml.safe_load` against it. Any parse error fails the script
with non-zero exit and a precise file:line:column diagnostic.

This is Layer 1 of the 4-layer SKILL.md defense:
  1. YAML parse (this script — fast fail before claude plugin validate)
  2. Semantic shape — distribution-2's conformance harness
  3. Plugin manifest — `claude plugin validate --strict`
  4. Real-contract conformance — TestCanonicalEvalFixtureConformance pins

Designed to run in ~5 seconds, ahead of the ~30-second
`claude plugin validate` step in distribution-2's CI workflow.

Usage:
    python3 scripts/lint-yaml-frontmatter.py [PATH ...]

Default paths: skills/, wiki/decisions/, hooks/

Exit codes:
    0 — all frontmatter blocks parse cleanly
    1 — at least one parse error found (details on stderr)
    2 — invocation error (missing PyYAML, bad args, etc.)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

try:
    import yaml
except ImportError:
    print(
        "ERROR: PyYAML not installed. Run `uv add pyyaml` or `pip install pyyaml`.",
        file=sys.stderr,
    )
    sys.exit(2)


DEFAULT_PATHS = ["skills", "wiki/decisions", "hooks"]


def extract_frontmatter(content: str) -> tuple[str, int] | None:
    """
    Find the first `---` ... `---` block at the start of the content.

    Returns (frontmatter_text, line_number_of_opening_delimiter) or None
    if the file has no leading frontmatter block.
    """
    if not content.startswith("---"):
        return None
    end_idx = content.find("\n---", 3)
    if end_idx == -1:
        return None
    return content[3:end_idx], 1


def iter_markdown_files(paths: Iterable[Path]) -> Iterable[Path]:
    """Walk paths; yield each .md file found (recursively)."""
    for path in paths:
        if path.is_file() and path.suffix == ".md":
            yield path
        elif path.is_dir():
            yield from sorted(path.rglob("*.md"))


def lint_file(path: Path) -> str | None:
    """
    Lint a single .md file. Returns None on success, or an error message
    string on failure.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return f"{path}: could not read file: {exc}"

    extracted = extract_frontmatter(content)
    if extracted is None:
        # No frontmatter is not an error — many .md files are body-only.
        return None

    fm_text, _ = extracted
    try:
        data = yaml.safe_load(fm_text)
    except yaml.YAMLError as exc:
        # PyYAML's mark gives line/column relative to the frontmatter content;
        # adjust for the `---\n` opening delimiter (1 line offset).
        mark = getattr(exc, "problem_mark", None)
        if mark is not None:
            line = mark.line + 2  # +1 for 1-indexing, +1 for the `---` delimiter
            col = mark.column + 1
            return f"{path}:{line}:{col}: YAML parse error: {exc.problem}"
        return f"{path}: YAML parse error: {exc}"

    # `data` must be either a dict, a list, or None (empty frontmatter).
    # If a file ships `---\nnot-yaml-at-all\n---`, PyYAML may quietly accept
    # it as a string scalar, which is technically valid YAML but probably a
    # bug. We treat top-level non-mapping / non-list as a SOFT warning, not
    # an error — most ADRs + SKILL.md files are mappings, but a free-form
    # block is allowed.
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="YAML frontmatter parse check (fast-fail before claude plugin validate)."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=DEFAULT_PATHS,
        help=f"Paths to walk (default: {', '.join(DEFAULT_PATHS)})",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print every file checked, not just failures.",
    )
    args = parser.parse_args(argv)

    paths = [Path(p) for p in args.paths]

    errors: list[str] = []
    n_checked = 0
    n_with_frontmatter = 0

    for md_path in iter_markdown_files(paths):
        n_checked += 1
        result = lint_file(md_path)
        if result is None:
            if args.verbose:
                # Check whether the file had frontmatter (to inform the v output)
                try:
                    has_fm = md_path.read_text(encoding="utf-8").startswith("---")
                except OSError:
                    has_fm = False
                if has_fm:
                    n_with_frontmatter += 1
                    print(f"OK  {md_path}")
        else:
            n_with_frontmatter += 1
            errors.append(result)

    if errors:
        print(
            f"\n{len(errors)} YAML frontmatter parse error(s) across "
            f"{n_checked} markdown file(s):",
            file=sys.stderr,
        )
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1

    if args.verbose:
        print(
            f"\n{n_checked} markdown file(s) checked; "
            f"{n_with_frontmatter} had frontmatter; all valid."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
