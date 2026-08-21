"""frontmatter-type-1 — backfill the derived frontmatter `type:`.

Stamps `type:` onto every wiki page that lacks one and whose path the
derivation table recognizes. Tree-wide global migration in the
trust-backfill-1 mold: direct writes + own journal, revertible via the
whole-wiki pre-update snapshot. Spec:
docs/superpowers/specs/2026-08-21-knowledge-flow-seams-design.md §2.5

The table itself lives in `lib.memory.page_types` and is shared with the
write door and the lint — this migration never carries its own copy.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.memory.page_types import ensure_type  # noqa: E402
from lib.ren_paths import state_dir, wiki_root  # noqa: E402

_SKIP_DIRS = {".ren", ".git"}


def _pages(root: Path):
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root)
        if any(part in _SKIP_DIRS or part.startswith(".") for part in rel.parts[:-1]):
            continue
        yield path, rel


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    check_only = "--check" in argv

    root = wiki_root()
    if not root.is_dir():
        print("frontmatter-type-1: no wiki root, nothing to do")
        return 0

    stamped = 0
    skipped = 0
    journal_lines: list[dict] = []

    for path, rel in _pages(root):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue

        new_text = ensure_type(text, rel.as_posix())
        if new_text == text:
            skipped += 1
            continue

        if check_only:
            print(f"{rel.as_posix()}: WOULD STAMP type:")
        else:
            path.write_text(new_text, encoding="utf-8")
            print(f"{rel.as_posix()}: stamped type:")
            journal_lines.append({
                "migration": "frontmatter-type-1",
                "page": rel.as_posix(),
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
        stamped += 1

    if journal_lines and not check_only:
        log = state_dir() / "migrations" / "frontmatter-type-1.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as fh:
            for line in journal_lines:
                fh.write(json.dumps(line) + "\n")

    verb = "would stamp" if check_only else "stamped"
    print(f"frontmatter-type-1: {stamped} {verb}, {skipped} already typed or unmapped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
