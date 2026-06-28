# RenOS

> *from **仁 (rén)** — the Confucian word for **humaneness**: the irreducible human core of any system.*

**RenOS** is a governable second-brain OS for Claude Code. Claude Code now ships the muscle — scheduled
routines, agent teams, background memory. RenOS is the thin, governable layer that aims all of it at a
single source of truth you actually own: a transparent wiki you can read, override, and steer. The
machine runs the muscle; **you stay the mind.**

Most memory systems consolidate in the dark and hand you a black box. RenOS keeps the brain in the open
and in your hands. **Ship the engine — you bring the 仁.**

You install it once, run `/ren:install`, and from then on every Claude Code session wakes up already
knowing your projects, your decisions, and where you left off.

> **Solo-first.** RenOS runs per-person and fully local — your wiki lives on *your* disk and never
> leaves it unless you push it to your own backup remote. (Anyone you share the plugin with runs their
> own independent copy; there is no shared cross-user channel.)

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

`/ren:install` sets up a vetted set of Claude Code plugins that work well together (development
methodology, cross-session memory, token-efficient context, version-aware docs, more). And because
**keys ≠ instructions** — a granted capability is not the same as a documented intent — `/ren:doctor
--permissions` gives you a read-only audit of which tool-keys are actually on your ring (MCP
servers, `allow`/`deny`/`ask` rules, broad grants like a bare `Bash`), so what the docs *say* and
what your tools *can do* can't quietly drift apart.

### Capabilities — `/ren:*` skills with eval hygiene

The framework's own skills (`/ren:wrap`, `/ren:recall`, `/ren:note`, `/ren:improve-skill`, …) ship with
execution contracts and binary evals. Two of them — `/ren:wrap`'s signal classifier and
`/ren:improve-skill` — are marked **EXPERIMENTAL** on purpose: the **bike-method** of earned trust.
The training wheels stay on (a conservative deterministic default for `/ren:wrap`; a wired but
autonomy-gated eval loop for `/ren:improve-skill`) until real supervised runs prove the autonomy out.
`/ren:improve-skill` now runs against a real LLM-judge backend; `--autonomous` mode requires hard
ceilings (`--max-iterations` + `--max-budget-usd`) and the EXPERIMENTAL label lifts only after
≥3 logged clean supervised runs (ADR-036).

### Cadence — a deterministic daily loop

`/ren:wrap` at session end consolidates *real* signal into your wiki (most sessions write nothing —
that's the discipline, not a bug). `/ren:insights` mines your local Claude Code session history for
what's working and what's slowing you down. Upgrades are schema-versioned with
snapshot-before-migrate and are always opt-in.

---

## Requirements

- **Claude Code** ≥ 1.0.33 (run `claude --version`; update with `npm i -g @anthropic-ai/claude-code@latest` or `brew upgrade claude-code`).
- **`gh`** (GitHub CLI), authenticated (`gh auth status`) — used by `/ren:doctor`'s update check and `/ren:update` to read the marketplace. Optional unless you want update notifications.
- **`python3`** (3.10+) — the wake-up hook and several skills are Python (standard library only).

`/ren:doctor` checks all of this for you after install.

---

## Install (about 10 minutes)

```text
/plugin marketplace add hazarsozer/ren-os
/plugin install ren@ren-os
/reload-plugins
/ren:install
```

1. **`/plugin marketplace add hazarsozer/ren-os`** — registers the private marketplace
   (ask the maintainer to add you as a read collaborator first).
2. **`/plugin install ren@ren-os`** — installs the plugin.
3. **`/reload-plugins`** — activates it in the current session.
4. **`/ren:install`** — runs the 7-stage onboarding: environment check → required plugins →
   conditional/optional plugins → identity → wiki skeleton → `/ren:doctor` verification →
   first-session walkthrough. It's idempotent — re-run it any time and it resumes where it left off.

> Updating later? `/plugin marketplace update ren-os` refreshes the catalog.

---

## The daily loop

- **Wake up (automatic).** A SessionStart hook injects your wiki context at the start of every
  session — your master index, the current project's state, and recent log. Nothing to run.
- **Work.** Use Claude Code normally. The curated stack is doing its job underneath.
- **`/ren:wrap` (session end).** Consolidates what you learned and, *if* there's real signal
  (a decision, a pattern, a gotcha, a stack change), writes it to your wiki. Most sessions write
  nothing — that's the discipline, not a bug. *(The classifier is EXPERIMENTAL — see Capabilities.)*

Helpers:

- **`/ren:bootstrap-project <name>`** — scaffolds a project sub-wiki.
- **`/ren:ingest-project [path]`** — brownfield counterpart to `/ren:bootstrap-project`: reads an existing project (read-only), drafts a populated sub-wiki from its README/stack/git history, previews it, and writes on your approval.
- **`/ren:insights`** — read-only: mines your local session history for what's working / what's
  slowing you down (`--days N`, `--project <name>`).
- **`/ren:doctor --permissions`** — read-only audit of the tool-keys on your ring (keys ≠ instructions).

---

## Your wiki is yours

The framework's load-bearing principle: **your wiki is private, local, and yours.** It lives on
*your* machine; the maintainer never touches it; nothing in it is pushed anywhere you didn't
choose. The only outbound path is the backup remote *you* configure for `/ren:backup` (per
`docs/RECOVERY.md`) — there is no cross-user channel.

By default your wiki lives at `~/.startup-framework/wiki/`. You can move it via the
`wikiRoot` plugin setting. Your code-projects root (used for project detection) defaults to
`~/Dev`; change it with the `devRoot` setting if you keep projects elsewhere (e.g. `~/code`).

---

## Commands

| Command | What it does |
|---|---|
| `/ren:install` | One-time (idempotent) onboarding — sets up the whole framework |
| `/ren:doctor` | Health check: environment, plugins, schema versions, available updates, backups |
| `/ren:doctor --permissions` | Read-only **permission audit** ("keys on your ring") — MCP servers, allow/deny rules, broad grants, enabled plugins/hooks. Never prints secrets. |
| `/ren:update` | Opt-in framework upgrade — snapshots, migrates your wiki, shows diffs for approval |
| `/ren:wrap` | End-of-session consolidation into your wiki (only when there's real signal) |
| `/ren:insights` | Read-only insights from your local Claude Code session history (`--days`, `--project`) |
| `/ren:bootstrap-project <name>` | Create a project sub-wiki |
| `/ren:ingest-project [path]` | Brownfield ingest — read-only scan, populated sub-wiki draft, writes on approval |
| `/ren:code-map` | Read-only symbol→line-range code-map via lean-ctx; load-on-demand, regenerable cache. |

(Plus an automatic SessionStart wake-up hook — you never invoke it directly.)

---

## Keeping up to date

Releases are **monthly stable** (with out-of-cycle patches for security or broken-hook fixes).

- **`/ren:doctor`** tells you when a new version is available. It never updates on its own.
- **`/ren:update`** performs the upgrade *when you choose to* — it snapshots your wiki first,
  runs any schema migrations, and shows you a diff to approve before anything is written.
  There is **no auto-update on session start**; updates are always opt-in.

Want early access to release candidates? Enable the `rcChannel` plugin setting and use
`/ren:update --rc`. Everyone else rides the monthly stable cadence.

If something ever goes wrong, **`docs/RECOVERY.md`** walks through the recovery scenarios
(snapshots, rollback, re-bootstrap).

---

## Licensing

The RenOS itself is **MIT** (declared in the plugin manifest). The curated stack it
installs is a mix of **MIT**, **Apache-2.0**, and **Elastic License v2 (ELv2)**.

⚠️ **Read `LICENSES.md` before you ship a hosted SaaS.** One component (**Context Mode**) is ELv2,
which restricts offering it as a hosted/managed service to third parties without a separate
commercial agreement. Personal use, team use, and shipping it inside your own product are fine —
`LICENSES.md` spells out exactly what that means for you.

---

*Maintained by [Hazar Sozer](https://github.com/hazarsozer). Private distribution for the friend
group — see the maintainer to be added as a collaborator. MIT licensed.*
