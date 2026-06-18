# code-map — learnings

_Append confirmed gotchas/wins here (ADR-012). Seed entries:_
- lean-ctx is adopted as a **CLI** (not MCP/serve) — CLI-over-MCP saves 60–70% tokens.
- The map is a **cache**, never wiki content; line numbers churn, so it must not be version-controlled.
- Staleness tracks **all** source files (not just symbol-bearing ones) — else symbol-less files like `__init__.py` falsely read as "added".
