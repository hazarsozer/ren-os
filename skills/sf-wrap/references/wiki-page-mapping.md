---
title: "/sf:wrap signal-label → wiki-page diff-plan mapping"
type: skill-reference
parent_skill: sf-wrap
version: 0.1.0
date: 2026-05-28
---

# Signal label → wiki page diff plan

Translates the 7 labels from `signal-threshold.md` into concrete `(file_path, proposed_diff)` pairs per ADR-014's taxonomy.

## Always (regardless of label)

| File | Action |
|---|---|
| `wiki/projects/<active>/CONTEXT.md` | **REWRITE** the entire file with the new session pointer (paragraph + open questions). Always. This is the wake-up hook's read target for next session. |
| `wiki/projects/<active>/log.md` | **APPEND** one line: `## [YYYY-MM-DD HH:MM] <label-or-"routine"> | <one-sentence-summary>` (chronological invariant per ADR-004). |
| `wiki/log.md` (master) | **APPEND** one line **only if** any label other than `none` fired. Routine sessions don't get master-log entries. |

## Per-label mapping

### `decision`

| File | Action |
|---|---|
| `wiki/projects/<active>/decisions/<slug>.md` | **CREATE** new file with full ADR-style frontmatter (per ADR-011 schema) + decision body. Use `framework_version: 1.0.0`, `schema_version: 1`, `type: decision`, `status: accepted`, `date: <today>`. |
| `wiki/projects/<active>/STATE.md` | **APPEND** to "Recent decisions" section: `- [<slug>](decisions/<slug>.md) — <one-line>` |
| `wiki/projects/<active>/index.md` | **APPEND** to decisions catalog if not already present |

### `pattern`

| File | Action |
|---|---|
| `wiki/projects/<active>/patterns/<slug>.md` (project-scoped) OR `wiki/patterns/<slug>.md` (cross-project) | **CREATE** new file with `type: pattern` frontmatter + body. Decide project-vs-master scope per ADR-004: "lean toward master for synthesis ('the auth pattern'), project for instance ('Sidecar's auth implementation')." |
| `wiki/projects/<active>/STATE.md` | **APPEND** to "Recent learnings" if project-scoped pattern |
| `wiki/projects/<active>/index.md` | **APPEND** to patterns catalog |

### `lesson`

| File | Action |
|---|---|
| `wiki/projects/<active>/STATE.md` | **APPEND** to "Recent learnings" section: `- <one paragraph including specific reproduction context>` |
| `skills/<related-skill>/learnings.md` (per ADR-011 optional pattern) | **APPEND** if the lesson is specific to a Claude Code skill or tooling quirk (not a domain lesson) |

No new files for `lesson` unless it warrants a full pattern page (in which case re-label as `pattern`).

### `stack_change`

| File | Action |
|---|---|
| `wiki/projects/<active>/STATE.md` | **EDIT** the "Active work" section to reflect new stack components |
| `wiki/projects/<active>/REQUIREMENTS.md` | **EDIT** non-functional section IF the stack change affects runtime topology, deployment surface, or operational constraints. Otherwise skip. |
| `wiki/projects/<active>/ROADMAP.md` | **EDIT** "we are here" marker IF the stack change advances or rewinds a phase |

### `milestone`

| File | Action |
|---|---|
| `wiki/projects/<active>/ROADMAP.md` | **EDIT** check the completed milestone's box; move "we are here" marker; add the next milestone in line if needed |
| `wiki/projects/<active>/STATE.md` | **EDIT** the "Active work" section to reflect the new active items for the next phase |

### `purpose_shift`

| File | Action |
|---|---|
| `wiki/projects/<active>/PROJECT.md` | **EDIT** the purpose paragraph (and possibly target-users / success-criteria sections). Show the diff prominently; this is a rare event and the user will want to confirm carefully. |
| `wiki/projects/<active>/REQUIREMENTS.md` | **EDIT** if the purpose shift implies scope changes |
| `wiki/projects/<active>/ROADMAP.md` | **EDIT** if the new purpose requires roadmap rework |

### `none`

| File | Action |
|---|---|
| (nothing in the wiki) | — |

CONTEXT.md still rewrites, log.md still appends "routine" entry, master log skipped.

## Active project resolution

The "active project" is determined by cwd:
- If `cwd` is `~/Dev/<X>/` (or any subdirectory thereof) AND `wiki/projects/<X>/` exists → active = X
- If `cwd` doesn't match → active = None

When active = None:
- Project-scoped writes are skipped
- Decisions/patterns may still go to master `wiki/decisions/` or `wiki/patterns/` if cross-project
- The terse-feed entry uses `project=None` (renders as "unscoped" per the format spec)

## Diff format

All proposed diffs are **unified diff format** (compatible with `git apply --check` for verification before application). Generated via Python's `difflib.unified_diff()` or equivalent. Example:

```diff
--- a/wiki/projects/sidecar/STATE.md
+++ b/wiki/projects/sidecar/STATE.md
@@ -10,6 +10,9 @@
 ## Recent decisions
 
+- [auth-magic-link-only](decisions/auth-magic-link-only.md) — Dropped OAuth for V1 (2026-05-28)
+
 ## Recent learnings
```

## Atomicity

All approved diffs in a wrap are applied as a single atomic batch:
1. `git restore` checkpoint of `wiki/` before any write
2. Apply diffs one by one
3. If ANY application fails → `git restore wiki/` rollback; surface error to user; abort feed write
4. If ALL succeed → commit (if friend has `wiki/` as a git repo per ADR-026) OR leave uncommitted (per friend preference)

The atomicity guarantee means the wiki never ends up in a half-updated state. Important because the wake-up hook reads from the wiki the next session — partial writes would degrade context quality.
