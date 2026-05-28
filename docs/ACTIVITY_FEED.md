# Activity Feed — what your friends see, what stays private

The **Activity Feed** is the only thing in the framework that flows between you
and your friends. Everything else (your wiki, your notes, your project state)
stays on your machine. This doc covers what it shares, what it doesn't, and how
to turn it off when you want privacy.

## What it is

A shared private GitHub repo. Each friend has one file: `<your-handle>.log.md`.
At the start and end of each Claude Code session, the framework appends one
entry to your file and pushes it. Your friends' next sessions pull and read.

Mental model: **your Claude tells the group's Claudes what you worked on, in two
sentences, automatically, at session boundaries.** Nothing else.

## What a session-end entry looks like

```markdown
## [2026-05-28 16:45] end | hazar | session complete

Worked on sidecar — JWT verification middleware finished; /api/login email regex fixed.
Touched: src/auth/jwt.ts, src/api/login.ts, wiki/projects/sidecar/STATE.md.
```

That's it. Project + 1-2 sentences + file list. Capped at 300 characters total
in the body. No code. No decisions. No quoted reasoning. Just enough for a
friend's Claude to say "Hazar was working on JWT middleware last night —
maybe sync before parallel work."

Session-start entries are even smaller — one line:

```markdown
## [2026-05-29 09:30] start | hazar | working in ~/Dev/sidecar/
```

## What does NOT get shared

- **Your wiki.** Stays local. The framework never auto-pushes wiki content.
- **Your code.** Format validators reject triple-backticks in the entry body.
- **Decisions, reasoning, transcripts.** The format constraint IS the privacy
  mechanism — there's nowhere for them to go.
- **Other friends' content.** You see what they pushed; they see what you pushed.
  There's no central indexer reading everyone's stuff.
- **Anything tagged `<private>`** in your wiki — that tag tells your local Claude
  to keep content out of any output, including session summaries.

The two pieces of info you can't avoid sharing:
1. **What directory you're working in** (`~/Dev/sidecar/`). If a directory name
   is sensitive, rename it locally OR skip the session (see below).
2. **The file paths you touched** in end entries. Same workaround.

## Turning it off

Three opt-out surfaces, in increasing scope:

| Surface | Scope | When to use |
|---|---|---|
| `/sf:wrap --skip-feed` | This wrap only | "Don't push THIS end entry" |
| `SF_SKIP_FEED=1 claude` | Entire session | Sensitive work session from the start |
| `/sf:disable-feed` | Current session, from this point on | Mid-session "stop sharing" |

When any of the three is active, the framework writes NOTHING — no local entry,
no push. Your friends won't know the session happened.

**Heads-up:** if you disable mid-session AFTER the start entry already pushed,
that start entry is already public — git history preserves it. Removal requires
coordinated history rewriting (see ADR-021). Prefer to set `SF_SKIP_FEED=1`
BEFORE launching Claude when you know in advance the session will be sensitive.

## What you see from other friends

Two places:

**1. Wake-up hook (automatic).** At the start of each session, your Claude pulls
the latest feed and includes recent activity from each friend in the wake-up
context. You'll see something like:

```
## Activity Feed — recent friend activity (synced 2m ago)

friend-b — 3 sessions this week, most recent yesterday 20:00
  - Stripe webhook handler
  - webhook tests
  - rate-limit middleware

friend-c — 1 session, 3 days ago
  - initial scaffolding for restore/
```

**2. `/sf:catch-up` (on demand).** When you join after time away, or want to
see what's been happening on a project:

```
/sf:catch-up                # last 30 days, all projects, all friends
/sf:catch-up sidecar        # filter by project
/sf:catch-up --days 7       # last week only
/sf:catch-up --from friend-b
```

Renders by-project buckets with overlap warnings ("hazar + friend-b both touched
src/auth/jwt.ts on 5/27 — check for divergence").

## Where the files live

On your machine:

```
~/.startup-framework/
├── wiki/                       # your local wiki — never shared
└── activity-feed/              # your clone of the shared repo
    ├── <your-handle>.log.md    # your own log (you write here)
    ├── <other>.log.md          # other friends' logs (read-only for you)
    ├── identities/<handle>.md  # public-facing identity per friend
    ├── .queue.log              # offline-queue (local-only, gitignored)
    └── .state.json             # sync state (local-only, gitignored)
```

You write only to your own `<handle>.log.md`. Multiple friends ending sessions
simultaneously write to different files — no merge conflicts by design.

## Common questions

**Q: What if the network is down when I `/sf:wrap`?**
A: Your local entry still commits. The push gets queued in `.queue.log` and retries
on your next session-start. Your work isn't lost; friends just see it later.

**Q: What if a friend's `gh` auth expires?**
A: `/sf:doctor` catches it; their next pull/push fails gracefully and surfaces
"check `gh auth status`". Other friends are unaffected.

**Q: What if my project name is sensitive (e.g., `Dev/stealth-acquisition/`)?**
A: Either rename the local directory before working, or use `SF_SKIP_FEED=1`
for those sessions. The framework can't redact paths it doesn't know to hide.

**Q: Can I leave the group?**
A: Yes. The maintainer revokes your write access on GitHub; your past entries stay
as historical record. Your local wiki is unaffected — it was always yours.

**Q: I see a `…` at the end of someone's summary in wake-up. What does that mean?**
A: Budget-trim suffix. The wake-up payload is capped at ~2.5K tokens; when many
friends are active, the framework trims summary text rather than dropping friends
entirely. Per-friend coverage is preserved; some briefs are shortened.

## When to ask for help

Run `/sf:doctor` first — it reports sync status, auth, and schema versions.
For the technical contract, see `~/.startup-framework/activity-feed/README.md`.
If genuinely stuck, ask in the friend group's chat.

The Activity Feed is the framework's only cross-friend layer. Everything else
is yours. Use the opt-outs freely — they're there for exactly that reason.
