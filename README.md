# Startup Framework

> A private Claude Code plugin for a small group of friends building startups together.
> Per-friend hierarchical wiki (long-term memory) + a curated plugin stack + a cross-friend
> Activity Feed + self-improving skills — all wired into one daily loop.

You install it once, run `/sf:install`, and from then on every Claude Code session wakes up
already knowing your projects, your decisions, and what your friends have been shipping.

---

## What you get

- **A wiki that remembers.** Every session starts with your relevant context auto-injected
  (decisions, project state, recent log) — no re-explaining. You own it; it lives on *your* disk.
- **A curated stack.** `/sf:install` sets up a vetted set of Claude Code plugins that work well
  together (development methodology, cross-session memory, token-efficient context, docs, more).
- **A cross-friend Activity Feed.** Opt-in. See what the group shipped; share your own session
  highlights. High-signal only — routine work never pollutes the feed.
- **Self-improving skills.** The framework's own skills get better over time via an evaluation loop.
- **Safe upgrades.** Schema-versioned wiki with snapshot-before-migrate and opt-in updates.

---

## Requirements

- **Claude Code** ≥ 2.1.154 (run `claude --version`; update with `npm i -g @anthropic-ai/claude-code@latest` or `brew upgrade claude-code`).
- **`gh`** (GitHub CLI), authenticated (`gh auth status`) — used by the Activity Feed.
- **`python3`** (3.10+) — the wake-up hook and several skills are Python (standard library only).

`/sf:doctor` checks all of this for you after install.

---

## Install (about 10 minutes)

```text
/plugin marketplace add hazarsozer/sf-marketplace
/plugin install startup-framework@sf-marketplace
/reload-plugins
/sf:install
```

1. **`/plugin marketplace add hazarsozer/sf-marketplace`** — registers the private marketplace
   (ask the maintainer to add you as a read collaborator first).
2. **`/plugin install startup-framework@sf-marketplace`** — installs the plugin.
3. **`/reload-plugins`** — activates it in the current session.
4. **`/sf:install`** — runs the 7-stage onboarding: environment check → required plugins →
   Activity Feed + optional plugins → identity → wiki skeleton → `/sf:doctor` verification →
   first-session walkthrough. It's idempotent — re-run it any time and it resumes where it left off.

> Updating later? `/plugin marketplace update sf-marketplace` refreshes the catalog.

---

## The daily loop

- **Wake up (automatic).** A SessionStart hook injects your wiki context at the start of every
  session — your master index, the current project's state, and recent activity. Nothing to run.
- **Work.** Use Claude Code normally. The curated stack is doing its job underneath.
- **`/sf:wrap` (session end).** Consolidates what you learned and, *if* there's real signal
  (a decision, a pattern, a gotcha, a stack change), writes it to your wiki and emits a terse
  Activity Feed entry. Most sessions write nothing — that's the discipline, not a bug.

Project-scoped helpers:

- **`/sf:bootstrap-project <name>`** — scaffolds a project sub-wiki.
- **`/sf:catch-up <project>`** — summarizes recent friend activity for a project.

---

## Your wiki is yours

The framework's load-bearing principle: **every friend has their own private wiki on their own
machine.** The maintainer never touches your wiki, and your wiki is never pushed anywhere you
didn't choose. The only thing that crosses the group boundary is what *you* publish to the
Activity Feed via `/sf:wrap`.

By default your wiki lives at `~/.startup-framework/wiki/`. You can move it via the
`wikiRoot` plugin setting. Your code-projects root (used for project detection) defaults to
`~/Dev`; change it with the `devRoot` setting if you keep projects elsewhere (e.g. `~/code`).

---

## The Activity Feed (opt-in)

A separate private GitHub repo the group shares for short session reports. You set it up during
`/sf:install` (or skip it). Each friend appends to their own `<handle>.log.md`; nobody overwrites
anyone else's. `/sf:doctor` reports its health; `/sf:catch-up` summarizes it.

---

## Commands

| Command | What it does |
|---|---|
| `/sf:install` | One-time (idempotent) onboarding — sets up the whole framework |
| `/sf:doctor` | Health check: environment, plugins, schema versions, available updates, backups |
| `/sf:update` | Opt-in framework upgrade — snapshots, migrates your wiki, shows diffs for approval |
| `/sf:wrap` | End-of-session consolidation + Activity Feed entry (only when there's signal) |
| `/sf:bootstrap-project <name>` | Create a project sub-wiki |
| `/sf:catch-up <project>` | Summarize recent friend activity for a project |

(Plus an automatic SessionStart wake-up hook — you never invoke it directly.)

---

## Keeping up to date

Releases are **monthly stable** (with out-of-cycle patches for security or broken-hook fixes).

- **`/sf:doctor`** tells you when a new version is available. It never updates on its own.
- **`/sf:update`** performs the upgrade *when you choose to* — it snapshots your wiki first,
  runs any schema migrations, and shows you a diff to approve before anything is written.
  There is **no auto-update on session start**; updates are always opt-in.

Want early access to release candidates? Enable the `rcChannel` plugin setting and use
`/sf:update --rc`. Everyone else rides the monthly stable cadence.

If something ever goes wrong, **`docs/RECOVERY.md`** walks through the recovery scenarios
(snapshots, rollback, re-bootstrap).

---

## Licensing

The Startup Framework itself is **MIT** (declared in the plugin manifest). The curated stack it
installs is a mix of **MIT**, **Apache-2.0**, and **Elastic License v2 (ELv2)**.

⚠️ **Read `LICENSES.md` before you ship a hosted SaaS.** One component (**Context Mode**) is ELv2,
which restricts offering it as a hosted/managed service to third parties without a separate
commercial agreement. Personal use, team use, and shipping it inside your own product are fine —
`LICENSES.md` spells out exactly what that means for you.

---

*Maintained by [Hazar Sozer](https://github.com/hazarsozer). Private distribution for the friend
group — see the maintainer to be added as a collaborator. MIT licensed.*
