---
title: "/sf:recall grep-strategy — scoring + snippet heuristic (v1)"
type: skill-reference
parent_skill: sf-recall
version: 0.1.0
date: 2026-05-28
---

# Grep strategy (v1)

Per ADR-005, V1 wiki search is a deliberate grep over `wiki/**/*.md`. V2 (qmd-based hybrid search) is the upgrade path when the wiki grows past ~200 pages. This doc defines the v1 heuristic.

## Tokenization

Query is lowercased and split on whitespace + punctuation. Common stop-words (`a`, `an`, `the`, `of`, `is`, `we`, `i`, `to`) are dropped to avoid matching too eagerly. Stop-word list is small + opinionated; expandable in `lib/grep.py`'s `STOP_WORDS` constant.

Example:
```
query: "what did we decide about postgres"
tokens (after stop-word strip): ["what", "did", "decide", "about", "postgres"]
```

In practice the LLM will phrase queries with stop-words; this drops them to focus the grep.

## Per-file scoring

For each `*.md` file under `wiki_root`:

1. **Title hits**: tokens appearing in the YAML frontmatter `title:` field score **3** each.
2. **Heading hits**: tokens appearing in `^## ` or `^# ` markdown headings score **2** each.
3. **Body hits**: tokens appearing anywhere else score **1** each.
4. **File-kind multiplier**:
   - `wiki/decisions/*.md` → ×1.5 (decisions are high-value; surface them first)
   - `wiki/patterns/*.md` → ×1.3
   - `wiki/.session-notes/*.md` → ×0.8 (notes are still surfacing-able, but less authoritative than decisions/patterns)
   - All others → ×1.0
5. **Recency boost**: files modified in the last 30 days get a +0.5 bonus (recent wins ties).

Files with score == 0 are dropped (no tokens hit).

## Snippet extraction

For each kept file, find the FIRST line where any query token appears (case-insensitive). Extract:
- The matching line itself
- The line BEFORE (if any)
- The line AFTER (if any)

Render as a 3-line excerpt, prefixed with the file path + line number:
```
wiki/decisions/008-wake-up-hook.md:42:
  ...
  The wake-up mechanism uses a SessionStart hook that injects wiki context...
  Each session begins with a context-injection message in the conversation layer
```

If the matching line is the FIRST or LAST in the file, the missing context line is shown as ` ` (blank) to preserve the 3-line shape.

## Ranking + cap

Hits sorted by score descending; ties broken by file mtime (newer wins).

Truncate to top N (default `n_hits=10`). The friend can re-run with a narrower query if they want more / want different results.

## Output format

Per the SKILL.md user-facing rendering:

```markdown
## Wiki matches for "<query>"
- `<relative-path>:<line>` (score N.N): <truncated first line of snippet>
  ```
  <full 3-line snippet>
  ```
```

The score is rendered for diagnostic transparency; friends learn to trust higher-scored results and re-query when scores cluster low.

## V2 transition trigger (ADR-005 cross-reference)

When ANY of the following hits per `wiki/decisions/005-*.md`:
- Wiki size > 200 markdown files
- p95 `recall()` latency > 1s
- Friends report consistent "I know it's in there but I can't find it" complaints

…then `lib/grep.py` is replaced by `lib/qmd_search.py` with a hybrid BM25+vector+LLM-rerank backend. The public `recall()` API stays unchanged; only the internal scoring layer swaps.

Per ADR-005, the v2 path is deliberately preserved by keeping the layer abstraction tight (one function: `grep_wiki(wiki_root, query) -> list[RecallHit]`).

## Why we don't use `claude --bare --print` for the grep

Tempting: ask an LLM "find the most relevant page about X." But:
- v1 wiki sizes (a few dozen pages) don't justify the latency + cost
- Deterministic results matter for `/sf:doctor` smoke checks against `recall()`
- The grep heuristic above is good enough for v1; LLM-judged retrieval is the v2 upgrade if v1 misses

Deterministic > clever, at v1 scale.
