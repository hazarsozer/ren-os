---
title: qmd (Tobi Lütke) — Hybrid Search for Local Markdown Knowledge Bases
type: research
source_url: https://github.com/tobi/qmd
source_fetched: 2026-05-28
license: MIT
ingested: 2026-05-28
tags: [search, markdown, wiki, bm25, vector-search, llm-rerank, mcp, local, v2-upgrade-path, foreground-research]
status: ingested
related: [llm-wiki-pattern, claude-mem, context-mode]
---

# qmd (Tobi Lütke) — Hybrid Search for Local Markdown Knowledge Bases

## TL;DR

A local hybrid search engine for markdown knowledge bases by Tobi Lütke (CEO of Shopify). Combines three strategies entirely on-device: **BM25 full-text** (SQLite FTS5) + **vector semantic search** (local GGUF embeddings) + **LLM re-ranking** (local Qwen3-reranker). MIT-licensed. Runs ~2GB of local models via node-llama-cpp. Has both a CLI and an MCP server mode. **This is Karpathy's recommended v2 upgrade path for the LLM Wiki pattern** when index-driven recall stops scaling. NOT needed for our v1; drop-in compatible when we get there.

## Why this matters

Karpathy's LLM Wiki text says the `index.md` pattern works "at moderate scale (~100 sources, ~hundreds of pages)" but beyond that **"you want proper search."** He specifically names qmd as a good option. Our v1 wiki stays index-driven; v2/v3, when the wiki grows, qmd is the drop-in upgrade.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Claude Code session                                       │
│   │                                                         │
│   ├── CLI: qmd search / qmd vsearch / qmd query           │
│   │                                                         │
│   └── MCP server: qmd mcp [--http --daemon]               │
│         exposes tools: query, get, multi_get, status      │
│   ↓                                                         │
│  ┌────────────────────────────────────────────────────┐ │
│  │ qmd runtime (Node 22+ or Bun 1.0+)                  │ │
│  │  - node-llama-cpp for local model inference         │ │
│  │  - Three local GGUF models (~2GB total):            │ │
│  │     • embeddinggemma-300M  (~300MB)                 │ │
│  │     • qwen3-reranker        (~640MB)                │ │
│  │     • qmd-query-expansion   (~1.1GB)                │ │
│  └────────────────────────────────────────────────────┘ │
│   ↓                                                         │
│  ┌────────────────────────────────────────────────────┐ │
│  │ ~/.cache/qmd/index.sqlite                          │ │
│  │  - FTS5 BM25 index                                  │ │
│  │  - Vector storage                                    │ │
│  │  - LLM response cache                                │ │
│  └────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

## The three search modes

| Command | Strategy | When to use |
|---|---|---|
| `qmd search` | BM25 keyword-only | Fast keyword matches; lowest cost |
| `qmd vsearch` | Vector similarity only | Conceptually-related results without keyword overlap |
| `qmd query` | Hybrid + LLM re-rank | Best quality; slightly slower; default for the MCP server |

## MCP integration

Configure in Claude Desktop's MCP config:
```json
{
  "mcpServers": {
    "qmd": {
      "command": "qmd",
      "args": ["mcp"]
    }
  }
}
```

Or for Claude Code: install via plugin marketplace.

**MCP tools exposed**: `query`, `get`, `multi_get`, `status`.

**Daemon mode** (`qmd mcp --http --daemon`): runs as a long-lived HTTP server to avoid reloading the ~2GB models on every invocation. Optional but recommended for active use.

## Install

```
npm install -g @tobilu/qmd
# or
bun install -g @tobilu/qmd
```

Models auto-download from HuggingFace on first use.

## Dependencies

- Node.js ≥ 22 OR Bun ≥ 1.0
- macOS: `brew install sqlite` (needed for FTS5 extension support)
- ~2GB disk for models
- Optional: tree-sitter grammars for AST-aware code chunking

**No Python, no external API keys.** Fully offline-capable.

## Configuration

| Option | Purpose |
|---|---|
| `qmd collection add <path> --name <label> --mask <glob>` | Add a directory to indexed collections |
| `qmd context add qmd://<path> "<description>"` | Provide context hints to improve relevance |
| `--chunk-strategy auto` | Tree-sitter AST chunking for code; regex default |
| `--json` / `--files` / `--csv` / `--md` / `--xml` | Output formats |
| `QMD_EDITOR_URI` | Configure editor link templates (VS Code, Cursor, Zed, Sublime) |
| `QMD_EMBED_MODEL` | Override embedding backend (e.g., multilingual CJK models) |
| `QMD_LLAMA_GPU` | `metal` / `vulkan` / `cuda` / `false` (CPU-only) |
| `QMD_EMBED_PARALLELISM` | Adjust embedding worker count (default 1 on Windows for CUDA stability) |

## License

**MIT**. Adoption unencumbered.

## Limitations and warnings

- **Model switching requires re-indexing** — changing `QMD_EMBED_MODEL` requires `qmd embed -f` (vectors are model-specific)
- **Windows CUDA parallelism issues** — defaults to parallelism=1; use Vulkan or tune `QMD_EMBED_PARALLELISM` cautiously
- **TTY detection for editor links** — OSC 8 hyperlinks only when stdout is a terminal; piped output is plain
- **FTS query language not fully documented** — advanced syntax supported but README is light
- **Initial model download** — first use downloads ~2GB; document in onboarding

## How this informs the framework

### V1: not needed

Our wiki is small. Index-driven recall (the `index.md` pattern) is sufficient. qmd would add 2GB of dependencies for marginal benefit at our v1 scale.

### V2+: drop-in upgrade path

When the wiki grows past Karpathy's "~100 sources, ~hundreds of pages" envelope:
- Install qmd
- Index the existing wiki collection
- Wake-up hook calls `query` tool via MCP instead of reading `index.md` blindly
- Wiki structure (raw markdown, frontmatter, link discipline) **doesn't need to change**

The framework's design must keep this option open — no architectural choices that would preclude adding qmd later. Tests:
- ✅ Wiki is plain markdown (qmd reads markdown)
- ✅ Wiki is git-versioned (qmd indexes any directory)
- ✅ Wake-up hook is replaceable (logic abstracted from data layer)

### License-stack consideration

Adding qmd later adds an MIT dependency. Aligns with our existing license diversity:
- Apache-2.0: claude-mem, Skill Creator
- MIT: Superpowers, GSD Redux (if ever adopted), qmd (if adopted)
- ELv2: Context Mode
- ???: Frontend Design (verify)

Document in stack `LICENSES.md`.

### qmd shares architecture with claude-mem + Context Mode

All three use SQLite + FTS5. qmd adds vector + LLM re-ranking on top. Pattern is converging:
- **SQLite FTS5** is the standard local-search primitive for Claude-Code-adjacent tools
- Vector + re-rank is the upgrade layer

Worth noting in our design: if we ever build our own wiki search (instead of using qmd), the same primitives are the right choice.

### The daemon trade-off

qmd's `--daemon` mode keeps the 2GB models loaded for fast queries. That IS a daemon — but it's optional (subprocess mode works for occasional queries). Pattern: **plugins can offer daemon and non-daemon modes**, letting users choose. Our framework's own pieces should follow this if they ever need significant compute.

## Tensions / open questions

1. **At what wiki scale do we transition from index.md to qmd?** Karpathy's "~100 sources, hundreds of pages" is the rough envelope. We should set a concrete trigger in our framework docs (e.g., "switch when index.md exceeds 200 entries or 20KB").
2. **2GB model download UX** — friction at install if we ever bundle qmd. Make optional, document clearly.
3. **Daemon mode in friend-group settings** — if a friend opens multiple sessions, does daemon mode handle concurrency well? Worth testing before recommending.
4. **Other qmd implementations** — `ehc-io/qmd` is an alternative; `hjanuschka/pi-qmd` is a port. Tobi Lütke's is the canonical one (Karpathy mentioned it). Stick with this.

## Connections to prior research

| Prior source | Connection |
|---|---|
| Karpathy LLM Wiki | qmd was explicitly named as the recommended search tool when index-driven recall stops scaling |
| claude-mem | Same SQLite + FTS5 primitive; claude-mem operates at the observations layer, qmd at the document layer |
| Context Mode | Same SQLite + FTS5 primitive; Context Mode at the events layer, qmd at the wiki layer |
| Anchor Tags (Ben Fellows) | qmd's deterministic queryable index is what Ben's manifest is — both bet on structure + retrieval |

## Followups

- Decide concrete trigger thresholds for transitioning from index.md to qmd (likely in the v2 design phase, not now)
- Test qmd against a sample wiki sized like our projected v2 (50-200 pages) to verify behavior

## Reference

- GitHub: https://github.com/tobi/qmd
- Author: Tobi Lütke (Shopify CEO)
- Alternative implementations: https://github.com/ehc-io/qmd, https://github.com/hjanuschka/pi-qmd (port)
- Fetched: 2026-05-28
- License: MIT
- Status for our framework: **V2 upgrade path, not v1**
