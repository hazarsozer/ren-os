"""folder-note-hubs-1 verifier — tree assertions the frontmatter-only
verify_page primitive cannot express. Exit 0 pass, 1 fail."""
from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.pointer import parse_pointer_line  # noqa: E402
from lib.ren_paths import wiki_root  # noqa: E402

_SKIP_PARTS = {"raw", "archive"}
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_MD_LINK_RE = re.compile(r"\]\(\s*<?([^()\s#>]+\.md)>?(?:#[^()\s]*)?(?:\s+\"[^\"]*\")?\s*\)")


def _skipped(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    return any(p.startswith(".") or p in _SKIP_PARTS for p in rel.parts)


def _fm(text: str) -> str:
    m = _FRONTMATTER_RE.match(text)
    return m.group(1) if m else ""


def _pages(root: Path):
    for p in sorted(root.rglob("*.md")):
        if not _skipped(p, root):
            yield p


def leftover_hubs(root: Path) -> list[str]:
    return [str(p.relative_to(root))
            for knowledge in sorted(root.glob("projects/*/knowledge"))
            for p in sorted(knowledge.rglob("index.md"))
            if not _skipped(p, root)]


def stale_hub_links(root: Path) -> list[str]:
    knowledge_roots = [k.resolve() for k in root.glob("projects/*/knowledge")]
    out = []
    for page in _pages(root):
        for target in _MD_LINK_RE.findall(page.read_text(encoding="utf-8")):
            if Path(target).name != "index.md" or target.startswith(("http", "repo:", "/")):
                continue
            for base in (page.parent, root):
                cand = (base / target).resolve()
                if any(cand.is_relative_to(k) for k in knowledge_roots):
                    out.append(f"{page.relative_to(root)} -> {target}")
                    break
    return out


def misnamed_hubs(root: Path) -> list[str]:
    out = []
    for page in _pages(root):
        if "knowledge" not in page.relative_to(root).parts:
            continue
        if re.search(r"^hub:\s*true\s*$", _fm(page.read_text(encoding="utf-8")), re.MULTILINE):
            if page.name != f"{page.parent.name}.md":
                out.append(str(page.relative_to(root)))
    return out


def unparseable_pointers(root: Path) -> list[str]:
    out = []
    for page in _pages(root):
        text = page.read_text(encoding="utf-8")
        if "type: l2-map" not in _fm(text):
            continue
        in_dm = False
        for line in text.splitlines():
            if line.startswith("## "):
                in_dm = line.strip() == "## Decision map"
                continue
            if in_dm and line.lstrip().startswith("- [") and parse_pointer_line(line) is None:
                out.append(f"{page.relative_to(root)}: {line.strip()[:60]}")
    return out


def main() -> int:
    root = wiki_root()
    failures = []
    for name, fn in (("leftover-hub", leftover_hubs), ("stale-link", stale_hub_links),
                     ("misnamed-hub", misnamed_hubs), ("pointer-parse", unparseable_pointers)):
        for detail in fn(root):
            failures.append(f"FAIL {name}: {detail}")
    for f in failures:
        print(f)
    if failures:
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
