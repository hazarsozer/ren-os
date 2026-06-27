---
name: cadence
description: |
  Use when the friend wants to automate a recurring task and needs to pick the
  RIGHT primitive ("should this be a /loop, a cron, a /goal, or a Cloud
  Routine?"). Triggers on /ren:cadence. Presents the decision matrix (ADR-034
  §1), routes to the lowest tier that fits, and applies the framework
  conventions (self-terminating loops, auto-compact companion cron, measurable
  /goal exit, failure footer, env-var sourcing). For the cloud tier it hands off
  to /ren:routine-init. Thin glue over native primitives — runs nothing itself.
version: 0.1.0
license: MIT
framework_version: "1.0.0"
schema_version: 1
type: skill
owner_module: sf-cadence

contract:
  required_outputs:
    - "A recommended cadence tier (/loop | Cron | /goal | Cloud Routine) with the one-line reason it fits"
    - "For local tiers: the exact guarded invocation (self-terminating stop + failure footer; auto-compact companion cron for long loops; measurable exit for /goal)"
    - "For the cloud tier: a handoff to /ren:routine-init"
  budgets:
    turns: 3
    files_written: 0
    duration_seconds: 15
  permissions:
    read:
      - "references/**"
    write: []
    execute: []
  completion_conditions:
    - "A tier is recommended with its reason"
    - "Run is side-effect-free (no files written; no schedule created without the friend's go-ahead)"
  output_paths: []

tags: [cadence, routines, loop, cron, goal, routing, read-only]
related_skills: [routine-init, recall, doctor]
references_required:
  - "references/cadence-matrix.md"
  - "references/conventions.md"
---

# cadence

The cadence router. Answers "what's the right way to make this recur?" with the **decision matrix** (ADR-034 §1) and applies the framework's safety conventions. It runs nothing itself — it routes to native primitives (`/loop`, `CronCreate`, `/goal`, Cloud Routines) and to `/ren:routine-init`.

## When to use

- Friend invokes `/ren:cadence` or asks "should this be a loop or a cron or a routine?"
- Before `/ren:routine-init`, to confirm a Cloud Routine is actually the right tier.

## When NOT to use

- The friend already knows the tier and just wants to scaffold a cloud routine → `/ren:routine-init` directly.
- The question is how to *split work across agents* (sub-agent vs parallel team vs dynamic workflow), not how to schedule it → see `references/agent-orchestration.md`.

## Behavior

1. **Clarify the task's shape** (ask only what's needed): does it need to run with the machine off? what's the cadence (continuous / minutes / hourly+ / one long push)? is there a measurable done-criterion? does it fan out into many parallel pieces?
2. **Route via the matrix** (`references/cadence-matrix.md`). Use the **lowest tier that fits**:
   - intra-session watch (deploy/PR/context-budget) → `/loop`
   - scheduled session loop (machine on) → `CronCreate`
   - long autonomous loop with a measurable exit → `/goal`
   - machine-off / production cadence (≥1h) → **Cloud Routine** → hand off to `/ren:routine-init`
3. **Apply the conventions** (`references/conventions.md`) to whatever tier is chosen:
   - **Self-terminating**: every `/loop`/cron carries a stop condition (kill after N iterations or a time window) so no orphaned background job persists.
   - **Auto-compact companion cron**: for a long-running loop, pair it with a second cron whose sole payload is `/clear` (~every 5 min) to prevent context rot.
   - **Failure footer**: any unattended prompt appends "if this fails, email me via Resend MCP `mcp__resend__send-email`".
   - **Measurable exit for `/goal`**: a concrete done-criterion (passing test, coverage threshold), never a subjective prompt (which loops forever).
   - **Env-var sourcing**: tell the run secrets are env vars; do not look for `.env`.
4. **Emit** the recommended tier + reason + the exact guarded command (or the `/ren:routine-init` handoff). Create a schedule only with the friend's explicit go-ahead, and recommend **Run-Now before scheduling**.

## What this skill does NOT do

- Reimplement `/loop`/Cron/`/goal` — those are native; this routes to them.
- Run a daemon or scheduler (ADR-003).
- Scaffold the cloud repo — that's `/ren:routine-init`.

## Eval

`eval/eval.json` asserts the router recommends the correct tier for canonical prompts (machine-off→Cloud Routine + routine-init handoff; intra-session watch→/loop with a stop condition; measurable long job→/goal) and always attaches the relevant convention.

## References

- `references/cadence-matrix.md` — the primitive ladder + the decision matrix (ADR-034 §1).
- `references/conventions.md` — self-terminating, auto-compact companion cron, failure footer, measurable exit, env-var sourcing, off-peak, terminal-vs-desktop cron + jitter.
- `references/agent-orchestration.md` — the **other axis**: how to *decompose* work across agents (quick-ask → skill → sub-agent → agent-team → /goal → dynamic-workflow) + model-routing (Haiku workers, 3–5 concurrent cap). Cadence picks *when* it runs; this picks *how it fans out*.
