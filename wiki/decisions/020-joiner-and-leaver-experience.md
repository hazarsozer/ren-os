---
title: "ADR-020: Joiner & Leaver Experience"
status: superseded
superseded-by: "ADR-031 (2026-05-30): solo-first pivot — no friend group, so no joiner/leaver experience"
date: 2026-05-28
sunset-review: 2026-11-28
references-pages: [simon-scrapes-agentic-os]
affects-components: [install, doctor, activity-feed, distribution, skills]
relates-to: [015-onboarding, 017-per-friend-wiki-scope, 018-activity-feed, 019-framework-distribution]
---

# ADR-020: Joiner & Leaver Experience

> ⚠️ **SUPERSEDED by [ADR-031](031-solo-first-pivot.md) (2026-05-30).** Solo-first: there is no friend group, so there is no joiner or leaver experience. A "joiner" with no feed is just a fresh `/sf:install`. Preserved for history (and in the `baseline-v1.0-full-wiki` tag).

## Context

Friends will join and leave the group over the framework's lifetime. ADR-015 (Onboarding) describes the install flow assuming a fresh install. ADR-019 (Distribution) describes the marketplace + Activity Feed repos that already exist by the time a second friend joins. ADR-017 (Per-Friend Wiki Scope) establishes that no group state can be inherited — each friend's wiki is local-only.

This ADR settles the two related membership-change cases that fall through the cracks of the other ADRs:

1. **Joiner**: a new friend joins the group months after the framework is already in use
2. **Leaver**: a friend leaves the group (drops out, moves on, gets removed)

Without this ADR, joiners would do `/sf:install` and the framework would attempt to bootstrap fresh Activity Feed repos that already exist, while leavers would leave orphaned state with no documented cleanup path.

## Decision

### Equal access in v1

There are no privileged roles in v1. Every friend is:
- A **read** collaborator on the framework marketplace repo (per ADR-019)
- A **write** collaborator on the Activity Feed repo (per ADR-018)

The "maintainer" role (who ships releases, who admins the GitHub repos) is informally held by whoever does the work — initially Hazar. We don't formalize it in v1. Differentiate roles only if needed later.

### Joiner flow

When Friend X joins:

**Out-of-band steps** (existing maintainer does these via GitHub UI):
1. Add Friend X as **read collaborator** on the framework marketplace repo
2. Add Friend X as **write collaborator** on the Activity Feed repo
3. Send Friend X the install command (one Slack/WhatsApp message)

**In-band steps** (Friend X runs these):
1. Install Claude Code if not installed
2. Run the standard install command (per ADR-019):
   ```
   /plugin marketplace add <our-org>/<framework-marketplace>
   /plugin install startup-framework@<our-org>-startup-framework-marketplace
   ```
3. Run `/sf:install` — the framework's 7-stage onboarding (per ADR-015) runs with these adaptations:

| Stage | First friend (Hazar) | Joiner (Friend X) |
|---|---|---|
| 1. Env check | Same | Same |
| 2. Required plugins | Same | Same |
| 3. Activity Feed setup | Creates new repo, becomes first contributor | Detects existing repo URL (provided during install), clones it, adds own `<handle>.log.md` + `identities/<handle>.md` |
| 4. Identity bootstrap | Same | Same (writes own `wiki/identity.md` locally) |
| 5. Wiki bootstrap | Creates fresh empty wiki | Creates fresh empty wiki (no group history inherited per ADR-017) |
| 6. `/sf:doctor` verification | Same | Same |
| 7. First-session walkthrough | Same + maybe note "you're the first; others will catch up here over time" | Same + suggest running `/sf:catch-up` (new skill, see below) to skim recent Activity Feed |

**`/sf:install` detects existing repo**: when stage 3 runs, if the user provides a repo URL that already exists (already has commits, has other friends' `*.log.md` files), the installer skips bootstrap and just clones + adds the new friend's files.

### `/sf:catch-up <project>` skill (new addition)

Per the user's approval. A skill that helps a joiner (or any friend returning after time away) get oriented quickly:

**Behavior:**
1. Reads the Activity Feed (all friends' `<handle>.log.md` files)
2. Filters entries by:
   - Project / directory mentioned (if user passed `<project>` argument)
   - Time range (default: last 30 days; `--days N` to override)
   - Friend (optional `--from <handle>` filter)
3. Summarizes what happened: who worked on what, key decisions called out, current state-of-play
4. Suggests next steps (e.g., "Friend B last worked on auth-flow yesterday — consider chatting with them before starting parallel work")

**Output**: rendered in conversation; not written to wiki (user can manually promote insights via `/sf:wrap`).

**Slash commands**:
```
/sf:catch-up                       # Last 30 days, all projects, all friends
/sf:catch-up <project>             # Filter by project/directory
/sf:catch-up --days 7              # Last week only
/sf:catch-up --from hazar          # Just Hazar's activity
/sf:catch-up <project> --days 7    # Combined filters
```

Lives in the framework's skill set, ships in the marketplace install.

### Joiner identity flows the same way

Per ADR-015's identity-bootstrap (Stage 4):
- Friend X answers the interview questions
- `wiki/identity.md` is written locally (their per-friend wiki)
- A copy of identity-relevant fields (display name, contact preferences, what they typically work on) is written to `<activity-feed-repo>/identities/<handle>.md` — visible to other friends

The local `wiki/identity.md` is more detailed (includes preferences, working style, etc.); the Activity Feed `identities/<handle>.md` is the public-facing summary.

### Leaver flow

When Friend X leaves the group:

**Out-of-band steps**:
1. **Existing maintainer removes Friend X** as collaborator on the framework marketplace repo (now read-blocked)
2. **Existing maintainer removes Friend X** as collaborator on the Activity Feed repo (write-blocked; can no longer push)
3. **Optional**: archive their identity:
   ```
   git mv identities/<handle>.md identities/archived/<handle>.md
   git commit -m "archive <handle> identity (left group YYYY-MM-DD)"
   git push
   ```
   This is **soft archive**, not delete — preserves history, removes them from the active roster other friends might browse.

**What stays in the Activity Feed**:
- `<handle>.log.md` stays where it is (historical record; their last writes preserved). Other friends' wake-ups can still see what they had been working on.
- All their past commits stay in git history.

**On Friend X's machine** (if they want to keep using their wiki for personal use after leaving):
- Their per-friend wiki stays local and functional
- Activity Feed git push will fail (no write access) — their `/sf:wrap` will warn but session continues
- They can run `/sf:install --remove-activity-feed` to clean up their local clone + skip future Activity Feed pushes

**What the framework does NOT do automatically**:
- Doesn't delete Friend X's log file (that's the maintainer's call)
- Doesn't notify other friends about the departure (do that via Slack/Discord)
- Doesn't revoke their installed plugins on their machine (the plugins are software they own; framework doesn't reach in)

### What if the marketplace repo's last maintainer leaves?

The repo has no admin → no one can add new joiners → group can't grow.

**Mitigation**: GitHub allows multiple admins. When designating maintainers, name at least 2 admins on each repo. Document in the friend group's onboarding that admin = bus-factor-of-2 minimum.

Document this in the framework's `README.md` for the marketplace repo (this is an out-of-framework concern; ADR-020 just flags it).

## Consequences

**Easier:**
- Joining is mechanically the same as first-install with one detection point (existing repo)
- No special "joiner mode" code path that diverges significantly from the standard install
- Leaving is mostly out-of-band GitHub admin work; framework doesn't fight you
- `/sf:catch-up` is a small targeted skill that solves the "I missed everything; what's happening?" gap without violating per-friend-wiki separation

**Harder:**
- The maintainer has to remember the collaborator-invite step before sending the install command (could automate via a friend-group-bot later)
- Friend X's first `/sf:install` requires them to know the repo URLs (Hazar tells them in chat)
- Leaver cleanup is partly manual (archiving the identity file is optional)

**Now impossible:**
- Onboarding a friend who doesn't have a GitHub account (they need one for marketplace + Activity Feed access)
- Joining without a maintainer's prior collaborator invite (no anonymous joins)

**Sunset review trigger conditions:**
- Friend group's churn becomes high enough that manual collaborator invites become friction → automate via a bot
- Joiners struggle to get oriented → improve `/sf:catch-up` or add a richer onboarding-for-joiners flow
- The "no anonymous joins" requirement blocks a use case we hadn't anticipated → revisit

## Alternatives considered

### A) Joiners inherit existing wikis from one or more friends

**Considered shape**: When Friend X joins, copy Hazar's wiki to Friend X's machine as a starting point.

**Why rejected**: Violates ADR-017's per-friend-wiki scope. Friend X would inherit Hazar's biases, preferences, project framings — not a fresh start. The whole point of per-friend wikis is each friend grows their own perspective.

### B) Differentiated roles (maintainer / member / read-only observer)

**Considered shape**: Maintainer = repo admin, can ship releases. Member = standard. Observer = read-only.

**Why rejected for v1**: Premature. The friend group is small; differentiation adds complexity for hypothetical use cases. v1 = everyone equal. Revisit if and when needed.

### C) Build joiner-onboarding into `/sf:install` as a separate flow

**Considered shape**: `/sf:install --join` vs. `/sf:install --bootstrap` as distinct entry points.

**Why rejected**: One install command with detection (Stage 3 detects existing repo) is simpler. Friends don't need to remember a flag. The codepath is mostly shared; the divergence is small enough to inline.

### D) No `/sf:catch-up`; just tell joiners to read the Activity Feed manually

**Considered shape**: Skip the new skill; document the Activity Feed and let joiners scroll.

**Why rejected**: Per user's approval. The skill provides genuine value — a 30-day digest by project is much more useful than scrolling raw logs. Adds one skill to the framework's set, which is fine given the friend group has been on board with skill-shaped solutions throughout.

### E) Auto-delete leavers' log files on departure

**Considered shape**: When a leaver is removed as collaborator, their `<handle>.log.md` gets deleted.

**Why rejected**: Loses historical record. Existing friends' wake-ups may still want context like "Friend X worked on auth-flow last quarter — see their archived logs." Keep logs, archive identity.

## Open questions for implementation phase

1. **GitHub collaborator API** — can we automate the invite step via a friend-group-bot? Out of scope for ADR-020 itself; the option exists.

2. **`/sf:catch-up` output format** — markdown summary in conversation, or a written-to-disk briefing file? Defer to implementation; user preference matters more than upfront decision.

3. **Bus-factor enforcement** — should the framework's install pre-flight check refuse to install if the marketplace repo has only one admin? Probably overkill; document in README instead.

4. **What if a leaver wants their data deleted entirely** (GDPR-style "right to be forgotten")? Manual git history rewriting is destructive. Document as "we keep historical records; ask before joining if this matters to you."

## References

- `wiki/research/simon-scrapes-agentic-os.md` — Pillar 6 (Managing projects & clients) gestures at multi-client / multi-friend setups; joiner flow inherits the same pattern
- ADR-015 (Onboarding) — base install flow this ADR adapts for joiners
- ADR-017 (Per-Friend Wiki Scope) — no group history inheritance principle
- ADR-018 (Activity Feed) — the shared repo joiners connect to (cloning instead of bootstrapping)
- ADR-019 (Framework Distribution) — the marketplace repo joiners need access to (out-of-band collaborator invite)
