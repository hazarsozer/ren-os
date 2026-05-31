# AskUserQuestion 4-Option Cap — Reusable Mitigation Patterns

**Scope:** any framework skill that needs more than 4 options in a multiple-choice or multi-select question.

`AskUserQuestion` is Claude Code's built-in tool for showing the friend a small set of options. It enforces a hard cap of **4 options per question** for UX consistency. When the option space genuinely exceeds 4, the skill picks one of the patterns below.

This doc is intentionally located inside `sf-interview/references/` for v1 because `/sf:interview` is the heaviest consumer (8 of its 18 questions hit the cap). When a second skill needs the patterns, lift the doc into a shared `skills/_shared/references/` location and update both references — the patterns themselves stay the same.

## The four patterns

| Pattern | When | Cost | Drawback |
|---|---|---|---|
| **Pagination** | Options form a long flat list with no natural categorization | One extra question (page 2 only if "more" chosen) | Friend may not know what's on page 2 before clicking through |
| **Category cascade** | Options group naturally (build/design/data, etc.) | One extra question per chosen category | Two-stage UX; categories themselves must be ≤4 |
| **Combine** | Two semantic axes were collapsed into one question | One extra question (a 2nd axis becomes its own prompt) | Composed answer needs a documented render rule |
| **Open-ended fallback** | Any of the above + the option set is open-ended in nature (e.g. tools, package managers) | None — friend types text | Loses normalized enum benefits; requires post-hoc cleanup |

The fallback should be offered *alongside* any of the first three on multi-select questions, as an escape hatch. Friends who already have a comma-separated list in mind shouldn't be forced through pagination.

## Pattern 1: Pagination

**Use when**: option count is 5–8, options are individually meaningful but don't categorize naturally.

**Structure**:
1. Page 1: 3 most-likely-relevant options + `more...`
2. If friend picks `more...`, show Page 2: remaining options (each up to 4) + `none of these`
3. Combine into the final answer

**Example — Q12 clouds (7 options)**:
- Page 1: `aws | vercel | supabase | more...`
- Page 2 (only if `more...`): `gcp | cloudflare | self-hosted | other`

**Choosing what goes on page 1**: rank by "expected % of friends who'd pick this" (qualitative). Most-common-first reduces total prompts shown.

**Multi-select variant**: page 1 captures their first picks; page 2 (always offered, since multi-select means "all that apply") shows the rest; final answer = union.

## Pattern 2: Category cascade

**Use when**: options group into ≤4 meaningful buckets, and most friends would only pick within one or two buckets.

**Structure**:
1. Stage 1: ask "Which category/categories?" — up to 4 broad categories + an `other` open-ended escape
2. Stage 2 (per category chosen): drill into sub-options for that category
3. Final answer = union across drilled categories

**Example — Q4 strong skills (9 options across 4 categories)**:
- Stage 1: `build | design | product-ops | other`
- Stage 2 (per choice):
  - build → `ai-ml | backend | frontend | data-eng | devops` (5 sub-options — itself uses pagination)
  - design → `design` (single — confirm)
  - product-ops → `product | content`
  - other → open-ended

**Choosing categories**: each category should be (a) intuitively-named, (b) collectively-exhaustive in the relevant domain, (c) mutually-exclusive at the category level.

**When this pattern compounds**: if a sub-category itself has > 4 options (e.g. "build" with 5), pagination applies at stage 2. Cascade + paginate is fine; don't go three deep.

## Pattern 3: Combine

**Use when**: the original question was actually two orthogonal axes folded into one option list.

**Structure**:
1. Split the question into two sub-questions (each ≤4 options).
2. Compose the answers into one stored value via a documented render rule.

**Example — Q7 communication style (5 options collapsed to 4 via splitting)**:
- Sub-question 7a (tone): `formal | casual | case-by-case | other`
- Sub-question 7b (emoji): `yes | no | occasionally | case-by-case`
- Composition: `<tone>-<emoji-token>` → e.g. `casual-no-emoji`, `formal-some-emoji`, `case-by-case-with-emoji`

**Render rule must be documented** wherever the composed value is consumed (here: `references/output-format.md`'s `communication_style` field spec). New combinations are allowed without schema change — the field type is "string".

**When NOT to combine**: if the two axes aren't truly orthogonal (e.g. "language + framework" where some languages don't have certain frameworks), the cross product is broken and combine is the wrong pattern. Use cascade instead.

## Pattern 4: Open-ended fallback

**Use when**: the option space is inherently open (tools, package managers, custom roles), OR as an always-on escape hatch on multi-select cascades.

**Structure**:
1. Present the structured options first (using one of the three patterns above).
2. Offer a separate prompt: "Or type a comma-separated list."
3. On free-form input, normalize each entry against the known enum; unknown entries map to `other` in the structured field AND the raw text is preserved in the narrative markdown body.

**Example — Q10 languages (11 options across 4 categories)**:
- Cascade first (`systems | web | mobile | data-or-other` → drill in)
- Fallback offered always: `Or type "rust, swift" or any comma list`

**Why always offer the fallback**: friends who know exactly what they want should be able to type it. Forcing them through cascades wastes turns and feels patronizing.

## Choosing per question

The mapping for `/sf:interview`'s 8 over-cap questions is in `references/question-template.md` — strategy field per question. When authoring a new skill that hits the cap, document the per-question choice the same way: type, strategy, options, default.

Decision flow:

```
> Q has > 4 options?
  YES → Are options categorizable into ≤4 groups?
         YES → Cascade
         NO  → Is the option space open in nature?
                YES → Open-ended (with optional pagination of common picks first)
                NO  → Is there a 2nd semantic axis hidden inside the question?
                       YES → Combine
                       NO  → Pagination
  NO  → Native (no mitigation needed)
```

## Anti-patterns

- **Don't silently drop options** to fit the cap. The friend should always have a path to express the choice they want.
- **Don't make Page 2 / Stage 2 invisible.** "more..." or category names must be obvious in Page 1, so the friend knows the option exists.
- **Don't cascade three levels deep.** Two stages is the UX limit. If you'd need three, redesign the question.
- **Don't forget the fallback on multi-select.** The escape hatch is what keeps the structured cascade from feeling like a maze.
- **Don't normalize unknown free-form to silent `other`.** Always preserve the original text somewhere (markdown body, sibling list field) so the friend can grep it back.

## Revision history

- v1 (2026-05-28) — initial four-pattern catalog. Authored for `/sf:interview` per ADR-022's open question #1. Promoted to first-class reusable per team-lead's ask.
