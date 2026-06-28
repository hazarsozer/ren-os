---
name: routine-init
description: |
  Use when the friend wants to deploy a scheduled/cloud automation ("set up a
  daily digest", "run X on a schedule", "make a Cloud Routine"). Triggers on
  /ren:routine-init <name>. Scaffolds a lean per-routine GitHub repo (small
  CLAUDE.md + a skill-as-prompt with the failure footer baked in) and writes a
  routine-spec wiki page so the wake-up hook + /ren:doctor can see it. Per
  ADR-034: thin glue over Cloud Routines — no scheduler of its own. For picking
  the right cadence tier (/loop vs Cron vs /goal vs Cloud), use /ren:cadence first.
version: 0.1.0
license: MIT
framework_version: "1.0.0"
schema_version: 1
type: skill
owner_module: sf-cadence

contract:
  required_outputs:
    - "A lean routine repo at <dest>/<slug>/ with CLAUDE.md, ROUTINE_PROMPT.md, state.md, run-log.md"
    - "A routine-spec wiki page at ~/.startup-framework/wiki/routines/<slug>.md (conformant frontmatter)"
    - "A printed next-steps checklist (push to GitHub, create the cloud env with network tier + secrets, Run-Now before scheduling)"
  budgets:
    turns: 4
    files_written: 5
    duration_seconds: 30
  permissions:
    read:
      - "skills/routine-init/templates/**"
      - "~/.startup-framework/wiki/identity.md"
    write:
      - "~/.startup-framework/wiki/routines/**"
      - "<dest-dir>/<slug>/**"
    execute:
      - "skills/routine-init/lib (routine_init)"
  completion_conditions:
    - "The repo dir and the routine-spec page both exist after a successful run"
    - "On any name/trigger/tier/skill/verification validation failure OR an existing target, nothing is written (clean refusal)"
  output_paths:
    - "~/.startup-framework/wiki/routines/"
    - "<dest-dir>/<slug>/"

tags: [cadence, routines, scaffold, cloud, lifecycle]
related_skills: [cadence, recall, doctor, backup]
references_required:
  - "references/lean-repo.md"
references_on_demand: []
---

# routine-init

Scaffolds a **lean per-routine repo** for a Cloud Routine and records it in the wiki. The repo is the *muscle* (only what this one routine needs); the wiki routine-spec page is the *truth* (the wake-up hook surfaces it; `/ren:doctor` audits it). Per ADR-034.

## When to use

- Friend invokes `/ren:routine-init <slug> …` (canonical trigger).
- Friend says "set up a daily/weekly automation" or "deploy this as a Cloud Routine" — confirm the tier with `/ren:cadence` first (Cloud Routine is the right tier only for machine-off, ≥1h cadence), then run this.

## When NOT to use

- For an **intra-session** watch (deploy/PR/context-budget) → that's `/loop`, not a routine repo. Use `/ren:cadence`.
- For a **long autonomous loop with a measurable exit** → that's `/goal`. Use `/ren:cadence`.
- Empty `<slug>`, non-kebab-case, or unknown trigger/tier → refuse (the lib validates).

## Behavior

1. **Gather inputs** (ask only for what's missing):
   - `name` (kebab-case slug), `--skill <verb>` (the `/ren:` skill the routine runs),
   - `--trigger <cron|api|github>`, `--repo <git-url>` (the linked repo),
   - `--tier <trusted|full|custom>` (default `trusted` — see § Safety),
   - `--schedule "<natural language>"` (cron trigger only), `--expected "<one line>"`,
   - `--secrets "<env var names>"`, `--failure-email <addr>` (default: friend's email from `identity.md`),
   - `--verify <visual|test-run|lint|llm-judge|manual>` (how the routine's output is confirmed; default `manual`) + optional `--verify-tools <names>` (v2 routine-spec, C2),
   - `--dest <dir>` (where to create the repo; default the cwd).
2. **Resolve paths**: `wiki_root` = `~/.startup-framework/wiki`; `dest_dir` = `--dest` or cwd.
3. **Invoke the lib** `routine_init(...)` (see `lib/__init__.py`). It validates, refuses to overwrite, scaffolds the four repo files (templates baked with the skill-as-prompt + failure footer + single-pass + env-var-sourcing conventions), and writes the conformant routine-spec page.
4. **Print next steps** (the lib does NOT touch GitHub or the cloud — those are the friend's outward actions):
   - `git init && git add -A && git commit` the new repo, then create a private GitHub repo and push.
   - In Claude Code, create a **Cloud Environment**: set network tier (`trusted` unless arbitrary domains are genuinely needed), add the secrets named in `--secrets` as env vars (NOT in the repo).
   - Configure the routine: linked repo + the prompt is `ROUTINE_PROMPT.md` + the schedule.
   - **Run-Now once** and watch it one-shot cleanly before scheduling (green-before-schedule, the TDD of cadence).

## Safety (ADR-034 §4)

- **Network tier defaults to `trusted`** (Anthropic allowlist). `full` = unrestricted egress = a prompt-injection exfiltration surface; only choose it deliberately. `/ren:doctor` flags `full`-tier routines.
- **Secrets live in the cloud env, never the repo.** The scaffolded CLAUDE.md/ROUTINE_PROMPT.md tell the run to use env vars directly and never look for a `.env`.
- **Never bypass-permissions for cadence.** Auto Permission Mode for team-plan unattended runs; manual allow/deny for solo (ADR-031).

## What this skill does NOT do

- Talk to GitHub or Anthropic's cloud (no repo creation, no scheduling) — it prints the steps; the friend acts.
- Pick the cadence tier — that's `/ren:cadence`.
- Run a daemon or watch for the routine's pushes — pull-model only (ADR-003/026).

## Failure-degradation modes

| Failure | Behavior | User-visible |
|---|---|---|
| Non-kebab name | Refuse, no writes | "Invalid routine name … Use kebab-case" |
| Bad trigger/tier | Refuse, no writes | "Invalid trigger_type/network_tier …" |
| Bad verification strategy | Refuse, no writes | "Invalid verification_strategy …" |
| Target repo or spec page exists | Refuse, no writes | "Refusing to overwrite …" |

## Eval

`eval/eval.json` asserts: a clean run writes the 4 repo files + the spec page; the spec page carries `type: routine-spec` + required fields + (v2) `verification_strategy`; the prompt bakes in the Resend failure footer and `/ren:recall --routine .`; invalid inputs and existing targets refuse with no writes.

## References

- `references/lean-repo.md` — the lean-repo discipline + the export-from-rich-session step.
- ADR-034 (cadence-as-glue), ADR-026 (git pull-model write-back), ADR-027 (routine-spec page-type; v2 adds `verification_strategy` — C2, the framework's first schema migration).
