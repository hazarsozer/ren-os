---
name: routine-init
description: |
  Use when the friend wants to declare a pre-declared routine/loop — a
  scheduled or triggered automation that runs unattended. Documents the v3
  routine-spec schema (Task 6.3): every routine must declare its schedule,
  exit criterion, failure handler, AND a capability/path allowlist bounding
  WHAT it may touch, not just when it runs. Triggers on the
  /ren:routine-init slash command.
version: 0.4.2
license: MIT

framework_version: "0.4.2"
schema_version: 3
type: skill
execution_tier: deterministic

contract:
  required_outputs:
    - "A routine-spec page validated against the v3 schema (validate_routine_spec)"
    - "A non-empty allowlist.paths for any NEW spec (migrated specs may start empty — see migrations/routine-spec-2-to-3/README.md)"
  budgets:
    turns: 3
    files_written: 0
    duration_seconds: 15
  permissions:
    read:
      - "~/.renos/wiki/routines/**"
    write: []
    execute: []
  completion_conditions:
    - "validate_routine_spec(spec) returns valid=True with no errors"
  output_paths: []

tags: [routine, cadence, allowlist, governance, schema]
related_skills: [metric-watch]
references_required: []
references_on_demand: []
---

# routine-init

The declaration side of spec §3.5's routine model: **a routine's declaration must bound what it may touch, not just when it runs.** This skill's `lib` doesn't scaffold a repo (see "Scope" below) — it validates the v3 routine-spec schema and provides the runtime allowlist check every routine calls before proposing a write.

## The v3 schema (REQUIRED fields)

```yaml
schema_version: 3
allowlist:
  paths: ["projects/myproj/**"]          # wiki-relative globs the routine may propose writes to
  capabilities: ["recall", "queue-propose"]   # named capabilities it may invoke
failure_handler: "notify-journal"        # the ONLY valid value in 0.2
exit_criterion: "<non-empty string>"     # human-readable, required
```

- **`allowlist.paths` must be non-empty for a NEW spec.** A routine that may touch anything is invalid BY SCHEMA — there is no "allow everything" escape hatch. (A migrated v2→v3 spec is the one exception: it may start with empty `paths` until a human fills it in — see `migrations/routine-spec-2-to-3/README.md`.)
- **`allowlist.paths` must never include `global/` or `global/**`.** Routines can never write to the global tier — enforced here at declaration time, and independently again at apply time by `lib.governance.tiers.tier_of` (Task 6.1): a routine `memory_write` to a `global/` page is always `diff_approved`, never `auto`.
- **`failure_handler` has exactly one valid value: `"notify-journal"`.** Spec §3.5: "failure = notify + journal." There is no free-text failure-handler mechanism in 0.2 (donor's pre-0.2 free-text handlers, e.g. "email me@x via Resend MCP", described a mechanism 0.2 doesn't implement — see the 2-to-3 migration's overwrite behavior).
- **`exit_criterion` is required and must be non-empty.** A routine with no declared stopping condition isn't bounded, regardless of what its allowlist says.

## When to use this skill

- Friend invokes `/ren:routine-init` to declare a new scheduled/triggered automation
- Friend or `/ren:doctor` needs to validate an existing routine-spec page against the current schema

## When NOT to use this skill

- The routine already exists and just needs its metrics watched → `/ren:metric-watch` (sibling skill, reads routine-adjacent signals, doesn't touch routine-spec pages)
- Migrating an existing v2 spec to v3 → run `migrations/routine-spec-2-to-3/migrate.sh` directly (or via whatever migration-runner eventually wraps it); this skill validates, it doesn't migrate

## Behavior

1. Collect the routine's declared fields (schedule, exit criterion, failure handler — fixed to `"notify-journal"`, allowlist paths/capabilities) from the friend.
2. Call `skills.routine-init.lib.validate_routine_spec(spec, migrated=False)`. Any error blocks the declaration; warnings (there are none for a NEW spec — those only apply to `migrated=True`) are informational.
3. Once valid, the routine-spec page is written (page-writing itself is outside this module's scope — see below).
4. At runtime, whenever the routine is about to `lib.memory.queue.propose` a write, it calls `skills.routine-init.lib.check_proposal_against_allowlist(routine_spec, proposal)` FIRST. A `False` result means the routine must not propose that write — the allowlist is checked before the queue's own producer/writer validation, not instead of it.

## Scope note (what this skill's `lib` does NOT do)

Donor's `skills/routine-init/lib/__init__.py` scaffolds an entire lean per-routine repo (`CLAUDE.md`, `ROUTINE_PROMPT.md`, `state.md`, `run-log.md`) from templates, plus writes the routine-spec wiki page itself. That repo-scaffolding machinery (ADR-034 "cadence-as-glue") is a separate, larger surface this task's brief and test list don't touch — Task 6.3 is specifically about the v3 schema fields and allowlist enforcement. `lib/__init__.py` here is deliberately narrow: schema validation + the runtime allowlist check, nothing else. Scaffolding a full routine repo (if/when RenOS needs it) is future work layered on top of this validation, not part of it.

## Failure-degradation modes

| Failure | Behavior | User-visible |
|---|---|---|
| No allowlist declared | `validate_routine_spec` returns an error | "allowlist is required..." |
| `allowlist.paths` includes `global/**` | Validation error, regardless of other fields | "...touches global/ — routines can never write global" |
| `failure_handler` set to anything but `notify-journal` | Validation error | "failure_handler must be one of ('notify-journal',)..." |
| Empty `exit_criterion` | Validation error | "exit_criterion is required..." |
| A routine proposes outside its allowlist | `check_proposal_against_allowlist` returns `False`; the routine must not call `queue.propose` | (caller's responsibility to surface this — this function only answers yes/no) |

## References

- Task 6.1 (`lib/governance/tiers.py`) — the apply-time enforcement this schema's declaration-time checks complement
- `migrations/routine-spec-2-to-3/` — the v2→v3 migration, including the failure_handler overwrite rationale
- Spec §3.5 — the routine-declaration model this schema implements
