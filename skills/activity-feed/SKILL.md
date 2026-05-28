---
name: activity-feed
description: The cross-friend Activity Feed surface — invoked by /sf:doctor for status checks and by /sf:catch-up for friend-activity summaries. Wraps the feed/ Python module with shell-friendly entrypoints (status.sh, catch-up.sh) so other skills can shell out without importing Python. Per ADR-018 + ADR-021. Do NOT call this skill directly for normal session writes — those flow through the wake-up hook and /sf:wrap which import feed/ directly.
type: skill
schema_version: 1
framework_version: 1.0.0
owner_module: sf-feed
---

# activity-feed

The skill-facing surface for the Activity Feed. Other skills shell out to `scripts/`
here when they need feed status or summaries without taking a Python import dep.

## Files

| File | Purpose |
|---|---|
| `scripts/status.sh` | Prints `{remote, last_sync_iso, push_ok, …}` JSON. Consumed by `/sf:doctor`. |
| `scripts/catch-up.sh` | Thin wrapper around `/sf:catch-up` for shell-friendly invocation (TODO #22). |

## When to invoke

- **`/sf:doctor`** shells to `scripts/status.sh` to render the Activity Feed section
  of its health report (remote URL, last-sync timestamp, push status, pending queue
  count, schema-drift status).
- **`/sf:catch-up`** is itself a separate skill (`skills/sf-catch-up/`) — it imports
  `feed` directly. This skill's `catch-up.sh` is a future convenience wrapper, not
  the primary entrypoint.

## What this skill is NOT

- Not the writer surface. Wake-up hook + `/sf:wrap` import `feed.feed_write_entry`
  directly per the locked lifecycle-2 ↔ feed contract (sealed 2026-05-28).
- Not the disable-feed skill. That lives at `skills/sf-disable-feed/` and writes the
  session-state file directly.
- Not a stable-API surface. The JSON shape printed by `status.sh` is owned by sf-feed
  and may evolve; consumers (sf-doctor) should treat new fields as additive.

## Related

- `feed/` module — the Python implementation surface
- `skills/sf-doctor/` — primary consumer of `status.sh`
- `skills/sf-catch-up/` — separate skill for `/sf:catch-up` (TODO #22)
- `skills/sf-disable-feed/` — opt-out marker writer
- ADR-018 — Activity Feed architecture
- ADR-021 — privacy boundaries
