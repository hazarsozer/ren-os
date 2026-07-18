#!/usr/bin/env python3
r"""lint-shell-portability.py — guard shipped shell scripts against GNU-only syntax.

Stock macOS = bash 3.2 + BSD sed. CI's macOS runner has Homebrew bash 5 on
PATH, so runtime tests can miss bash-4isms — this lint is the deterministic
guard. Origin: issue #9 (v0.5.6 broke /ren:update + migrations on macOS).

Rules:
  1. mapfile/readarray            → bash 4+ builtins (use a while-read loop)
  2. bare `sed -i` (no suffix)    → BSD sed eats the script as the suffix (use -i.bak)
  3. GNU one-liner `/a text`      → BSD needs `a\` + newline (also /i, /c)
"""
import re
import sys
from pathlib import Path

SCAN_DIRS = ("skills", "migrations", "hooks", "scripts")

RE_MAPFILE = re.compile(r"\b(mapfile|readarray)\b")
RE_BARE_SED_I = re.compile(r"\bsed\s+(?:-\w+\s+)*-i(?=\s|\"|'|$)")
# One-line GNU append/insert/change inside a sed script arg: /a<space>text
# on the same line (the portable form puts a backslash-newline after a\).
# Require the sed script arg to START with a quoted address (/"pat"/[aic]) to avoid
# false-positives on substitutions like s/a b/c/ or addresses with other commands like /pat/d.
RE_GNU_ONELINE_AIC = re.compile(r"""\bsed\b[^\n]*["']/[^"']*/[aic] \S""")


def scan_file(path: Path) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(path.read_text().splitlines(), 1):
        code = line.split("#", 1)[0] if not line.lstrip().startswith("#") else ""
        if not code.strip():
            continue
        if RE_MAPFILE.search(code):
            hits.append((lineno, "mapfile/readarray is bash 4+ (macOS ships 3.2) — use a while-read loop"))
        if RE_BARE_SED_I.search(code):
            hits.append((lineno, "bare `sed -i` breaks BSD sed — use `sed -i.bak` (attached suffix)"))
        elif RE_GNU_ONELINE_AIC.search(code):
            hits.append((lineno, "GNU one-liner sed append/insert/change — use portable `a\\` + newline form"))
    return hits


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    failed = False
    for d in SCAN_DIRS:
        for sh in sorted((root / d).rglob("*.sh")) if (root / d).is_dir() else []:
            for lineno, msg in scan_file(sh):
                print(f"{sh.relative_to(root)}:{lineno}: {msg}")
                failed = True
    if failed:
        return 1
    print("shell-portability lint: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
