# Public Summary Format — `<feed>/identities/<handle>.md`

The public-facing subset of the friend's identity. Lives in the Activity Feed at `~/.startup-framework/activity-feed/identities/<handle>.md`. Written via `feed.upsert_identity(handle, public_identity_md)`.

Per plan §3 (cross-team-ratified) + my answer to feed-2's contract — sf-onboarding owns the rendering; sf-feed owns the commit/push mechanics and the canonical path.

## What's in the public summary

YAML frontmatter — strict subset of local identity.md fields:

```yaml
---
handle: <handle>
name: "<Display Name>"
phase: <phase>
strong_skills: [...]
clouds: [...]
contact:                       # whole block omitted if neither field below is set
  timezone: "<IANA tz>"        # included only if set in local identity
  working_hours: "<text>"      # included only if set in local identity (per feed-2's catch-up ask)
---
```

Markdown body — short, scannable. One bold "Phase" line up top for at-a-glance browsing in the feed's `identities/` directory; then two paragraphs:

```markdown
# <handle>

**Phase:** <phase>

<one-paragraph intro — verbatim from Q2 of the interview>

## What I contribute

<one-paragraph contribution — verbatim from Q18>
```

The bold `**Phase:** <phase>` line is a feed-2 editorial accept: friends browsing `identities/` by hand should see phase without re-reading frontmatter. The line is omitted if phase is `other` (uninformative).

## What's NOT in the public summary

Per ADR-017's privacy-by-default + plan §3:

- `package_managers`, `databases`, `languages` — these are technical preferences that friends often want privatekept (or only narrate selectively). The friend can edit the public file to add them if they wish.
- `working_style`, `communication_style`, `plans_before_code`, `tdd_attitude` — preferences about how the friend wants their *own* AI to behave. No reason for other friends to see them.
- `growth_areas` — sensitive; "I want to grow at X" is a vulnerability the friend may or may not want to share.
- `contact.working_hours` — included **conditionally** in v1: if the friend provided a value at Q9 (the field is non-empty), it's included; if Q9 was skipped or left blank, the field is omitted. No separate opt-in prompt — the act of filling Q9 is the opt-in. (Earlier draft of this doc required a separate yes/no; that was dropped per feed-2's catch-up suggestion to surface working_hours when known, so the catch-up renderer can show "friend X is offline UTC nights".)
- `skipped_questions` — internal bookkeeping.
- Markdown sections beyond intro + contribution + the Phase line — Background, Working style, Tech preferences, Strong opinions stay LOCAL only.

## Rendering rules

1. **Frontmatter first**, then body. Same delimiters as local identity.md.
2. **Empty lists omitted** — if `strong_skills` is `[]`, omit the field entirely from frontmatter rather than writing `strong_skills: []`. Reduces noise.
3. **Empty `contact` block omitted** — if neither `timezone` nor opted-in working_hours has a value, omit the whole `contact:` block.
4. **Body H1 is the handle, not the name** — handles are public identifiers and stable; names may evolve, may be sensitive, may include characters the feed's path can't represent (the handle restricts to kebab-case for a reason).
5. **No emoji** if local `communication_style` contains `no-emoji`. Same rule applies as locally.
6. **Total size target** < 1 KB. The public file is meant to be skimmable across the friend group.
7. **Trailing newline** required (POSIX text-file convention; sf-feed's idempotent commit relies on byte-stable content).

## Friend-edit affordance

After `feed.upsert_identity` succeeds, the skill prints:

```
✓ Public summary pushed to <feed-url>/identities/<handle>.md

  If you'd like to redact further or add detail, edit that file directly
  and push. /sf:interview will detect manual public-file edits on next run
  and ask before overwriting them.
```

The "ask before overwriting" promise is honored by the re-run flow's diff step (see `re-run-flow.md` step 5): the diff includes the public file when it would change, and the friend can decline.

## Joiner case + handle collision

When sf-install Stage 3 detects a `joiner-clone` mode and `feed.detect_repo_state` reports the friend's chosen handle is in `existing_handles`, the orchestrator routes back to `/sf:interview` Q1 with the collision flag set. Q1 re-prompts for a different handle. No public summary is written until a non-colliding handle is settled.

## Idempotency contract with sf-feed

`feed.upsert_identity(handle, public_md)` only commits if the content actually changed. The skill computes `public_md` deterministically from the local identity (sorted YAML keys, fixed list ordering by enum-declaration order, stripped trailing whitespace). Same inputs → same output → no spurious commits.

This matters because:
- `/sf:interview` may run many times across the friend's framework lifetime.
- A no-op call should still be safe (no commit, no push, no feed log entry).
- Friends watching the feed shouldn't see daily "identity refreshed" entries when nothing actually changed.

## Cross-references

- plan §3 — public subset settled across teams
- ADR-018 — Activity Feed identities/ directory
- ADR-020 — joiner flow public summary
- ADR-022 — identity-interview spec
- ADR-017 — per-friend wiki privacy boundary
