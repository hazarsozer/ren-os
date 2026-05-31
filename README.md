# Startup Framework

> A private Claude Code plugin that turns every session into a compounding system:
> a per-project hierarchical wiki (long-term memory) + a curated plugin stack +
> self-improving skills — all wired into one daily loop.

You install it once, run `/sf:install`, and from then on every Claude Code session wakes up
already knowing your projects, your decisions, and where you left off.

> **Solo-first.** The framework runs per-person and fully local — your wiki lives on *your* disk
> and never leaves it unless you push it to your own backup remote. (Friends you share the plugin
> with each run their own independent copy; there is no shared cross-user channel.)

---

## What you get — the Four C's

The framework is organized around four layers — a framing borrowed lightly from Nate Herk's
*"Building an AI Operating System on Claude Code"*: **Context → Connections → Capabilities →
Cadence**, each built on the one before it.

### Context — a wiki that remembers

Every session starts with your relevant context auto-injected (decisions, project state, recent
log) — no re-explaining. You own it; it lives on *your* disk. This is the **default shift**: the
right context is loaded *by default*, so you begin every session already oriented instead of
re-establishing where you left off.

### Connections — a curated, audited stack

`/sf:install` sets up a vetted set of Claude Code plugins that work well together (development
methodology, cross-session memory, token-efficient context, version-aware docs, more). And because
**keys ≠ instructions** — a granted capability is not the same as a documented intent — `/sf:doctor
--permissions` gives you a read-only audit of which tool-keys are actually on your ring (MCP
servers, `allow`/`deny`/`ask` rules, broad grants like a bare `Bash`), so what the docs *say* and
what your tools *can do* can't quietly drift apart.

### Capabilities — `/sf:*` skills with eval hygiene

The framework's own skills (`/sf:wrap`, `/sf:recall`, `/sf:note`, `/sf:improve-skill`, …) ship with
execution contracts and binary evals. Two of them — `/sf:wrap`'s signal classifier and
`/sf:improve-skill` — are marked **EXPERIMENTAL** on purpose: the **bike-method** of earned trust.
The training wheels stay on (a conservative deterministic default for `/sf:wrap`; an honest
"requires a configured backend" for `/sf:improve-skill`) until real runs prove the autonomy out.

### Cadence — a deterministic daily loop

`/sf:wrap` at session end consolidates *real* signal into your wiki (most sessions write nothing —
that's the discipline, not a bug). `/sf:insights` mines your local Claude Code session history for
what's working and what's slowing you down. Upgrades are schema-versioned with
snapshot-before-migrate and are always opt-in.

---

## Requirements

- **Claude Code** ≥ 1.0.33 (run `claude --version`; update with `npm i -g @anthropic-ai/claude-code@latest` or `brew upgrade claude-code`).
- **`gh`** (GitHub CLI), authenticated (`gh auth status`) — used by `/sf:doctor`'s update check and `/sf:update` to read the marketplace. Optional unless you want update notifications.
- **`python3`** (3.10+) — the wake-up hook and several skills are Python (standard library only).

`/sf:doctor` checks all of this for you after install.

---

## Install (about 10 minutes)

```text
/plugin marketplace add hazarsozer/sf-marketplace
/plugin install sf@sf-marketplace
/reload-plugins
/sf:install
```

1. **`/plugin marketplace add hazarsozer/sf-marketplace`** — registers the private marketplace
   (ask the maintainer to add you as a read collaborator first).
2. **`/plugin install sf@sf-marketplace`** — installs the plugin.
3. **`/reload-plugins`** — activates it in the current session.
4. **`/sf:install`** — runs the 7-stage onboarding: environment check → required plugins →
   conditional/optional plugins → identity → wiki skeleton → `/sf:doctor` verification →
   first-session walkthrough. It's idempotent — re-run it any time and it resumes where it left off.

> Updating later? `/plugin marketplace update sf-marketplace` refreshes the catalog.

---

## The daily loop

- **Wake up (automatic).** A SessionStart hook injects your wiki context at the start of every
  session — your master index, the current project's state, and recent log. Nothing to run.
- **Work.** Use Claude Code normally. The curated stack is doing its job underneath.
- **`/sf:wrap` (session end).** Consolidates what you learned and, *if* there's real signal
  (a decision, a pattern, a gotcha, a stack change), writes it to your wiki. Most sessions write
  nothing — that's the discipline, not a bug. *(The classifier is EXPERIMENTAL — see Capabilities.)*

Helpers:

- **`/sf:bootstrap-project <name>`** — scaffolds a project sub-wiki.
- **`/sf:insights`** — read-only: mines your local session history for what's working / what's
  slowing you down (`--days N`, `--project <name>`).
- **`/sf:doctor --permissions`** — read-only audit of the tool-keys on your ring (keys ≠ instructions).

---

## Your wiki is yours

The framework's load-bearing principle: **your wiki is private, local, and yours.** It lives on
*your* machine; the maintainer never touches it; nothing in it is pushed anywhere you didn't
choose. The only outbound path is the backup remote *you* configure for `/sf:backup` (per
`docs/RECOVERY.md`) — there is no cross-user channel.

By default your wiki lives at `~/.startup-framework/wiki/`. You can move it via the
`wikiRoot` plugin setting. Your code-projects root (used for project detection) defaults to
`~/Dev`; change it with the `devRoot` setting if you keep projects elsewhere (e.g. `~/code`).

---

## Commands

| Command | What it does |
|---|---|
| `/sf:install` | One-time (idempotent) onboarding — sets up the whole framework |
| `/sf:doctor` | Health check: environment, plugins, schema versions, available updates, backups |
| `/sf:doctor --permissions` | Read-only **permission audit** ("keys on your ring") — MCP servers, allow/deny rules, broad grants, enabled plugins/hooks. Never prints secrets. |
| `/sf:update` | Opt-in framework upgrade — snapshots, migrates your wiki, shows diffs for approval |
| `/sf:wrap` | End-of-session consolidation into your wiki (only when there's real signal) |
| `/sf:insights` | Read-only insights from your local Claude Code session history (`--days`, `--project`) |
| `/sf:bootstrap-project <name>` | Create a project sub-wiki |

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
