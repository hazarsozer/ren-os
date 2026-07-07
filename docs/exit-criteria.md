# RenOS 0.2 — Exit Criteria Report

**Date:** 2026-07-06 · **Spec:** scope v2.1 §4 ("0.2 — The measured core")
**Build:** green-field harvest per the 2026-07-06 implementation plan; two Sonnet builders + orchestrator review per task; adversarial holistic review (verdict SHIP-WITH-FIXES, both blockers fixed and re-verified).

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Cache-preservation experiment run: real `cache_read_input_tokens` across ≥20 sessions, published in the README | **STARTED / PENDING-CALENDAR** | Collector shipped (`lib/instrument/collect.harvest_session_usage`, fixture-verified against the real transcript shape). Needs ≥20 real sessions of dogfooding — cannot be compressed. README's Measured Numbers table carries the PENDING marker. |
| 2 | Injected-context size + per-capability tokens collected automatically; retrieval hit-rate computed against the frozen fixture + mechanical miss log | **DONE (machinery) / collection ongoing** | `injected_bytes` recorded by the wake-up hook on every session; `l3_fetch`/`wakeup_surface` join gives the mechanical miss rate (`lib/instrument/miss_log.misses`). Retrieval hit-rate vs frozen fixture: **12/12** for the shipped ranker (`tests/evalkit` + orchestrator cross-check). |
| 3 | Token estimator calibrated against the real tokenizer | **DONE (machinery) / needs real samples** | `lib/instrument/estimator.calibrate` blends real (text, reported_tokens) pairs; math fixture-verified. First real calibration happens as session usage accrues. |
| 4 | Wrap classifier's eval passes and demonstrably gates (incl. fail-closed) before shipping as the write gate | **DONE** | `tests/skills/wrap/test_gate_eval.py`: 12/12 with a correct LLM stub; crashing LLM → every accept-case fails, every refuse-case passes, fail_closed events recorded. Deterministic fallback can never return "durable". Runs in CI. |
| 5 | Codex reads a project's context from the canonical files | **DONE — demonstrated live** | codex-cli 0.139.0 (gpt-5.5) oriented from `AGENTS.md` alone, cited the L2 map, both decision pages, and global preferences correctly. `docs/codex-read-proof.md` + transcript. Harness-neutrality lint: zero offenders on generated surfaces. |
| 6 | A friend can install → onboard (≤ budget) → see the first-session artifact → work a week → update, without the founder | **MACHINE PATH DONE / PENDING-CALENDAR (real friend)** | `tests/integration/test_friend_week.py`: full 7-day story over public surfaces only (install, partial interview, ingest + artifact, pin/recall/wake-up, wrap + screen, correction, retrospective, revert, update, doctor) — green in CI. The real friend-week needs a real friend and a real week. |
| 7 | Memory integrity drill: bad write found (provenance), reverted (targeted), downstream flagged — end-to-end | **DONE** | `tests/integration/test_integrity_drill.py`: llm-auto bad write found by writer-class journal filter, reverted (ADD deleted / UPDATE restored byte-exact), citers flagged, history not rewritten, no wedged locks. Runs in CI. Founding pages are also journaled/revertible after review FIX 1. |

## Review record (2026-07-06)

Adversarial holistic pass by the builder that did NOT write each half. Findings: 1 CRITICAL (wiki bootstrap bypassed the write substrate — **fixed**: `stamp_skeleton` routes through `apply_write` with human provenance; founding pages journaled + revertible), 1 HIGH (raw recall queries in metrics — **fixed**: scrub-guard redaction, third instance of the pattern), 1 policy tension (guards fail open — **ruled**: kept, documented in `docs/data-flow.md`, compensated by the `check_guard_health` doctor check), 1 accepted limitation (ULID ordering across concurrent processes — documented in `lib/memory/queue.py`). Earlier in-build catches: classifier-preview secret redaction; wrap Refused-section secret leak (caught by the builder's own TDD).

## Honest summary

Everything buildable is built, tested, and demonstrated. Two criteria are calendar-bound by design (1 and the human half of 6) — they START now, with the machinery already collecting. Per spec §2, the README publishes PENDING markers instead of estimates.
