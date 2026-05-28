---
name: sf-disable-feed
description: Use when the user runs `/sf:disable-feed` to opt the current session out of the Activity Feed. Writes the per-session marker that gates feed.is_skip_active(), so the upcoming /sf:wrap (and any subsequent feed writes) become no-ops. Also invoked when the user requests a "private session" mid-conversation. Per ADR-021 — the format constraint plus this opt-out together ARE the privacy mechanism.
type: skill
schema_version: 1
framework_version: 1.0.0
owner_module: sf-feed
---

# sf-disable-feed

The per-session kill switch for the Activity Feed. Highest precedence in the opt-out
chain (per ADR-021 + plan §6.1). When triggered, ALL subsequent `feed_write_entry`
calls in this session become no-ops — no local entry, no remote push.

## When to invoke

- User runs the `/sf:disable-feed` slash command directly.
- User says "make this session private" / "don't share this with the group" / similar
  privacy intent mid-conversation, BEFORE doing the sensitive work.

## What this skill does

1. Resolves the current session ID from `$CLAUDE_SESSION_ID` (Claude Code populates this
   on session start). If unset, uses `"default"` as a fallback session ID.
2. Writes `~/.startup-framework/state/session-<id>.json` with:
   ```json
   {
     "skip_feed": true,
     "reason": "user-disabled",
     "timestamp": <unix-seconds>
   }
   ```
3. Reports the outcome to the user, INCLUDING a warning if a session-start entry was
   already pushed (per plan §6.2 behavior matrix — the start entry can't be retroactively
   removed without git filter-repo coordination per ADR-021).

## Precedence reminder

The skip chain (highest wins):
1. `/sf:disable-feed` state file ← this skill writes it
2. `SF_SKIP_FEED=1` env var
3. `--skip-feed` flag on `/sf:wrap`

ANY of the three being set → no write to the Activity Feed.

## What this skill does NOT do

- **Does not unwrite a session-start entry that already pushed.** ADR-021 §"Deletion is
  hard" — git filter-repo + coordinated re-clone is the only path. We warn loudly when
  the user disables mid-session.
- **Does not delete claude-mem captures.** claude-mem has its own SessionEnd hook;
  suppress that separately via its own controls if needed.
- **Does not provide an `/sf:enable-feed` counterpart.** Per plan §6.4 — deferred to v2 if friends ask. To re-enable, start a fresh Claude Code session.

## Invocation

The skill driver shells out to a small Python helper that imports `feed.skip`:

```bash
python3 -m feed.skip --mark-disabled --session-id "${CLAUDE_SESSION_ID:-default}"
```

(or equivalently, calls `feed.skip.mark_session_disabled(session_id=...)` directly from
the consolidate/orchestration layer that owns the slash command.)

## Verifying the disable took effect

After running, the friend can verify:

```bash
python3 -c "from feed import is_skip_active; print(is_skip_active())"
# → (True, 'session-disabled')
```

`/sf:doctor` also surfaces the session-disabled state in its Activity Feed section.

## Related

- `feed.skip.is_skip_active` — the single source of truth this skill influences
- `feed.skip.mark_session_disabled` — the underlying writer function
- ADR-021 — privacy boundaries (terse format + opt-out surfaces)
- ADR-018 — Activity Feed architecture
- Plan §6.1–§6.4 — precedence rules + behavior matrix + skill spec
