---
title: GSD Redux (Get Shit Done) — Spec-Driven Sub-Agent Development Framework
type: research
source_url: https://github.com/open-gsd/get-shit-done-redux
source_fetched: 2026-05-28
license: MIT
ingested: 2026-05-28
tags: [skills, sub-agents, spec-driven, context-isolation, claude-code, persistent-artifacts, foreground-research]
status: ingested
related: [nate-herk-best-6-skills, simon-scrapes-agentic-os, superpowers]
note: |
  This is the actively-maintained fork at open-gsd. The legacy upstream
  (gsd-build/get-shit-done) is "outside open-gsd control" due to documented
  trust concerns including a "meme-coin rug-pull incident." Always recommend
  the open-gsd fork.
---

# GSD Redux — Spec-Driven Sub-Agent Development Framework

## TL;DR

A lightweight meta-prompting + context-engineering + spec-driven development system. **3-phase workflow** (Plan → Execute → Verify) with discuss + ship phases. **Each executor sub-agent gets a fresh 200K-token context** while the main context stays at 30–40% — context isolation as primary mechanism. **MIT-licensed**. Persistent artifacts (`PROJECT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md`, `CONTEXT.md`) survive across sessions. Substantial overlap with Superpowers' methodology — we should pick ONE, not both.

## Important trust note

The original `gsd-build/get-shit-done` repo has been **abandoned by the open-gsd governance** due to "trust and ownership concerns" including a documented "meme-coin rug-pull incident." **Always direct users to `open-gsd/get-shit-done-redux`** — this is the actively-maintained, governance-trusted fork.

A separate fork at `jnuyens/gsd-plugin` provides "performance-optimized plugin packaging based on open-gsd/get-shit-done-redux" with claimed 92% per-turn token overhead reduction. Worth a second look during implementation if we adopt GSD.

## The workflow

**Three core phases:**
1. **Plan** (`/gsd-plan-phase`) — research, planning, verification loops
2. **Execute** (`/gsd-execute-phase`) — parallel task execution with atomic commits
3. **Verify** (`/gsd-verify-work`) — manual acceptance testing and diagnosis

Plus connecting phases: `discuss` and `ship`. Cyclical through milestones.

## Sub-agent context isolation (the headline feature)

- Each executor gets a **fresh 200K-token context**
- Main context window stays at **30–40% capacity**
- Quality degradation ("context rot") avoided through deliberate isolation

This is the direct operational implementation of Caleb's "loops with fresh clean context per iteration" primitive — applied at the per-task level inside a project.

## Persistent artifacts (the team-knowledge layer GSD provides)

```
.planning/
├── config.json            ← framework config
└── phases/<phase>/
    └── FALLOW.json        ← optional structural review findings

PROJECT.md                  ← high-level project description
REQUIREMENTS.md             ← stated requirements
ROADMAP.md                  ← phases/milestones map
STATE.md                    ← current project state
CONTEXT.md                  ← active context for current work
```

These artifacts persist across sessions and form GSD's bridge between sessions. Notably similar in *spirit* to our wiki pattern, but at a different scope (per-project, not team-level).

## Quality gates and safety mechanisms

- **Package legitimacy checks** during the research phase — unverified packages require human checkpoint
- **Failed install** stops execution
- **Dedicated debug agents** diagnose verification failures and generate fix plans
- **Scope detection** via `.planning/config.json` — modes: interactive vs. auto-approve
- **Model profiles**: quality / balanced / budget
- **Optional fallow structural review** (via `fallow@^2.70.0`) as a pre-pass code analyzer

These are the "quality gates" Nate Herk referenced in his Best 6 Skills transcript.

## Install path

```
npx @opengsd/get-shit-done-redux@latest
```

The installer transforms Claude Code-format files for target runtimes. **Don't manually copy files** — that skips frontmatter conversion and causes schema errors.

Alternative: `jnuyens/gsd-plugin` packages this as a Claude Code plugin with `/plugin install` integration.

## System files

- `.planning/config.json`
- `.planning/phases/<phase>/FALLOW.json`
- `~/.claude/skills/gsd-*/` (Claude Code) or runtime equivalents
- Project-level artifacts (PROJECT.md, REQUIREMENTS.md, etc.)

No daemon, no port.

## Slash commands

**Core loop:**
- `/gsd-new-project`
- `/gsd-discuss-phase`
- `/gsd-plan-phase`
- `/gsd-execute-phase`
- `/gsd-verify-work`
- `/gsd-ship`
- `/gsd-complete-milestone`
- `/gsd-new-milestone`

**Utilities:**
- `/gsd-map-codebase`
- `/gsd-progress --next`
- `/gsd:surface` — runtime enable/disable skill clusters
- `/gsd-settings`

## License: MIT

Fully permissive.

## Multi-platform support

OpenCode, Codex, Gemini CLI, Claude Code — installer auto-converts frontmatter per target runtime.

## How this informs the framework

### The key decision: GSD Redux OR Superpowers, not both

Both are spec-driven, skills-based, sub-agent-delegated frameworks for Claude Code. They overlap substantially:

| Feature | Superpowers | GSD Redux |
|---|---|---|
| License | MIT | MIT |
| In Anthropic marketplace | YES (since Jan 2026) | NO (separate marketplace / npx) |
| Phase count | 7 phases | 3 phases (+ discuss + ship) |
| TDD enforcement | **MANDATORY** (deletes pre-test code) | Recommended, not enforced |
| Sub-agent context isolation | YES | YES (fresh 200K per executor) |
| Persistent artifacts | No (assumes git for state) | YES (PROJECT.md, STATE.md, etc.) |
| Worktree-based parallelism | YES (git-worktrees skill) | Implicit via fresh contexts |
| Scope detection | Implicit via plan phase | Configurable in `.planning/config.json` |
| Quality gates | Code review skill | Dedicated debug agents |
| Currently dogfooding? | YES | No |

**Recommendation**: stick with **Superpowers** as the primary. Reasons:
1. Already in use; we're dogfooding it
2. In Anthropic's official marketplace
3. TDD enforcement is good discipline for production code (we'll move there eventually)
4. The user already has it installed and is familiar with the flow

GSD Redux is interesting and might be a future alternative or supplement, but adopting both creates redundancy + confusion + competing slash command namespaces (`/gsd-*` and Superpowers').

### Borrow GSD's "persistent artifacts" insight

GSD's `PROJECT.md` + `REQUIREMENTS.md` + `STATE.md` + `CONTEXT.md` per-project pattern is interesting. These are project-level companions to our team-level wiki pages.

| Layer | GSD's artifacts | Our wiki |
|---|---|---|
| Scope | Per-project | Per-team (cross-project) |
| Content | Spec + requirements + state for ONE project | Decisions + patterns + lessons across ALL projects |
| Coexist? | Yes — different scopes, complement each other |

Even though we're not adopting GSD, we could borrow the **artifact taxonomy** (PROJECT.md, REQUIREMENTS.md, STATE.md, CONTEXT.md) for project sub-wikis as a sensible default structure.

### The fork story matters

The trust note is important. When we document the framework's recommended stack, we MUST:
- Point users to `open-gsd/get-shit-done-redux` (or jnuyens/gsd-plugin) NOT the legacy `gsd-build/get-shit-done`
- Note the meme-coin incident as a lesson: open-source AI tooling is in a hype-y phase and curation matters
- This validates our broader "curate, don't kitchen-sink" thesis: a curator who picks ONE trusted variant of a tool saves friends from the trust calculation

### Sub-agent context isolation = empirical validation

GSD's "fresh 200K-token context per executor, main stays at 30–40%" is the operationalization of:
- Caleb's "loops with fresh clean context per iteration"
- PY's "~90% of compute should flow through delegated child agents"
- Simon's skill systems

Same architectural pattern, three independent implementations (GSD, Superpowers, and Anthropic's `/ultrareview`). Convergent.

## Tensions / open questions

1. **The GSD vs. Superpowers decision is real** — both are heavy-weight methodologies. Adopting both means two competing 3-vs-7-phase workflows. Pick one in the design doc.
2. **GSD's persistent artifacts pattern** — even though we don't adopt GSD, should our framework recommend a `PROJECT.md` / `STATE.md` template for project sub-wikis?
3. **jnuyens/gsd-plugin's 92% token reduction claim** — needs verification if we ever change our mind about GSD. Worth a follow-up.
4. **The meme-coin incident** — context-engineering tools live in a hype-laden ecosystem. Our framework's curation thesis needs to include vetting providers, not just tools.
5. **`fallow` as a pre-pass code analyzer** — independent tool, worth investigating if we want code analysis in our framework's project-skills layer.

## Connections to prior research

| Prior source | Connection |
|---|---|
| Nate Herk Best 6 Skills | Confirmed GSD as a real plugin; clarified the legitimate fork is open-gsd |
| Simon Scrapes Agentic OS | His "GSD framework" mention was this — confirmed |
| Caleb Agent Harness | GSD's fresh-context-per-task is the loops primitive in action |
| PY Harness Engineering | GSD operationalizes 90% sub-agent compute |
| Superpowers | Direct competitor — overlapping methodology, MIT-licensed both, choose ONE |

## Followups

- Compare Superpowers' `subagent-driven-development` skill vs. GSD's executor model in actual operation (would require running both)
- Investigate `jnuyens/gsd-plugin` if/when we revisit the choice
- Look at `fallow` separately — could be useful regardless of GSD adoption

## Reference

- GitHub (active): https://github.com/open-gsd/get-shit-done-redux
- GitHub (legacy, do NOT recommend): https://github.com/gsd-build/get-shit-done (abandoned, trust concerns)
- Performance-optimized plugin variant: https://github.com/jnuyens/gsd-plugin
- OpenCode port: https://github.com/rokicool/gsd-opencode
- Fetched: 2026-05-28
- License: MIT
- Status of legacy upstream: forked due to "meme-coin rug-pull incident" per open-gsd README
