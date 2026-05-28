---
title: "ADR-012: Two-Layer Self-Improvement — L1 Description via Skill Creator + L2 Body via Karpathy Loop"
status: accepted
date: 2026-05-28
sunset-review: 2026-11-28
references-pages: [simon-scrapes-self-improving-skills, skill-creator, py-harness-engineering, llm-wiki-pattern, ralph]
affects-components: [skills, eval, improvement-loops]
relates-to: [006-curated-stack, 011-skill-schema, 015-onboarding]
amendments:
  - "2026-05-28: added native Claude Code safety primitives subsection — `--max-turns`, `--max-budget-usd`, `--bare` flags are CC-built-in mechanisms `/sf:improve-skill` should leverage alongside `--max-iterations` for autonomous-mode safety bounds. Discovered via official-docs-validation pass against Claude Code CLI reference."
  - "2026-05-28 (correction): `--max-turns` documented in the prior amendment does NOT exist as a CLI flag in Claude Code `2.1.154` (verified empirically against `claude --help`, `claude agents --help`, `claude project --help`, `claude doctor --help` — all null results). The prior amendment scanned the wrong doc surface. Adjusted `/sf:improve-skill` autonomous-mode pre-flight requirement to two flags: `--max-iterations` (our framework cap; canonical) + `--max-budget-usd` (CC-native; print-mode only for inner sub-runs). Shadow turn-tracking via response-count summation is the belt-and-suspenders fallback for non-print contexts. `--bare` and `--max-budget-usd` confirmed as documented. See `hooks/wake-up/CC_API_NOTES.md` §11 + §12 + Appendix A for the full verification trail (verbatim `claude --help` receipts). Re-check `--max-turns` availability on each CC release; if it returns, restore the three-flag requirement."
---

# ADR-012: Two-Layer Self-Improvement — L1 Description via Skill Creator + L2 Body via Karpathy Loop

## Context

**Self-improvement is the most strongly-supported design pattern in the entire research base.** Four converging signals:

1. Karpathy's "auto-research" pattern: read code → make change → run test → keep or revert → loop. The primitive that generalizes to any improvable artifact.
2. Simon Scrapes' two-layer skill improvement: Layer 1 (description for activation) + Layer 2 (body for output quality). Practical implementation for Claude Code skills.
3. PY's harness-engineering research: empirically, **self-evolution was the only consistently-helpful module** in NLH ablation studies (+4.8 SWE-Bench, +2.7 OS-World).
4. Anthropic's Skill Creator already IMPLEMENTS Layer 1: `scripts/improve_description.py` + `run_loop.py` with 60% train / 40% test split, 3 runs per query, up to 5 iterations.

The Skill Creator implementation is Apache-2.0, in the official marketplace, and battle-tested. **Layer 1 is solved by adoption (per ADR-006).** Layer 2 is the configuration's contribution — applying the Karpathy loop on top of the eval/eval.json schema established in ADR-011.

The risk if we don't formalize this: we ship skills without an improvement loop, they degrade silently as Claude models evolve (per PY's "assumptions expire" theme), and the friend group has no concrete tool when they want to refine a skill.

The opportunity: Layer 2 is mostly orchestration. We don't have to reinvent the eval format (compatible with Skill Creator's per ADR-011), the loop primitive (Karpathy's), or the agent driving it (Claude Code itself). We provide the orchestrating skill: `/sf:improve-skill <skill-name>`.

## Decision

**Self-improvement is two layers, both shipped:**

### Layer 1 (activation): Skill Creator's description optimizer

**Adopted via ADR-006.** No new framework code. Friends invoke it as:

```
/skill-creator
> Improve my <skill-name> skill description
```

It uses:
- The eval.json from ADR-011 (compatible format)
- 60/40 train/test split
- 3 runs per query for reliable trigger rate
- Up to 5 iterations
- Requires `ANTHROPIC_API_KEY` (noted in ADR-006 caveats; OK for friend group)

Output: an improved `description` field in the skill's frontmatter. The skill triggers more reliably on the queries it should match.

### Layer 2 (body quality): Karpathy auto-research loop applied to SKILL.md

**New framework skill: `improve-skill-body`.** Invoked via:

```
/sf:improve-skill <skill-name>
```

Or in autonomous mode:

```
/sf:improve-skill <skill-name> --autonomous --max-iterations 10
```

Behavior follows Karpathy's loop applied to SKILL.md body content (NOT the description — that's Layer 1's job):

1. Read SKILL.md (body section), references/, eval/eval.json
2. Run all tests, score pass rate against binary assertions
3. If perfect (all pass): exit with "no improvements found"
4. If any assertion fails:
   - Diagnose which assertion(s) failed and why
   - Propose ONE change to SKILL.md (e.g., add an instruction, clarify a step, add a reference)
   - Apply change, `git commit` (atomic, revertible)
   - Re-run tests
   - If score improved: keep the change, advance to next iteration
   - If score dropped: `git reset --hard HEAD~1` and try a different change
5. Continue until:
   - All assertions pass (success exit)
   - `--max-iterations` reached
   - User runs `/cancel-improve` or `Ctrl-C`

**Default mode is interactive** — user sees each proposed change and approves before applying. **Autonomous mode** (`--autonomous`) skips approval, suitable for overnight runs. Both modes require `--max-iterations` for safety.

**Operating principles** (carried from the research):

- **One change per iteration.** Narrow attempt loop (per PY's discipline-narrowing principle + Simon's instruction).
- **Binary assertion only.** No subjective qualifiers (per ADR-011's schema discipline). Subjective quality goes through Skill Creator's qualitative dashboard separately.
- **Git as memory.** Each iteration is a commit; revert is `git reset`. No fancy state management.
- **Autonomous mode never asks the human** during a run (per Karpathy's "never stop" prompt pattern). Pre-flight check ensures `--max-iterations` is set so the loop is bounded.

**Native Claude Code safety primitives** (added 2026-05-28 via official-docs-validation pass):

Claude Code provides built-in safety mechanisms our autonomous self-improvement runs can leverage directly:

- **`--max-turns N`** — limits the number of agentic turns; CC exits with error when limit reached. Useful as a hard upper bound for our Karpathy loop regardless of friend's `--max-iterations` argument.
- **`--max-budget-usd N`** — maximum dollar amount to spend on API calls before stopping. Print-mode only, but for autonomous overnight runs this prevents runaway costs.
- **`--bare`** — skips auto-discovery of hooks, skills, plugins, MCP servers, auto-memory, and CLAUDE.md. Useful for the inner per-iteration sub-agent calls in autonomous mode where we don't want the framework's overhead in each sub-run.

Implementation should expose these as `/sf:improve-skill` flags (e.g., `--max-iterations 10 --max-turns 50 --max-budget-usd 5.00`) so friends can set multiple safety bounds simultaneously.

**Where this skill ships:** As part of the configuration's own framework skills (under `skills/improve-skill-body/`, following ADR-011's schema).

**`learnings.md` updates** (optional, per ADR-011): when improve-skill-body runs and finds patterns (e.g., "this skill consistently fails on assertion X because instruction Y is ambiguous"), the skill can update `learnings.md` so future runs of the same skill (not the improvement loop, but the skill itself in normal use) get the context.

## Consequences

**Easier:**
- **Friends can improve skills overnight.** The autonomous mode runs while they sleep, advancing the skill's quality without their constant attention.
- **Quality compounds.** As skills improve, the bar for new skills rises. Improvement loops are reusable infrastructure.
- **No reinvention.** Layer 1 = adopted (Skill Creator). Layer 2 = orchestration on top of ADR-011's schema + Karpathy's primitive + Claude Code's existing tools.
- **Skill maintenance is partially automated.** When Claude models change, friends can re-run improvement loops on their existing skills to adapt.

**Harder:**
- **Iteration cost.** Each improvement loop costs API tokens (multiple test runs + Claude proposing changes). For substantial skills, this is significant.
- **Authoring evals well is a learned skill.** Bad binary assertions can drive the loop to make changes that don't actually improve real-world output. Onboarding (ADR-015) needs an "authoring evals" guide.
- **Autonomous mode requires trust.** Friends running overnight on critical skills must have confidence in the change-revert discipline. We mitigate via the one-change-per-iteration rule + git history + max-iterations cap.
- **Git pollution.** Many small commits during improvement loops can pollute git history. Mitigation: improvement runs commit to a dedicated branch (`/sf:improve-skill <name>` auto-creates `improve/<name>/<timestamp>`); squash-merge to main only when complete.

**Now impossible:**
- Shipping a skill without an improvement path. Every skill has eval.json + can run through both layers.
- "Manual-only" skill quality assurance. The autonomous loop is available; humans can choose to use it or not, but the infrastructure is there.

**Sunset review trigger conditions:**
- Anthropic ships a comparable Layer 2 mechanism → adopt theirs, retire ours
- Skill Creator changes its eval.json format such that ADR-011's schema breaks → adapt
- Improvement loops consistently produce regressions (signaling the binary-assertion methodology is failing for our domain) → reconsider methodology
- Token cost of autonomous runs becomes prohibitive → add token-budget caps + smarter early-stop conditions

## Alternatives considered

### A) Layer 1 only — skip Layer 2

**Considered shape**: Use Skill Creator for description optimization; don't ship a body-improvement loop.

**Why rejected**: The body is where most skill quality lives. Description optimization is about activation; once the skill triggers, what it produces matters most. Skipping Layer 2 leaves the most valuable improvement vector unsupported. Four converging research signals all point at Layer 2 being important; we ship it.

### B) Layer 2 with a richer state machine instead of Karpathy's simple loop

**Considered shape**: Multi-strategy improvement (different change types: add instruction / clarify step / reorder / add reference), with state machine deciding which to try next.

**Why rejected**: Premature optimization. The Karpathy loop is empirically successful (it's what Simon Scrapes demonstrated). Adding complexity without evidence is the wrong move. v2 can refine if Karpathy-style proves limiting.

### C) Use Ralph for Layer 2 instead of a dedicated skill

**Considered shape**: Set up a Ralph-style autonomous loop that improves the skill until the eval passes.

**Why rejected**: Ralph is general-purpose (any task with completion criteria). Our Layer 2 is specific: improve a skill, defined by eval, with the body change as the action. A dedicated skill encodes that specificity better. Also, Ralph requires a Stop hook (per ADR-006 it's documented-not-bundled). We don't want Layer 2 to require Ralph installation.

### D) Continuous improvement without manual trigger

**Considered shape**: After every session, check whether any skill could be improved; if yes, queue an improvement run.

**Why rejected**: Too much automation. Friends want to choose WHEN to run improvement loops (because they're expensive in tokens). Trigger-driven manual invocation respects that choice.

## References

- `wiki/research/simon-scrapes-self-improving-skills.md` — the two-layer pattern + Karpathy auto-research loop applied to skills
- `wiki/research/skill-creator.md` — Layer 1 implementation (description optimizer)
- `wiki/research/py-harness-engineering.md` — empirical evidence: self-evolution is the only consistently-helpful module
- `wiki/research/llm-wiki-pattern.md` — Karpathy's auto-research primitive (origin)
- `wiki/research/ralph.md` — the lightweight loop pattern Layer 2 echoes (but isn't Ralph)
- ADR-006 (Curated Stack) — adopts Skill Creator for Layer 1
- ADR-011 (Skill Schema) — defines the eval.json format Layer 2 consumes
- ADR-015 (Onboarding) — needs to include an "authoring evals" guide
