---
name: distill
description: |
  The #60 wiki-distiller (spec 2026-08-18 §3): batch-mine L1 narratives
  newer than the stored watermark for durable learnings the live wrap gate
  missed, and land them through the single write door, producer="distiller",
  capped at WRITE_CAP writes per run.
version: 0.8.6
license: MIT

framework_version: "0.8.6"
schema_version: 1
type: skill
execution_tier: deterministic

contract:
  required_outputs:
    - "Advances watermark to result[\"watermark_after\"] when non-None (never guessed, always lib-computed)"
    - "Returns counts: applied, held, suggested, gated_out, refused, duplicates, capped_remainder, watermark_after"
  budgets:
    turns: 3
    files_written: 1
    duration_seconds: 60
  permissions:
    read:
      - "~/.renos/wiki/**"
    write:
      - "~/.renos/wiki/**"
      - "~/.renos/wiki/.ren/distiller-watermark.json"
      - "~/.renos/wiki/.ren/seed-tree-watermark-*.json"
      - "~/.renos/wiki/.ren/journal.jsonl"
      # --seed-tree (Task 7, spec 2026-08-31 §3) widens the write surface
      # past lessons/: a concept-kind lesson lands as a taxonomy leaf, with
      # its leaf/parent hubs and schema.md's fence additively updated.
      - "~/.renos/wiki/projects/*/knowledge/**"
      - "~/.renos/wiki/projects/*/schema.md"
  completion_conditions:
    - "Watermark advanced only to result[\"watermark_after\"], and only if mining, classification, and application all succeeded"
    - "Malformed agent reply stops the flow; watermark untouched"
    - "Every candidate passed through apply_candidates (no silent drops)"
    - "A capped run's remainder stays behind the watermark (spec §3.4) — watermark_after never advances past an unprocessed session's earliest L1"
    - "--seed-tree: a missing/unparseable schema.md refuses the WHOLE run — zero writes — rather than guessing a placement"
  output_paths:
    - "~/.renos/wiki/lessons/"
    - "~/.renos/wiki/projects/*/knowledge/lessons/"
    - "~/.renos/wiki/projects/*/knowledge/**"
    - "~/.renos/wiki/projects/*/schema.md"
    - "~/.renos/wiki/.ren/distiller-watermark.json"
    - "~/.renos/wiki/.ren/seed-tree-watermark-*.json"

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
- `/ren:distill --seed-tree <project>` — MANUAL TRIGGER ONLY (spec 2026-08-31
  §3 behavior 1). Backfills the concept tree from a project's EXISTING
  `knowledge/lessons/` pages — durable concepts written before concept-tree
  routing existed, or missed by a session's own wrap gate. This mode is
  NEVER part of the scheduled weekly routine; it runs only when a friend (or
  the live session, deliberately) asks for it by name.

## Flow

1. **Batch.** `uv run python -c "from skills.distill.lib import l1_batch, read_watermark; import json; print(json.dumps(l1_batch(read_watermark())))"` from the framework repo (or the versioned plugin cache with `UV_PROJECT_ENVIRONMENT` redirected, same as /ren:update's convention). Empty batch → report "watermark caught up", stop.
2. **Dedup context.** For each distinct `session` in the batch, collect `landed_pages(session)`.
3. **Mine.** Spawn ONE `ren-distiller` agent (worker-class) with the batch's `escaped_body` texts and the per-session landed sets. Parse its reply as the candidate JSON array. A malformed reply → stop, report, watermark UNTOUCHED.
4. **Classify.** Build one classifier prompt per candidate via `build_classifier_prompt(item, eligible_targets=eligible_update_targets(source_session), project=...)` and spawn ONE classifier-class subagent (batched, same pattern as /ren:wrap step 3) returning an index-keyed JSON verdict array.
5. **Apply.** Assemble `candidates` (lib shape: item/verdict/source_session/project/content=proposed_content/page=None) and call `apply_candidates(candidates, run_session="distill-<date>", batch=batch, watermark_before=read_watermark())`. Print the returned counts; a non-zero `capped_remainder` is reported as "N candidates carried to the next run"; `duplicates` (noop-duplicate replays) is reported separately and never counts against the cap.
6. **Advance the watermark** to `result["watermark_after"]` — ONLY if steps 3-5 completed without an exception AND `watermark_after` is not `None`. The lib computes it: a fully-processed batch (no remainder) advances to the batch's max `ren_ts`; a capped run advances only up to (not past) the earliest L1 belonging to a session with unprocessed candidates, so that session's L1s stay behind the watermark and get re-mined next run (spec §3.4, §3.5). A `None` watermark_after with a non-empty remainder means no advance this run — say so on the report screen. Any exception in steps 3-5 leaves the watermark untouched (re-run safe; the journal dedup makes replays idempotent).
7. **Report.** One screen: batch size, candidates, applied/held/suggested/gated_out/refused/duplicates, capped remainder, new watermark (or "no advance this run" when `watermark_after` is `None`).

## `--seed-tree <project>` flow (Task 7, spec 2026-08-31 §3)

Manual trigger only — see "When to use" above. A single call does the whole
run; there is no separate mine/classify subagent hand-off like the L1 flow
above, because the candidates are already-written lessons, not narrative to
mine, and this mode always has a live `llm_call` to gate them with.

1. **Run.** `seed_tree(project, llm_call, cap=None)` (from `skills.distill.lib`).
2. Internally: loads `projects/<project>/schema.md`'s taxonomy — a missing
   or unparseable schema.md refuses the WHOLE run (`result["blind"]` is set,
   "no taxonomy — run ingest's taxonomy draft first"; run `/ren:ingest-project`
   or hand-seed a taxonomy first). Otherwise it enumerates
   `projects/<project>/knowledge/lessons/*.md` newer than the project's own
   `seed_tree_watermark` (kept separate from the scheduled distiller's
   watermark), gates each lesson body through the LIVE classifier, and for
   every `kind == "concept"` verdict that resolves to a brand-new taxonomy
   leaf: places it via the SAME concept-create machinery `/ren:wrap` uses
   (mints the page, maintains its leaf/parent hubs, additively splices
   `schema.md`), then appends a `See: [[<node>]]` pointer to the source
   lesson. Everything else (already-a-lesson verdicts, non-durable verdicts,
   an invalid concept placement) is skipped — advancing the watermark past
   it, since there is nothing to write for a lesson that's already sitting
   on disk as a lesson.
   **Known limitation:** a concept placement that resolves to an ALREADY-
   EXISTING taxonomy node is also skipped, and the source lesson is left
   un-annotated (`result["existing_node_skipped"]`, distinct from
   `result["gated_out"]`'s classifier-noise cases) — `--seed-tree` does not
   accrete onto existing nodes; that machinery is `/ren:wrap`'s own
   `_concept_node_page` + merge path. Backfilling accretion for this mode
   is future work, not this task's scope.
3. **Report.** Same counter shape as the L1 flow (`applied`/`held`/
   `suggested`/`gated_out`/`refused`/`duplicates`/`capped_remainder`), plus
   `annotated` (the `See:` pointer UPDATEs — these count toward the cap
   exactly like any other write), `existing_node_skipped`, and `blind`.

## What this skill does NOT do

- Write any wiki file directly — apply_candidates (and, for `--seed-tree`,
  the same concept-create machinery `/ren:wrap` uses) are the only write
  paths.
- Advance the watermark on a failed run, or past an unprocessed session's earliest L1 on a capped run.
- Touch quarantine banners, trust stamps, or the backup remote.
- Run `--seed-tree` on a schedule — it is manual-trigger only, never folded
  into the weekly routine.
