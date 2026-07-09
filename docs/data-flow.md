# Data flow (council A-7)

What stays on this machine, what ever reaches a model API, and what never does — one page, kept current as the source of truth for §3.5/§3.6 governance and the risk-tier gate (`lib/governance/tiers.py`).

## Stays local, always

- The wiki itself: every page under `wiki/` (identity, decisions, patterns, research, project L1/L2 pages).
- The write-safety substrate: `wiki/.ren/journal.jsonl`, `wiki/.ren/snapshots/`, `wiki/.ren/queue/*.json`, `wiki/.ren/locks/`.
- Instrumentation: `wiki/.ren/metrics/*.jsonl` (every `KIND_*` metric — injected bytes, cache-read tokens, L3 fetches, wake-up surfaces, capability/code-map tokens, classifier events), `wiki/.ren/metrics/estimator.json`.
- Derived, regenerable artifacts: the code-map cache (`plugin_data_dir()/code-maps/`).
- Session transcripts (`~/.claude/projects/**/*.jsonl`) — read by `lib.instrument.collect.harvest_session_usage` for ground-truth token accounting, never written, never forwarded anywhere.

None of the above is ever transmitted anywhere by this framework. Backup (`/ren:backup`) pushes the wiki to a **user-controlled private remote** — that's the friend's own infrastructure choice, not a framework-operated data flow, and is out of scope for this statement.

## Sent to a model API — and exactly when

There are exactly two classes of moment this happens, and neither is at session start:

- **`/ren:wrap` time** — the session's own model (whatever the friend is already talking to) reasons over the session's wrap-candidate content (narrative + durable-write candidates) to classify each candidate via the fail-closed gate (`skills/wrap/lib/classifier.py`). This is the SAME model instance already in the conversation — not a second API call to a different service.
- **The classifier gate itself**, when an `llm_call` is supplied, sends the candidate item's text for a durable/session-only/discard verdict.
- **Ingest and retrospective worker subagents** — `/ren:ingest-project` and the
  retrospective flow dispatch session-local subagent workers (see
  `doctrine/agent-orchestration.md`) that read repo docs or session transcripts
  and draft wiki content. Same model account the session already uses; the
  drafted content then goes through the same scrub-gated write queue as
  everything else.

That's the entire list. No background jobs, no separate service, no telemetry endpoint.

## NEVER sent, under any circumstance

- **No LLM call at session start.** Wake-up (`hooks/wake-up/`) is pure heuristic ranking (token overlap + recency + path hints) and local file reads — unanimous council decision, and the reason `tests/hooks/test_wakeup.py` includes an explicit no-LLM/no-network source scan.
- **Raw metrics files.** `wiki/.ren/metrics/*.jsonl` is read locally by `lib.instrument.collect`/`estimator`/`miss_log` to compute rates and calibration; the raw JSONL itself is never uploaded or forwarded.
- **The journal, as a file.** Provenance records are read locally (by revert, doctor, the retrieval-eval harness); the journal file itself never leaves the machine.
- **Transcripts, as files.** `harvest_session_usage` reads `~/.claude/projects/**/*.jsonl` locally to sum real token counts; the transcript file is never transmitted — only the four integers it derives (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`) ever leave that function, and even those stay local (recorded via `collect.record`, not sent anywhere).

## The publishing rule

**No transcript content in published numbers.** When cache-preservation results, hit-rates, or any other measured number from this instrumentation surface is published (a README section, an exit-criteria report), it is an **aggregate only** — a count, a rate, a mean — never a quoted transcript line, never a raw metrics-file dump, never a per-session breakdown small enough to re-identify what was discussed. This is the same discipline `scrub`/quarantine apply to wiki content, applied to the measurement surface itself.

## Classifier-event preview redaction (defense-in-depth)

`skills/wrap/lib/classifier.py`'s `gate()` records a `classifier_event` metric (`KIND_CLASSIFIER_EVENT`) whenever it falls back to the deterministic path (`fail_closed` or `no_llm`), including a short `item_preview` of the candidate text for debuggability. Since the metrics surface is itself part of this data-flow statement (local-only, but still a surface a doctor/eval script reads), that preview is scanned with `lib.memory.scrub.scan` before being recorded — if the candidate text looks secret-shaped, the preview is replaced with the literal string `"<redacted: secret-shaped content>"` instead of a truncated excerpt. This is defense-in-depth: the candidate text was already supposed to be scrubbed upstream, but the instrumentation surface doesn't trust that and re-checks at its own write path.

## Cross-references

- `lib/governance/tiers.py` (Task 6.1; pivoted to the two-plane model in v2.2, spec §10) — the risk-tier gate this statement's "what requires a human" boundary maps onto: `auto` = any non-global memory write (the data plane — every writer, including unattended ones), auto-applied but always provenance-tagged, snapshotted, and one-step revertible; `diff_approved` = `global/` pages (the instruction plane — promotion, human, and conversational alike) plus all code/config writes, queued for a human diff review; `ask` = destructive actions, always an explicit human ask, flatly refused (never downgraded) when unattended. Contradictions are model-resolved with recorded reasoning, not queued for a human.
- `lib/instrument/collect.py` (Task 3.1) — the metrics surface this statement's "stays local" section describes
- `skills/wrap/lib/classifier.py` (exit criterion 4) — the one place an LLM call happens outside the session's own conversation turn
- `hooks/wake-up/wakeup/__init__.py` (Task 5.1) — the no-LLM-at-session-start invariant

## Guard failure posture (Task 9.3 ruling)

The PreToolUse guards (`hooks/guards/pre_push_scan.py`, `write_gate.py`) fail
**open** on internal error: a guard that crashes allows the tool call through
with a warning rather than blocking. This is deliberate — a buggy guard that
exited non-zero on every call would brick the entire harness for a
non-technical friend, which is a worse failure than the narrow window an
internal guard error opens. The compensating control is `/ren:doctor`'s
`guard_health` check: it exercises every guard with a safe synthetic payload
and WARNS "guard degraded — investigate before relying on enforcement" the
moment a guard stops answering healthily. The queue/write-substrate itself
remains fail-closed (scrub refusals, classifier fallback never writes durable)
— fail-open is scoped to the hook layer only.
