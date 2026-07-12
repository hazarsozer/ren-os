---
name: wiki-health
description: |
  Use when the friend (or a scheduled routine) wants a coherence check on the
  wiki: dangling L2 pointers, contradicting pages, duplicate pages, numeric
  drift between facts, a mass-deletion anomaly scan, and the
  quarantined/unreviewed-content inventory. Triggers on /ren:wiki-health.
  This is 0.3's replacement for per-write human approval
  (v2.2 removed the queue gate on data-plane writes) — the autonomous
  auditor that runs periodically instead of a human reviewing every diff.
version: 0.5.1
license: MIT

framework_version: "0.5.1"
schema_version: 1
type: skill
execution_tier: judgment

contract:
  required_outputs:
    - "The rendered sweep report (skills.wiki-health.lib.render_report output) shown to the friend"
  budgets:
    turns: 6
    files_written: 0
    duration_seconds: 60
  permissions:
    read:
      - "~/.renos/wiki/**"
      - "~/.renos/wiki/.ren/journal.jsonl"
    write: []
    execute: []
  completion_conditions:
    - "sweep() ran and every finding it returned is either fixed (with reasoning recorded via propose_and_apply/resolve_and_apply), listed as intentionally left, or the friend was asked about it"
  output_paths: []

tags: [judgment, wiki-health, coherence, sweep, self-improvement]
related_skills: [doctor, retrospective, pin, wrap]
references_required: []
references_on_demand: []
---

# wiki-health

The minimal coherence sweep. With v2.2's two-plane pivot (data plane
auto-applies, only `global/` promotion stays human-gated), no human reviews
every write anymore — this skill is what catches what a per-write reviewer
used to catch, by sweeping periodically instead of gating continuously.

## When to use this skill

- Friend invokes `/ren:wiki-health` directly
- A scheduled routine wants a periodic coherence pass
- After a burst of auto-applied writes the session has reason to distrust
  (e.g. a retrospective pass just queued a lot of proposals)

## Behavior

1. Call `skills.wiki-health.lib.sweep()` — read-only, six findings:
   `dangling_pointers`, `contradiction_pairs`, `duplicate_pairs`,
   `numeric_drift_pairs`, `mass_deletions`, `quarantined_pages`, plus
   `generated_at`.
2. Call `render_report(findings)` and show the friend the full report
   **before** touching anything — the friend sees what was found even if
   the session is about to fix most of it unattended.
3. For each finding, the model fixes what it mechanically can, with the
   reasoning recorded on the write itself:
   - **Dangling pointer**: if the intended target is unambiguous (a single
     obvious rename/move candidate), repair the pointer through
     `lib.memory.queue.propose_and_apply` (`producer="retrospective"` — the
     closest existing self-review producer; `wiki-health` isn't its own
     producer class in 0.3, see "What this skill does NOT do"). If more than
     one plausible target exists, this is an ambiguity — ask, don't guess.
   - **Contradiction pair**: if one side is clearly the newer/superseding
     claim (recency, an explicit correction elsewhere in the session), apply
     the fix via `lib.memory.queue.resolve_and_apply`, whose `resolution`
     argument records WHY the surviving claim stands — never fix a
     contradiction silently. If it's not obvious which side is right, this
     is genuine ambiguity — ask.
   - **Duplicate pairs** — two applied pages whose bodies share ≥90% of
     their lines; the live session proposes consolidating (UPDATE one,
     DELETE the other) through the normal write flow, or asks the friend
     when unsure which survives.
   - **Numeric drift** — the same fact line appearing with different
     numbers (across two pages, or twice within one page): almost always a
     stale value. The live session asks the friend which number is
     current, then fixes via `resolve_and_apply` with a note.
   - **Mass-deletion anomaly**: never auto-fix. This is a "look at this"
     signal, not a repair target — surface the window (count, pages, start
     time) and ask the friend if it was intentional.
   - **Quarantined page**: never auto-release. Quarantine exists precisely
     because llm-auto content hasn't been human-reviewed; wiki-health's job
     is to surface the inventory, not to review it on the friend's behalf.
     When the sweep lists quarantined pages, offer them to the friend by
     name. If the friend explicitly confirms a page is accurate ("yes, that
     map is right"), call `release_page(<page>, session)` — the banner is
     removed through the write substrate (journaled, revertible). Never
     release on your own judgment; a sweep finding is an offer, not a
     decision.
   - **Judge-dismissed pairs** (only when `llm_call` was passed to `sweep()`):
     never auto-anything. `render_report` shows a `## Judge-dismissed (for
     review)` section with the judge's reason/confidence next to the
     original heuristic evidence, so the friend can see what the judge
     filtered out — anti-Goodhart visibility, not a repair target.
4. Before applying ANY batch of mechanical fixes, list the intended fixes
   to the friend first — **never mass-edit without listing intended fixes
   first**, even when every fix in the batch is individually unambiguous.
5. Ask the human 2-3 targeted questions ONLY on genuine ambiguity (an
   unclear dangling-pointer target, an unresolvable contradiction). This is
   a short, specific interview — never a full diff review of everything the
   sweep found.

## What this skill does NOT do

- Schedule itself. No cron/routine wiring in this minimal version — 0.3
  runs it on explicit invocation only; periodic scheduling is future work.
- Cross-reference facts beyond what `lib.memory.semantics`'s
  `contradiction_evidence`, `duplicate_evidence`, and
  `numeric_drift_evidence` already give it. No new detection intelligence
  lives here — this skill is a consumer of those heuristics (wiki-wide,
  all-pairs, not `detect`'s single-write sibling-glob scope), not an
  extension of them.
- Add a dedicated `"wiki-health"` producer to `lib.memory.queue`'s
  `_PRODUCERS` tuple. Repairs this skill drives go through
  `propose_and_apply`/`resolve_and_apply` under the `"retrospective"`
  producer (the existing self-review class closest in kind) rather than
  widening the producer enum for one new caller — revisit if 0.3+ wants
  finer-grained provenance on wiki-health's own fixes specifically.
- Present a diff for per-write approval. That gate is gone (v2.2); the
  report in step 2 plus the "list before mass-editing" rule in step 4 are
  the transparency mechanism that replaces it.

## Failure-degradation modes

| Failure | Behavior | User-visible |
|---|---|---|
| No wiki root | `sweep()` returns empty findings for wiki-derived checks, journal-derived `mass_deletions` still runs | Report shows "none" in every wiki-derived section |
| Journal file absent | `mass_deletions` is `[]` (`journal.entries()` returns `[]` cleanly) | "## Mass deletions\n- none" |
| A page is unreadable (permissions, encoding) | Skipped in that page's checks, doesn't crash the sweep | Absent from findings, not called out individually (known v1 gap) |

## References

- `skills/doctor/lib/__init__.py` (`check_dangling_pointers`) — the L2
  pointer-map check this skill's dangling-pointer walk mirrors structurally
  (message-per-CheckResult there vs. one record per finding here)
- `lib/memory/semantics.py` (`detect`, `contradiction_evidence`,
  `duplicate_evidence`, `numeric_drift_evidence`) — the pairwise cores this
  skill's `contradiction_pairs`, `duplicate_pairs`, and
  `numeric_drift_pairs` each use directly for one shared wiki-wide
  all-pairs scan, rather than `detect`'s sibling-directory candidate set
- `lib/memory/queue.py` (`propose_and_apply`, `resolve_and_apply`) — the
  write-safety substrate any mechanical fix goes through
- v2.2 doctrine (spec §10, two-plane governance) — why this skill exists:
  it's the auditor that replaces per-write human approval on the data plane
