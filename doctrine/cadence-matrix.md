---
type: doctrine
activation: agent-pulled
scope_glob: null
---

# Cadence decision matrix

**Rule: use the lowest tier that fits.** (Capability ladder: quick ask → skill → sub-agent → agent team → /goal → dynamic workflow.)

| Primitive | Statefulness / durability | Use for |
|---|---|---|
| `/loop` | intra-session, **retains context**, ≤ 3 days | deploy/PR watches, context-budget checks |
| `CronCreate` / `CronList` / `CronDelete` | session-scoped; terminal **7d** / desktop **3d**; ~30-min jitter | scheduled session loops (interval mental model, not wall-clock) |
| `/goal` | autonomous depth-first loop until a **measurable** exit (≤ 24h+) | overnight improvement runs, weekly scans |
| **Cloud Routines** | machine-off; cron/API/GitHub triggers; cold fresh env each run; quota (Max 15/day, min 1h) | production cadence → use `/ren:routine-init` |

## Width vs. depth

- "Does this break into many independent pieces running simultaneously?" → dynamic workflow (Haiku workers + one Opus synthesizer).
- "Do I need to keep checking against a done-criterion until it flips?" → `/goal`.
- Combining width and depth is very expensive — do it deliberately.

## Trigger types (Cloud Routines)

- **cron** — natural-language schedule, min 1 hour.
- **api** — outbound POST from another automation (enables chaining).
- **github** — PR / push / issue / release webhook (CI/CD integration).

## Behavioral gotchas

- **Terminal vs desktop cron:** in the terminal, crons survive `/clear` and persist up to 7 days; in the desktop app, `/clear` kills all crons and expiry is 3 days.
- **Jitter:** cron firing adds up to 30 minutes of random jitter — think intervals, not exact wall-clock.
- **Quota:** Pro 5/day, Max 15/day, Team/Enterprise 25/day; min interval 1 hour. `/ren:doctor` surfaces headroom.
