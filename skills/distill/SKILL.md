---
name: distill
description: |
  The #60 wiki-distiller (spec 2026-08-18 §3): batch-mine L1 narratives
  newer than the stored watermark for durable learnings the live wrap gate
  missed, and land them through the single write door, producer="distiller",
  capped at WRITE_CAP writes per run.
version: 0.7.9
license: MIT

framework_version: "0.7.9"
schema_version: 1
type: skill
execution_tier: deterministic

contract:
  required_outputs:
    - "Advances watermark to max ren_ts of the batch (only on fully successful run)"
    - "Returns counts: applied, held, suggested, gated_out, refused, capped_remainder"
  budgets:
    turns: 2
    files_written: 1
    duration_seconds: 60
  permissions:
    read:
      - "~/.renos/wiki/**"
      - "~/.renos/l1/**"
    write:
      - "~/.renos/wiki/.ren/distiller-watermark.json"
      - "~/.renos/wiki/.ren/journal.jsonl"
  completion_conditions:
    - "Watermark advanced only if mining, classification, and application all succeeded"
    - "Malformed agent reply stops the flow; watermark untouched"
    - "Every candidate passed through apply_candidates (no silent drops)"
  output_paths: []

tags: [knowledge-synthesis, wiki-distill, batch-mining, routine]
related_skills: [wrap, routine-init]
references_required: []
references_on_demand: []
---

# distill

The #60 wiki-distiller (spec 2026-08-18 §3): batch-mine L1 narratives newer
than the stored watermark for durable learnings the live wrap gate missed,
and land them through the single write door, producer="distiller", capped at
WRITE_CAP writes per run.

## When to use

- `/ren:distill` — on-demand run (the first backlog-rescue run is this).
- The weekly routine (routines/distiller-weekly.md) runs the same flow.

## Flow

1. **Batch.** `uv run python -c "from skills.distill.lib import l1_batch, read_watermark; import json; print(json.dumps(l1_batch(read_watermark())))"` from the framework repo (or the versioned plugin cache with `UV_PROJECT_ENVIRONMENT` redirected, same as /ren:update's convention). Empty batch → report "watermark caught up", stop.
2. **Dedup context.** For each distinct `session` in the batch, collect `landed_pages(session)`.
3. **Mine.** Spawn ONE `ren-distiller` agent (worker-class) with the batch's `escaped_body` texts and the per-session landed sets. Parse its reply as the candidate JSON array. A malformed reply → stop, report, watermark UNTOUCHED.
4. **Classify.** Build one classifier prompt per candidate via `build_classifier_prompt(item, eligible_targets=eligible_update_targets(source_session), project=...)` and spawn ONE classifier-class subagent (batched, same pattern as /ren:wrap step 3) returning an index-keyed JSON verdict array.
5. **Apply.** Assemble `candidates` (lib shape: item/verdict/source_session/project/content=proposed_content/page=None) and call `apply_candidates(candidates, run_session="distill-<date>")`. Print the returned counts; a non-zero `capped_remainder` is reported as "N candidates carried to the next run".
6. **Advance the watermark** to the batch's max `ren_ts` — ONLY if steps 3-5 completed without an exception. Any failure leaves the watermark untouched (re-run safe; the journal dedup makes replays idempotent).
7. **Report.** One screen: batch size, candidates, applied/held/suggested/gated_out/refused, capped remainder, new watermark.

## What this skill does NOT do

- Write any wiki file directly — apply_candidates is the only write path.
- Advance the watermark on a failed or partial run.
- Touch quarantine banners, trust stamps, or the backup remote.
