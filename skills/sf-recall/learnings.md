---
title: "sf-recall learnings"
type: skill-learnings
parent_skill: sf-recall
version: 0.1.0
date: 2026-05-28
---

# sf-recall — learnings

## Open log

### 2026-05-28 — Word-boundary matching is the right grep semantic

First implementation used naive `str in lower_content` substring matching. A test query `"totally-not-there"` tokenized to `["totally", "not", "there"]`; the substring "not" matched "notes" in a Session-notes page despite no actual word "not" appearing.

Fix: switched to `re.compile(r"\b" + re.escape(token) + r"\b", re.IGNORECASE)` per-token. This is the standard grep semantic — friends typing `/sf:recall "auth"` expect to find the WORD auth, not substrings like "author" or "authentic."

Trade-off accepted: `/sf:recall "post"` will no longer surface pages about "postgres" via accidental prefix match. Friends who want prefix search can re-query with the full prefix; we don't have prefix-specific tokens in V1.

V2 (qmd-based hybrid search per ADR-005) will use semantic matching that handles "post→postgres" naturally via vector similarity. v1 grep is deliberate but bounded.

### 2026-05-28 — Reader/writer asymmetry inherited from feed-2's contract

`/sf:recall` calls `feed_read_tail()` which **never raises on not-bootstrapped** (returns empty list). Only `feed.config.handle()` raises (`HandleNotConfiguredError`, `SchemaVersionMismatchError`). Caught both silently per plan §5: feed-side problems shouldn't pollute a wiki-search command's output.

This mirrors feed-2's design philosophy: reads are inherently safe to attempt; writes require bootstrap. Our wake-up hook (when it lands) will follow the same pattern: read first (silent on missing), write later (explicit FeedWriteResult violation codes).

Filing in sf-improve-skill's learnings.md too when I touch it — the asymmetry is a general API-design lesson worth surfacing across the team's lib code.

### 2026-05-28 — Initial design notes

- Pure-logic grep + score in `lib/__init__.py`; no LLM call. v1 wiki sizes don't justify LLM-based retrieval; deterministic results matter for `/sf:doctor` smoke checks.
- Snippet is 3 lines (prev + match + next). More context bloats the user-facing output; less breaks readability. 3 is the sweet spot.
- `.session-notes/` IS in the grep scope (×0.8 multiplier — surfaceable but lower-priority than decisions/patterns). Friends should be able to recall their own pins via the standard recall path; no separate "recall my notes" skill needed.
- Hidden dirs (anything starting with `.` except `.session-notes/`) excluded — `.git/`, `.venv/`, etc.
- File-mtime recency bonus (+0.5 if <30 days) breaks ties toward freshness without dominating the per-token weights.

## Related artifacts

- ADR-005 (Wiki Retrieval Evolution) — v1 grep → v2 qmd transition
- ADR-009 (Consolidate via /wrap) — names this as a companion command
- `references/grep-strategy.md` — full v1 heuristic
- feed-2's exception contract — silent-empty on read, explicit-violation on write
