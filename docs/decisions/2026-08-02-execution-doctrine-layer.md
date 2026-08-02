# Decision — execution doctrine layer: wake-up-injected hard-gate card, detect-and-delegate, one shipped agent

- **Date:** 2026-08-02
- **Status:** accepted
- **Scope:** `hooks/wake-up/wakeup/doctrine_card.py`, `agents/ren-reviewer.md`,
  `skills/doctor` (`execution_doctrine` check)

> Dated-filename convention, same as the other 2026-08-01 records — this
> repo has no numbered ADR series.

## Context

The MacBook triggering gap (see `wiki/log.md`, memory bridge
`macbook-harness-transfer`): a fresh session on the second machine did not
reliably show the process discipline (brainstorm-first, atomic decomposition,
TDD dispatch, review-gate) that the dev machine took for granted. Root-cause
analysis found the discipline was never installed anywhere the plugin ships —
it lived in the dev machine's local dotfiles setup (global `CLAUDE.md`, local
agent definitions, muscle memory from the harness author's own sessions). The
gap was **context injection, not installation**: `/ren:install` had put the
framework's files on disk correctly; nothing then injected the process
discipline into a session's actual context at the moment it mattered.

## Decision

1. **Wake-up-injected hard-gate execution doctrine card.** Every wake-up
   renders a ≤50-line, ~400-token card (`doctrine_card.py`) as an early
   section: brainstorm gate → decompose → TDD dispatch → review gate, framed
   as MANDATORY gates with red-flag rationalizations named and rebutted. This
   guarantees the discipline is present in context on the machine that has
   never seen the author's local setup, not just the one that has.

2. **Detect-and-delegate to superpowers.** `superpowers_installed()` checks
   the local plugin cache; when present, the card's gates delegate to the
   superpowers process skills (`superpowers:brainstorming`,
   `superpowers:subagent-driven-development`,
   `superpowers:test-driven-development`) instead of re-describing them. When
   absent, a self-contained fallback variant carries the same four gates
   without naming skills that aren't there, plus a pointer at `/ren:doctor`
   for the recommended companion.

3. **One shipped agent: `ren-reviewer`.** The review gate needs an
   enforcement arm, not just an instruction to "review the work." RenOS now
   ships `agents/ren-reviewer.md` — verified findings with runnable repros,
   scope + TDD conformance checks, a fixed report format. This is the first
   agent RenOS ships; 0.6.5 is scoped as the shipped-agents *mechanism*
   (discovery, versioning, the wiki/memory-health family) built on what this
   one agent proves out.

4. **Doctor check: `execution_doctrine`.** Verifies the card's references
   (agent names, superpowers skill ids) actually resolve against what's
   shipped, and warns on manual `<!-- renos:doctrine-stopgap -->` CLAUDE.md
   residue left over from pre-0.6.4 interim fixes, so stopgaps get retired
   once the real mechanism lands.

## Alternatives rejected

- **Skill-only (a `doctrine` skill the model must remember to invoke).**
  Rejected: skills are pulled, not pushed — a skill nobody invokes is dead
  weight. The whole point is that the discipline must be present without the
  model or the user having to remember it exists on a machine that's never
  seen it before.
- **CLAUDE.md-only (bake the doctrine into the shipped CLAUDE.md template).**
  Rejected: static text in a template drifts from what's actually shipped
  (agent names rename, skills get added/removed) with no mechanism to catch
  it, and it doesn't compose with the plugin's existing wake-up injection
  path where every other piece of session-start context already lives.
- **Memory-based (let the learning brain infer the discipline from repeated
  sessions).** Rejected: doctrine is an instruction-plane concern per the
  v2.2 pivot (data plane auto-applies; instruction plane is human-gated,
  deliberately stable). Hard gates that block or unblock actions are not the
  kind of thing that should be learned probabilistically from usage
  patterns — they need to be true from the first session on a new machine,
  not converged on after enough repetitions.

## Consequences

- A fresh session on any machine — first install or the twentieth — now
  carries the same non-negotiable process gates, closing the MacBook gap at
  its actual root cause (injection) rather than patching the symptom
  (reminding the user to paste something in manually).
- The interim CLAUDE.md stopgap (`<!-- renos:doctrine-stopgap -->` block)
  remains a valid bridge for pre-0.6.4 installs and is self-retiring once
  the doctor check flags it as superseded.
- The card is intentionally thin (≤50 lines) — it names gates and delegates
  detail to superpowers or the fallback prose, not a full process manual, to
  keep the wake-up token budget honest.
- 0.6.5 inherits an explicit shape to design against: generalize
  `ren-reviewer`'s shipping pattern into a real shipped-agents mechanism, and
  extend it to the wiki/memory-health family named in the 0.6 planning
  ledger (issue ren-os#11).
