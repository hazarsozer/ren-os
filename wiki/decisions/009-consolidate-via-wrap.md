---
title: "ADR-009: Consolidate via /wrap Slash Command (Not Stop Hook)"
status: accepted
date: 2026-05-28
sunset-review: 2026-11-28
references-pages: [ralph, claude-mem, simon-scrapes-agentic-os, prompt-engineering-agent-harness, anthropic-marketplace-catalog]
amendments:
  - "2026-05-28: noted /revise-claude-md (claude-md-management) as CLAUDE.md-layer complement at a different surface; not a competitor to /sf:wrap"
affects-components: [memory, wiki, session-end, skills, slash-commands]
relates-to: [004-wiki-design-hierarchical, 008-wake-up-hook, 010-hook-ordering, 012-self-improvement]
---

# ADR-009: Consolidate via /wrap Slash Command (Not Stop Hook)

## Context

The consolidate mechanism is the partner to the wake-up hook (ADR-008): it captures what was learned during a session and persists the high-signal subset into the wiki. The wiki updates are what the *next* session's wake-up reads. Without consolidate, the loop is broken — wake-up has nothing fresh to load.

Two implementation paths were initially on the table:

**Path A: Stop hook (automatic at session end).**
Claude Code emits a Stop event when the session ends. A hook intercepts and runs consolidate logic.

**Path B: `/wrap` slash command (manual user invocation).**
The user calls `/wrap` when they want to consolidate. No hook involvement.

The Ralph research surfaced a critical collision: **Ralph's loop pattern uses a Stop hook** to intercept session exit and re-feed the prompt. If our consolidate also uses Stop, the two compete. Either:
- Ralph's hook intercepts → re-feeds → consolidate never runs
- Our hook intercepts first → context now polluted with consolidation work that wasn't requested

Even setting Ralph aside, claude-mem has a SessionEnd hook. The configuration's Stop intercept would either fire before or after claude-mem's — and the ordering is non-trivially user-affecting (do we read claude-mem's compressed observations from THIS session as input to our consolidate? Or has it not run yet?).

Additionally, the user's preferences from prior sources point toward control: the autonomous "never stop, don't ask the human" pattern (per Simon Scrapes' self-improving skills source) is for **purpose-built improvement loops**, not for routine session-end work. Consolidate is the latter category — quality matters more than autonomy.

## Decision

**Consolidate is invoked via `/wrap` slash command, not via Stop hook.**

**Concrete behavior:**

- User runs `/wrap` (or any aliases we provide, e.g., `/sf:wrap`) when they want to end the session and persist learnings.
- The slash command activates the `consolidate` skill from our framework's skill set.
- The consolidate skill:
  1. Reads the session log (Claude Code's record of the session, plus any structured notes the user pinned via `/note` — see future ADR if we adopt that pattern).
  2. Determines what to promote to the wiki using a **high signal threshold** (decision made? pattern learned? lesson earned? stack change? gotcha discovered? → promote. Routine debugging / normal coding → don't promote).
  3. Hands promotion work to relevant wiki-maintenance agents (the `wiki-updater` agent for writes, schema-enforcing).
  4. Writes a **session pointer** — one paragraph: what was done, what's next, where attention should go. This pointer feeds the next session's wake-up.
  5. Appends a one-line entry to the project's `log.md` (if in a project directory) or to the master `log.md`.
  6. Returns a brief summary to the user.

**What `/wrap` does NOT do:**

- Run automatically. The user controls it.
- Block session exit. After `/wrap` completes, the session ends normally (or continues if the user keeps working).
- Compete with claude-mem's auto-capture. claude-mem captures observations continuously throughout the session (per its 5 lifecycle hooks); `/wrap` is our team-level synthesis on top, not a competitor.
- Modify CLAUDE.md mid-session (cache-preservation, per ADR-008's principle). Project-level CLAUDE.md updates are safe to write (per Nate Herk's "edits don't apply until restart") but should be deliberate, not part of every `/wrap`.

**Default discipline: most sessions produce ZERO wiki edits.** Most work is routine. Only sessions with genuine signal touch the wiki. Per ADR-004's general rule: "would I want this loaded next session by default? If no, it doesn't go in."

**Optional but recommended companion commands:**

- `/sf:note <text>` — pin something during the session for `/wrap` to consider promoting. Cheap, useful when the user knows mid-session "this is worth remembering."
- `/sf:recall <query>` — explicit wiki query mid-session, doesn't trigger consolidation. For when the user knows what they need but the wake-up didn't pre-load it.

(These are separate slash commands, not strict requirements of consolidate — but they pair naturally and should ship together.)

**Coexistence with `/revise-claude-md` (claude-md-management plugin, added 2026-05-28):**

ADR-006's curated stack now includes `claude-md-management`, which ships its own `/revise-claude-md` command for capturing session learnings into project CLAUDE.md files. This is **not a competitor to `/sf:wrap`**; they target different files:

| Tool | Target file | Layer | What gets captured |
|---|---|---|---|
| `/sf:wrap` (this ADR) | `wiki/projects/<p>/STATE.md`, `CONTEXT.md`, `log.md` | Wiki (conversation-layer per ADR-008) | Decisions, patterns, lessons (signal-thresholded) |
| `/revise-claude-md` | `CLAUDE.md`, `.claude.local.md` | System-prompt-cached layer (next session's CLAUDE.md inheritance) | Bash commands discovered, code patterns, environment quirks |

Both can be invoked at the end of a productive session. The friend group can:
- Use `/sf:wrap` for studio-knowledge promotion (deliberate, high-signal)
- Use `/revise-claude-md` for project-CLAUDE.md hygiene (bash commands learned, env quirks documented)
- Or both, in sequence

No collision: `/revise-claude-md` writes only at restart (CLAUDE.md cache-edit safety per Nate Herk research) and is approve-each-diff. Onboarding (ADR-015) should mention both in the first-session walkthrough so friends know which to use when.

## Consequences

**Easier:**
- **No collision with Ralph's Stop hook.** Friends can install Ralph on demand (per ADR-006) without our framework getting in the way.
- **No ordering negotiation with claude-mem's SessionEnd hook.** Different lifecycle stages, different invocation models.
- **User has explicit control.** No accidental consolidations of throwaway sessions. The signal-to-noise ratio of the wiki stays high.
- **Easier to develop and test.** Slash commands are simpler to iterate than hook integrations.

**Harder:**
- **Discipline is required.** Users have to remember to call `/wrap` when sessions have signal. Forgetting means the wake-up will miss recent learnings.
- **No telemetry signal of "the session ended."** If we ever want to know whether the user wrapped or just exited, we'd need additional instrumentation. (Out of scope for v1.)
- **First-time users will skip `/wrap`.** Onboarding (ADR-015) needs to teach the convention.

**Now impossible:**
- Fully automatic, hands-off consolidation. The user controls the action.

**Sunset review trigger conditions:**
- Friends consistently forget `/wrap` and the wiki rots → reconsider automatic invocation (maybe with a smart filter that decides whether to run, rather than universal Stop hook)
- Ralph users in the friend group are common → confirm `/wrap` was the right call
- Claude Code adds a "graceful session end" callback distinct from Stop → could reconsider Stop hook with the new event
- Hooks ecosystem matures and ordering becomes negotiable per ADR-010 in a clean way → could revisit

## Alternatives considered

### A) Stop hook (automatic at session end)

**Considered shape**: SessionEnd or Stop hook invokes consolidate every time the session ends.

**Why rejected**: Ralph collision (per the Context section). Plus ordering complexity with claude-mem's SessionEnd. Plus runs consolidate on throwaway sessions where there's nothing to learn — adds noise to wiki, wastes tokens.

### B) Stop hook with a smart filter

**Considered shape**: Hook runs, but consolidate first decides whether the session had genuine signal. If yes, promote. If no, exit silently.

**Why rejected**: Still has the Ralph collision. The filter logic adds complexity. And the user's preference for explicit control (especially in the friend-group context where multiple users will be touching the same wiki) means automatic decisions about what's "signal worthy" are higher-stakes than slash command + user judgment.

### C) Hybrid: `/wrap` is primary, optional Stop hook fallback

**Considered shape**: Slash command is the recommended path; if user forgets, a Stop hook fires a 1-minute grace period asking "wrap this session? y/n" before consolidating.

**Why rejected**: Still has Ralph collision (the grace-period prompt depends on Stop). And it adds UX complexity for the few-seconds-late case. Better to lean fully into the slash command convention.

### D) Use Claude Code's native conversation-summary mechanism

**Considered shape**: Hook into Claude Code's auto-summarization on `/compact` to capture wiki-worthy content.

**Why rejected**: `/compact` is meant for context-window management, not deliberate learning consolidation. The signal-to-noise ratio is wrong (compact summarizes EVERYTHING; we want to promote only high-signal items). Different concerns.

### E) No consolidate skill at all — rely on claude-mem alone

**Considered shape**: claude-mem captures observations automatically; the team-level wiki is updated manually by humans editing markdown.

**Why rejected**: Per Karpathy's foundational thesis (the LLM Wiki pattern), **the LLM should do the bookkeeping**. Humans editing the wiki manually = humans abandon wikis. The whole reason the LLM Wiki pattern works is because maintenance cost approaches zero with LLM-driven updates. Removing consolidate removes the value.

## References

- `wiki/research/ralph.md` — the Stop hook collision concern that drove this decision
- `wiki/research/claude-mem.md` — claude-mem's SessionEnd hook + auto-capture; we don't compete with it
- `wiki/research/simon-scrapes-agentic-os.md` — `learnings.md` pattern that's similar in spirit but applied per-skill, not per-session
- `wiki/research/prompt-engineering-agent-harness.md` — Stop hooks as one of the 9 harness components; we use them sparingly
- ADR-004 (Wiki Design Hierarchical) — sets the wiki's structure that consolidate updates
- ADR-008 (Wake-Up Hook) — partner mechanism; the session pointer consolidate writes is what wake-up reads
- ADR-010 (Hook Ordering Coordination) — addresses the broader question of multi-plugin hook coexistence; `/wrap` sidesteps this entirely by not using a hook
- ADR-012 (Two-Layer Self-Improvement) — uses Ralph-style autonomy for skill-improvement loops; that's different from consolidate's quality-controlled writes

---

## Amendment — 2026-06-28: instincts hot tier added below /wrap (ADR-037, C3a)

ADR-037 introduces a **hot-capture tier** beneath the manual `/wrap` consolidate: a durable, typed
`instincts` page-type captured via `/ren:note --instinct` (explicit + cheap, hierarchically routed). This
does **not** change this ADR's core posture — consolidation stays manual, never a Stop hook. The hot tier
makes *capture* liberal without making *consolidation* automatic; the governed hot→curated promotion sweep
(C3b) will likewise be proposal-diff-gated, never a Stop hook. See ADR-037.
