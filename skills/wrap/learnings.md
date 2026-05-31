---
title: "sf-wrap learnings (per-skill feedback log)"
type: skill-learnings
parent_skill: sf-wrap
version: 0.1.0
date: 2026-05-28
---

# sf-wrap — learnings

Per ADR-011's optional pattern: this file accumulates lessons learned during the skill's evolution. The `/sf:improve-skill` loop (ADR-012) appends here when it discovers patterns (e.g., "this skill consistently fails on assertion X because instruction Y is ambiguous"). Friends running `/sf:wrap` normally don't see this file unless something surfaces a related issue.

## Open log

*(populated as the skill is used and improved)*

## Initial design notes (2026-05-28, lifecycle-2)

- The signal-threshold classifier is the load-bearing intelligence. The DEFAULT (ADR-031) is a conservative DETERMINISTIC heuristic — EXPERIMENTAL (bike-method): it scans the transcript + `/sf:note` pins for deliberate signal phrases, biases hard to `none`, and never raises. The LLM-prompt path (`build_classifier_prompt`/`parse_classifier_output`) ships as primitives for a future upgrade. **Bias toward `none`** is the core discipline.
- CONTEXT.md is **always** rewritten — even on routine sessions. This is the next session's wake-up pointer and must reflect the latest state regardless of signal level.
- Solo-first (ADR-031): there is no Activity Feed write. `/sf:wrap` is a single channel — the local wiki ("what we learned", deliberate knowledge curation). Routine sessions land at `none` and touch only CONTEXT.md.
- The 7-label set may evolve. Watch for clusters that consistently miscarry (e.g., if "lesson" is being conflated with "pattern" by the classifier). Add labels via amendment to `references/signal-threshold.md`.
