# sf-insights — synthesis prompt

This is the contract for turning the collector's fact-block into the user-facing
report. The **script collects facts; the LLM synthesizes the narrative.** Your job
is judgment over the data — never invention beyond it.

## Input

You are given exactly one block on stdout from `scripts/collect.py`, delimited by:

```
=== SF-INSIGHTS COLLECTED DATA (v1) ===
...
=== END SF-INSIGHTS COLLECTED DATA ===
```

It contains: the window (`window_days`), the project filter, `sessions_found`,
an `## AGGREGATE` section (projects, top_tools, top_topics, cc_versions_seen,
error_signals), a per-session `## SESSIONS` section, and optionally a
`## SESSION_SUMMARIES` section from narrative `save-session` `.tmp` files.

## Hard rules (read first)

1. **Bound every claim to the data.** Each observation must trace to a number,
   tool, topic, project, or snippet that appears in the block. When you assert
   something, cite the evidence inline, e.g. "Bash ran 142× across 9 sessions" or
   "3 sessions show a retry pattern."
2. **Never invent activity.** If `sessions_found: 0`, say the window is empty and
   suggest widening `--days` or relaxing `--project`. Do not fabricate trends,
   dates, or projects that aren't in the block.
3. **Read-only.** Do not write any file, do not run the collector with side
   effects, do not call the network. Print the report to the user only.
4. **No secrets.** The collector summarizes; if any raw value that looks like a
   credential slipped into a snippet, do not repeat it — describe it generically.
5. **Stay bounded.** Aim for a tight, scannable report (roughly 250–500 words).
   You are summarizing a summary; do not re-list every session.

## Output — exactly these four sections, in this order

Emit a Markdown report with these four `##` headers, verbatim:

### `## Usage at a Glance`
The factual base, paraphrased from `## AGGREGATE`: how many sessions, over how many
days, across which projects, the most-used tools, and the headline error/retry
counts. Pure facts, lightly narrated. No recommendations here.

### `## What's Working`
Patterns the data supports as *effective*: heavily-and-cleanly-used tools, projects
with many sessions and low error signal, topics that recur (sustained focus). Each
bullet cites its evidence. If the data is too thin to claim anything, say so.

### `## What's Hindering`
Friction the data *shows*: error/retry hotspots (high `tool_errors` /
`error_phrase_hits` / `retry_suspected=yes`), tools that churn, projects that appear
once and stall, or a scattered topic spread suggesting context-switching. Cite the
numbers. Distinguish "the data shows X" from "X might mean Y" (a hypothesis).

### `## Quick Wins`
2–5 small, concrete, data-grounded next actions tied directly to what the prior two
sections surfaced (e.g. "the auth project shows 11 Bash errors — add a Makefile
target so the build command stops being retyped"). No generic advice; every item
must point back to an observation.

## Empty-window template

If `sessions_found: 0`, still emit all four headers. Under each, state plainly that
there is no data in the window and (under Quick Wins) suggest `--days 90` or dropping
the `--project` filter. Do not invent anything.
