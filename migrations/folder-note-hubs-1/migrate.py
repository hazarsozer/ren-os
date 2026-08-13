"""folder-note-hubs-1 — knowledge hubs become folder notes.

Renames every `index.md` below a `projects/<slug>/knowledge/` root to
`<parent-folder>.md`, stamps `hub: true` where missing, and (Task 2)
rewrites every inbound link wiki-wide. Tree-wide global migration in the
project-knowledge-1 mold: direct writes + own journal, revertible via the
whole-wiki pre-update snapshot. Spec:
docs/superpowers/specs/2026-08-13-folder-note-hubs-design.md
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.ren_paths import state_dir, wiki_root  # noqa: E402

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_SKIP_PARTS = {"raw", "archive"}


def _skipped(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    return any(p.startswith(".") or p in _SKIP_PARTS for p in rel.parts)


def build_rename_map(root: Path) -> dict[Path, Path]:
    """Resolved-absolute {old_index_md: new_folder_note}; collisions skipped with a WARN."""
    renames: dict[Path, Path] = {}
    for knowledge in sorted(root.glob("projects/*/knowledge")):
        for old in sorted(knowledge.rglob("index.md")):
            if _skipped(old, root):
                continue
            new = old.parent / f"{old.parent.name}.md"
            if new.exists():
                print(f"WARN: {new.relative_to(root)} exists; leaving "
                      f"{old.relative_to(root)} for manual repair", file=sys.stderr)
                continue
            renames[old.resolve()] = new.resolve()
    return renames


def stamp_hub_true(text: str) -> str:
    m = _FRONTMATTER_RE.match(text)
    if m is None:
        return text
    block = m.group(1)
    if re.search(r"^hub:", block, re.MULTILINE):
        return text
    return f"---\n{block}\nhub: true\n---\n" + text[m.end():]


def _journal(entries: list[dict]) -> None:
    path = state_dir() / "migrations" / "folder-note-hubs-1.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")


def main() -> int:
    root = wiki_root()
    renames = build_rename_map(root)
    if not renames:
        print("SKIP: no knowledge hubs named index.md")
        return 0
    # Task 2 inserts the link-rewrite pass here, before any rename.
    entries = []
    for old, new in sorted(renames.items()):
        new.write_text(stamp_hub_true(old.read_text(encoding="utf-8")), encoding="utf-8")
        old.unlink()
        entries.append({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "from": str(old.relative_to(root)),
            "to": str(new.relative_to(root)),
        })
    _journal(entries)
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
