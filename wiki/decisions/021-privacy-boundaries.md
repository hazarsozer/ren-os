---
title: "ADR-021: Privacy Boundaries — Terse Format Constraint + Local Default + --skip-feed Override"
status: superseded
superseded-by: "ADR-031 (2026-05-30): solo-first pivot — the Activity Feed (whose privacy this ADR governed) is removed"
date: 2026-05-28
sunset-review: 2026-11-28
references-pages: [claude-mem, ecc-everything-claude-code, team-coordination-survey]
affects-components: [activity-feed, consolidate, wiki, install]
relates-to: [017-per-friend-wiki-scope, 018-activity-feed, 009-consolidate-via-wrap]
amends:
  - "ADR-018 (specifies the structured terse format for Activity Feed entries)"
---

# ADR-021: Privacy Boundaries

> ⚠️ **SUPERSEDED by [ADR-031](031-solo-first-pivot.md) (2026-05-30).** These privacy boundaries governed the Activity Feed (the terse-format constraint, `--skip-feed`, local default). The feed is removed in the solo-first pivot, so there is no cross-user surface to govern — the wiki is local-only by construction. Preserved for history (and in the `baseline-v1.0-full-wiki` tag). Nate Herk's "keys ≠ instructions" framing (cited in ADR-031) carries the spirit forward as the read-only permission audit.

## Context

ADR-017 establishes per-friend wikis are local-private. ADR-018 establishes the Activity Feed as the only place cross-friend content flows (auto via session-start + `/sf:wrap`). That left open questions:

- Could sensitive content leak via the auto-generated summaries?
- Should we add secret-scanning, diff-review, `<private>` tags as safety nets?

The user clarified the load-bearing answer: **Activity Feed session-close summaries are deliberately terse (couple sentences) and structured (only project/task/files)**. The format constraint itself does most of the privacy work. Comprehensive safety nets are overkill given the format.

This ADR codifies that approach.

## Decision

### The format constraint is the privacy mechanism

Activity Feed session-close entries follow a strict format:

```markdown
## [<timestamp>] end | <handle> | session complete

Worked on <project-or-dir> — <task brief (1-2 sentences)>.
Touched: <comma-separated file list>.
```

**The summary is bounded**: only contains project/directory + brief task description + file paths. The consolidate skill is prompted to produce exactly this shape — no code snippets, no decision details, no quoted reasoning, no commentary on others.

Session-start entries are similarly minimal:

```markdown
## [<timestamp>] start | <handle> | working in <dir>
```

(One line; no body.)

### `/sf:wrap --skip-feed` for entirely-private sessions

Friends can wrap a session without pushing anything to the Activity Feed:

```
/sf:wrap --skip-feed
```

Behavior:
- Wiki consolidation runs normally (local wiki updates per ADR-009)
- NO entry is written to `<handle>.log.md`
- NO commit to Activity Feed repo
- NO push to GitHub
- Other friends won't see this session happened (their next pull won't include it)

Use cases:
- Sensitive work (stealth project, confidential client, personal reflection session)
- Throwaway exploration the friend doesn't want to surface
- Test runs

The `--skip-feed` flag is meant for occasional use, not as a workaround for poor format constraints. If a friend finds themselves using `--skip-feed` most of the time, that's a signal the format constraint needs revision (raise via amendment).

### Session-start entries are pushed automatically; `--skip-feed-start` available

The session-start entry posts on SessionStart hook firing. If a friend knows in advance the session will be sensitive:

```
# at the start of a session, before doing anything:
/sf:disable-feed         # Skip this session's start + end entries entirely
```

Or set an environment variable for one-time skip:

```
SF_SKIP_FEED=1 claude
```

These prevent the SessionStart hook from posting the "active" entry.

### `<private>` tag — separate concept, for local AI behavior

The `<private>` tag (borrowed from claude-mem's pattern) is preserved in the framework but for a **different purpose** than Activity Feed protection:

- `<private>...</private>` content in wiki pages (e.g., identity.md, personal notes) signals to the friend's own Claude that this content shouldn't be surfaced in conversation outputs or auto-summaries
- It's NOT about Activity Feed (the format constraint handles that)
- It's about preventing the friend's local AI from quoting personal reflections, sensitive identity fields, etc.

The wake-up hook (per ADR-008) and consolidate skill (per ADR-009) honor `<private>` tags by:
- Loading the wrapping context but treating the inner content as no-quote / no-surface
- Excluding the tagged content from any output the friend might share

Implementation: simple regex strip in any content destined for output. Per-plugin (claude-mem, Context Mode) respect to `<private>` tags is the plugin's responsibility — we can't enforce it across plugins; we document the convention.

### Deletion is hard — document the procedure

Git history preserves Activity Feed content. Removing something truly requires:

1. `git filter-repo` or BFG to rewrite history removing the file
2. Force push to the Activity Feed repo
3. **All other friends must re-clone** (their local clones will conflict)

This is destructive and disruptive. Document in framework README + onboarding:

> "What gets pushed to Activity Feed, stays — git history preserves everything. If you accidentally push something that must be removed: contact the group via WhatsApp/Discord, coordinate a history-rewrite + force-push, expect everyone to re-clone. Prevention is much cheaper: use `/sf:wrap --skip-feed` for sensitive sessions, manually edit the auto-summary before push, or just don't wrap sessions you don't want recorded."

### No framework-level secret scanning in v1

We don't ship a secret scanner because:

- The Activity Feed format doesn't include code → secrets wouldn't appear in auto-generated entries
- The friend's local wiki / claude-mem / Context Mode are private (no leak vector to scan)
- A scanner would add complexity for a use case the format constraint already prevents
- ECC's AgentShield (per ecosystem research) covers this if a friend wants comprehensive scanning — recommend as a per-project conditional plugin

Trade-off accepted: if a friend explicitly pastes a secret into the Activity Feed (e.g., they manually edit a summary to include code with an API key), the framework doesn't catch it. That's a "don't do that" situation; secret scanning would be patching around a workflow violation the friend chose to make.

### File path leakage trade-off

Even terse summaries include file paths. A friend working on a directory whose name is sensitive (e.g., `Dev/stealth-acquisition/`) WILL surface that directory name in their auto-generated entries.

Mitigation options for the friend (no framework support needed):
- `--skip-feed` for the whole session
- Rename the local directory to something innocuous before working
- Manually edit the auto-summary before it's pushed

Document the trade-off; don't try to solve it at the framework level (would require directory-name-redaction which is overengineered).

### What the framework provides + what the friend owns

| Privacy concern | Framework provides | Friend owns |
|---|---|---|
| Terse Activity Feed format | Strict format spec; consolidate skill enforces | — |
| Skip a session from feed | `--skip-feed` flag; `SF_SKIP_FEED=1` env var; `/sf:disable-feed` command | Deciding when to use them |
| Local-only wiki content | Wikis stay on disk; no auto-push | — |
| `<private>` tag for local AI behavior | Honored by wake-up + consolidate | Tagging their own content |
| Secret in wiki | claude-mem handles per its design (per-friend local) | Not pasting secrets into Claude in the first place |
| Deletion from Activity Feed | Documented procedure (git filter-repo) | Coordinating with other friends |
| File path / project name sensitivity | `--skip-feed` flag | Choosing what to feed in vs. skip |
| Comprehensive secret scanning | Not in v1; recommend Aikido / ECC AgentShield as optional add-ons | Installing if desired |

## Consequences

**Easier:**
- Privacy is mostly automatic via format constraint
- No friction from diff-review or secret-scanning on every wrap
- `--skip-feed` gives explicit opt-out for sensitive cases
- `<private>` tag stays useful for the friend's own AI behavior, separated from the Activity Feed concern
- Honest documentation: friends know exactly what's shared and what's local

**Harder:**
- Friend must remember to use `--skip-feed` proactively for sensitive sessions (can't undo after-the-fact without git rewrite)
- File path / project name leakage trade-off requires friend awareness
- If consolidate skill's format-constraint enforcement drifts (e.g., a future LLM ignores the prompt template), summaries could become longer + leak more → format constraint must be verified on each release (per ADR-019 + ADR-012 binary assertions)

**Now impossible:**
- Accidentally pushing 50 lines of code to the Activity Feed via auto-summary (format prevents it)
- A silent secret leak through normal session activity (only possible if friend explicitly pastes a secret into a summary or commits one to wiki manually)

**Sunset review trigger conditions:**
- Friends report sensitive content leaking despite the format constraint → tighten format spec or add scanner
- `--skip-feed` becomes commonly used (>50% of sessions) → format constraint is broken; revise
- A friend's project requires comprehensive secret scanning (e.g., they work with real production secrets) → add Aikido/AgentShield as recommended

## Alternatives considered

### A) Diff-review default with `--no-review` opt-out

**Considered shape**: `/sf:wrap` shows the auto-generated entry as a diff; user approves before push.

**Why rejected per user direction**: Adds friction every wrap. The terse format constraint does enough work that constant review is overkill. Friends who want extra paranoia can `--skip-feed` and write their own entry manually.

### B) Framework-level secret scanner

**Considered shape**: Ship a 14-pattern regex scanner that blocks pushes containing common secret patterns (API keys, tokens, AWS credentials, etc.). Inspired by ECC's AgentShield.

**Why rejected per user direction**: The format constraint prevents code/secrets from appearing in auto-summaries. Scanning adds complexity for a use case the format prevents. Friends who need scanning for other reasons (their own code, projects with real secrets) can add Aikido / ECC AgentShield as per-project plugins.

### C) Per-content `<private>` tag protects Activity Feed too

**Considered shape**: `<private>` tag in wiki content marks it as "never surface in Activity Feed."

**Why rejected**: Conflates two concerns. `<private>` is for local-AI behavior; Activity Feed protection is `--skip-feed`. Keeping them separate gives friends clearer mental model.

### D) Always-on diff-review with no opt-out

**Considered shape**: Force review on every wrap regardless.

**Why rejected**: Severe friction. Most sessions are routine and the format constraint covers them. Forcing review = friends start avoiding `/sf:wrap` (the framework's worst possible outcome).

## Open questions for implementation phase

1. **How does `--skip-feed` interact with claude-mem's own SessionEnd hook?** claude-mem's auto-capture happens regardless of our consolidate skill. If a session is sensitive, the friend might want to suppress claude-mem capture too (e.g., a `/claude-mem:disable-capture` if they expose one). Out of scope for ADR-021; flag as concern.

2. **Auto-summary format enforcement** — how to ensure the consolidate skill actually produces the terse format and doesn't drift? Per ADR-011 + ADR-012, the consolidate skill has eval/eval.json with binary assertions; should include assertions like "Activity Feed entry is under 200 characters", "Activity Feed entry contains no triple-backtick code blocks", "Activity Feed entry mentions at least one file or directory."

3. **What if the auto-summary draft is too long and the friend doesn't notice?** Two mitigation paths: (a) hard-cap the summary in code (truncate at 300 chars), (b) show a brief preview in the conversation before push so the friend sees it. Implementation detail.

4. **Coordinating deletion** — should the framework provide a `/sf:scrub-feed <commit-hash>` skill that walks friends through coordinated history rewriting? Probably overkill; document the manual procedure instead.

## References

- `wiki/research/claude-mem.md` — `<private>` tag pattern (we borrow for local-AI behavior, not Activity Feed protection)
- `wiki/research/ecc-everything-claude-code.md` — ECC's AgentShield 14-pattern secret scanning (recommend as optional add-on, not framework-level)
- `wiki/research/team-coordination-survey.md` — original team-coord framing where privacy was a bigger concern (this ADR shows why the simpler design has simpler privacy story)
- ADR-009 (Consolidate via /wrap) — `--skip-feed` flag lives here
- ADR-018 (Activity Feed) — format spec from this ADR amends ADR-018
- ADR-017 (Per-Friend Wiki Scope) — local-by-default principle this ADR implements concretely
