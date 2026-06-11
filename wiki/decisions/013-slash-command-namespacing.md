---
title: "ADR-013: Slash Command Namespacing — `/sf:*` Prefix for All Framework Commands"
status: superseded
superseded-by: "ADR-033 (2026-06-11): RenOS rebrand — command namespace /sf: → /ren:"
date: 2026-05-28
sunset-review: 2027-05-28
references-pages: [context-mode, claude-mem, superpowers, ralph]
affects-components: [slash-commands, install, docs, ux]
relates-to: [006-curated-stack, 008-wake-up-hook, 009-consolidate-via-wrap, 012-self-improvement]
---

# ADR-013: Slash Command Namespacing — `/sf:*` Prefix for All Framework Commands

> ⚠️ **SUPERSEDED by [ADR-033](033-renos-rebrand.md) (2026-06-11).** The RenOS rebrand changed the command namespace from `/sf:` to `/ren:` (plugin `name: sf → ren`). This ADR's `/sf:` references are preserved as the historical record of the original decision; the shipped surface now uses `/ren:`.

## Context

Slash commands are how users invoke skills, hooks, and configuration utilities in Claude Code. Each plugin in our adopted stack registers its own:

| Plugin | Example commands |
|---|---|
| **Context Mode** | `/context-mode:ctx-stats`, `/context-mode:ctx-doctor`, `/context-mode:ctx-purge`, `/context-mode:ctx-insight` |
| **claude-mem** | (uses MCP tools more than slash commands; minimal slash surface) |
| **Superpowers** | (skills activate automatically; few explicit slash commands at the user level) |
| **Skill Creator** | `/skill-creator` |
| **Ralph** (if installed) | `/ralph-loop`, `/cancel-ralph` |
| **Anthropic built-in** | `/re`, `/ultrareview`, `/compact`, `/clear`, `/model`, `/plugin`, ... |

The configuration is going to introduce its own commands (already mentioned across other ADRs):

- `/sf:wake-up` (manual re-wake; per ADR-008 it's mostly automatic via hook but available manually)
- `/sf:wrap` (consolidate; per ADR-009)
- `/sf:note <text>` (pin during session; per ADR-009)
- `/sf:recall <query>` (mid-session wiki query; per ADR-009)
- `/sf:improve-skill <name>` (Layer 2 self-improvement; per ADR-012)
- `/sf:doctor` (install verification; per ADR-010 and forthcoming ADR-015)
- Future: `/sf:lint-skills`, `/sf:audit-stack`, `/sf:wrap-checkpoint`, etc.

Without a consistent prefix, our commands risk:
1. **Name collisions** with Anthropic built-ins or other plugins (e.g., if someone names a skill `improve-skill` and a built-in arrives with the same name)
2. **Discoverability problems** — friends typing `/` to autocomplete won't easily find our commands among the long list
3. **Identity confusion** — friends won't know which command came from where when debugging
4. **Future-proofing** — as the ecosystem grows, namespace pollution becomes worse

Context Mode demonstrates the right pattern: every command starts with `/context-mode:` (using Claude Code's plugin-namespacing convention). We adopt the same approach.

## Decision

**All framework-shipped slash commands use the `/sf:` prefix.**

`sf` stands for **startup-framework** (the directory name + the user's working title). Short enough to type quickly; specific enough to disambiguate.

**Naming conventions:**

| Command type | Pattern | Example |
|---|---|---|
| Skill invocation | `/sf:<skill-name>` | `/sf:improve-skill` |
| Lifecycle action | `/sf:<verb>` | `/sf:wrap`, `/sf:wake-up` |
| Utility / introspection | `/sf:<noun>` | `/sf:doctor`, `/sf:audit-stack` |
| Mid-session helper | `/sf:<verb-or-noun>` | `/sf:note`, `/sf:recall` |

**Rules:**

1. **Verbs in imperative form** for actions: `/sf:wrap`, `/sf:improve-skill`, `/sf:audit-stack`
2. **Kebab-case** for multi-word commands
3. **No alias-only commands without an alias-target** (every alias points to a real command)
4. **One canonical name per command.** If we want `/sf:wrap` and `/sf:consolidate` both available, one is the canonical name and the other is documented as an alias; auto-completion shows the canonical one first.

**Documented aliases** (when intuitive synonyms exist):

| Canonical | Aliases |
|---|---|
| `/sf:wrap` | (none in v1; `/sf:consolidate` could be a v2 alias if friends prefer the longer name) |
| `/sf:improve-skill` | (none) |
| `/sf:doctor` | (none) |
| `/sf:recall` | (none; `/sf:query` was considered but recall better captures the wiki-search semantics) |

**Cross-plugin command compatibility**: our prefix doesn't interfere with Context Mode's `/context-mode:*` or Skill Creator's `/skill-creator` or Anthropic built-ins (`/re`, `/ultrareview`, `/compact`, etc.). Each plugin has its own namespace; ours is `/sf:`.

**Plain `/sf` (no colon, no command)**: reserved for showing a help index of all `/sf:*` commands. If Claude Code's slash command system supports it, `/sf` alone prints something like:

```
Startup Framework commands:
  /sf:wake-up         Re-load wiki context manually
  /sf:wrap            Consolidate session learnings into wiki
  /sf:note <text>     Pin something for /sf:wrap to consider
  /sf:recall <q>      Query the wiki without auto-loading more
  /sf:improve-skill <name>   Run Layer 2 self-improvement loop
  /sf:doctor          Verify install + diagnose issues
```

If `/sf` alone isn't supported by Claude Code (some slash systems require a colon-or-nothing), then `/sf:help` is the canonical help command.

## Consequences

**Easier:**
- **Auto-complete is clean.** Typing `/sf` shows all the configuration's commands at once.
- **No collisions with built-ins or other plugins.** Anthropic's `/re` and our hypothetical `/sf:re` couldn't clash.
- **Identity is obvious.** When a command misbehaves, the prefix tells the user where to look (and where to file the bug).
- **Future expansion is safe.** We can add `/sf:*` commands without worrying about ecosystem collisions.

**Harder:**
- **More typing.** `/sf:wrap` is 8 characters vs. `/wrap` is 5. Mitigation: short prefix, kebab-case for multi-word, friends adopt the namespace via muscle memory.
- **Friends switching from other tools** may type `/wrap` (without prefix) out of habit. Document the prefix prominently in onboarding.

**Now impossible:**
- Bare `/wrap`, `/recall`, `/improve-skill`, etc. as framework commands. They MUST be prefixed.

**Sunset review trigger conditions:**
- Claude Code introduces a global "preferred plugin" or "default namespace" mechanism that obviates manual prefixing → revisit
- The configuration is significantly renamed (e.g., friend group picks a project name and the dir/prefix should follow) → revisit prefix
- A widely-adopted convention emerges in the broader ecosystem that conflicts with `/sf:` → revisit

## Alternatives considered

### A) No prefix; bare commands like `/wrap` and `/note`

**Considered shape**: Skip namespacing. Use short, intuitive names.

**Why rejected**: Collision risk with built-ins, other plugins, future additions. The friend group's wiki will outlive any short-term convenience. Some friend later installs another plugin that uses `/wrap`, and now we have a problem.

### B) Different prefix (`/saf:`, `/team:`, `/yo:`, etc.)

**Considered shape**: Pick a different short prefix.

**Why rejected**: `/sf:` matches the directory name (`startup-framework/`), is unique enough not to clash with common other prefixes, and is short. Other options either conflict (`/team:` could be too generic; `/yo:` is too casual for an internal tool) or aren't more memorable.

### C) Longer prefix (`/startup-framework:*`)

**Considered shape**: Full name as prefix for maximum clarity.

**Why rejected**: Too long to type repeatedly. Context Mode's experience (`/context-mode:ctx-stats` is already 22 characters before the command) shows long prefixes get annoying. `/sf:` is the right balance.

### D) Multiple prefixes by command category (`/skill:*` for skills, `/wiki:*` for wiki actions, `/install:*` for setup)

**Considered shape**: Categorize commands by domain with different prefixes.

**Why rejected**: Overcomplicated. Friends would have to remember which category each command belongs to. Single namespace is simpler and discoverable.

### E) Match Context Mode's `/<plugin>:<subcommand>` pattern exactly

**Considered shape**: Use `/startup-framework:wrap` (full name + colon + command).

**Why rejected**: This is what alternative C above proposes. Same rejection reasoning. `/sf:` is a deliberate short-form.

## References

- `wiki/research/context-mode.md` — `/context-mode:*` namespacing pattern that informed our approach
- `wiki/research/superpowers.md` — auto-activating skills (less reliant on slash commands)
- `wiki/research/ralph.md` — `/ralph-loop` + `/cancel-ralph` slash patterns
- `wiki/research/claude-mem.md` — minimal slash surface (MCP-driven)
- ADR-006 (Curated Stack) — names other plugins whose slash commands we coexist with
- ADRs 008, 009, 012 — name the specific `/sf:*` commands this ADR formalizes
