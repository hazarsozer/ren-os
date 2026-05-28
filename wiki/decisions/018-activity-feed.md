---
title: "ADR-018: Activity Feed — Friend Group Session Reports via Shared GitHub Repo"
status: accepted
date: 2026-05-28
sunset-review: 2026-11-28
references-pages: [team-coordination-survey, simon-scrapes-agentic-os]
affects-components: [hooks, wake-up, consolidate, install, distribution, friend-group-coordination]
relates-to: [008-wake-up-hook, 009-consolidate-via-wrap, 015-onboarding, 017-per-friend-wiki-scope, 019-framework-distribution]
amends:
  - "ADR-006 (remove MCP Agent Mail from stack table — we're not using it; the activity feed is a built-in framework feature instead)"
  - "ADR-015 (replace Stage 3 Agent Mail conditional install with required Activity Feed setup step: shared GitHub repo URL + gh CLI auth + local clone)"
amended-by:
  - "ADR-021 (2026-05-28): formalized the TERSE FORMAT for session-end entries — couple sentences, only project/task/files, NO code/decisions/commentary. This format constraint is the primary privacy mechanism. Also added `--skip-feed` flag + `SF_SKIP_FEED=1` env var + `/sf:disable-feed` for entirely private sessions."
---

# ADR-018: Activity Feed — Friend Group Session Reports via Shared GitHub Repo

## Context

The friend group works in parallel on the same projects from different machines. Without any cross-friend visibility:
- Hazar starts a session, doesn't know Friend B has been mid-flight on the same project for the past 2 hours
- Friend B finishes a session having solved a problem that would have unblocked Hazar; the knowledge sits in Friend B's local wiki unseen
- Two friends both ship breaking changes to the same project, unaware of each other
- The group lacks any low-friction "what's happening across the studio right now" signal

ADR-017 establishes that wikis are per-friend-local. ADR-018 needs to solve the cross-friend visibility problem **without** breaking the per-friend-local principle.

Our research considered MCP Agent Mail (Dicklesworthstone) as a candidate solution. Initial framing was "team-coordination plugin" with file reservations. The user's clarification reframed the actual need: this isn't messaging between people (use WhatsApp/Discord for that); it isn't shared wiki state (we just rejected that); it's **automated session reports** — Claude tells Claude what's happening at session boundaries.

Under that lens, MCP Agent Mail's full machinery (FastMCP HTTP server, FTS5 indexing, file reservations, agent identity handshakes) is overkill. We just need a shared git repo of markdown reports + hooks that read/write it.

## Decision

**The framework ships a built-in "Activity Feed" feature.** No external plugin; no MCP Agent Mail; no daemons.

### Architecture

```
                ┌────────────────────────────────────┐
                │  Shared private GitHub repo        │
                │   (e.g., friend-group/activity-feed)│
                │                                     │
                │   hazar.log.md                      │
                │   friend-b.log.md                   │
                │   friend-c.log.md                   │
                │   identities/                       │
                │     hazar.md                        │
                │     friend-b.md                     │
                │   README.md                         │
                └────────────────────────────────────┘
                            ▲              ▲
                            │              │
                  git pull/push   git pull/push
                            │              │
                  ┌─────────┴──┐  ┌────────┴─────┐
                  │  Hazar's    │  │ Friend B's   │
                  │  machine    │  │ machine      │
                  │             │  │              │
                  │  SessionStart→ pull, write    │
                  │              "[friend] active" │
                  │              read others'     │
                  │              recent activity  │
                  │                               │
                  │  /sf:wrap → write summary,    │
                  │              git push         │
                  └─────────────┘  └──────────────┘
```

### File format (per-friend log files prevent write conflicts)

Each friend writes only to **their own log file** (`<handle>.log.md`). Multiple friends ending sessions simultaneously commit different files → no merge conflicts.

Log entry format follows ADR-004's chronological-invariant convention:

```markdown
## [2026-05-28 14:30] start | hazar | working in Dev/sidecar/

(optional first-line context: "continuing the auth-flow work from yesterday's session-pointer")

## [2026-05-28 16:45] end | hazar | session complete

Here's what's done:
- Implemented JWT verification middleware per wiki/projects/sidecar/decisions/003-auth.md
- Fixed bug in /api/login endpoint (regex was rejecting valid emails)
- Updated wiki/projects/sidecar/STATE.md with current progress
- TODO: write tests for the JWT middleware (next session)

## [2026-05-28 18:10] start | hazar | working in Dev/sidecar/
...
```

The format is grep-parseable (same as wiki/log.md per ADR-004): `## [YYYY-MM-DD HH:MM] <start|end> | <handle> | <description>`.

### Hook integration (extends ADR-008 + ADR-009, doesn't replace them)

**At SessionStart** (extends ADR-008 wake-up hook):
1. **Wiki wake-up runs first** (per ADR-008) — loads master index + project context + CONTEXT.md
2. **Activity-feed sub-step runs second**:
   - `git pull` the activity-feed repo
   - Read tail (last ~10 entries) of EACH friend's `*.log.md` file
   - Read tail of own `<handle>.log.md` for personal continuity
   - Append a new entry: `## [<now>] start | <handle> | working in <cwd>` to own log file
   - `git commit -m "<handle> session start"` + `git push`
   - Pass aggregated activity-feed context into the wake-up conversation-layer message (alongside wiki context per ADR-008)

**At `/sf:wrap`** (extends ADR-009 consolidate):
1. **Wiki consolidate runs first** (per ADR-009) — updates STATE.md / CONTEXT.md / log.md as warranted
2. **Activity-feed sub-step runs second**:
   - Compose a session-end summary (LLM-authored based on the session's signal)
   - Append `## [<now>] end | <handle> | session complete\n\n<summary>` to own `<handle>.log.md`
   - `git commit -m "<handle> session end"` + `git push`

### Identity in the activity feed

`<handle>.log.md` and `identities/<handle>.md` use the handle from the friend's `wiki/identity.md` (per ADR-015's identity-bootstrap). One friend's identity flows from their local wiki → into the activity feed.

`identities/<handle>.md` holds public-facing identity info other friends will see (display name, what they typically work on, contact info if they want). Each friend authors their own; other friends pull-and-read but don't modify.

### Auto-deliver, no approval flow

Per user direction: messages auto-deliver. No approval queue. Friends in the group implicitly trust each other; if a friend turns adversarial we have bigger problems than the activity feed.

If any friend wants to leave the group: their write access is revoked from the shared GitHub repo. Existing log entries stay (historical record); they can no longer post new ones.

### Content (summaries), not references

For v1, summaries are inlined into the log entries. Friends pasting wiki excerpts is fine.

When v2's master-wiki aggregator (per ADR-017's Direction A) ships, references become possible — log entries can point at `aggregator.example.com/hazar/wiki/decisions/...` URLs. Defer that pattern; not in v1.

### What this is NOT

- Not a messaging tool (use WhatsApp / Discord for that)
- Not a chat (no replies, no threads)
- Not a skill-distribution channel (use GitHub or manual install for skills)
- Not a shared wiki (per ADR-017, wiki stays per-friend-local)
- Not a file-reservation system (no advisory locks)
- Not MCP Agent Mail (the research candidate that initially seemed to fit but turned out to be overengineered for this use case)

### Onboarding integration (amends ADR-015)

`/sf:install` Stage 3 (conditional plugins) — previously had Agent Mail as a conditional install. **Replace** with:

**Stage 3 — Activity Feed setup (always runs, not optional):**
1. Ask: "What's the GitHub repo URL for your friend group's activity feed?" (e.g., `friend-group/activity-feed`)
   - If repo doesn't exist yet: "Be the first to set it up — guide friend to create a private repo on GitHub and configure as collaborator"
2. Verify `gh auth status` (or run `gh auth login` if needed)
3. Clone the repo to a known local path (e.g., `~/<framework-dir>/activity-feed/`)
4. Verify push access (test commit a placeholder file in `identities/<handle>.md` from the identity-bootstrap output)
5. Confirm success

If a friend is the FIRST one in the group: they create the repo + the framework writes initial structure (README.md + `identities/<handle>.md`).

If a friend is joining LATER: they're added as collaborator first (out-of-band step the existing friends handle); then their install clones + sets up their own `<handle>.log.md`.

### Privacy considerations

The activity feed sees:
- Which directory you're working in (cwd at session start)
- What you summarize as "done" at session end

The activity feed does NOT see:
- Your wiki content (stays per-friend-local)
- Your code (just summary text you choose to include)
- Your project state (STATE.md is in your local wiki, not the activity feed)

For sensitive work: don't run `/sf:wrap` during sessions you don't want others to see. Or override the auto-summary to be less detailed. The framework defaults to truthful summaries; the friend can edit before the commit happens (the consolidate skill can show the diff for approval, similar to `/revise-claude-md`'s pattern).

## Consequences

**Easier:**
- Cross-friend visibility on parallel work — Hazar boots up, sees Friend B has been working on Dev/sidecar/ for 2 hours; can pull from main or coordinate via WhatsApp
- Lightweight: just git + markdown + hooks; no MCP Agent Mail or external plugins
- Self-hosted on GitHub (no vendor service); friends own the repo
- Per-friend log files = no write conflicts
- Mirrors wiki/log.md format = consistent mental model

**Harder:**
- Initial group setup requires creating + sharing a private GitHub repo (one-time per group)
- Friends joining the group need to be added as collaborators (out-of-band, GitHub UI)
- Git network failures on push can fail session-start/session-end silently — need graceful-degradation (log a warning, continue session; retry on next session-start)
- The `gh` CLI dependency adds another required tool to Stage 1 environment check

**Now impossible:**
- Cross-friend coordination via shared state — by design; messages are append-only reports
- Real-time messaging (use WhatsApp / Discord)

**Sunset review trigger conditions:**
- Friends actually want messaging (replies, threads, attachments) — at which point MCP Agent Mail becomes appropriate; revisit
- GitHub becomes unavailable / unsuitable — switch to GitLab/Gitea/etc.
- Friend group grows past 5-7 people such that per-friend log files become unwieldy — restructure (per-day files? aggregator?)
- A master-wiki aggregator (ADR-017 Direction A) ships and supersedes the per-friend log files

## Alternatives considered

### A) Adopt MCP Agent Mail with shared git remote

**Considered shape**: Use MCP Agent Mail configured to point at a shared GitHub repo as its Git backend. Get FTS5 search, file reservations, agent identity handshakes, structured messaging.

**Why rejected**: Overengineered for our use case. The user explicitly stated: "This is a simple reporter, nothing further. The framework is already becoming complex, no need to overengineer even worse." MCP Agent Mail's HTTP server, SQLite indexing, file-reservation machinery, FastMCP framework — all overhead we don't need for "two hook-triggered git commits per session."

### B) Per-friend peer-to-peer via Agent Mail's native HTTP transport

**Considered shape**: Each friend runs their own Agent Mail HTTP server; friends' Claudes message each other directly.

**Why rejected**: Requires every friend's machine to be online + reachable. Requires firewall traversal or LAN-only operation. Requires Agent Mail server management. None of this beats "shared GitHub repo" which is already always-on and zero-management for friends.

### C) Mercury / Proton MCP (commercial SaaS)

**Considered shape**: Use Mercury.build's hosted multi-agent service.

**Why rejected per ecosystem survey**: sends data to third-party servers; opaque license + pricing; not aligned with "friends own their data" preference. GitHub is the friend group's chosen sharing surface.

### D) Don't ship any cross-friend visibility in v1

**Considered shape**: Defer the entire activity-feed concept; let friends coordinate manually via WhatsApp.

**Why rejected**: The user explicitly raised cross-friend awareness as valuable, especially for parallel work on the same project. Implementing it is cheap (just hooks + git); not implementing it leaves real value on the table. Plus the friend group's whole proposal-to-friends moment is "we have this magical thing"; "your friend's Claude sees what your Claude was doing yesterday" is genuinely magical when it works.

### E) Single shared log.md (not per-friend log files)

**Considered shape**: One `log.md` in the shared repo; everyone appends to it.

**Why rejected**: Concurrent commits to the same file cause git merge conflicts. Conflict resolution either fails (push rejected) or requires manual intervention (bad UX for hooks running invisibly). Per-friend files trivially solve this at the cost of needing to read multiple files at session start.

### F) Activity feed in same repo as the framework / wiki

**Considered shape**: Put the activity-feed log files in the per-friend wiki repo.

**Why rejected**: Conflates personal wiki (local-private per ADR-017) with cross-friend reports (shared by design). Different scopes → different repos. The user wants the wiki strictly local.

## Open questions for implementation phase

1. **Where on disk** does the activity-feed repo get cloned? Suggestion: `~/<framework-dir>/activity-feed/` consistent with where the friend's wiki lives. Settle in writing-plans phase.

2. **What if push fails** (network down, permissions revoked, etc.)? Suggestion: log warning, queue the commit locally, retry on next successful pull. Don't block the session.

3. **What if the same friend starts two sessions in parallel** (e.g., two terminal windows)? Log entries from both would be ordered by timestamp; no fundamental conflict. The wake-up would show both as "active". Probably fine.

4. **Should there be a `/sf:activity` slash command** for manually browsing the activity feed mid-session? Out of scope for ADR-018; could be added as v1.1 if friends ask.

5. **How to handle a friend who LEAVES the group?** GitHub collab access revoked. Their old logs stay in the repo as historical record. The framework on their machine continues writing to its local `<handle>.log.md` but push fails permanently → friend should run `/sf:install --remove-activity-feed` to clean up (separate command, not v1 blocker).

## References

- `wiki/research/team-coordination-survey.md` — the survey that initially pointed at MCP Agent Mail; this ADR explains why we built simpler instead
- `wiki/research/simon-scrapes-agentic-os.md` — Pillar 8 (Access anywhere) gestures at shared studio access; activity feed is the friend-group implementation of that idea
- ADR-008 (Wake-Up Hook) — extended by this ADR's SessionStart sub-step
- ADR-009 (Consolidate via /wrap) — extended by this ADR's session-end sub-step
- ADR-015 (Onboarding) — amended by this ADR to replace Stage 3 conditional Agent Mail with required Activity Feed setup
- ADR-017 (Per-Friend Wiki Scope) — explicitly preserves per-friend-local wiki separation; activity feed is the cross-friend layer that doesn't violate ADR-017
- ADR-019 (Framework Distribution) — forthcoming; covers gh CLI dependency + GitHub-as-distribution-mechanism patterns
