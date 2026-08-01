#!/usr/bin/env python3
"""
migrations/foreign-remint-1/migrate.py — restamp mis-minted
`ren_trust: "foreign"` pages to `"model"` (issue #22).

Before #22, `lib.memory.provenance.trust_class` minted "foreign" for every
`producer="ingest"` write — including knowledge pages drafted by RenOS's own
subagents from the friend's own repo and applied through the queue. The
foreign stamp holds an L2 map out of wake-up UNCONDITIONALLY (spec §4.5's
structural-artifact exemption lifts only the quarantine-withhold check), so
an ingested project's wiki pages could never reach wake-up, even released.

Remint rule (brief, verbatim):
  - `ren_trust == "foreign"` AND `ren_writer` in the known NON-HUMAN writer
    classes ("llm-auto", "retrospective", "routine")  ->  restamped "model"
  - anything else (no `ren_trust`, non-foreign trust, `ren_writer: "human"`,
    or no `ren_writer` at all)                        ->  left untouched

The writer condition bounds the restamp to the mis-minted population: every
existing foreign stamp was self-minted by the ingest door (which always
writes `writer="llm-auto"`) or backfilled by trust-backfill-1 onto pages
that carried a queue-written `ren_writer`. A foreign page with NO writer
stamp has genuinely unknown provenance and conservatively keeps "foreign".
Quarantine banners are untouched — a reminted page still stays out of
context until released.

Only the `ren_trust` line is rewritten; every other frontmatter line and the
entire body are left byte-for-byte untouched.

Idempotent: a page already stamped "model" (or anything non-foreign) is
skipped.

Standalone global migration (same shape decision as trust-backfill-1 — see
that migration's README): "is this page mis-minted foreign?" is a per-file
property, not a page-type dispatch, so this walks the whole wiki tree once
rather than riding `skills/wiki-migration`'s schema_version chain.

Contract:
  argv:   [] | ["--check"]  (--check reports what WOULD be reminted, no writes)
  env:    honors whatever `lib.ren_paths.wiki_root()` already resolves
          (REN_WIKI_ROOT / CLAUDE_PLUGIN_OPTION_WIKIROOT / REN_FRAMEWORK_ROOT).
  stdout: one summary line per reminted page, then one totals line.
  exit:   0 always.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.memory import provenance  # noqa: E402
from lib.ren_paths import wiki_root  # noqa: E402

_NON_HUMAN_WRITERS = ("llm-auto", "retrospective", "routine")

_TRUST_LINE_RE = re.compile(r'^ren_trust: "foreign"$', re.MULTILINE)


def _should_remint(text: str) -> bool:
    prov = provenance.read_frontmatter_provenance(text)
    if prov is None:
        return False
    return (
        prov.get("trust") == "foreign"
        and prov.get("writer") in _NON_HUMAN_WRITERS
    )


def _remint(text: str) -> str:
    """Rewrite exactly the `ren_trust: "foreign"` frontmatter line to
    `"model"`. Everything else — including the body, which could
    legitimately contain the same string — is untouched: the substitution
    is bounded to the leading frontmatter block."""
    match = provenance._FRONTMATTER_RE.match(text)
    if match is None:
        return text
    fm = text[: match.end()]
    body = text[match.end():]
    fm = _TRUST_LINE_RE.sub('ren_trust: "model"', fm, count=1)
    return fm + body


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    check_only = "--check" in args

    root = wiki_root()
    reminted = 0
    skipped = 0

    for page in sorted(root.rglob("*.md")):
        rel = page.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue

        try:
            text = page.read_text(encoding="utf-8")
        except OSError:
            continue

        if not _should_remint(text):
            skipped += 1
            continue

        if check_only:
            print(f"{rel.as_posix()}: WOULD REMINT ren_trust=foreign -> model")
        else:
            page.write_text(_remint(text), encoding="utf-8")
            print(f"{rel.as_posix()}: reminted ren_trust=foreign -> model")
        reminted += 1

    verb = "would remint" if check_only else "reminted"
    print(f"foreign-remint-1: {reminted} {verb}, {skipped} left untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
