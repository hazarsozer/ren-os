---
title: "Observability Tools for Claude Code (dash0 + native + alternatives)"
type: research
sources:
  - https://www.dash0.com/guides/teach-your-ai-coding-agent-opentelemetry
  - https://github.com/dash0hq/agent-skills
  - https://github.com/TechNickAI/claude_telemetry
  - https://code.claude.com/docs/en/agent-sdk/observability
source_fetched: 2026-05-28
ingested: 2026-05-28
tags: [observability, opentelemetry, token-tracking, ecosystem-survey, foreground-research, native-claude-feature]
status: ingested
related: [anthropic-marketplace-catalog, nate-herk-give-me-10-mins, context-mode]
note: |
  Quick ingest discovered that dash0 is NOT the token-tracking observability plugin
  I expected. It's an OpenTelemetry-best-practices skill for AI agents. But the
  research revealed something more important: **Claude Code has native
  OpenTelemetry support** via its Agent SDK — exports traces, metrics, events to
  any OTLP backend. The framework gets observability for free if we recommend it.
---

# Observability Tools for Claude Code

## TL;DR

**The most important finding here isn't a plugin — it's that Claude Code itself has native OpenTelemetry support.** Anthropic's Agent SDK exports traces, metrics, and events to any OTLP backend (Honeycomb, Datadog, Grafana, Langfuse, Dash0, self-hosted collectors). dash0 turned out to be agent-skills that TEACH instrumentation patterns, not a token-tracking dashboard. The framework gets observability for free by documenting how to enable native OTel in ADR-015 onboarding. Optional richer wrappers exist (claude_telemetry from TechNickAI) but aren't needed for v1.

## What dash0 actually is (not what I expected)

[Dash0 Agent Skills](https://github.com/dash0hq/agent-skills) are skills that **teach Claude Code (and Cursor, Windsurf) how to write good OpenTelemetry instrumentation**. They include:

- **otel-collector skill** — configure + deploy OpenTelemetry Collector (receivers, processors, exporters, pipelines, batching, tail sampling, RED metrics)
- **otel-semantic-conventions skill** — decision framework for OTel semantic conventions (searches Attribute Registry before inventing custom attributes)

So dash0's skills are **for friend-group projects that emit OpenTelemetry**, not for observing the Claude Code session itself.

This is useful but different from what would directly serve our token-efficiency north star at the framework level.

## What we actually want: native Claude Code OpenTelemetry

**Claude Code's Agent SDK exports OpenTelemetry traces/metrics/events natively** to any OTLP backend.

Per [Anthropic's official docs](https://code.claude.com/docs/en/agent-sdk/observability):
> *"Every request, every session, every token consumed can be traced and exported via OpenTelemetry."*

Backends that work:
- Honeycomb
- Datadog
- Grafana
- Langfuse
- Dash0 (yes, the same Dash0 — they're an OTel backend AND ship agent-skills)
- Self-hosted OTel Collector

**This is the framework's token-tracking observability solution.** No plugin needed; configure native CC + an OTLP endpoint.

Friends who want detailed token tracking + cost analysis can:
1. Enable native CC OpenTelemetry export
2. Point at any OTLP backend of their choice
3. Get traces of every tool call, every session, every token

## Optional wrappers / alternatives

### claude_telemetry (TechNickAI)

> "OpenTelemetry wrapper for Claude Code CLI that logs tool calls, token usage, costs, and execution traces to Logfire, Sentry, Honeycomb, or Datadog. Drop-in replacement that swaps 'claude' command for 'claudia'."

A wrapper that augments CC's native telemetry with additional event capture. Useful if friends want pre-built integrations beyond CC's defaults.

### Nate Herk's local token dashboard

Per his transcript, Nate ships a local GitHub repo with a token-tracking dashboard. This was an option before we knew CC had native OTel. Now: probably redundant for friends who use native OTel, but a self-hosted alternative for friends who don't want external backends.

### Context Mode's `ctx_insight` (already in our stack)

Per the Context Mode research, `/context-mode:ctx-insight` opens a local web UI dashboard with 90 metrics covering Context Mode's specific token-tracking. Different layer than native OTel — focused on Context Mode's compression metrics.

### lean-ctx's browser dashboard

If we ever swap to lean-ctx (per its research), it includes a browser dashboard with real-time token tracking + budget profiles. Different layer than native OTel — focused on lean-ctx's compression metrics.

## How this informs the framework

### Major reframe: observability is mostly free

Native Claude Code OpenTelemetry → friends get full observability without our framework building or recommending any specific tool. The framework's responsibility is just **documenting how to enable it in onboarding**.

Concrete ADR-015 onboarding addition:

```
Stage 6 (verification) optional step:
  "Want token/session observability? Enable native OpenTelemetry by setting
   OTEL_EXPORTER_OTLP_ENDPOINT and OTEL_EXPORTER_OTLP_HEADERS env vars to your
   chosen backend (Honeycomb, Datadog, Grafana, Langfuse, self-hosted)."
```

That's the whole observability story for v1. **No new plugin in the curated stack.**

### dash0's agent-skills could be a per-project addition

If the friend group ever builds a project that emits OpenTelemetry, dash0's skills are useful. **Out of framework scope; per-project decision.**

### Token-budget tracking can use OTel

The gap-ADR we'd planned around "token budgets" (item 8 in pre-design-doc gaps) can be implemented via OTel exports + a backend that supports alerting (e.g., Honeycomb's Triggers, Datadog's Monitors). **No new framework code needed.**

Likely amendment to the gap-ADR for token budgets: "use native OTel + chosen backend's budget/alert features."

## Tensions / open questions

1. **None major.** Native CC OpenTelemetry is the cleanest answer for observability.
2. **Friends without an OTLP backend** — many friend groups won't have Honeycomb/Datadog/etc. Mitigation: recommend free tier of Langfuse or self-hosted Grafana stack; or simply skip observability for v1.
3. **Privacy** — telemetry exports could send code context to external backends. Mitigation: self-hosted collector + storage; document in onboarding.

## Connections to prior research

| Prior source | Connection |
|---|---|
| Nate Herk Prompt Caching | His token-tracking dashboard recommendation is now substitutable by native OTel |
| Context Mode `ctx_insight` | Different layer (compression-specific); still has value but for Context Mode specifically |
| lean-ctx browser dashboard | Same — different layer; usable if we ever swap |
| Anthropic Marketplace Catalog | dash0 is in the catalog as `dash0` plugin — agent-skills are part of broader Dash0 offering |
| ADR-015 (Onboarding) | Should mention OTel as optional configuration |

## Followups

- No urgent followups. dash0 question is answered — it's not what we needed; native CC OTel is.
- If user wants the very-thorough version, we could deep-dive Logfire / Langfuse / Honeycomb's specific integration with CC; defer unless explicit need.

## Reference

- Dash0 agent-skills: https://github.com/dash0hq/agent-skills
- Dash0 guide: https://www.dash0.com/guides/teach-your-ai-coding-agent-opentelemetry
- Claude Code OpenTelemetry docs: https://code.claude.com/docs/en/agent-sdk/observability
- claude_telemetry wrapper: https://github.com/TechNickAI/claude_telemetry
- SigNoz blog on CC + OTel: https://signoz.io/blog/claude-code-monitoring-with-opentelemetry/
- General Analysis comprehensive guide: https://generalanalysis.com/guides/claude-code-control-observability-opentelemetry
- HN discussion: https://news.ycombinator.com/item?id=45325410
- Fetched: 2026-05-28
