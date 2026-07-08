# queue-governance 0.2 → 0.3

Task 10 (RenOS 0.3, "the ungated brain"). Releases queue entries that were
only left `pending` because 0.2 gated every write behind a human
approve/apply step. v2.2's two-plane governance pivot (spec §10) auto-applies
the DATA plane and keeps only the INSTRUCTION plane (`global/` pages) and
unresolved `contradicts` holds pending — a friend upgrading from 0.2.x still
has a queue full of entries pending for the OLD reason (0.2 gated
everything), not the new one (instruction-plane / contradiction). This
migration reclassifies them once.

## Shape decision: standalone script, not the wiki-migration chain

`migrations/routine-spec-1-to-2/` and `migrations/routine-spec-2-to-3/`
follow `skills/wiki-migration`'s chain shape: a `schemas.json` registry keyed
by **page type**, an ordered list of `<type>-<from>-to-<to>` migration
directory names, and a `migrate.sh <page_path>` invoked once **per matching
page**. That shape is built around frontmatter transforms on individual wiki
pages.

This migration operates on **queue state**
(`state_dir()/queue/*.json`, per `lib/ren_paths.py::state_dir` —
`<wiki_root>/.ren`), not wiki-page frontmatter:

- There is no "page type" here to register in `schemas.json` — a queue entry
  isn't a wiki page and doesn't carry a `schema_version` frontmatter field.
- The decision ("release or hold?") is a property of the **whole queue
  entry** — a `Proposal` (page, writer, content) plus its `conflicts` list —
  evaluated via `lib.memory.queue.auto_apply_eligible`. Nothing here is a
  per-page frontmatter transform, so there's no `migrate.sh <page_path>`
  contract to satisfy.
- A single run must see every pending entry at once (to decide `released` vs
  `held` per entry and report totals); the chain machinery's one-invocation-
  per-page model doesn't naturally express "walk N JSON files under a state
  directory."

So this is a standalone `migrations/queue-governance-2-to-3/migrate.py`,
**not** registered in `skills/wiki-migration/schemas.json` and **not**
discovered by `skills/wiki-migration/lib/__init__.py::migration_chain`.
Instead it's named directly as a post-update step in `skills/update/SKILL.md`
(0.3 update notes) so `/ren:update` sessions upgrading past 0.3 run it once.

## What it does

Walks `lib.memory.queue.pending()` (every entry still in `pending` status).
For each:

- **Eligible** (`queue.auto_apply_eligible(entry)` is `True` — no
  `contradicts` conflict, and the tier model resolves the proposal to
  `"auto"`, i.e. a bounded non-global memory write) → released via
  `queue.apply_auto(entry.qid)`. This is exactly what would have happened
  had the entry been proposed under v2.2 policy in the first place.
- **Ineligible** → left `pending`, unchanged. This is the CORRECT new-world
  steady state, not a leftover to clean up:
  - instruction-plane (`global/`) proposals are promotion suggestions — a
    human must still approve/apply them via `approve_and_apply`.
  - `contradicts` holds need a live session to reason about the conflict
    (revise the proposal, or `resolve_and_apply` with a stated reason) —
    this migration has no session to reason with, so it never resolves one.

`queue.auto_apply_eligible` is the SAME predicate `queue.propose_and_apply`
uses on the live data-plane door (Task 10 factored it out of
`propose_and_apply` for exactly this reuse) — this migration cannot drift
from live policy by construction.

## Idempotent

`queue.pending()` only returns entries still in `pending` status. Once an
entry is released it becomes `applied` and a second run never revisits it;
entries left pending stay pending (nothing here writes to them), so a second
run always finds the same (possibly smaller) pending set and is a clean
no-op. No `schema_version`-style marker field is needed — pending-ness IS the
migration state.

## Usage

```sh
# report only, no writes:
uv run python migrations/queue-governance-2-to-3/migrate.py --check

# apply:
uv run python migrations/queue-governance-2-to-3/migrate.py
```

Honors whatever `lib.ren_paths` already resolves for the wiki root
(`REN_WIKI_ROOT` / `REN_FRAMEWORK_ROOT` / etc.) — this script does not read
wiki-root env vars itself, it defers entirely to `lib.memory.queue`, the same
way any other queue caller does.

Prints one summary line per entry (`released -> applied (<page>)` or
`left pending — <reason> (<page>)`), then one totals line.

## Rollback

Each release goes through the normal `apply_auto` write path — provenance
(G2) and one-step revert (G4) apply exactly as they do to any other
auto-applied write; there is no bespoke rollback mechanism for this
migration specifically. A friend who wants to undo a release reverts that
individual write like any other, or restores from the pre-update wiki
snapshot `/ren:update` already takes.
