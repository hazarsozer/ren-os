#!/usr/bin/env python3
"""Lint guard: forbid dev-wiki content from leaking into wiki-skeleton/ templates.

The plugin ships a fresh empty skeleton — never the framework's own
development wiki content. Templates must hold only structural scaffolding
and the small placeholder-variable set documented in `wiki-skeleton/manifest.yaml`.
This lint walks every file under the known template roots and asserts no
forbidden substring appears.

Forbidden substrings are listed in `forbidden-substrings.txt` (same directory
as this script). The list is intentionally small and curated; expand it when
a PR review catches new drift.

Usage
-----
    # Default: scan every known template root in the repo
    # (wiki-skeleton/templates/, wiki-skeleton/modules/*/, skills/*/templates/)
    python3 scripts/lint_no_dev_wiki_content.py
    # exit 0 = clean, exit 1 = hits found

Or pass one or more explicit template roots:

    python3 scripts/lint_no_dev_wiki_content.py path/to/templates [more/templates ...]

Output
------
On hit: one line per match, `<file>:<line>:<column>: <substring>`.
Stdlib only — runs anywhere Python 3.11+ runs.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Hit:
    file_path: Path
    line_number: int  # 1-indexed
    column: int  # 1-indexed
    substring: str
    line_text: str


def load_forbidden_substrings(forbidden_file: Path) -> list[str]:
    """Read forbidden-substrings.txt; strip comments and blank lines; dedupe
    by case-folded form so case-variant duplicates don't produce duplicate
    hits in the report."""
    if not forbidden_file.is_file():
        raise FileNotFoundError(
            f"Forbidden-substring list not found at {forbidden_file}. "
            "This file is required; the lint refuses to run without it."
        )

    seen_lowered: set[str] = set()
    substrings: list[str] = []
    for raw in forbidden_file.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Allow quoted substrings to preserve leading/trailing whitespace.
        if (
            len(stripped) >= 2
            and stripped[0] == stripped[-1]
            and stripped[0] in {'"', "'"}
        ):
            stripped = stripped[1:-1]
        lowered = stripped.lower()
        if lowered in seen_lowered:
            continue
        seen_lowered.add(lowered)
        substrings.append(stripped)
    return substrings


def walk_templates(templates_root: Path) -> list[Path]:
    """Return every regular file under a template root. Excludes .gitkeep
    (zero-byte by convention) only when its content is empty."""
    if not templates_root.is_dir():
        raise NotADirectoryError(
            f"Templates root not found at {templates_root}."
        )

    files: list[Path] = []
    for path in sorted(templates_root.rglob("*")):
        if not path.is_file():
            continue
        # Skip empty .gitkeep markers — they hold no content to scan.
        if path.name == ".gitkeep" and path.stat().st_size == 0:
            continue
        files.append(path)
    return files


def scan_file(file_path: Path, substrings: list[str]) -> list[Hit]:
    """Case-insensitive substring scan of one file. Returns all hits."""
    hits: list[Hit] = []
    try:
        text = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Binary file inside a template root. Not expected; flag with a
        # synthetic hit so a reviewer notices.
        return [
            Hit(
                file_path=file_path,
                line_number=0,
                column=0,
                substring="<binary file in template root>",
                line_text="",
            )
        ]

    lowered_substrings = [(orig, orig.lower()) for orig in substrings]
    for line_idx, line in enumerate(text.splitlines(), start=1):
        lowered_line = line.lower()
        for original, lowered in lowered_substrings:
            start = 0
            while True:
                hit_at = lowered_line.find(lowered, start)
                if hit_at == -1:
                    break
                hits.append(
                    Hit(
                        file_path=file_path,
                        line_number=line_idx,
                        column=hit_at + 1,
                        substring=original,
                        line_text=line,
                    )
                )
                start = hit_at + max(1, len(lowered))
    return hits


def format_hits(hits: list[Hit], root: Path) -> str:
    """One line per hit, sorted by file then line then column."""
    ordered = sorted(
        hits,
        key=lambda h: (str(h.file_path), h.line_number, h.column, h.substring),
    )
    out_lines = []
    for hit in ordered:
        try:
            relative = hit.file_path.relative_to(root)
        except ValueError:
            relative = hit.file_path
        out_lines.append(
            f"{relative}:{hit.line_number}:{hit.column}: "
            f'forbidden substring "{hit.substring}" '
            f"in line: {hit.line_text.strip()[:120]}"
        )
    return "\n".join(out_lines)


def repo_root() -> Path:
    """Repo root inferred from this script's location: <repo>/scripts/…"""
    return Path(__file__).resolve().parent.parent


def discover_default_template_roots(repo: Path) -> list[Path]:
    """Default set of template directories to scan when argv is empty.

    Covers:
      - <repo>/wiki-skeleton/templates/        (master wiki skeleton)
      - <repo>/wiki-skeleton/modules/*/        (opt-in modules, e.g. venture)
      - <repo>/skills/*/templates/             (per-skill template payloads)

    Missing directories are silently skipped; the caller's empty-set warning
    handles the "scanned nothing" case.
    """
    roots: list[Path] = []
    wiki_skel = repo / "wiki-skeleton" / "templates"
    if wiki_skel.is_dir():
        roots.append(wiki_skel)
    modules_dir = repo / "wiki-skeleton" / "modules"
    if modules_dir.is_dir():
        for module in sorted(modules_dir.iterdir()):
            if module.is_dir():
                roots.append(module)
    skills_dir = repo / "skills"
    if skills_dir.is_dir():
        for skill in sorted(skills_dir.iterdir()):
            candidate = skill / "templates"
            if candidate.is_dir():
                roots.append(candidate)
    return roots


def resolve_template_roots(argv: list[str], repo: Path) -> list[Path]:
    """Argv-supplied roots win; otherwise discover defaults."""
    explicit_args = argv[1:]
    if explicit_args:
        roots: list[Path] = []
        for raw in explicit_args:
            candidate = Path(raw).resolve()
            if not candidate.is_dir():
                raise NotADirectoryError(
                    f"Explicit template root {candidate} is not a directory."
                )
            roots.append(candidate)
        return roots
    return discover_default_template_roots(repo)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    repo = repo_root()
    forbidden_file = repo / "scripts" / "forbidden-substrings.txt"
    substrings = load_forbidden_substrings(forbidden_file)

    template_roots = resolve_template_roots(argv, repo)
    if not template_roots:
        print(
            "warn: no template roots discovered. "
            "Expected wiki-skeleton/templates/ or skills/*/templates/ under the repo. "
            "The lint passed vacuously.",
            file=sys.stderr,
        )
        return 0

    all_files: list[Path] = []
    all_hits: list[Hit] = []
    for root in template_roots:
        files = walk_templates(root)
        all_files.extend(files)
        for path in files:
            all_hits.extend(scan_file(path, substrings))

    if not all_files:
        print(
            f"warn: {len(template_roots)} template root(s) scanned, no files found.",
            file=sys.stderr,
        )
        return 0

    if not all_hits:
        roots_summary = ", ".join(
            str(root.relative_to(repo)) for root in template_roots
        )
        print(
            f"ok: {len(all_files)} template file(s) across "
            f"{len(template_roots)} root(s) [{roots_summary}], "
            f"{len(substrings)} forbidden substring(s), no hits."
        )
        return 0

    print(format_hits(all_hits, repo))
    print(
        f"\nfail: {len(all_hits)} forbidden-substring hit(s) across "
        f"{len({h.file_path for h in all_hits})} file(s).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
