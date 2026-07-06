---
type: doctrine
activation: always-on
scope_glob: null
---

# Cadence conventions

Apply these to whatever tier cadence work routes to. A cloud scaffold (`/ren:routine-init`) bakes the relevant ones into its templates automatically; for local `/loop`/cron/`/goal` you apply them by hand.

## Self-terminating loops
Every `/loop` or `CronCreate` carries a stop condition — "kill the cron after N iterations" or "stop after <time window>". Prevents orphaned background jobs persisting past their useful life.

## Auto-compact companion cron
For a long-running loop that accumulates stale context, pair the work cron with a second cron whose sole payload is `/clear` (~every 5 minutes). Prevents context rot.

## Failure-notification footer (required for unattended runs)
Append to any unattended prompt: *"If this run fails for any reason, send me an email via the Resend MCP tool `mcp__resend__send-email` with the error."* Headless runs fail silently by default; this is zero-infrastructure observability.

## Measurable exit for `/goal`
`/goal` must have a concrete, measurable done-criterion (a passing test, a coverage threshold, a file that exists). A subjective prompt causes infinite iteration.

## Explicit env-var sourcing
Tell the run exactly where secrets are: *"My X key is an environment variable — use it directly, do not look for a `.env`."* Without this, Claude searches for `.env` per CLAUDE.md conventions and fails silently.

## Run-Now before scheduling
Iterate on the routine interactively with **Run-Now** until it one-shots cleanly, then schedule. Green-before-schedule — the TDD of cadence.

## Off-peak scheduling
Anthropic throttles session-window drain by demand; peak ≈ 8am–2pm ET weekdays. Schedule heavy multi-agent / large-refactor cadence off-peak.

## Permission posture
Auto Permission Mode for team-plan unattended runs; manual allow/deny for solo Pro/Max. **Never** bypass-permissions for cadence.
