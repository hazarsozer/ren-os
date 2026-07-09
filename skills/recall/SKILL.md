---
name: recall
description: |
  Use when the friend explicitly wants to look something up in the wiki
  mid-session, beyond what wake-up already injected. Triggers on the
  /ren:recall slash command followed by a free-text query. Every fetch this
  skill performs is logged — that log is the mechanical miss-measurement
  substrate (spec §3.2), not a surveillance feature.
version: 0.3.6
license: MIT

framework_version: "0.3.6"
schema_version: 1
type: skill
execution_tier: deterministic

contract:
  required_outputs:
    - "Up to k ranked {page, content} results rendered to the user"
    - "One l3_fetch metric line recorded for EVERY returned page"
  budgets:
    turns: 1
    files_written: 0
    duration_seconds: 5
  permissions:
    read:
      - "~/.renos/wiki/**"
    write:
      - "~/.renos/wiki/.ren/metrics/**"
    execute: []
  completion_conditions:
    - "collect.read(kind=KIND_L3_FETCH) has one new entry per returned page"
  output_paths:
    - "~/.renos/wiki/.ren/metrics/"

tags: [producer, mid-session, recall, retrieval, l3]
related_skills: [pin, wrap]
references_required: []
references_on_demand: ["docs/data-flow.md"]
---

# recall

The L3 fetch verb. Wake-up (Phase 5) injects what it can at session start; `/ren:recall <query>` is what the friend reaches for when they need something wake-up didn't surface. Every page this skill returns is logged as an L3 fetch — see "Why every fetch is logged" below.

## When to use this skill

- Friend invokes `/ren:recall "<query>"` — free-text lookup against the wiki
- Friend says: "what do we know about X", "look up Y", "did we already decide on Z" — confirm the query, then call `fetch()`

## When NOT to use this skill

- Friend wants to record something, not look it up → `/ren:pin`
- The answer is already visible in the current conversation (wake-up already surfaced it) — don't re-fetch what's already in context

## Behavior

1. Resolve the active `session` id and the friend's free-text `query`.
2. Call `skills.recall.lib.fetch(query, session, k=3)` (or a caller-supplied `k`).
3. `fetch` ranks every `*.md` page under the wiki root via `rank(query, candidate_pages, wiki_root)` (token overlap + recency + path-kind hints — see "Scoring" below), takes the top-k, and reads their content.
4. For **every** page returned (not just the one the friend acts on), `fetch` calls `lib.instrument.miss_log.log_fetch(page, query, session)` — this is unconditional, not optional instrumentation the skill can skip.
5. Render the results to the friend (page path + relevant excerpt/full content, caller's choice of formatting).

## Why every fetch is logged

Per spec §3.2 ("Honest miss measurement"): a fetch of active-project knowledge that wake-up *could have* surfaced is, by mechanical definition, a wake-up miss. `lib.instrument.miss_log.misses()` joins these `l3_fetch` records against wake-up's `wakeup_surface` records (same session) to compute a hit/miss rate with a computable denominator — no LLM self-report of "did I already know this." This is instrumentation feeding an honest metric, not tracking the friend; see `docs/data-flow.md` for the full data-flow picture (Phase 6).

## Scoring (`rank`)

Carried from the pre-0.2 recall heuristic: word-boundary token matching against a page's frontmatter `title`, its markdown headings, and its body (title hits weigh most, body hits are capped per token so keyword-stuffing can't dominate), a small recency bonus for pages touched in the last 30 days, and a path-kind multiplier (`decisions/` and `patterns/` pages score higher; `.session-notes/` lower). `rank`'s signature — `(query, candidate_pages, wiki_root) -> list[str]` — matches the retrieval-eval harness's `ranker_fn` contract exactly, so Phase 5's wake-up ranker and this skill's `fetch` can share the same scoring function and the same eval fixture.

## What this skill does NOT do

- Route to an "instincts-only" mode. Donor's `--instincts` flag is dropped entirely for 0.2 — recall here only ranks ordinary wiki pages.
- Read routine cross-run state (`state.md`/`run-log.md`). That's a routine-runner concern, not this skill's.
- Decide what wake-up injects. `rank` is shared code, but wake-up (Phase 5) calls it independently at session start; this skill is the on-demand, mid-session path only.
- Write anything to the wiki. `fetch` is read-only against wiki pages; its only write is the `l3_fetch` metric line via `collect.record`.

## Failure-degradation modes

| Failure | Behavior | User-visible |
|---|---|---|
| Empty query | Refuse, prompt for a query | "What should I recall? Usage: /ren:recall \"<query>\"" |
| Wiki root absent or has no pages | `fetch` returns `[]`, no crash | "Nothing found — the wiki looks empty." |
| A candidate page is unreadable (permissions, encoding) | Scored as 0, included in ranking, empty content if selected | (silent — doesn't block other results) |

## References

- Task 3.3 (`lib/instrument/miss_log.py`) — the log_fetch/misses substrate this skill feeds
- Spec §3.1 (L3) + §3.2 (honest miss measurement) — the mechanical miss definition
- `skills/recall/lib/__init__.py` (donor, `~/Dev/startup-framework`) — the scoring heuristic this carries
- `docs/data-flow.md` (Phase 6, on demand) — full picture of what's logged and why
