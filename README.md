# RenOS (仁) 0.2 — "The measured core"

An **Agentic OS**: a knowledge + governance layer that runs on top of coding-agent
harnesses (Claude Code first). Two pillars, one leg:

- **Memory that compounds** — user-owned plain files every session reads and extends,
  with update/correct/revert semantics (never append-only).
- **Tokens that aren't wasted** — every injected byte budgeted, cached, or pointed-to.
- **Autonomy you can trust** — writes gated by risk tier and provenance, not faith.

**Success bar:** measured pillars. Token/cache/memory claims are instrumented against
ground truth and published as real numbers. *(Numbers: PENDING — collection in progress.)*

## Quick start

```bash
uv sync
uv run pytest
```
