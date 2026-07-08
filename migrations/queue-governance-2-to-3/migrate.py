#!/usr/bin/env python3
"""
migrations/queue-governance-2-to-3/migrate.py — release 0.2-gated data-plane
queue entries under v2.2 two-plane governance (Task 10).

Shape decision (see README.md for the full rationale): this migration walks
QUEUE STATE (`state_dir()/queue/*.json`), not a wiki page's frontmatter.
`skills/wiki-migration`'s chain machinery (`schemas.json` + per-page
`migrate.sh`, as used by `routine-spec-1-to-2`/`routine-spec-2-to-3`) is
page-type-oriented — one script invoked once per matching PAGE, driven by a
registry keyed by page type. There is no page type here and no per-page
invocation model fits: one run of this script must see the WHOLE queue at
once, because "is this proposal instruction-plane?" and "does it have a
contradicts conflict?" are properties of a queue entry, not of a wiki page's
frontmatter. So this is a standalone script, run once directly (not
discovered via `schemas.json`), wired into `skills/update/SKILL.md`'s 0.3
update notes as a named post-update step instead.

Policy (mirrors `lib.memory.queue.propose_and_apply`'s hold logic via the
shared `queue.auto_apply_eligible` predicate — Task 10 factored that helper
out of `propose_and_apply` specifically so this migration and the live
data-plane door can't drift):
  - pending entry, `auto_apply_eligible` True  -> release via `apply_auto`
    (it was only pending because 0.2 gated every write; v2.2 policy would
    have auto-applied it on propose).
  - pending entry, `auto_apply_eligible` False -> LEFT PENDING. Under v2.2
    this is the correct steady state: an instruction-plane (`global/`)
    proposal is a promotion suggestion; a `contradicts` hold needs a live
    session to reason about it. Migrating these to "applied" would silently
    write to the instruction plane or paper over an unresolved contradiction
    — never done here.

Idempotent: `queue.pending()` only returns entries still in `pending` status,
so a second run sees nothing left to release and is a clean no-op.

Contract:
  argv:   [] | ["--check"]  (--check reports what WOULD be released without
                              applying anything — no writes)
  env:    honors whatever `lib.ren_paths` already resolves (REN_WIKI_ROOT /
          REN_FRAMEWORK_ROOT / etc.) — this script does not read wiki-root
          env vars itself, it defers entirely to `lib.memory.queue`.
  stdout: one summary line per entry (released/left-pending + why), then one
          totals line.
  exit:   0 always (a migration that can't classify an entry leaves it
          pending, which is always safe — there is no failure exit here).
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.memory import queue  # noqa: E402
from lib.governance.tiers import queue_auto_apply_allowed  # noqa: E402


def _hold_reason(entry: queue.QueueEntry) -> str:
    """Why `entry` (already known ineligible) is being left pending — for
    the per-entry summary line only; not used for the release decision
    itself (that's `queue.auto_apply_eligible`, the single source of truth)."""
    if any(c.get("kind") == "contradicts" for c in entry.conflicts):
        return "contradiction hold — needs live reasoning (resolve_and_apply)"
    if not queue_auto_apply_allowed(entry.proposal):
        return "instruction-plane (global/) — human-gated promotion suggestion"
    return "not eligible"  # pragma: no cover - defensive; auto_apply_eligible covers both cases above


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    check_only = "--check" in args

    entries = queue.pending()
    if not entries:
        print("queue-governance-2-to-3: no pending entries — nothing to do")
        return 0

    released = 0
    held = 0
    for entry in entries:
        page = entry.proposal.page
        if queue.auto_apply_eligible(entry):
            if check_only:
                print(f"{entry.qid}: WOULD RELEASE ({page})")
            else:
                queue.apply_auto(entry.qid)
                print(f"{entry.qid}: released -> applied ({page})")
            released += 1
        else:
            print(f"{entry.qid}: left pending — {_hold_reason(entry)} ({page})")
            held += 1

    verb = "would release" if check_only else "released"
    print(f"queue-governance-2-to-3: {released} {verb}, {held} left pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
