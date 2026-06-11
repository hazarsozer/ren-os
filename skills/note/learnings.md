---
title: "sf-note learnings"
type: skill-learnings
parent_skill: sf-note
version: 0.1.0
date: 2026-05-28
---

# sf-note — learnings

## Open log

### 2026-05-28 — Initial design notes

- Defensive session-id sanitization: only `[a-zA-Z0-9_-]` allowed; everything else falls back to unsessioned-notes.md. Closes a path-traversal vector at zero cost — file is local-only so the actual harm is small, but the cost of safety is also small. Belt-and-suspenders.
- Multi-line text escaped via `\n` literal substitution rather than raw newlines: preserves the "one bullet per pin" invariant so `/ren:wrap`'s parser doesn't have to handle multi-line bullets.
- Per ADR-021 distinction: notes are LOCAL (not Activity Feed). No format-shape privacy filter applies. The friend writes whatever helps them remember; format constraint is only the Activity Feed surface.

## Related artifacts

- ADR-009 (Consolidate via /wrap) — this skill is the companion `/ren:note` named there
- `skills/sf-wrap/SKILL.md` § "Step 1. Gather inputs" — consumes these notes during wrap
- `skills/sf-recall/SKILL.md` — for reading back via wiki-grep (notes files included in the grep scope)
