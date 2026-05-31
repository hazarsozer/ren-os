# Resume Protocol — `/sf:install` idempotent checkpoint

Per plan §2 + team-lead's three pushbacks. Loaded by SKILL.md step 0.

## Checkpoint file

**Path resolution** (in order):

1. `$XDG_STATE_HOME/sf/install-state.json` if `XDG_STATE_HOME` is set.
2. Otherwise `~/.local/state/sf/install-state.json` (XDG default per the spec).
3. On non-Linux platforms without XDG, fall back to `~/.startup-framework/.install-state.json` — a hidden file next to the framework root.

The file is machine-local infrastructure, NOT wiki content. It does not belong inside `~/.startup-framework/wiki/`.

**Schema:** see `install-state.schema.json` (sibling file). JSON Schema draft 2020-12.

**Atomic writes:** every persistence step writes to `<path>.tmp`, then `rename(tmp, path)`. POSIX atomic-rename semantics guarantee a partial write never corrupts the prior good state.

**Validation:** SKILL.md step 0 validates the loaded file against the schema before doing anything with it. A malformed file aborts the run with explicit guidance:

```
$XDG_STATE_HOME/sf/install-state.json is malformed.
  Reason: <parser-error>
  Path:   <absolute-path>

Resolve by one of:
  /sf:install --reset       Delete the checkpoint and re-run install fresh.
  Edit the file manually    If you know what you're doing.
```

## Resume decision rules

The orchestrator computes the **entry stage** from the checkpoint:

```
entry_stage = min({1..7} \ completed_stages_set)
```

— first stage in 1..7 not yet completed. If `completed_stages` = `[1..7]`, the install is already done; print the final summary and exit clean.

The orchestrator runs `entry_stage`, then sequentially every subsequent stage. **It does NOT skip ahead past gaps**. If `completed_stages = [1, 3]` (Stage 2 missed somehow), entry_stage = 2, and after Stage 2 completes, Stage 3 runs again (idempotent re-check; harmless).

## Per-stage skip overrides

Some stages always run their core check even when marked completed (per team-lead P1):

- **Stage 1** always re-runs `claude auth status`, `gh auth status`, env-var presence, version probes. The check is cheap; correctness wins. Only the prompt-for-fix UX is skipped when last checkpoint was green.
- **Stage 6** always re-runs `/sf:doctor`. Same rationale.
- **Stages 2, 3, 4, 5, 7** are idempotent at the action level — re-running them after success does no work (each stage's pre-check sees its outputs already exist and exits clean).

Concretely, the rule is encoded as a per-stage `always_recheck` boolean in this protocol doc:

```yaml
stage_recheck:
  1: true    # env-state may have changed since last run
  2: false   # plugin install is durable
  3: false   # conditional-plugin choices are durable
  4: false   # identity.md is durable
  5: false   # wiki skeleton is durable
  6: true    # cheap, drives Stage 7 decision
  7: false   # one-shot acknowledgment
```

## Failure semantics

When a stage raises a recoverable error:

1. Capture `{stage: N, error_summary: "<short>", error_detail: "<full traceback or message>", ts: "<ISO>"}`.
2. Append to `state.abort_log` (bounded to last 32 entries; older entries dropped).
3. Persist state atomically.
4. Print to friend:

   ```
   Stage N (<name>) hit a problem:
     <error_summary>

   Re-run /sf:install to resume from Stage N.
   If the problem persists, /sf:install --redo-stage <N-1> may help.

   Full error log: <state-file-path>
   ```

5. Exit non-zero.

When a stage raises an UNrecoverable error (e.g. orchestrator bug, schema malformed mid-run):

1. Persist state with the abort_log entry.
2. Print the full error, no friendly framing.
3. Exit non-zero with code 2 (distinguish from "stage-level failure" code 1).

## Side-effect rollback policy

**No automatic rollback.** Per plan §2.2:

- A failed Stage 2 plugin install leaves successfully-installed prior plugins in place. Re-run resumes from the failed plugin.
- A failed Stage 3 conditional-plugin install leaves any already-installed conditional plugin in place. Re-run skips it and re-offers the remaining conditionals.
- A failed Stage 5 wiki bootstrap leaves any written skeleton files in place. Re-run sees them via the loader's `copy_if_missing` rule.

The single exception: state file corruption. If the orchestrator can't persist the state file, the run aborts immediately with a clear filesystem-level error; no further stages execute.

## CLI variants

| Command | Behavior |
|---|---|
| `/sf:install` | Default. Resume from checkpoint. |
| `/sf:install --reset` | Friend confirms; delete checkpoint file; do NOT touch wiki, plugins, or identity. Next `/sf:install` runs from scratch. |
| `/sf:install --redo-stage <N>` | Remove N (and any subsequent completed_stages that depended on N's outputs — table below). Persist. Resume from N. |

### --redo-stage dependency table

Removing stage N forces recomputation of these downstream stages:

| N | Removed from completed_stages |
|---|---|
| 1 | 1 (and re-runs all subsequent, since env may have changed) |
| 2 | 2, 6 (doctor re-checks) |
| 3 | 3, 6 (doctor re-checks conditional plugins) |
| 4 | 4, 6 |
| 5 | 5, 6 |
| 6 | 6 |
| 7 | 7 |

## What this protocol deliberately does NOT do

- Doesn't lock the checkpoint file (no other process should be writing it; if two `/sf:install` runs race, the later one's atomic rename wins and the earlier one's progress is lost — surface this as an "unexpected stage rollback" warning at next resume).
- Doesn't snapshot the wiki or plugins for rollback. Per the no-rollback policy.
- Doesn't expire the checkpoint. A stale checkpoint from 6 months ago is still valid input; the friend can `--reset` if they want a clean slate.

## Cross-references

- `install-state.schema.json` — the JSON Schema this protocol references
- ADR-027 — schema versioning that bumps this file when the protocol evolves
- plan §2 — original failure-resume design
- team-lead pushbacks P1 (Stage 1 always-check) + P2 (Stage 5 additive-diff)
