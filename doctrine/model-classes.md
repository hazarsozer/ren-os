---
type: doctrine
activation: agent-pulled
scope_glob: null
---

# Model classes

Routing doctrine speaks in classes, never model names. This table is the only
name→class mapping; update it when new models ship.

| class | current models | use for |
|---|---|---|
| orchestrator | claude-fable-5, claude-opus-5 | main-session orchestration, synthesis, judgment, hardest reasoning |
| worker | claude-sonnet-5 | non-trivial coding, exploration with judgment, most subagents, delegated fan-out coordination |
| classifier | claude-haiku-4-5 | fan-out workers, classification, summarization, scoring, judges |

<!-- renos:model-map-updated: 2026-07-30 -->
