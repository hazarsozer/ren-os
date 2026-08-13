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
_MD_LINK_RE = re.compile(
    r"(\]\(\s*<?)"                       # opener through optional <
    r"([^()\s#>]+\.md)"                  # target path (no anchor)
    r"((?:#[^()\s>]*)?>?(?:\s+\"[^\"]*\")?\s*\))"  # anchor/title/closer
)
_SCHEMA_HUB_LINE_RE = re.compile(
    r"^- Hub files are always named `index\.md`\.\s*$", re.MULTILINE
)
_SCHEMA_HUB_REPLACEMENT = (
    "- Hub files are folder notes named after their folder "
    "(`<topic>/<topic>.md`), with `hub: true` in frontmatter."
)


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


def rewrite_links(text: str, page: Path, root: Path,
                  renames: dict[Path, Path]) -> tuple[str, int]:
    """Rewrite md-link targets that resolve (file- or root-relative) to a renamed hub."""
    count = 0

    def _sub(m: re.Match) -> str:
        nonlocal count
        target = m.group(2)
        if not target.endswith("index.md") or target.startswith(("http://", "https://", "repo:", "/")):
            return m.group(0)
        for base in (page.parent, root):
            try:
                cand = (base / target).resolve()
            except OSError:
                continue
            if cand in renames:
                count += 1
                new_target = target[: -len("index.md")] + renames[cand].name
                return m.group(1) + new_target + m.group(3)
        return m.group(0)

    return _MD_LINK_RE.sub(_sub, text), count


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
    rewrites = 0
    for page in sorted(root.rglob("*.md")):
        if _skipped(page, root):
            continue
        text = page.read_text(encoding="utf-8")
        new_text, n = rewrite_links(text, page, root, renames)
        if page.name == "schema.md":
            new_text, n2 = _SCHEMA_HUB_LINE_RE.subn(_SCHEMA_HUB_REPLACEMENT, new_text)
            n += n2
        if n:
            page.write_text(new_text, encoding="utf-8")
            rewrites += n
    entries = []
    for old, new in sorted(renames.items()):
        new.write_text(stamp_hub_true(old.read_text(encoding="utf-8")), encoding="utf-8")
        old.unlink()
        entries.append({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "from": str(old.relative_to(root)),
            "to": str(new.relative_to(root)),
        })
    entries.append({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "rewrites": rewrites,
    })
    _journal(entries)
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
