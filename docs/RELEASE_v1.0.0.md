# Release v1.0.0 — artifacts

Scaffold for Hazar to fill in at first-ship. Three pieces:

1. **GitHub Release body** — what `gh release create` posts
2. **Activity Feed announcement** — what Hazar drops in his `<handle>.log.md`
3. **One-line elevator pitch** — for friend-group out-of-band sharing

Replace `<…>` placeholders before publishing.

---

## 1. GitHub Release body

> Paste this (after editing) into the body of the v1.0.0 GitHub Release. The `release.yml` workflow may auto-populate from the CHANGELOG excerpt — if so, this is the override copy.

### Title

```
Startup Framework v1.0.0 — the first stable
```

### Body (target: ≤500 words)

```markdown
# v1.0.0 — the first stable

The Startup Framework's first ship. A private Claude Code framework for a friend group building startups together.

## What it ships

- **6 curated plugins** — Superpowers, Skill Creator, claude-mem, Context Mode, context7, claude-md-management. One conditional plugin (Frontend Design). One documented-not-bundled (Ralph).
- **Per-friend hierarchical wiki** — your design history, lives on your machine, optional self-sync via your own git remote.
- **Activity Feed** — cross-friend session reports via a shared private GitHub repo. Terse-format-as-privacy. Per-session opt-out (`/sf:wrap --skip-feed`).
- **Schema-versioned wiki pages** — 16 page-types registered at schema v1. Future versions ship migrations; your wiki stays readable.
- **Self-improving skills** — `/sf:improve-skill` runs the Karpathy auto-research loop with four safety primitives (per ADR-012).
- **One-command install** — `/sf:install` walks 7 stages in ~10 minutes.
- **One-command verify** — `/sf:doctor` reports env + plugins + schemas + update + backup status in one screen.
- **Opt-in updates** — `/sf:update` is user-invoked; never automatic. Snapshot before every migration. Latest 3 retained.

## Install

```
/plugin marketplace add <org>/sf-marketplace
/plugin install startup-framework@sf-marketplace
/sf:install
```

10 minutes. You're done.

## License

Framework itself: MIT.

Curated stack mix: MIT (Superpowers, framework code), Apache-2.0 (Skill Creator, claude-mem), ELv2 (Context Mode — SaaS distribution restricted). See `LICENSES.md` in your install for the full surface.

## Curated stack — what each plugin earns its slot for

| Plugin | Solves |
|---|---|
| Superpowers | development methodology (7-phase workflow) |
| Skill Creator | skill authoring + Layer 1 description optimizer |
| claude-mem | cross-session memory (3-layer progressive disclosure) |
| Context Mode | within-session token efficiency (~58× compression) |
| context7 | version-aware docs lookup (no more "wrote code against an outdated library") |
| claude-md-management | CLAUDE.md quality audit + session-learning capture |

## Cadence going forward

- **Monthly stable releases.** Never daily. Out-of-cycle patches only for security or broken hooks.
- **Opt-in updates.** `/sf:doctor` notifies; you decide when to upgrade.
- **N+3 schema deprecation window.** Pages stay readable for 3 framework versions after a schema bump.
- **Pre-release channel (RC).** Friends who want early access subscribe to `sf-marketplace-rc`; dogfood for a week before stable.

## What's deliberately NOT in v1

Per ADR-023:
- Shared wiki across friends (wikis are per-friend-local; cross-friend visibility is the Activity Feed only)
- Auto-update on session start
- Daily release cadence
- Cross-LLM portability (Claude-Code-only at v1; content is portable markdown)
- A `/sf:rollback` slash command (use `/sf:update --restore-snapshot` flag instead)

## Acknowledgements

To the four sub-teams who built this: sf-onboarding, sf-lifecycle, sf-feed, sf-distribution. Cross-team review caught real bugs; the integration validation pass caught a few more. Shipping > shipping perfectly.

To the friend group who'll use it: feedback shapes v1.1.

## Get going

```
/sf:install
```

See you in the Activity Feed.
```

---

## 2. Activity Feed announcement template

> Paste into your `<handle>.log.md` in the activity-feed repo after the tag is pushed.

```markdown
## [<YYYY-MM-DD HH:MM>] release | <your-handle> | framework v1.0.0 stable shipped — see CHANGELOG
```

That's the line. The Activity Feed terse-format constraint (per ADR-021) means we don't write more. Friends pulling the feed on their next `/sf:wake-up` will see the entry; `/sf:doctor` will detect the update.

If you want to add nuance (a one-liner about what to try first), append a second short entry within the same minute:

```markdown
## [<YYYY-MM-DD HH:MM>] note | <your-handle> | first stable. /sf:doctor expects N=0 warnings on a fresh install. If you hit any, paste output in our group thread.
```

Two lines max. Detailed announcements go in the GitHub Release body, not the feed.

---

## 3. Friend-facing one-line elevator pitch

For WhatsApp / Discord / wherever the friend group hangs out. Use one of these — your call which:

### Option A (lean / functional)

> A private Claude Code framework for our friend group. Installs in 10 minutes via `/plugin marketplace add <org>/sf-marketplace`. Per-friend wiki + cross-friend visibility + opt-in updates. Try `/sf:install` when you have a quiet hour.

### Option B (memory-pain-led)

> If you're tired of re-explaining your context to Claude every session, this framework fixes it. 10-minute install. Your wiki stays on your machine. We see each other's high-level activity via a shared feed. Try it: `/plugin marketplace add <org>/sf-marketplace` → `/sf:install`.

### Option C (cinematic)

> v1 of the framework is up. The bet: Claude is sharper when it remembers you. Install: `/plugin marketplace add <org>/sf-marketplace` → `/sf:install`. 10 minutes, then run a session normally and tell me what felt different.

### Option D (your own words)

Whatever you write — keep it ≤2 sentences for the pitch + the two install commands. The framework's job is to feel low-friction; the announcement should too.

---

## Maintainer reminders

- The `release.yml` workflow will auto-create a GitHub Release on tag push. The body it auto-populates comes from `CHANGELOG.md`'s v1.0.0 entry. If you want THIS file's body content used instead, paste it manually after the release is created.
- The auto-`--prerelease` flag fires on `-rc.*` tags. v1.0.0 (no `-rc.` suffix) ships as a full release.
- After tagging: post the Activity Feed announcement BEFORE notifying friends out-of-band. The feed is the canonical "where it shipped" timestamp.
- Friends with `userConfig.rcChannel = true` will continue tracking sf-marketplace-rc. They're already running RC-equivalent content; the stable tag is their cue to switch back to the stable marketplace if they want.

If anything goes wrong post-tag: `docs/RELEASING.md` § Recovery from a bad release. The PATCH escape hatch (v1.0.1) is always available.
