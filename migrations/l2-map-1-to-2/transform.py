"""Body transform for l2-map 1→2 (#53). Invoked by migrate.sh with
PYTHONPATH=<repo root>. Write-temp-then-rename; exits 1 (page untouched)
if any rewritten line fails to re-parse."""
from __future__ import annotations

import sys
from pathlib import Path

from lib.pointer import REPO_REF_PREFIX, parse_pointer_line, render_pointer_line

TARGET_SCHEMA = 2


def transform(text: str) -> str:
    out: list[str] = []
    in_frontmatter = False
    frontmatter_done = False
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
                frontmatter_done = True
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

    if not frontmatter_done:
        print("FAIL: page has no frontmatter block", file=sys.stderr)
        raise SystemExit(1)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def main() -> None:
    page = Path(sys.argv[1])
    original = page.read_text(encoding="utf-8")
    result = transform(original)
    tmp = page.with_suffix(page.suffix + ".migrating")
    tmp.write_text(result, encoding="utf-8")
    tmp.replace(page)


if __name__ == "__main__":
    main()
