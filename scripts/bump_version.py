#!/usr/bin/env python3
"""Version SSOT — bump script + site inventory.

`.claude-plugin/plugin.json` `"version"` is the single source of truth. Every
other version-bearing site in the repo must agree with it; this script both
rewrites all of them in one pass and exposes the site list so a hygiene test
can catch drift on any commit, not just release day.

Usage
-----
    uv run python scripts/bump_version.py 0.3.0

Refuses non-semver arguments (must match `X.Y.Z`, digits only).

Sites covered
-------------
- `.claude-plugin/plugin.json` `"version"` (the SSOT)
- `pyproject.toml` `version = "..."`
- `lib/ren_paths.py` `FALLBACK_FRAMEWORK_VERSION = "..."`
- `skills/interview/lib/__init__.py` `FRAMEWORK_VERSION = "..."`
- `skills/ingest-project/lib/scan.py` `return "..."` fallback (the historical
  docstring prose mentioning the version is intentionally left untouched —
  only the literal return value is a live site)
- `README.md` version badge
- every `skills/*/SKILL.md` `version:` and `framework_version:` frontmatter
  fields

Stdlib only — runs anywhere Python 3.11+ runs.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

# (relative path, pattern). Each pattern's group(0) must contain group(1)
# (the version substring) exactly once, so a plain string-replace on the
# matched span is a safe, formatting-preserving rewrite.
_FIXED_SITES: tuple[tuple[str, re.Pattern], ...] = (
    (".claude-plugin/plugin.json", re.compile(r'"version": "(\d+\.\d+\.\d+)"')),
    ("pyproject.toml", re.compile(r'^version = "(\d+\.\d+\.\d+)"', re.MULTILINE)),
    ("lib/ren_paths.py", re.compile(r'^FALLBACK_FRAMEWORK_VERSION = "(\d+\.\d+\.\d+)"', re.MULTILINE)),
    ("skills/interview/lib/__init__.py", re.compile(r'^FRAMEWORK_VERSION = "(\d+\.\d+\.\d+)"', re.MULTILINE)),
    ("skills/ingest-project/lib/scan.py", re.compile(r'return "(\d+\.\d+\.\d+)"')),
    ("README.md", re.compile(r'version-(\d+\.\d+\.\d+)-e34234')),
)

_SKILL_VERSION_RE = re.compile(r'^version: (\d+\.\d+\.\d+)$', re.MULTILINE)
_SKILL_FRAMEWORK_VERSION_RE = re.compile(r'^framework_version: "(\d+\.\d+\.\d+)"$', re.MULTILINE)


def _skill_mds(root: Path) -> list[Path]:
    return sorted((root / "skills").glob("*/SKILL.md"))


def version_sites(root: Path) -> list[tuple[str, str]]:
    """Return (site-label, found-version) for every version-bearing site.

    SKILL.md files contribute two entries (one per field), labeled
    `<path>#version` / `<path>#framework_version` so both are distinguishable
    and traceable back to a file.
    """
    root = Path(root)
    sites: list[tuple[str, str]] = []

    for rel_path, pattern in _FIXED_SITES:
        path = root / rel_path
        text = path.read_text(encoding="utf-8")
        match = pattern.search(text)
        if not match:
            raise ValueError(f"version pattern not found in {rel_path}")
        sites.append((rel_path, match.group(1)))

    for skill_md in _skill_mds(root):
        text = skill_md.read_text(encoding="utf-8")
        rel = str(skill_md.relative_to(root))

        match = _SKILL_VERSION_RE.search(text)
        if not match:
            raise ValueError(f"version: field not found in {rel}")
        sites.append((f"{rel}#version", match.group(1)))

        match = _SKILL_FRAMEWORK_VERSION_RE.search(text)
        if not match:
            raise ValueError(f"framework_version: field not found in {rel}")
        sites.append((f"{rel}#framework_version", match.group(1)))

    return sites


def _sub_once(text: str, pattern: re.Pattern, new_version: str, label: str) -> str:
    def _replace(match: re.Match) -> str:
        return match.group(0).replace(match.group(1), new_version)

    new_text, count = pattern.subn(_replace, text, count=1)
    if count == 0:
        raise ValueError(f"version pattern not found: {label}")
    return new_text


def main(new_version: str, root: Path | None = None) -> list[str]:
    """Rewrite every version-bearing site to `new_version`. Returns the list
    of rewritten file paths. Raises ValueError on a non-semver argument or a
    missing site."""
    if not SEMVER_RE.match(new_version):
        raise ValueError(f"'{new_version}' is not a valid semver (expected X.Y.Z)")

    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    changed: list[str] = []

    for rel_path, pattern in _FIXED_SITES:
        path = root / rel_path
        text = _sub_once(path.read_text(encoding="utf-8"), pattern, new_version, rel_path)
        path.write_text(text, encoding="utf-8")
        changed.append(str(path))

    for skill_md in _skill_mds(root):
        rel = str(skill_md.relative_to(root))
        text = skill_md.read_text(encoding="utf-8")
        text = _sub_once(text, _SKILL_VERSION_RE, new_version, f"{rel}#version")
        text = _sub_once(text, _SKILL_FRAMEWORK_VERSION_RE, new_version, f"{rel}#framework_version")
        skill_md.write_text(text, encoding="utf-8")
        changed.append(str(skill_md))

    return changed


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: bump_version.py X.Y.Z", file=sys.stderr)
        sys.exit(2)
    try:
        rewritten = main(sys.argv[1])
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"bumped {len(rewritten)} site(s) to {sys.argv[1]}")
