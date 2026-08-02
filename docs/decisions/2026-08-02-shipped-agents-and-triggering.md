# Decision — shipped-agents mechanism + the triggering-channel doctrine

- **Date:** 2026-08-02
- **Status:** accepted
- **Scope:** `agents/ren-wiki-lint.md`, `agents/ren-planner.md`,
  `skills/wiki-health/lib` (`run_incremental_lint`, watermark), `skills/wrap`
  (session-summary journal line + non-blocking lint spawn + open-work
  reconcile), `hooks/wake-up/wakeup` (unlinted nudge + open-work section +
  doctrine card v2), `skills/doctor` (`agent_shadowing` check)

> Dated-filename convention, same as `2026-08-02-execution-doctrine-layer.md`
> and the other 2026-08-01 records — this repo has no numbered ADR series.

## Context

0.6.4 shipped RenOS's first agent (`ren-reviewer`) as a single-purpose
enforcement arm for the doctrine card's review gate, and left the
shipped-agents *mechanism* — how a second, third, Nth agent gets discovered,
kept from colliding with a friend's own agents, and actually triggered
without the model having to remember it exists — as 0.6.5's explicit scope
(see that ADR's Consequences). This train (0.6.5) built the substrate a
shipped agent needs to be useful rather than decorative:

- an append-only session-summary journal (`wrap`) so there is something to
  lint incrementally in the first place;
- a lint watermark + incremental selection (`wiki-health`) so a hygiene
  agent only ever looks at what changed;
- `run_incremental_lint`, which routes safe fixes through the write queue
  and judgment-shaped findings to the suggestions store — the wiki-write
  discipline the rest of the framework already follows;
- an open-work ledger so "what's still open" is a queryable wiki fact, not
  something living only in a human's head between sessions;
- `ren-planner`, a wiki-aware plan decomposer for the doctrine card's
  decompose gate.

Two shipped agents (`ren-wiki-lint`, `ren-planner`) now exist alongside
`ren-reviewer`, each triggered from a different place. Without naming those
places explicitly, a shipped agent risks becoming reachable only by an
operator who happens to remember the right invocation — the same failure
mode the execution-doctrine-layer ADR diagnosed for process discipline in
general (context injection, not installation, was the actual gap).

## Decision

1. **A shipped agent's trigger sites are load-bearing, not incidental.**
   Every shipped agent must be reachable through at least one of three
   channels (see §Triggering doctrine below), and its frontmatter
   `description:` must say which. An agent file with no named channel is
   dead weight — same reasoning the execution-doctrine ADR gave for
   rejecting a skill-only doctrine ("skills are pulled, not pushed").

2. **`agent_shadowing` doctor check.** A user-level or project-level
   `.claude/agents/<name>.md` whose filename collides with a shipped
   `agents/*.md` shadows the shipped behavior (Claude Code resolves agent
   names to whichever definition it finds first; the shipped one is not
   guaranteed to win). The check warns, naming the colliding agent(s), and
   covers both `claude_user_dir()/agents` and — when the current directory
   resolves to a project the repo-path↔slug registry knows about — that
   project's own `.claude/agents/` too, so the same collision is caught
   whether a friend's conflicting agent lives globally or per-project.

3. **Hygiene and planning stay read-mostly / scratch-only.** `ren-wiki-lint`
   never edits wiki pages directly — every write goes through the
   `wiki-health` engine's write queue, and judgment-shaped findings become
   suggestions rather than silent edits. `ren-planner` writes only brief
   files to a scratch directory, never the wiki or the repo. Neither
   pattern is new (the write-queue discipline predates this train), but
   codifying it here keeps future shipped agents from reaching for a
   shortcut that bypasses it.

## Triggering doctrine

A shipped agent is reachable through exactly one or more of three channels.
Every future shipped agent's frontmatter `description:` names which:

1. **The doctrine card** (`hooks/wake-up/wakeup/doctrine_card.py`) — a gate
   in the wake-up-injected execution doctrine names the agent directly.
   `ren-planner` is named at the decompose gate; `ren-reviewer` at the
   review gate.
2. **Wrap steps** (`skills/wrap/lib`) — `/ren:wrap` spawns the agent as part
   of session close-out. `ren-wiki-lint` is spawned non-blocking at wrap
   close-out.
3. **Wake-up nudges** (`hooks/wake-up/wakeup`) — a wake-up-rendered section
   names the agent as the fix for a detected condition. The unlinted-journal
   nudge names `ren-wiki-lint`; the open-work `## Open work` section is the
   parallel pattern for surfacing a condition, though it currently prompts
   the human rather than naming an agent to spawn.

A shipped agent named in none of the three is functionally uninstalled —
the file exists on disk (per `/ren:install`) but nothing in a session's
actual context ever surfaces it, which is the same "installation, not
injection" gap the execution-doctrine-layer ADR closed for process
discipline. `check_agent_shadowing` protects a shipped agent's *name* once
it exists; this section is what keeps a new shipped agent from shipping
unreachable in the first place.

## Alternatives rejected

- **A central agent registry/dispatch table.** Rejected for 0.6.5: three
  agents do not yet justify an indirection layer over grep-able direct
  references in the doctrine card, wrap, and wake-up. Revisit if the count
  grows enough that keeping references in sync by hand becomes error-prone.
- **Shadowing check blocks (`error`) instead of `warn`.** Rejected: a
  friend's own same-named agent may be an intentional override (the
  execution-doctrine ADR's own detect-and-delegate precedent treats
  presence/absence of external tooling as routing information, not a hard
  failure) — the check's job is to make the collision visible, not to
  assume it is always the friend's mistake.

## Consequences

- `ren-wiki-lint` and `ren-planner` join `ren-reviewer` as shipped agents,
  each reachable from a documented, grep-able trigger site rather than
  living only as a file on disk.
- `check_agent_shadowing` extends the 0.6.4 execution-doctrine check family
  (`execution_doctrine`) with the shipped-agent-integrity half of the same
  concern: doctrine now verifies both that its referenced agents *exist*
  and that nothing silently shadows them.
- The next shipped agent (the wiki/memory-health family named in the
  execution-doctrine-layer ADR's Consequences) has a doctrine to follow
  rather than a precedent to reverse-engineer: name your channel(s) in the
  frontmatter, write through the existing queue/scratch discipline, and the
  doctor check picks up the collision case for free.
