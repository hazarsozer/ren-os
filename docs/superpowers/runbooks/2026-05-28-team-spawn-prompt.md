# Team Spawn Prompt — Startup Framework Implementation Phase

**Date written:** 2026-05-28
**Audience:** future-Claude in a fresh tmux-hosted session, opened by Hazar to start implementing the framework
**Status:** runbook — follow it, but validate every proposal against the design doc before acting

---

## You are reading this in a fresh session inside tmux. Here's what's going on.

You are the **team lead** for an experimental Claude Code Agent Teams workflow. The user (Hazar) has just opened a tmux session and launched you inside it specifically to spawn a team that builds the **startup-framework** Claude Code plugin.

This is the implementation phase of a multi-day design effort. The design is done. The wiki is complete. The tour HTML has been demoed. Now we build the actual plugin code.

You are not implementing alone. You are coordinating 4 teammates, each owning a slice of the plugin. The user wants to dogfood the agent-definition patterns the framework itself will ship with.

---

## Pre-flight Confirmation (do these before reading further)

Run these four checks in parallel. If any fails, **stop and tell the user** — do not spawn teammates with a broken setup.

```bash
# 1. Claude Code version ≥ 2.1.32
claude --version

# 2. Experimental flag and tmux mode are loaded
jq '.env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS, .teammateMode' \
  /home/hsozer/Dev/startup-framework/.claude/settings.local.json
#    → expect: "1", "tmux"

# 3. You are actually inside a tmux session (split-pane requires this)
echo "$TMUX"
#    → expect: non-empty path like /tmp/tmux-1000/default,1234,0

# 4. tmux is available with mouse mode
tmux show-options -g mouse
#    → expect: mouse on
```

Then verify the user has set **Default teammate model** in `/config` to **Default (leader's model)**. If not, ask them to do it before spawning — otherwise teammates spawn with the small default model and you'll have a smart lead coordinating dumb workers.

---

## Required Reading (in order, before spawning anything)

| # | File | Why |
|---|---|---|
| 1 | `docs/superpowers/specs/2026-05-28-startup-framework-design.md` | The ~600-line design doc. Single source of truth for what's being built. Read all of it. |
| 2 | `wiki/index.md` | Master catalog of 27 ADRs + 25 research pages. |
| 3 | `wiki/decisions/006-required-plugin-stack.md` | What we curate vs build vs reject. |
| 4 | `wiki/decisions/008-wake-up-hook.md` | The cache-preservation pattern. **This is the riskiest single artifact in V1** — its theoretical correctness is documented but untested. |
| 5 | `wiki/decisions/009-consolidate-via-slash-command.md` | Why `/sf:wrap` is user-invoked, NOT a Stop hook. |
| 6 | `wiki/decisions/012-two-layer-self-improvement.md` | The Karpathy loop pattern for `/sf:improve-skill`. |
| 7 | `wiki/decisions/015-install-onboarding-flow.md` | The 7-stage `/sf:install`. |
| 8 | `wiki/decisions/017-per-friend-wiki-scope.md` | **Load-bearing.** Wikis are per-friend-local. |
| 9 | `wiki/decisions/018-activity-feed.md` | GitHub-repo-with-per-friend-log-files pattern. |
| 10 | `wiki/decisions/019-framework-distribution.md` | Private marketplace + monthly stable releases. |
| 11 | `wiki/decisions/022-identity-interview-skill.md` | AI identity interview for `/sf:interview`. |
| 12 | `wiki/decisions/023-v1-scope-fence.md` | What's IN / OUT / V2+ for V1. |
| 13 | `wiki/decisions/027-schema-versioning.md` | `schema_version` + migration semantics. |
| 14 | `tour/index.html` (skim) | Visual mental model of the framework. Don't re-read every section — just scan §01 Repos and §03 Daily Loop to ground yourself. |

After reading, summarize back to the user in 4–6 bullets: what V1 ships, what's deferred, what's load-bearing, and what's untested. This is your alignment checkpoint before any spawn.

---

## Why Agent Teams (decision already made — don't relitigate)

The framework has 4 genuinely independent aspects that map naturally to separate workers. Single-session implementation works but loses the parallelism + dogfooding benefit. Plain subagents work but can't talk to each other, which matters here because the hooks builder and lifecycle builder need to negotiate the `/sf:wrap` contract live.

Cost trade-off is accepted: tokens scale linearly with teammate count, but the user wants this trade-off.

---

## Proposed Team Structure (4 teammates)

**This is a starting point.** Before spawning, validate it against the design doc and propose adjustments to the user. Get user sign-off on the ownership matrix before any `TeamCreate`.

### Teammate 1: `sf-onboarding`

**Owns:** the one-time-per-friend installation experience.

- `/sf:install` — 7-stage onboarding flow (ADR-015)
- `/sf:interview` — AI-driven identity interview (ADR-022)
- The "joiner experience" end-to-end (ADR-020)

**Files:** `skills/sf-install/`, `skills/sf-interview/`, fragments of the wiki skeleton that ships with the plugin.

**Coordination contracts:**
- With `sf-distribution`: the `/sf:install` skill is INVOKED via the plugin's install path. Distribution owns the plugin-packaging side; onboarding owns the user-facing flow that runs after install completes.
- With `sf-feed`: `/sf:install` registers the friend's handle with the Activity Feed. Must agree on registration message format.

**Constraints to honor:**
- AskUserQuestion has a 4-option cap; some interview questions need 5+ options. Decide pagination vs. open-ended fallback per question.
- Identity interview must produce a structured profile that other framework components can read (handle, name, role, etc.).

---

### Teammate 2: `sf-lifecycle`

**Owns:** everything that runs during day-to-day sessions — slash commands + hooks.

- `/sf:wrap` — end-of-session consolidate (ADR-009). User-invoked, NOT a Stop hook.
- `/sf:doctor` — health check + update notifier (ADR-019)
- `/sf:update` — opt-in update flow (ADR-019)
- `/sf:improve-skill <name>` — Layer 2 Karpathy self-improvement loop (ADR-012)
- **SessionStart wake-up hook (ADR-008)** — the highest-risk artifact. Inject context into CONVERSATION layer, NOT system prompt, to preserve cache.

**Files:** `skills/sf-wrap/`, `skills/sf-doctor/`, `skills/sf-update/`, `skills/sf-improve-skill/`, `hooks/wake-up/`.

**Coordination contracts:**
- With `sf-feed`: `/sf:wrap` writes the session-end summary entry to the Activity Feed. Wake-up hook reads other friends' Feed tails. Both directions need format agreement.
- With `sf-onboarding`: respect the friend-profile schema that interview produces.

**Critical risk:** ADR-008's cache-preservation claim is theoretically correct per Nate Herk's research, but **untested in practice**. Validate it empirically before declaring the hook done. Suggested verification: instrument the hook to log cache hit/miss ratios from prompt-cache headers and compare with/without the hook over 10+ session starts.

**Native CC safety primitives to leverage** (per ADR-012 amendment): `--max-turns`, `--max-budget-usd`, `--bare` for the self-improvement loop.

---

### Teammate 3: `sf-feed`

**Owns:** the Activity Feed module — the only cross-friend communication channel in V1.

- GitHub repo write logic (per-friend `<handle>.log.md` files — file separation prevents write conflicts)
- Terse format enforcement (ADR-021 — privacy via format constraint, NOT secret scanning)
- SessionStart "active" entry write + tail-read of other friends' logs
- `/sf:wrap` end-of-session summary writer (called by `sf-lifecycle`'s `/sf:wrap`)
- `--skip-feed` flag + `SF_SKIP_FEED=1` env var for fully-private sessions

**Files:** `feed/` module, GitHub write utilities, format schema.

**Coordination contracts:**
- With `sf-lifecycle`: `/sf:wrap` calls into this module for the end-of-session write. Wake-up hook calls into this module for the friends'-tails read. **Define the function signatures together with sf-lifecycle before either of you implements.**
- With `sf-onboarding`: receive registration call when a new friend installs.

**Constraints to honor:**
- ADR-021: entries are deliberately terse (project, task, files — no transcripts, no secrets).
- ADR-018: per-friend file separation is the conflict-avoidance mechanism. Do NOT introduce shared files.
- GitHub repo URL is a config value, not hardcoded — Hazar will set it when implementation begins.

---

### Teammate 4: `sf-distribution`

**Owns:** how the plugin gets to friends and how it's released over time.

- `marketplace.json` (private marketplace per ADR-019)
- Plugin packaging (`.claude-plugin/` structure)
- Semver discipline + monthly stable release cadence
- README + user-facing install instructions
- The plugin shell that `sf-onboarding`'s `/sf:install` plugs into
- Schema versioning machinery (ADR-027 — `schema_version` field, migration scripts, N+3 deprecation)

**Files:** `.claude-plugin/`, `marketplace.json`, top-level `README.md`, `CHANGELOG.md`, schema-migration scripts.

**Coordination contracts:**
- With `sf-onboarding`: provide the plugin install shell that onboarding's flow runs inside.
- With everyone: surface a schema-version contract so each teammate's modules declare their version.

**Constraints to honor:**
- ADR-019: monthly stable cadence, NOT daily. `/sf:doctor` notifies of updates; `/sf:update` is opt-in.
- ADR-027: backwards-compat commitment across N+3 versions for friend wiki schemas.

---

## File Ownership Matrix (propose to user before spawning)

| Path | Owner | Notes |
|---|---|---|
| `skills/sf-install/` | sf-onboarding | |
| `skills/sf-interview/` | sf-onboarding | |
| `skills/sf-wrap/` | sf-lifecycle | calls into `feed/` |
| `skills/sf-doctor/` | sf-lifecycle | |
| `skills/sf-update/` | sf-lifecycle | |
| `skills/sf-improve-skill/` | sf-lifecycle | uses `--max-turns`, `--max-budget-usd`, `--bare` |
| `hooks/wake-up/` | sf-lifecycle | cache-preservation risk |
| `feed/` | sf-feed | per-friend log writers + tail readers |
| `.claude-plugin/` | sf-distribution | plugin manifest |
| `marketplace.json` | sf-distribution | |
| `README.md` | sf-distribution | |
| `CHANGELOG.md` | sf-distribution | |
| `wiki-skeleton/` (template) | sf-onboarding | seed wiki shipped with the plugin |

**Rule:** if a teammate needs to touch a path outside its column, it must message the owning teammate first via `SendMessage` and get agreement. No silent cross-domain edits.

---

## Spawn Protocol

Follow this sequence — do **not** improvise the order.

### Step 0: Write subagent definition files (before any `TeamCreate`)

For each of the 4 roles, write `.claude/agents/<role-name>.md` with frontmatter:

```yaml
---
name: sf-onboarding
description: Owns the one-time-per-friend installation flow for the startup-framework plugin. Includes /sf:install (7-stage onboarding per ADR-015) and /sf:interview (AI identity interview per ADR-022).
tools: Read, Edit, Write, Glob, Grep, Bash
model: opus
---
```

Body of each file: the teammate description from this runbook, condensed. The body is appended to the teammate's system prompt — keep it tight (under 100 lines per file).

**Important:** subagent `skills` and `mcpServers` frontmatter fields are NOT applied when running as a teammate. Don't include them; teammates load skills from project/user settings.

### Step 1: Get user approval on ownership matrix

Show the user the matrix above. Ask: "Approve as-is, or adjust?" Don't proceed until they say go.

### Step 2: Create the team

Use the `TeamCreate` tool (now loaded). Suggested team name: `sf-build-v1`.

Spawn 4 teammates referencing the subagent definitions by name:

```text
Spawn 4 teammates for the sf-build-v1 team:
- "onboarding" using the sf-onboarding agent type
- "lifecycle" using the sf-lifecycle agent type
- "feed" using the sf-feed agent type
- "distribution" using the sf-distribution agent type
Use the leader's model (Opus 4.7) for each.
Require plan approval before any teammate writes files.
```

The `Require plan approval` constraint is important. The first thing each teammate does is read its assigned ADRs and propose a plan; you (lead) approve or reject before they write code. This catches misalignment before it produces bad files.

### Step 3: Seat each teammate with its scope

Send each teammate (via `SendMessage`) a focused spawn prompt:
1. Their owned files
2. Their ADRs to read
3. Their coordination contracts
4. Their first deliverable (the plan)

Example for `onboarding`:

```text
You are the sf-onboarding teammate. Read these in order:
- docs/superpowers/runbooks/2026-05-28-team-spawn-prompt.md (the §Teammate 1 section is your scope)
- wiki/decisions/015-install-onboarding-flow.md
- wiki/decisions/020-joiner-and-leaver-experience.md
- wiki/decisions/022-identity-interview-skill.md

Your first deliverable: a plan for /sf:install + /sf:interview covering (1) skill file structure, (2) the 7-stage flow's step-by-step contract, (3) the friend-profile schema that downstream components will consume, (4) how AskUserQuestion's 4-option cap is handled for questions needing 5+ options.

Submit the plan for approval. Do not write any code until approved.
```

### Step 4: Watch and steer

Use Shift+Down to cycle teammates (or click panes in tmux split-mode) to read what each is doing. The lead's terminal shows the task list — press Ctrl+T to toggle it.

**Anti-pattern to avoid (called out in the doc):** the lead sometimes starts implementing tasks instead of waiting for teammates. If you notice yourself drafting skill code, stop and delegate.

### Step 5: Cleanup

When the build is done (or at end of session), ask the lead (yourself) to clean up the team:

```text
Clean up the team
```

Shut down each teammate first via `Ask the <name> teammate to shut down`. Cleanup fails if any teammate is still running.

---

## Coordination Contracts to Negotiate First

Before any teammate writes code, have a 3-way kickoff message thread (you + the two relevant teammates) to lock these:

1. **`/sf:wrap` ↔ `feed` end-of-session write contract.** What does sf-lifecycle pass to sf-feed? What's the terse-format schema? (sf-lifecycle + sf-feed)

2. **Wake-up hook ↔ `feed` tail-read contract.** How many entries from each friend? What's the cache-friendly injection format? (sf-lifecycle + sf-feed)

3. **`/sf:install` ↔ distribution install-shell contract.** Where does the plugin install machinery hand off to the user-facing flow? (sf-onboarding + sf-distribution)

4. **Friend-profile schema.** sf-onboarding produces it; everyone reads it. Agree on field names + types before sf-onboarding implements `/sf:interview`. (all 4)

Lock these contracts in `wiki/decisions/` as new ADRs (ADR-028 onward) before code begins. Use [[wiki-updater]] from inside `idea-generator/` later if you need schema-enforcing wiki writes; from app dirs, write the wiki directly per the doctrine in `/home/hsozer/Dev/CLAUDE.md` § Wiki Writes from App Directories.

---

## Quality Gates (set up after first sprint, not now)

Once the team is producing files, consider adding a `TaskCompleted` hook that runs `jq`-extracted task metadata and exits with code 2 if a "claim implementation complete" task lacks:
- A corresponding test file
- An ADR cross-reference (if the task involved a design choice)
- An entry in `wiki/log.md`

Don't add this on day one. Let the team run a few cycles first so the friction-vs-signal trade-off is visible.

---

## Done Criteria (V1 ship checklist)

The team's work is done when ALL of these are true:

- [ ] All 6 `/sf:*` skills exist as runnable Claude Code skills with frontmatter + body
- [ ] SessionStart wake-up hook implemented AND empirically verified to preserve cache hits
- [ ] Activity Feed module writes per-friend logs to a configured GitHub repo without conflicts
- [ ] `marketplace.json` parses and a clean install on a second machine produces a working plugin
- [ ] `/sf:install` runs end-to-end on a clean machine and a friend-profile file is produced
- [ ] `/sf:wrap` writes a terse summary to the Activity Feed (or skips it if `--skip-feed`)
- [ ] `/sf:doctor` detects "framework out of date" against the private marketplace
- [ ] `/sf:improve-skill` runs a Karpathy loop on a real SKILL.md file under `--max-budget-usd 1`
- [ ] README documents the install flow and Hazar can install his own framework end-to-end
- [ ] `wiki/log.md` has chronological entries for every meaningful decision the team made
- [ ] Each teammate has filed a "lessons learned" entry summarizing what surprised them

**Do not declare done early.** ADR-023's V1 fence is explicit about what's in scope; everything else is V2+.

---

## What NOT to Do

- Do not relitigate the design. 27 ADRs + 25 research pages + a self-reviewed design doc + 8 amendment passes are settled. If you disagree with an ADR, file an ADR-028+ amendment with reasoning and let the user decide — don't silently work around it.
- Do not let teammates edit files outside their owned column without coordination.
- Do not skip the plan-approval gate on the first few tasks. Once the team is calibrated, the user can relax this per-teammate.
- Do not use the `wiki-updater` subagent from this app directory — it doesn't work here. Write the wiki directly. See `/home/hsozer/Dev/CLAUDE.md` § Wiki Writes from App Directories for the doctrine.
- Do not use `--dangerously-skip-permissions`. The `.claude/settings.local.json` allow-list is pre-seeded with the dev-loop primitives; expand it explicitly if more is needed.
- Do not let the team run unattended for hours. The doc warns: "Letting a team run unattended for too long increases the risk of wasted effort."

---

## First Message to Send the User After Reading This

Once you've completed pre-flight + required reading, message the user with:

1. A 4–6 bullet summary of what V1 ships (proves you read the design doc)
2. Your validation of the proposed team structure (agree / propose changes)
3. The file-ownership matrix as you'd commit to it
4. A confirmation that you'll write the 4 subagent definitions, get approval on the matrix, and only then call `TeamCreate`

Wait for the user's "go" before any `TeamCreate` call.
