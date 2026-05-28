---
name: sf-catch-up
description: Use when the user runs `/sf:catch-up [project] [--days N] [--from handle] [--include-self] [--include-releases]` to see what friends have been working on. Pulls the activity-feed, filters entries by project / time-window / handle, buckets by (project, handle), surfaces same-file overlap warnings, and renders an in-conversation summary. Pure read API — does NOT write to wiki or push to feed. Per ADR-020 + plan §4.
type: skill
schema_version: 1
framework_version: 1.0.0
owner_module: sf-feed
---

# sf-catch-up

The friend-orientation skill. Helps joiners (just installed the framework) or
returning friends (away for days/weeks) get oriented to what the group has been
doing — without violating per-friend-wiki separation (ADR-017).

## When to invoke

- User runs `/sf:catch-up` directly
- User says "what's been happening?", "what did the group do this week?", "is anyone working on X?"
- Onboarding's Stage 7 (first-session walkthrough) suggests this to joiners per ADR-020
  §"7. First-session walkthrough — same + suggest running `/sf:catch-up`"

## CLI surface

```
/sf:catch-up                          # default: last 30 days, all projects, all friends, excludes self
/sf:catch-up <project>                # positional substring filter on project/cwd
/sf:catch-up --days N                 # override 30-day default
/sf:catch-up --from <handle>          # filter to one friend
/sf:catch-up --from <h1> --from <h2>  # multi-friend
/sf:catch-up <project> --days 7       # combined
/sf:catch-up --include-self           # opt-in: include own entries
/sf:catch-up --include-releases       # opt-in: show framework release announcements
```

## What the skill does (the 4-stage pipeline)

```
1. Fetch    → feed.pull() best-effort, 10s timeout
              On failure: proceed with stale local clone, flag at top of output
2. Filter   → feed.read_all_entries(since, from_handles, project_filter)
3. Group    → bucket by (project, handle); compute first/last activity per bucket;
              compute lexical file-overlap signal (same filename in Touched:
              across friends within the window)
4. Render   → structured markdown summary (NOT free-form LLM output for the data
              section). LLM-composed "Suggested next steps" section ONLY, capped
              at ≤5 bullets, explicitly marked as LLM-generated.
```

## Output template

```
# Activity Feed catch-up — last {N} days{filter_clauses}

## By project

### sidecar (3 friends, 12 sessions)
- **hazar** — 8 sessions, most recent 2026-05-28 16:45
  - JWT middleware (5/26), email regex fix (5/27), STATE.md updates (5/28)
- **friend-b** — 3 sessions, most recent 2026-05-27 20:00
  - Stripe webhook handler (5/25), webhook tests (5/27)
- ⚠️ **Overlap**: hazar + friend-b both touched src/auth/jwt.ts on 5/27 — check for divergence before parallel work

### restore (1 friend)
- **friend-c** — 1 session 5/26 — initial scaffolding

## Suggested next steps
- Sync with friend-b on src/auth/jwt.ts before continuing JWT work
- friend-c may want pairing on restore — they're solo so far

*LLM-generated suggestions; verify against actual code state.*

---
[feed] sources: hazar.log.md (8 entries), friend-b.log.md (3), friend-c.log.md (1) · synced 2m ago
```

## What this skill does NOT do

- Does NOT write to the wiki. User can promote insights via `/sf:wrap` if they want.
- Does NOT push anything to the Activity Feed.
- Does NOT call LLM for filtering/grouping — that's deterministic Python. ONLY the
  "Suggested next steps" section is LLM-composed, and even then it's bounded
  (≤5 bullets, marked as LLM-generated per team-lead's pushback on plan §4.3 to
  prevent editorializing about other friends' work).
- Does NOT show release entries unless `--include-releases` (default off — they're
  announcement noise for orientation).
- Does NOT cross-reference friends' wikis. Wikis stay per-friend-local per ADR-017;
  this skill reads ONLY the Activity Feed.

## Invocation

The skill driver shells out to:

```bash
python3 -m scripts.render \
    [--project <substring>] \
    [--days N] \
    [--from <handle>]... \
    [--include-self] \
    [--include-releases]
```

The script returns the rendered markdown on stdout. The skill consumer (Claude itself)
takes that output, optionally appends the LLM-composed "Suggested next steps" section
(constrained by the format-discipline rule), and surfaces to the user.

## Failure modes

- Feed not bootstrapped → script exits 2 with "Run /sf:install Stage 3" message
- Pull failed → renders with stale-warning banner at top, continues anyway
- No entries match filters → renders empty result with "no activity found in window" message
- Schema mismatch in a friend's log → skips that friend's file with a warning line, continues with the rest

## Related

- `feed/reader.py` — the read API consumed (`read_all_entries`, `pull`)
- `feed/format.py` — `FeedEntry` shape used internally
- `skills/sf-disable-feed/` — opt-out marker writer (this skill respects existing data; doesn't care about future skip state)
- ADR-020 — joiner & leaver experience (the spec that birthed this skill)
- ADR-018 — Activity Feed architecture
- Plan §4 — full skill specification
