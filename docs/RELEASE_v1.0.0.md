# Release v1.0.0 — artifacts

Scaffold for Hazar to fill in at first-ship. Two pieces:

1. **GitHub Release body** — what `gh release create` posts
2. **One-line elevator pitch** — for friend-group out-of-band sharing

Replace `<…>` placeholders before publishing.

(Activity Feed removed — ADR-031, solo-first pivot. There is no feed announcement; out-of-band notification + `CHANGELOG.md` + `/sf:doctor` carry "what shipped".)

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
- **Solo hierarchical wiki** — your design history, lives on your machine, optional self-sync via your own git remote.
- **Schema-versioned wiki pages** — 15 page-types registered at schema v1. Future versions ship migrations; your wiki stays readable.
- **Self-improving skills** — `/sf:improve-skill` runs the Karpathy auto-research loop with four safety primitives (per ADR-012).
- **One-command install** — `/sf:install` walks 7 stages in ~10 minutes.
- **One-command verify** — `/sf:doctor` reports env + plugins + schemas + update + backup status in one screen.
- **Opt-in updates** — `/sf:update` is user-invoked; never automatic. Snapshot before every migration. Latest 3 retained.

## Install

```
/plugin marketplace add <org>/sf-marketplace
/plugin install sf@sf-marketplace
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

Per ADR-023 + ADR-031:
- Any cross-user / multi-user layer — the framework is solo-first (the Activity Feed was removed; wikis are local-only)
- Auto-update on session start
- Daily release cadence
- Cross-LLM portability (Claude-Code-only at v1; content is portable markdown)
- A `/sf:rollback` slash command (use `/sf:update --restore-snapshot` flag instead)

## Acknowledgements

To the sub-teams who built this: sf-onboarding, sf-lifecycle, sf-distribution. Cross-team review caught real bugs; the integration validation pass caught a few more. Shipping > shipping perfectly.

To the friend group who'll use it: feedback shapes v1.1.

## Get going

```
/sf:install
```

Run a session and tell me what felt different.
```

---

## 2. Friend-facing one-line elevator pitch

For WhatsApp / Discord / wherever the friend group hangs out. Use one of these — your call which:

### Option A (lean / functional)

> A private Claude Code framework for our friend group. Installs in 10 minutes via `/plugin marketplace add <org>/sf-marketplace`. Per-person local wiki + opt-in updates. Try `/sf:install` when you have a quiet hour.

### Option B (memory-pain-led)

> If you're tired of re-explaining your context to Claude every session, this framework fixes it. 10-minute install. Your wiki stays on your machine — yours alone. Try it: `/plugin marketplace add <org>/sf-marketplace` → `/sf:install`.

### Option C (cinematic)

> v1 of the framework is up. The bet: Claude is sharper when it remembers you. Install: `/plugin marketplace add <org>/sf-marketplace` → `/sf:install`. 10 minutes, then run a session normally and tell me what felt different.

### Option D (your own words)

Whatever you write — keep it ≤2 sentences for the pitch + the two install commands. The framework's job is to feel low-friction; the announcement should too.

---

## Maintainer reminders

- The `release.yml` workflow will auto-create a GitHub Release on tag push. The body it auto-populates comes from `CHANGELOG.md`'s v1.0.0 entry. If you want THIS file's body content used instead, paste it manually after the release is created.
- The auto-`--prerelease` flag fires on `-rc.*` tags. v1.0.0 (no `-rc.` suffix) ships as a full release.
- After tagging: notify friends out-of-band. The `CHANGELOG.md` entry + `/sf:doctor`'s update notice are the canonical "what shipped" record (Activity Feed removed — ADR-031).
- Friends with `userConfig.rcChannel = true` will continue tracking sf-marketplace-rc. They're already running RC-equivalent content; the stable tag is their cue to switch back to the stable marketplace if they want.

If anything goes wrong post-tag: `docs/RELEASING.md` § Recovery from a bad release. The PATCH escape hatch (v1.0.1) is always available.
