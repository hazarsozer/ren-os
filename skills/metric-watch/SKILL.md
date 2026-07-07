---
name: metric-watch
description: |
  The §3.5 minimal metric-watch routine. Watches four signals — injection
  budget growth, memory growth rate, classifier fail-closed events, and
  backup configuration — and writes findings to the journal for the next
  wake-up to surface. Triggers on /ren:metric-watch, or (recommended) a
  weekly scheduled routine.
version: 0.2.0
license: MIT

framework_version: "0.2.0"
schema_version: 1
type: skill
execution_tier: deterministic

contract:
  required_outputs:
    - "One journal entry per run: writer=routine, op=NOOP, page=_metric-watch, extra.findings=[...]"
  budgets:
    turns: 1
    files_written: 0
    duration_seconds: 10
  permissions:
    read:
      - "~/.renos/wiki/**"
      - "~/.claude/plugins/data/renos/backups/**"
    write:
      - "~/.renos/wiki/.ren/journal.jsonl"
      - "~/.renos/wiki/.ren/metric-watch.json"
  completion_conditions:
    - "watch(session) returns a list (possibly empty) without raising"
    - "exactly one new journal.jsonl line for this run"
  output_paths: []

tags: [routine, metrics, governance, journal, notify]
related_skills: [routine-init]
references_required: []
references_on_demand: []
---

# metric-watch

Spec §3.5's minimal metric-watch: "one routine watches budget ceiling, memory growth rate, classifier fail-closed events, backup unconfigured and writes findings to the journal for the next wake-up." Four independent checks, one journal line per run.

## What it watches

| Check | Fires when | Finding kind |
|---|---|---|
| Injection budget | Latest `injected_bytes` wake-up payload > 1.5x the median of the last 10 | `injection-budget-growth` |
| Memory growth | Wiki `*.md` page count OR total bytes grown > 20% since the last metric-watch run | `memory-growth` |
| Classifier fail-closed | Any NEW `classifier_event` entries with `event=="fail_closed"` since the last run | `classifier-fail-closed` |
| Backup unconfigured | No `backup` git remote on the wiki repo AND no tarball newer than 7 days in the backups dir | `backup-unconfigured` |

Each check is isolated — one crashing produces a `check-error` finding (`{"kind": "check-error", "check": "<name>", "error": "<str>"}`) instead of preventing the other three from running.

## When to use this skill

- Friend invokes `/ren:metric-watch` for an on-demand check
- **Recommended cadence: weekly**, registered as an actual scheduled routine via whatever the friend's harness uses for cron-like scheduling (this skill is the CHECK; registering it as a live cadence is the friend's harness-level choice — see `skills/routine-init` for the routine-spec declaration a scheduled invocation of this skill would need, including its own allowlist: `_metric-watch` as a NOOP page needs no wiki-write allowlist entry at all, since it never proposes a memory write).

## When NOT to use this skill

- Watching a SPECIFIC routine's own health (not the framework's aggregate signals) — that's the routine's own `state.md`/run-log, surfaced by wake-up's `read_live_routines` (Task 5.1), not this skill

## Behavior

1. Call `skills.metric-watch.lib.watch(session)`.
2. `watch` runs all four checks (see table above), each wrapped so a crash becomes a `check-error` finding rather than an exception.
3. Findings are appended to the JOURNAL via `lib.memory.journal.append` — a `routine`-writer `Provenance` (`op="NOOP"`, `page="_metric-watch"`) carrying `extra={"findings": [...]}`. **Never a wiki page write** — wake-up already surfaces live routine state; the journal is the notify channel this check needs, and `_metric-watch` isn't a real page (no allowlist entry is needed for it — it's not a `lib.memory.queue.propose` call at all, `op="NOOP"` never touches a page).
4. Cross-run state (the memory-growth snapshot, the classifier high-water mark) persists at `state_dir()/"metric-watch.json"` — this is the one piece of state that must survive between runs; everything else is recomputed fresh each time from `collect.read`.

## What this skill does NOT do

- Write to wiki pages. Findings live in the journal only.
- Auto-remediate anything. A `backup-unconfigured` finding doesn't run `/ren:backup`; a `memory-growth` finding doesn't prune anything. This is observation, not action.
- Require a routine-spec allowlist entry for itself. Its own `op="NOOP"`/`page="_metric-watch"` journal write never goes through `lib.memory.queue`, so `check_proposal_against_allowlist` never gates it.

## Failure-degradation modes

| Failure | Behavior | User-visible |
|---|---|---|
| A single check raises (e.g. git not installed, corrupt state file) | That check's finding is `check-error`; the other checks still run and report normally | (surfaced in the journal, not a crash) |
| No prior metric-watch run yet | Memory-growth and classifier checks are naturally quiet (nothing to compare against) — not an error | — |
| Wiki root inaccessible | `watch()` still completes; individual checks that need it degrade gracefully (0 pages, no crash) | — |

## References

- Task 3.1/3.3 (`lib/instrument/collect.py`, `lib/instrument/miss_log.py`) — the metrics surface this routine reads
- Task 6.1 (`lib/governance/tiers.py`) — the risk-tier model; metric-watch's own journal write is `routine`+`NOOP`, outside the tier gate entirely (no page write)
- Task 5.1 (`hooks/wake-up/wakeup/__init__.py`'s `read_live_routines`) — where a friend sees this routine is live, not this skill's own output
- `docs/data-flow.md` — the local-only instrumentation surface this routine reads from and writes findings to
