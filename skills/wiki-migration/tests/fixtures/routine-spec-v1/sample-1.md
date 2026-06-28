---
title: "Routine: daily-digest"
type: routine-spec
schema_version: 1
framework_version: "1.0.0"
name: "daily-digest"
trigger_type: "cron"
linked_repo: "github.com/example/daily-digest"
network_tier: "trusted"
env_secrets_ref: "(none declared)"
schedule: "0 9 * * *"
expected_output: "A morning summary email"
failure_handler: "email me@example.com via Resend MCP"
created: "2026-06-01"
updated: "2026-06-01"
---

# Routine: daily-digest

Documents one live cadence routine deployed via `/ren:routine-init` (ADR-034). Surfaced by the wake-up hook and audited by `/ren:doctor`.

## What it does

A morning summary email

## Trigger

- **Type:** cron
- **Schedule:** 0 9 * * *

## Safety

- **Network tier:** trusted — Anthropic allowlist.
- **Secrets:** (none declared) — live in the cloud env, never the repo.
