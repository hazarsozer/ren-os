---
title: "Routine: distiller-weekly"
type: routine-spec
schema_version: 3
framework_version: "{{framework_version}}"
name: "distiller-weekly"
trigger_type: "cron"
schedule: "weekly"
expected_output: "Accumulated L1 durable_outcome batches distilled into L2/L3 wiki knowledge via the /ren:distill flow"
allowlist:
  paths: ["**"]
  capabilities: ["recall", "queue-propose"]
failure_handler: notify-journal
exit_criterion: "l1_batch(read_watermark()) is empty, or apply_candidates() returned because the per-run write cap was reached"
verification_strategy: manual
verification_tools: []
created: {{today}}
updated: {{today}}
---

# Routine: distiller-weekly

Documents the weekly cadence for the `/ren:distill` flow (Task 6, spec §3.1/§4.1) — the routine that turns accumulated `durable_outcome` events (`producer: "wrap"` or `"distiller"`) into distilled wiki knowledge. Surfaced by the wake-up hook and audited by `/ren:doctor`, like any other declared routine (ADR-034).

## What it does

Runs `/ren:distill`: reads the distiller watermark, batches unprocessed L1 material since that watermark (`l1_batch(read_watermark())`), and applies distilled candidates back into the wiki through the memory queue (`apply_candidates`), advancing the watermark on success.

## Trigger

- **Type:** cron
- **Schedule:** weekly

## Exit criterion

Stops for this run when either:

- `l1_batch(read_watermark())` returns empty (nothing left to distill), or
- `apply_candidates(...)` returned because the per-run write cap (`WRITE_CAP`) was reached — remainder carries to the next scheduled run.

## Failure handling

`notify-journal` (the only 0.2 failure handler, spec §3.5: "failure = notify + journal"): a failed run reports to the journal and leaves the watermark untouched, so nothing already-distilled is silently skipped and nothing partially-processed is falsely advanced past.

## Safety

- **Allowlist paths:** `**` (wiki-relative — distillation may touch any wiki page) — reads across the wiki freely; **all writes go through the memory queue** (`apply_candidates` → `lib.memory.queue.propose`), never a direct file write, so every distilled write is still subject to the queue's own governance (Task 6.1 tier checks, `check_proposal_against_allowlist`).
- **Capabilities:** `recall`, `queue-propose`.
- **State file:** `wiki_root()/.ren/distiller-watermark.json` (`skills/distill/lib.watermark_path()`) — the single piece of cross-run state this routine owns; untouched on failure.
- **Network tier:** none — local-only, reads/writes the local wiki and its own watermark file.
