---
title: "ADR-034: Cadence as Glue over Native Primitives (no framework scheduler)"
status: accepted
date: 2026-06-11
sunset-review: 2027-06-11
references-pages: [nate-herk-cadence-automation, new-angles-for-the-os, nate-herk-ai-os, ralph]
affects-components: [cadence, routines, skills, wiki-schema, doctor, backup, safety]
relates-to: [003-no-daemon-rule, 008-wake-up-hook, 009-consolidate-via-wrap, 014-project-sub-wiki-taxonomy, 026-backups-and-recovery, 027-schema-versioning, 031-solo-first-pivot, 033-renos-rebrand]
---

# ADR-034: Cadence as Glue over Native Primitives (no framework scheduler)

> Net-new — the framework had **zero** cadence ADRs (ADR-008 covers SessionStart only). Cadence was the
> self-identified weakest layer; the positioning pivot (`wiki/research/new-angles-for-the-os.md`,
> `docs/superpowers/specs/2026-06-08-nate-herk-ingest-positioning-design.md` Pillar 3) re-scoped it to
> **glue over native primitives**. Primary source: `wiki/research/nate-herk-cadence-automation.md`. This
> ADR is the binding decision the cadence build (roadmap slice **C4**) implements against.

## Context

Between the framework's design and mid-2026, Claude Code shipped a full ladder of scheduling primitives
— `/loop`, `CronCreate/List/Delete`, `/goal`, and **Cloud Routines** (machine-off; cron/API/GitHub
triggers; network-tiered cloud envs; quota-limited). The framework's job is no longer to *build*
cadence; it is to make these primitives **report home** to the governable wiki, with conventions that
keep unattended runs safe, observable, and recoverable — without adding any background process of its
own (ADR-003).

## Decision

**Cadence is thin glue over CC-native primitives. RenOS ships no scheduler or daemon of its own.** The
framework contributes scaffolding, conventions, write-back, documentation, and safety audits — never a
long-running process.

### 1. Primitive ladder + decision matrix (use the lowest tier that fits)

| Primitive | Statefulness / durability | Use for |
|---|---|---|
| `/loop` | intra-session, **retains context**, ≤ 3 days | deploy/PR watches, context-budget checks |
| `CronCreate/List/Delete` | session-scoped; terminal **7d** / desktop **3d**; ~30-min jitter | scheduled session loops (interval mental model, not wall-clock) |
| `/goal` | autonomous depth-first loop until a **measurable** exit criterion (≤ 24h+) | overnight `/ren:improve-skill`, weekly scans |
| **Cloud Routines** | machine-off; cron/API/GitHub triggers; cold fresh env each run; quota (Max 15/day, min 1h) | production cadence |

### 2. Write-back (Pillar 3 — control the truth, leverage the muscle)

Every run's durable result lands in the wiki (the truth layer), by execution locus:
- **Local** cadence (`/loop`, cron, `/goal`) → **direct file write** to the wiki.
- **Cloud Routines** (machine off) → **git-based write-back**: the run commits results/state to a branch
  and pushes; the user pulls (via `/ren:backup`/`git pull`). **Pull-model only** — reuses ADR-026 git
  plumbing.

**Explicitly rejected:** exposing the wiki as a local MCP server / any listener that watches a remote
for incoming commits. That is a daemon and **violates ADR-003**. The boundary: a routine's `git push` is
a child of the cloud session's lifecycle; the framework never runs a process that *waits* for it.

### 3. Framework glue (the surface C4 builds)

- **`ren-routine-init`** — scaffolds a **lean per-routine GitHub repo** from a template (small CLAUDE.md +
  only the needed skills/scripts; no unrelated project context burning run budget).
- **Skill-as-routine-prompt** convention — routine prompts invoke a named `/ren:` skill with an explicit
  order of operations (predictable one-shot execution).
- **Required failure-notification footer** — every routine prompt appends a failure handler (Slack/email
  via the globally-registered Resend MCP). Headless runs fail silently by default; this is zero-infra
  observability.
- **Self-terminating loops** (kill after N iterations / a time window) + an **auto-compact companion
  cron** (a second cron whose payload is `/clear`, every ~5 min) to prevent context rot.
- **`routine-spec` wiki page-type** — documents each live routine (name · trigger type · linked repo ·
  env/secrets ref · expected output · failure handler). The wake-up hook surfaces which automations are
  live. *Page-type is **specified here**; its `schemas.json` registration + template land in C4 (per
  ADR-027) to avoid drifting the page-type count before there's a consumer.*
- **`/ren:recall` reads `state.md`/`run-log.md`** from the routine repo at run start — the cross-run
  memory trail for stateless cloud runs.

### 4. Safety posture

- **Network-access tier** becomes a `/ren:doctor` audit dimension: default **trusted** (Anthropic
  allowlist); **flag `full`** as a prompt-injection exfiltration surface; secrets live in the cloud env,
  never the repo.
- **Permission mode by plan tier (ADR-031):** Auto Permission Mode for *team-plan* unattended runs;
  **manual allowlist/denylist for solo** Pro/Max users. **Never** bypass-permissions for cadence.
- **Named agent-vs-code boundary:** *"Scheduled automation deploys deterministic code; the agent's
  judgment and self-healing stay in the interactive session."* Deployed artifacts carry none of the
  agent's judgment — design routines as one-shot deterministic invocations with explicit guards.

### 5. WATCH (design-ready, not built)

**Daemon mode** + **Coordinator mode** are referenced in leaked CC source behind feature flags. When they
ship publicly, cadence wires in immediately via this same lean-repo + write-back design — no ground-up
rethink.

## Consequences

- **Unblocks C4** — gives the cadence build a binding architecture (the matrix, write-back model, glue
  surface, safety posture).
- **No daemon debt** — every cadence feature is a wrapper/convention over a native primitive or a
  pull-model git write; ADR-003 holds.
- **New page-type commitment** — `routine-spec` is an ADR-027 forward-compat commitment once C4 registers it.
- **Quota is a real ceiling** — Cloud Routines cap (Max 15/day) means `/ren:doctor`/`/ren:insights` should
  surface live quota consumption (open tension #1 from the research).

## Alternatives considered

- **Build a framework scheduler/daemon** — rejected: violates ADR-003; native primitives already cover
  the ladder; "just one small daemon" is exactly what ADR-003 forbids.
- **Wiki-as-MCP-server for write-back** (Ben AI's approach) — rejected: a listener/daemon, machine-on,
  violates ADR-003. Git pull-model write-back achieves the same "report home" without a process.
- **Per-primitive ADRs** (separate cadence/write-back/page-type decisions) — rejected: the pieces are
  interdependent; one coherent cadence decision is clearer for the C4 build.

## References

- `wiki/research/nate-herk-cadence-automation.md` — the primitive ladder, conventions, open tensions
- `wiki/research/new-angles-for-the-os.md` — Pillar 3 (control the truth / leverage the muscle) + the cadence angles
- ADR-003 (no-daemon rule) · ADR-026 (git backup plumbing) · ADR-014/027 (page-type taxonomy + schema registry) · ADR-031 (solo-first permission posture)

---

## Amendment — 2026-06-28: `routine-spec` v2 — `verification_strategy` (C2)

`routine-spec` gains a v2 (additive — the framework's first real schema migration; see the ADR-027 amendment):
**`verification_strategy`** (`visual | test-run | lint | llm-judge | manual`) + optional **`verification_tools`**
— how a routine's output is confirmed, not just what it does and how it fails. `/ren:routine-init` elicits it
(`--verify`, default `manual`); new pages write at schema 2, and v1 pages migrate via
`migrations/routine-spec-1-to-2/`. Design spec `docs/superpowers/specs/2026-06-28-c2-routine-spec-v2-design.md`.
