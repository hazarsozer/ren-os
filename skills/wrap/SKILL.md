---
name: wrap
description: |
  Use at session end when the friend wants to consolidate what they learned.
  Triggers on the /sf:wrap slash command. Applies a high-signal-threshold:
  most sessions produce ZERO wiki edits (that is the discipline per ADR-009 —
  routine work doesn't pollute the wiki). When signal exists (decision,
  pattern, lesson, stack change, milestone, purpose shift), updates the
  relevant ADR-014 pages with diffs shown for approval. Always rewrites the
  active project's CONTEXT.md (the next session's wake-up pointer).
  EXPERIMENTAL: the default classifier is a conservative deterministic
  heuristic (ADR-031 bike-method); the LLM path is a future upgrade.
version: 0.1.0
license: MIT

framework_version: 1.0.0
schema_version: 1
type: skill

contract:
  required_outputs:
    - "An updated wiki/projects/<active-project>/CONTEXT.md with the new session pointer"
    - "Zero or more diffs to wiki/projects/<active-project>/{STATE.md,ROADMAP.md,REQUIREMENTS.md,PROJECT.md} when the signal threshold is met"
    - "Zero or more new pages under wiki/projects/<active-project>/{decisions,patterns}/ when signal is decision/pattern grade"
    - "One appended entry in wiki/projects/<active-project>/log.md (always) and master wiki/log.md (only on a non-none signal)"
    - "A brief summary printed to the user covering: pages touched, next-session pointer"
  budgets:
    turns: 10
    files_written: 15
    duration_seconds: 90
  permissions:
    read:
      - "~/.startup-framework/wiki/**"
      - "~/.startup-framework/wiki/.session-notes/**"
      - "skills/sf-wrap/references/**"
    write:
      - "~/.startup-framework/wiki/**"
    execute: []
  completion_conditions:
    - "Either: the classifier returned 'none' → zero wiki edits + CONTEXT.md still rewritten"
    - "Or: the classifier returned a signal → all proposed wiki diffs applied or explicitly rejected by the user + CONTEXT.md rewritten"
    - "User has been shown the summary line"
  output_paths:
    - "~/.startup-framework/wiki/projects/<active-project>/"

tags: [session-end, consolidate, wiki, lifecycle]
related_skills: [sf-note, sf-recall, sf-bootstrap-project]
references_required:
  - "references/signal-threshold.md"
  - "references/wiki-page-mapping.md"
references_on_demand:
  - "references/diff-approval-ui.md"
  - "references/notes-discovery.md"
---

# sf-wrap

End-of-session consolidate. The partner to the wake-up hook (ADR-008): wake-up reads what `/sf:wrap` writes. Per ADR-009 this is a **user-invoked slash command**, NEVER a Stop hook (Ralph collision + claude-mem SessionEnd ordering + the discipline that most sessions are routine and shouldn't pollute the wiki).

Solo-first (ADR-031): `/sf:wrap` consolidates the **local wiki only**. The former Activity Feed session-end entry was removed with the feed module.

> **EXPERIMENTAL (bike-method, ADR-031):** the default signal classifier is a conservative DETERMINISTIC heuristic — it scans the transcript + `/sf:note` pins for deliberate signal phrases, biases HARD to `none`, and never raises. It has no semantic understanding (phrase-driven), so it can miss subtly-phrased signal and rarely over-fire on a keyword used casually. The LLM classifier path (`build_classifier_prompt` + `parse_classifier_output`) ships as primitives for a future upgrade.

## When to use this skill

- Friend invokes `/sf:wrap` (the canonical trigger)
- Friend says any of: "wrap up", "consolidate this", "let's save the learnings", "I'm done for the day" — confirm intent with them once, then run

## When NOT to use this skill

- Mid-session "save my progress" — the friend wants `/sf:note <text>` for that, not a full wrap
- Routine debugging session with no genuine signal — STILL invoke /sf:wrap if the friend asked, but expect ZERO wiki edits beyond the CONTEXT.md refresh. **Do not invent signal to justify wiki writes.** Per ADR-009: "would I want this loaded next session by default? If no, it doesn't go in."

## The pipeline

### Step 1. Gather inputs (read-only)

Sources:
- The session's transcript (Claude Code's record; reachable via the `transcript_path` hook-input field if invoked from a hook, or via `~/.claude/projects/<slug>/*.jsonl` otherwise)
- Any `/sf:note` pins for this session at `~/.startup-framework/wiki/.session-notes/<session-id>.md` (if no session-id available, also check `unsessioned-notes.md`)
- The cwd → determines the active project (or `None` if not in a `~/Dev/<X>/` dir)
- The current state of relevant wiki pages: `wiki/projects/<active>/STATE.md`, `CONTEXT.md`, `ROADMAP.md`, `REQUIREMENTS.md`, `PROJECT.md`, `log.md`, `index.md`

**Token discipline**: don't load PROJECT.md / REQUIREMENTS.md / ROADMAP.md unless the signal classifier (Step 2) signals they may need updates. Lazy-load on demand. Always load CONTEXT.md (you must rewrite it).

### Step 2. Apply the signal-threshold classifier

See `references/signal-threshold.md` for the full criteria. The **default** classifier (`lib/classifier.py:classify()`) is a conservative DETERMINISTIC heuristic (EXPERIMENTAL):

- It scans the combined transcript (session log + `/sf:note` pins) for deliberate, word-boundary signal phrases. **Pins dominate** — a single deliberate keyword in a pin is enough; the raw session log needs a full phrase.
- It biases HARD to `none` and **never raises** (every failure degrades to `none`).
- It proposes `candidate_artifacts` ONLY for fired `decision`/`pattern` (the page-creating labels); other labels (`lesson`/`stack_change`/`milestone`/`purpose_shift`) contribute their label (→ a log append) without a new file.
- It takes **no file-change-count input** by design (that would conflate wiki-maintenance files with project files).

The classifier returns ONE or more of:

- `none` → no signal; no wiki updates
- `decision` → a real architectural/scope decision; new file in `decisions/` + STATE.md update
- `pattern` → a reusable pattern; new file in `patterns/`
- `lesson` → a non-obvious learning ("gotcha"); STATE.md notes or learnings.md
- `stack_change` → tech-stack shift; STATE.md + maybe REQUIREMENTS.md
- `milestone` → roadmap milestone completed; ROADMAP.md
- `purpose_shift` → very rare; project's purpose/scope changed; PROJECT.md

Multi-label is allowed but capped (~2). When in doubt, prefer `none`. The wiki is sacred; the default is to not touch it.

### Step 3. Compose the diff plan

Use `references/wiki-page-mapping.md` to translate signal-label(s) → list of `(file_path, proposed_diff)` pairs. Diffs are unified-format text (compatible with `git apply --check` for verification).

**CONTEXT.md is always in the diff plan** (the session pointer is rewritten every wrap). Other pages only if signal warrants.

### Step 4. Show diffs for user approval

For each proposed diff, show the user:
- The target file path
- The proposed diff (with syntax highlighting if the host renders markdown nicely)
- Y/N/E[dit]/A[ll-yes] options

`--autonomous` flag (rare; not in V1) would skip this and apply all. **V1 default: ALWAYS prompt.**

### Step 5. Apply approved diffs atomically + close out

Use `git restore` checkpoint before any wiki write. If any single approved diff fails to apply cleanly:
1. Roll back ALL wiki writes from this wrap (`git restore wiki/`)
2. Surface the would-have-been diffs to the user with the failure cause
3. Tell the user how to retry

On success, append the one-line entry to `wiki/projects/<active>/log.md` (always) AND to the master `wiki/log.md` (only on a non-none signal). The chronological-invariant per ADR-004 must be preserved.

Print the final summary to the user:
```
/sf:wrap complete.
  Wiki: <N> pages updated (or "no signal; CONTEXT.md refreshed only")
  Next-session pointer (CONTEXT.md): "<first 100 chars>..."
```

## What `/sf:wrap` explicitly DOES NOT do

- Run automatically. Invoked by the user only.
- Block session exit. After it completes, the session can continue or end.
- Compete with claude-mem's SessionEnd capture (different layer; per ADR-002 + ADR-009).
- Modify CLAUDE.md (that's `/revise-claude-md`'s job per the claude-md-management plugin; see ADR-009 §"Coexistence with `/revise-claude-md`").
- Edit settings.json or any system-prompt-cached layer (per ADR-008 discipline).
- Promote routine debugging or coding to the wiki. The high-signal threshold is the discipline.

## Failure-degradation modes (per lifecycle plan §5)

| Failure | Behavior | User-visible |
|---|---|---|
| Session transcript unreadable | Treat as empty transcript → classifier returns `none` | "No session log found; CONTEXT.md refreshed only" |
| Classifier returns nothing (`none`) | Zero wiki edits beyond CONTEXT.md | "No wiki changes; CONTEXT.md refreshed" |
| Wiki write mid-batch fails | `git restore wiki/` rollback; show would-have-been diff | Retry instructions |

## Implementation note

V1 implementation lives in `skills/sf-wrap/lib/`. The default classifier (`lib/classifier.py:classify()`) is a conservative DETERMINISTIC heuristic — **EXPERIMENTAL** (ADR-031 bike-method): phrase-driven with a hard bias to `none`, never raises. `build_classifier_prompt()` + `parse_classifier_output()` ship as composable primitives for the future LLM classifier path; they are unit-tested but not wired into the default path.

The criteria the classifier encodes live in `references/signal-threshold.md`.

## References

- ADR-004 (Wiki Design Hierarchical) — directory shape we write
- ADR-008 (Wake-Up Hook) — the partner; CONTEXT.md is the handoff artifact
- ADR-009 (Consolidate via /wrap) — this skill's design rationale + non-Stop-hook decision
- ADR-014 (Project Sub-Wiki Taxonomy) — page mapping for diff plans
- ADR-031 (Solo-First Pivot) — Activity Feed removal; deterministic classifier as the EXPERIMENTAL default
- `references/signal-threshold.md` — the classifier criteria
- `references/wiki-page-mapping.md` — signal-label → diff-plan mapping
