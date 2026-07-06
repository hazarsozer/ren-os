# RenOS (仁) 0.2 — "The measured core"

An **Agentic OS**: a knowledge + governance layer that runs on top of coding-agent
harnesses (Claude Code first, Codex read-proven). Two pillars:

- **Memory that compounds** — user-owned plain markdown files every session reads and
  extends, with update/correct/revert semantics (never append-only). A single write
  queue (propose → approve/auto-apply → journal) is the one door every producer writes
  through; provenance and one-step revert make every write accountable.
- **Tokens that aren't wasted** — every injected byte budgeted, cached, or pointed-to.
  Wake-up is heuristic-only (no LLM at session start, by design); a calibrated
  estimator and real cache-token accounting replace guesswork.
- **Autonomy you can trust** — writes gated by risk tier and provenance, not faith.
  Reads are free; a routine's bounded memory writes auto-apply (with provenance +
  one-step revert); durable knowledge and code/config changes are diff-approved;
  destructive actions always ask, and refuse outright with no human present.

**Success bar:** measured pillars, not estimates. Per spec §2: *"if 0.2 ships and the
pillars are still estimates, 0.2 failed."* See "Measured numbers" below for where each
exit criterion actually stands.

## Quick start

```bash
uv sync
uv run pytest
```

Requires Python ≥3.11. No other runtime dependencies to build/test — `pyproject.toml`
pins `python-ulid`, `pyyaml`, `typing-extensions` for the framework itself.

## The skill surface

| Skill | What it's for |
|---|---|
| `/ren:install` | One-time onboarding: bootstrap `~/.renos/wiki`, identity, backup nag |
| `/ren:interview` | The identity + working-style interview (capped, skippable, sane defaults) |
| `/ren:bootstrap-project` <slug> | Start a brand-new project's memory (empty L2 map) |
| `/ren:ingest-project` [path] | Bring an EXISTING repo in as a populated L2 map — the first-session artifact |
| `/ren:pin "<text>"` | Reactive memory: "remember it like THIS" |
| `/ren:pin --wrong <page>` | Reactive correction: "that's wrong, drop it" (or `--instead "<text>"`) |
| `/ren:recall "<query>"` | On-demand L3 fetch — every fetch logged for the honest miss rate |
| `/ren:wrap` | End-of-session consolidation: the fail-closed classifier gate, L1 producer |
| `/ren:remember` | The "what do you remember about this project" first-session-artifact renderer |
| `/ren:queue` / `/ren:approve <qid>` / `/ren:reject <qid> <why>` / `/ren:revert <write_id>` | Review, approve, reject, and undo queued writes |
| `/ren:retrospective [--since <date>]` | Mine instrumentation + journal + session history for lessons, instruction tweaks, and skill candidates |
| `/ren:code-map` | Optional Graphify-backed structural code map (graceful absence if not installed) |
| `/ren:doctor` | Ten isolated health checks — env, wiki structure, frontmatter, schema versions, budget lint, dangling L2 pointers, graphify status, backup config, global-tier drift, harness neutrality |
| `/ren:backup` | Git-push-to-`backup`-remote primary, tarball fallback, retention |
| `/ren:update` | Snapshot → migrate → verify → diff-approve → apply, with rollback built in |
| `/ren:routine-init` | Declare a pre-declared routine/loop — schedule, exit criterion, failure handler, capability/path allowlist |
| `/ren:metric-watch` | The minimal metric-watch routine: budget growth, memory growth, classifier fail-closed events, backup-unconfigured — findings to the journal |

## Architecture at a glance

- **Memory tiers:** L1 (session-scoped, quarantine-bannered until reviewed) → L2 (per-project pointer-map, `projects/<slug>/map.md`) → L3 (on-demand recall, logged) → typed global tier (promotion-gated, never auto-applied).
- **The single write queue** (`lib/memory/queue.py`): every producer (pin, wrap, retrospective, routine, promotion) proposes; `lib/governance/tiers.py` decides `free`/`auto`/`diff_approved`/`ask`; `lib/memory/write_apply.py` is the only function that ever touches a wiki page.
- **Write-safety substrate:** provenance on every write (`lib/memory/provenance.py`), per-write snapshots (`lib/memory/snapshot.py`), an append-only journal (`lib/memory/journal.py`), one-step revert (`lib/memory/revert.py`), file leases against lost updates (`lib/memory/locks.py`).
- **Instrumentation with ground truth** (`lib/instrument/`): real `cache_read_input_tokens` from harness transcripts, a calibrated chars/token estimator, the mechanical L3-miss log — no self-reported numbers anywhere in this list.
- **Harness-neutral knowledge layer:** the wiki's canonical markdown IS the `AGENTS.md` surface (`lib/portability/agents_surface.py`); see [`docs/codex-read-proof.md`](docs/codex-read-proof.md) for the one working proof a foreign harness (Codex) can read it.

The wiki is **Obsidian-vault-compatible** — open `~/.renos/wiki` as a vault for a free knowledge graph. `tests/test_obsidian_invariant.py` pins the invariants that make that true (relative links only, no state-dir leakage into template content, no filename characters Obsidian can't open, no accidental `[[wikilink]]` collisions with the `{{placeholder}}` syntax).

## Measured numbers (spec §2 success bar)

Per spec: *"if 0.2 ships and the pillars are still estimates, 0.2 failed."* Status of each exit criterion as of this commit:

| Exit criterion | Status |
|---|---|
| 1. Real `cache_read_input_tokens` across ≥20 sessions, published | **PENDING** — collection harness (`lib.instrument.collect.harvest_session_usage`) is built and tested; the ≥20-session collection run itself hasn't happened yet (calendar-bound, needs real usage) |
| 2. Injected-context size + per-capability tokens automatic; retrieval hit-rate vs. the frozen fixture + mechanical miss log | **PENDING** — `injected_bytes`/`capability_tokens` recording is live (Task 5.1/3.1); the retrieval-eval fixture scoring (`skills.recall.lib.rank`, already 12/12 against the frozen fixture per Task 4.3's review) still needs the ≥20-session hit-rate computed and published alongside it |
| 3. Token estimator calibrated against the real tokenizer | **PENDING** — `lib.instrument.estimator.calibrate` is built and unit-tested (running average against real `(text, reported_tokens)` samples); it hasn't yet been fed real calibration samples from live sessions |
| 4. The wrap classifier's eval passes and demonstrably gates (fail-closed) | **DONE** — `skills/wrap/lib/classifier.py`'s gate eval proves a crash refuses to durable-promote; see `tests/skills/wrap/test_gate_eval.py` |
| 5. Codex read proof | **DONE** — see [`docs/codex-read-proof.md`](docs/codex-read-proof.md) |
| 6. Friend week (real usage) | **PENDING** — calendar-bound, not a code deliverable |
| 7. Integrity drill (revert, quarantine, lost-update detection under a rehearsed failure) | **DONE** in the test suite; a manual real-world rehearsal log is a separate PENDING artifact |

Nothing in this table is asserted from vibes — every DONE line has a corresponding test file; every PENDING line is either calendar-bound (needs real elapsed usage, not more code) or needs a collection run this repo's tooling already supports but hasn't been pointed at real sessions yet.

## References

- [`docs/data-flow.md`](docs/data-flow.md) — what stays local, what ever reaches a model API, what never does, and the publish-aggregates-only rule
- [`docs/codex-read-proof.md`](docs/codex-read-proof.md) — the harness-neutrality proof (exit criterion 5)
- [`doctrine/companions.md`](doctrine/companions.md) — optional tools (Graphify) that pair well with RenOS; zero required
- `CHANGELOG.md` — what changed and why, release to release

## License

MIT — see `LICENSE`.
