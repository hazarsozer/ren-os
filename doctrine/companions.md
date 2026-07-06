---
type: doctrine
activation: agent-pulled
scope_glob: null
---

# Recommended companions (v2.1 D-3)

Optional tools that pair well with RenOS. **Everything on this page is optional** — the framework works with zero of them installed, and none of them are health-checked in 0.2 (that's a 0.3 upgrade). This page exists so a friend who wants more capability knows what to reach for and how it fits the risk model, not to nag anyone into installing anything.

## Graphify — the code-map backend

The §3.2 code-map (`/ren:code-map`) is a thin wrapper over [Graphify](https://github.com/), an open-source (MIT), tree-sitter-based, deterministic code-structure tool — not a hand-rolled engine of ours.

- Install: `uv tool install graphifyy`
- Pin note: RenOS is built against the **0.9.x** line (`GRAPHIFY_PIN = "0.9"` in `lib.code_map`... see `skills/code-map/lib`). Graphify's API has churned across major versions; a version outside 0.9.x is a warning, not a hard failure.
- Doctor checks Graphify specifically (installed? pinned version? output fresh?) — it's the one companion on this page that gets that treatment, because the code-map capability directly depends on it. No other companion here gets a doctor check in 0.2.
- Graceful absence: not installed → the code-map capability says so plainly and stays unavailable. No fallback engine.

## Playwright MCP / Claude in Chrome — agent-verified visual/E2E testing

For sessions that want the agent to visually verify its own UI output (does the button actually render, does the flow actually complete) rather than taking a green test suite's word for it:

- **Playwright MCP** — browser automation via the Model Context Protocol; install per Playwright's own MCP server docs.
- **Claude in Chrome** — Anthropic's own browser extension integration.

Both are optional, and both are browser-control tools — which means the governance sentence below applies to them without exception.

> Browser control that can act on the logged-in web is destructive-tier under the risk model in docs/data-flow.md and §3.6 — it always asks, and it never runs unattended.

## Voice-input tools

User-side convenience tools (e.g. Whisper Flow-style dictation) for talking to Claude Code instead of typing. These require zero framework support — they sit entirely on the user's input path before anything reaches Claude Code — so there is nothing here to install, configure, or gate. Purely a personal-workflow choice.

## What's NOT on this page

No health-check machinery for any of these in 0.2 — that's explicitly deferred to 0.3. No LLM media-extraction paths from Graphify are ever invoked by the code-map wrapper (code-mode/tree-sitter only). No wiki/Obsidian export feature of Graphify is used to write wiki pages — the wiki's SSOT stays queue-governed, always.
