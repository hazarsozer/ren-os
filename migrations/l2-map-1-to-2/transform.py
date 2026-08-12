"""Body transform for l2-map 1→2 (#53). Invoked by migrate.sh with
PYTHONPATH=<repo root>. Write-temp-then-rename.

Owns its own idempotency and page-type guarding (#53 review findings 4-6) —
migrate.sh no longer greps the page itself; the whole-file grep it used to
run could false-SKIP on a BODY line that happened to read
`schema_version: 2` (e.g. quoted in a knowledge bullet), and it had no guard
at all against running on a non-l2-map page. Each guard below prints a
single `SKIP: <reason>` line to stdout and exits 0 with the file byte-
identical — none of these are transform FAILURES, so they must never trip
migrate.sh's rollback path:

  - no frontmatter block at all → not a migration candidate
  - frontmatter `type:` isn't `l2-map` → the README's promise that this
    migration never touches other page types
  - frontmatter already stamps `schema_version: 2` → idempotency

A genuine transform failure — a rewritten pointer line that doesn't
round-trip through lib.pointer — still prints to stderr, exits 1, and
leaves the page untouched.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from lib.pointer import REPO_REF_PREFIX, parse_pointer_line, render_pointer_line

TARGET_SCHEMA = 2

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def _frontmatter_block(text: str) -> str | None:
    """The raw text between the frontmatter fences, or None if there isn't
    one — checked structurally (fence position), never by whole-file grep."""
    match = _FRONTMATTER_RE.match(text)
    return match.group(1) if match else None


def _frontmatter_field(block: str, name: str) -> str | None:
    for line in block.splitlines():
        if line.startswith(f"{name}:"):
            return line[len(name) + 1 :].strip()
    return None


def transform(text: str) -> str:
    out: list[str] = []
    in_frontmatter = False
    schema_stamped = False
    in_decision_map = False

    for i, line in enumerate(text.splitlines()):
        if i == 0 and line == "---":
            in_frontmatter = True
            out.append(line)
            continue
        if in_frontmatter:
            if line == "---":
                if not schema_stamped:
                    out.append(f"schema_version: {TARGET_SCHEMA}")
                    schema_stamped = True
                in_frontmatter = False
                out.append(line)
                continue
            if line.startswith("schema_version:"):
                out.append(f"schema_version: {TARGET_SCHEMA}")
                schema_stamped = True
                continue
            out.append(line)
            continue

        if line.startswith("## "):
            in_decision_map = line.strip() == "## Decision map"
            out.append(line)
            continue
        if in_decision_map:
            ptr = parse_pointer_line(line)
            if ptr is not None and ptr.form == "arrow" and not ptr.target.startswith(REPO_REF_PREFIX):
                rewritten = render_pointer_line(ptr.topic, ptr.target, ptr.write_id)
                reparsed = parse_pointer_line(rewritten)
                if reparsed is None or reparsed.target != ptr.target or reparsed.topic != ptr.topic:
                    print(f"FAIL: rewrite does not round-trip: {line!r}", file=sys.stderr)
                    raise SystemExit(1)
                out.append(rewritten)
                continue
        out.append(line)

    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def main() -> None:
    page = Path(sys.argv[1])
    original = page.read_text(encoding="utf-8")

    frontmatter = _frontmatter_block(original)
    if frontmatter is None:
        print("SKIP: no frontmatter block")
        return
    if _frontmatter_field(frontmatter, "type") != "l2-map":
        print("SKIP: not an l2-map page")
        return
    if _frontmatter_field(frontmatter, "schema_version") == str(TARGET_SCHEMA):
        print(f"SKIP: already at schema {TARGET_SCHEMA}")
        return

    result = transform(original)
    tmp = page.with_suffix(page.suffix + ".migrating")
    tmp.write_text(result, encoding="utf-8")
    tmp.replace(page)


if __name__ == "__main__":
    main()
