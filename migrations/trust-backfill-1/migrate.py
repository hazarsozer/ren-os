#!/usr/bin/env python3
"""
migrations/trust-backfill-1/migrate.py — stamp `ren_trust` onto pre-0.5.1
wiki pages (0.5.1 Task 7).

Shape decision (mirrors `migrations/queue-governance-2-to-3/` — see that
migration's README for the fuller rationale): `ren_trust` is a provenance
frontmatter key stamped by `lib.memory.provenance` at the single write door
on EVERY new page, regardless of page type (spec §3.1, trust taxonomy,
0.5.1 Task 6). It is not a per-page-type `schema_version` field, so it does
not fit `skills/wiki-migration`'s chain shape (`schemas.json` page-type
registry + one `migrate.sh` invoked per matching page of a known type). A
single run of this script must instead walk the WHOLE wiki tree once,
because "does this page already carry `ren_trust`?" and "is it quarantined?"
are properties evaluated per file, not selected by a page-type dispatch.

So this is a standalone `migrate.py`, run directly (see
`skills/wiki-migration/schemas.json`'s `global_migrations` note for the
registry-discoverability entry) rather than driven by the chain machinery.
It still reuses that machinery's `verify.json` predicate shape
(`yaml.present` / `yaml.in` / `snapshot.body-identical`) for the accompanying
test, since `ren_trust` genuinely is a per-page frontmatter assertion.

Backfill rule (brief, verbatim):
  - `ren_writer == "human"`         -> "user"
  - `quarantine.is_quarantined()`   -> "foreign"
  - else                            -> "model"   (spec's conservative default)

Only the `ren_trust` line is inserted; every other frontmatter line and the
entire body are left byte-for-byte untouched.

Idempotent: a page that already carries `ren_trust` is skipped.

Contract:
  argv:   [] | ["--check"]  (--check reports what WOULD be stamped, no writes)
  env:    honors whatever `lib.ren_paths.wiki_root()` already resolves
          (REN_WIKI_ROOT / CLAUDE_PLUGIN_OPTION_WIKIROOT / REN_FRAMEWORK_ROOT).
  stdout: one summary line per stamped page, then one totals line.
  exit:   0 always.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.memory import provenance, quarantine  # noqa: E402
from lib.ren_paths import wiki_root  # noqa: E402

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)


def _classify(text: str) -> str:
    prov = provenance.read_frontmatter_provenance(text)
    writer = prov.get("writer") if prov else None
    if writer == "human":
        return "user"
    if quarantine.is_quarantined(text):
        return "foreign"
    return "model"


def _stamp_trust(text: str, trust: str) -> str:
    """Insert `ren_trust: "<trust>"` into an existing frontmatter block,
    right after `ren_op:` if present, else as the last line before the
    closing fence. Creates a bare frontmatter block if none exists. Body is
    left byte-for-byte untouched."""
    match = _FRONTMATTER_RE.match(text)
    line = f'ren_trust: "{trust}"'

    if match is None:
        return f"---\n{line}\n---\n" + text

    fm_content = match.group(1)
    body = text[match.end():]
    lines = fm_content.split("\n")

    inserted = False
    for i, fm_line in enumerate(lines):
        if fm_line.startswith("ren_op:"):
            lines.insert(i + 1, line)
            inserted = True
            break
    if not inserted:
        lines.append(line)

    return "---\n" + "\n".join(lines) + "\n---\n" + body


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    check_only = "--check" in args

    root = wiki_root()
    stamped = 0
    skipped = 0

    for page in sorted(root.rglob("*.md")):
        rel = page.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue

        try:
            text = page.read_text(encoding="utf-8")
        except OSError:
            continue

        prov = provenance.read_frontmatter_provenance(text)
        if prov is not None and prov.get("trust") is not None:
            skipped += 1
            continue

        trust = _classify(text)
        if check_only:
            print(f"{rel.as_posix()}: WOULD STAMP ren_trust={trust}")
        else:
            page.write_text(_stamp_trust(text, trust), encoding="utf-8")
            print(f"{rel.as_posix()}: stamped ren_trust={trust}")
        stamped += 1

    verb = "would stamp" if check_only else "stamped"
    print(f"trust-backfill-1: {stamped} {verb}, {skipped} already had ren_trust")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
