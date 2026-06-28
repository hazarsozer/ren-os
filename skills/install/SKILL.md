---
name: install
description: |
  Use when the friend invokes /ren:install. Orchestrates the 7-stage
  onboarding flow per ADR-015 (solo-first per ADR-031): environment check,
  required plugin install, conditional plugins, identity bootstrap, wiki
  skeleton bootstrap, doctor verification, and first-session walkthrough.
  Idempotent — re-running resumes from the last successful checkpoint at
  $XDG_STATE_HOME/sf/install-state.json. Never overwrites the friend's wiki;
  Stage 5 uses additive-diff with explicit approval. Default handoff is
  three explicit commands (no PostInstall hook in v1).
version: 0.1.0
license: MIT

contract:
  required_outputs:
    - "All 6 required plugins installed at pinned versions"
    - "~/.startup-framework/wiki/ skeleton present (or additive-diff'd onto existing wiki)"
    - "~/.startup-framework/wiki/identity.md populated via /ren:interview"
    - "Green /ren:doctor verification at end"
    - "Idempotent checkpoint file with all 7 stages marked completed"
  budgets:
    turns: 80                       # 7 stages × ~10 turns each; generous slack
    files_written: 30               # state file + wiki skeleton + LICENSES + identity
    duration_seconds: 1200          # 20 min target; allow up to 20 min for plugin install network
  permissions:
    read:
      - "~/.startup-framework/**"
      - "$XDG_STATE_HOME/sf/**"
      - "skills/install/references/**"
      - "wiki-skeleton/**"
    write:
      - "~/.startup-framework/wiki/**"
      - "$XDG_STATE_HOME/sf/install-state.json"
    execute:
      - "claude auth status"
      - "claude auth login"
      - "gh auth status"          # soft requirement, used by /ren:doctor's update check
      - "gh auth login"
      - "node --version"
      - "git --version"
      - "/plugin marketplace add"
      - "/plugin install"
  completion_conditions:
    - "All 7 stages report completed in $XDG_STATE_HOME/sf/install-state.json"
    - "Friend has explicitly acknowledged the Stage 7 walkthrough"
    - "/ren:doctor exit status is 0 with no red flags"
  output_paths:
    - "$XDG_STATE_HOME/sf/install-state.json"
    - "~/.startup-framework/wiki/**"

tags: [onboarding, install, orchestrator]
related_skills: [interview, bootstrap-project, doctor, update]
references_required:
  - "references/resume-protocol.md"
references_on_demand:
  - "references/stage-1-environment.md"
  - "references/stage-2-required-plugins.md"
  - "references/stage-3-conditional-plugins.md"
  - "references/stage-4-identity-bootstrap.md"
  - "references/stage-5-wiki-bootstrap.md"
  - "references/stage-6-doctor-verification.md"
  - "references/stage-7-walkthrough.md"
  - "references/install-state.schema.json"
---

# install

7-stage onboarding orchestrator. Idempotent, resumable, additive-only against any existing friend wiki content.

## When to use this skill

- Friend invokes `/ren:install` (canonical trigger).
- Friend says "let me re-run install" / "I think install didn't finish" — confirm and run; the resume protocol picks up at the right stage.
- After a framework update (`/ren:update`) when migration prompts the friend to re-verify their setup.

## When NOT to use this skill

- Friend wants to ADD a single plugin → tell them to use `/plugin install <name>` directly. This skill is the full install, not a one-off.
- Friend wants to migrate an existing wiki to a newer schema → `/ren:update` + `/ren:wiki-migration` own that path (sf-distribution).
- The friend has explicitly run `/ren:install --reset` and wants nothing to happen → exit cleanly; resetting state is its own command.

## How to use this skill

### 0. Load + validate checkpoint

Load `references/resume-protocol.md`. Open `$XDG_STATE_HOME/sf/install-state.json` (path resolution per the schema doc); validate against `references/install-state.schema.json`.

Branch:
- File doesn't exist → fresh install; create empty state with `completed_stages: []`.
- File exists + valid → resumable; the protocol determines the entry stage.
- File exists + malformed → refuse; print parser error + offer `/ren:install --reset` as remediation.
- File exists + `framework_version` newer than ours → refuse; recommend running `/ren:install` from the newer plugin version.

### 1. Run stages in order

For each stage 1–7, in order:

1. Skip if `stage_N in state.completed_stages` AND the stage doesn't override skip semantics (Stage 1 + Stage 6 always run their checks; see § "Per-stage skip overrides" below).
2. Load the stage's reference doc on demand: `references/stage-<N>-*.md`.
3. Execute the stage's procedure. The orchestrator passes the current state object; the stage returns an updated state.
4. Persist the updated state to disk before moving on (atomic write — `state.tmp` → `rename`).
5. If the stage raises a recoverable error, append to `state.abort_log` with `{stage, error_summary, ts}`; persist; exit with "re-run /ren:install to resume from Stage N" message.

### Per-stage skip overrides

- **Stage 1** ALWAYS runs its environment checks (per team-lead P1). When the checkpoint records last green checks, the stage skips only the prompt-for-fix UX; the underlying `claude auth status` / `gh auth status` / version probes still execute. Cost is sub-second; correctness wins.
- **Stage 6** ALWAYS runs (cheap; the doctor invocation is the verification surface).
- **Stage 7** runs once per checkpoint; `walkthrough_acknowledged: true` is the only stop condition.

### 2. Per-stage delegation

Each stage reference doc is self-contained. SKILL.md is the orchestrator; per-stage details live in their docs:

| Stage | What | Delegates to |
|---|---|---|
| 1 | Environment check | `references/stage-1-environment.md` |
| 2 | Required plugin install (6 plugins, ordered per ADR-010) | `references/stage-2-required-plugins.md` |
| 3 | Conditional plugins (opt-in, e.g. Frontend Design for UI work) | `references/stage-3-conditional-plugins.md` |
| 4 | Identity bootstrap via `/ren:interview` | `references/stage-4-identity-bootstrap.md` |
| 5 | Master wiki skeleton bootstrap (additive-diff) | `references/stage-5-wiki-bootstrap.md` |
| 6 | `/ren:doctor` verification | `references/stage-6-doctor-verification.md` (lifecycle owns `/ren:doctor` itself) |
| 7 | First-session walkthrough | `references/stage-7-walkthrough.md` |

### 3. CLI variants

- `/ren:install` — default; resume from checkpoint.
- `/ren:install --reset` — delete checkpoint; do NOT touch wiki or plugins; next `/ren:install` runs from scratch. Friend must explicitly confirm.
- `/ren:install --redo-stage <N>` — force re-execution of stage N; checkpoint records `completed_stages` is recomputed by removing N and any stage that depended on N's outputs.

### 4. Print a final summary

```
✓ Stage 1 — Environment ready
✓ Stage 2 — 6/6 required plugins installed at pinned versions
✓ Stage 3 — Conditional plugins resolved (none requested)
✓ Stage 4 — Identity bootstrapped (handle: <handle>)
✓ Stage 5 — Wiki skeleton at ~/.startup-framework/wiki/
✓ Stage 6 — /ren:doctor passed
✓ Stage 7 — Walkthrough acknowledged

Ready. Try /ren:wake-up to start your first session.
```

## Anti-patterns

- **Don't run stages out of order.** Even resume runs them sequentially; resume only changes which stage is the entry point.
- **Don't auto-fix things Stage 1 detected as missing.** Print the remediation; let the friend act; exit if they don't have the dependency. Auto-installing `gh` or `node` is out of scope.
- **Don't touch the friend's existing wiki content.** Stage 5 is additive-diff with explicit approval. Per ADR-017 + team-lead P2.
- **Don't pre-install Frontend Design or Ralph.** These are conditional (Stage 3 asks); auto-installing them violates ADR-006's curation.
- **Don't write to the wiki from Stages 1, 2, 3, 6, or 7.** Only Stages 4 and 5 write wiki content. Other stages write to the install-state checkpoint only.
- **Don't bypass the additive-diff approval prompt in Stage 5**, even if the diff is "just one new .gitkeep file". Friend's wiki is sacred per ADR-017.

## Eval expectations (see `eval/eval.json`)

- Fresh-machine test: 7 stages complete; checkpoint shows all stages done; doctor green
- Partial-stage-2 resume: re-running after 3-of-6 plugins installed picks up from plugin #4; doesn't reinstall #1–3
- Pushback P1 verification: Stage 1 checks always execute even after a green checkpoint
- Pushback P2 verification: Stage 5 against an existing wiki shows additive diff and writes nothing unless approved
- Pushback P3 verification: post-install does NOT auto-invoke any other slash command; friend is the trigger
