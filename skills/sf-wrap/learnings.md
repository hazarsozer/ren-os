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

- The signal-threshold classifier is the load-bearing intelligence. It's a structured prompt the LLM evaluates against the session transcript. **Bias toward `none`** is the core discipline.
- CONTEXT.md is **always** rewritten — even on routine sessions. This is the next session's wake-up pointer and must reflect the latest state regardless of signal level.
- Feed entry is written on routine sessions too (just timestamp + project + files), but classifier may decide `none` for wiki updates. Two-channel design: feed = "what happened" (cross-friend visibility), wiki = "what we learned" (deliberate knowledge curation).
- The 7-label set may evolve. Watch for clusters that consistently miscarry (e.g., if "lesson" is being conflated with "pattern" by the classifier). Add labels via amendment to `references/signal-threshold.md`.
