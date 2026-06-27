# C3a — Instincts Hot Tier (Compounding Memory, Tier 1) — Design Spec

> **Status:** Approved design (2026-06-28). Brainstormed via `superpowers:brainstorming`; scope +
> capture + routing locked with the maintainer via AskUserQuestion (see §2). Input to a
> `superpowers:writing-plans` pass and the contract for the subsequent TDD build.
>
> **Roadmap slice:** C3 (Pillar 4, "Compounding model") in
> `docs/superpowers/plans/2026-06-11-agentic-os-rebuild-roadmap.md` — **decomposed**. This is **C3a**
> (the hot-capture tier). **C3b** (the governed LLM consolidate/promote sweep) is a separate, later slice
> and is **out of scope here**.
> **Source of the model:** `docs/superpowers/specs/2026-06-08-nate-herk-ingest-positioning-design.md`
> §"Compounding model" (three tiers: hot capture → curated canonical → governed sweep).
> **Governs / amends:** new **ADR-037** (Compounding Memory Model), recording amendments to **ADR-009**
> (consolidate posture), **ADR-014** (sub-wiki taxonomy), **ADR-027** (schema registry).
> **Constrained by:** ADR-009 (consolidate is manual, never a Stop hook), ADR-031 (solo-first — no
> speculative autonomy; any LLM sweep is proposal-diff-gated), ADR-003 (no daemon).

---

## 1. Purpose

RenOS's compounding/memory pillar (P4) is the last untouched one. The positioning spec frames it as a
**three-tier model**: (1) **hot capture** — cheap, liberal, append; (2) **curated canonical** — the wiki
proper, high-signal promotions; (3) **governed sweep** — an LLM dedup/promote pass, "our controllable
answer to CC's opaque Auto-Dream."

C3a builds **tier 1 only**: a durable, hierarchically-routed `instincts` artifact ("what worked / what to
avoid / don't-repeat"), captured cheaply via `/ren:note` and read via `/ren:recall`. It is the foundation
the promotion + sweep (C3b) will later build on. Nothing here is signal-thresholded or LLM-inferred — that
is exactly what keeps it cheap and keeps the risky autonomy (the sweep) out of this slice.

The default behavior of `note`, `recall`, and `wrap` is **unchanged**; everything C3a adds is additive and
opt-in (an `--instinct` mode on `note`, an `--instincts` filter on `recall`).

---

## 2. Locked decisions (maintainer, 2026-06-28)

| # | Decision | Choice | Consequence |
|---|----------|--------|-------------|
| 1 | **Scope** | **Hot tier now (C3a); governed sweep deferred (C3b).** | Smallest coherent slice; one built page-type; the ADR-031-sensitive LLM sweep gets its own deliberate slice. Mirrors C5a/b/c. |
| 2 | **Capture mechanism** | **Extend `/ren:note`** with a typed `--instinct <kind>` mode. | Minimal new surface; `note` is already the "worth remembering" companion. Plain `/ren:note` stays byte-for-byte unchanged. |
| 3 | **Routing** | **Project-default, `--global` opt-in.** | Prevents cross-project contamination (positioning + memory note) with zero friction for the common case. No project context → global + notice. |
| 4 | **Page-type batch (ADR-027 "decide together")** | **`instincts` built; `experiment-log` forward-declared; `verification_strategy` recorded-as-planned.** | Decide all three shapes now; build only the `instincts` writer. `verification_strategy` is a field on `routine-spec`, so its v1→v2 bump + elicitation is deferred to the C2 build (recorded here, not migrated). |
| 5 | **Governance home** | **New ADR-037 (Compounding Memory Model)**, recording amendments to ADR-009/014/027. | Every pillar got its own ADR (C4→034, C2→035, C5→036). Cleaner than three orphan amendments. |
| 6 | **Instinct kinds** | `worked` · `avoid` · `dont-repeat` | Per the positioning model's exact framing. `dont-repeat` = a sharper, incident-specific `avoid`. |

---

## 3. The `instincts` page-type (tier-1 artifact)

One append-only file per wiki level, mirroring `log.md`:

- **Project:** `wiki/projects/<project>/instincts.md`
- **Global:** `wiki/instincts.md` (master wiki root)

**Frontmatter (schema_version 1):**
```yaml
---
type: instincts
schema_version: 1
framework_version: "0.1.0"   # stamped by the framework on write
scope: project               # project | global
updated: 2026-06-28
---
```

**Body** — append-only typed entries, newest at the bottom (chronological, like `log.md`):
```
- **[worked]** 2026-06-28 — run each tests/ dir as its own pytest call (basename-collision otherwise).
- **[avoid]** 2026-06-28 — don't put `commit` + a --double-dash flag in one bash command (hook blocks it).
- **[dont-repeat]** 2026-06-28 — Edit on a sed-viewed file fails; Read it first.
```

Template ships at `skills/note/templates/instincts.md.tmpl` (created-on-first-write). Registered in
`skills/wiki-migration/schemas.json` under `page_types.instincts` (`current: 1`, `path_pattern` covering
both `wiki/instincts.md` and `wiki/projects/*/instincts.md`, `owner_module: note`, `migrations: []`).

---

## 4. Capture — `/ren:note --instinct` (extends `skills/note/`)

`note` has real logic in `skills/note/lib/__init__.py` (tests in `lib/tests/test_note.py`), an
`eval/eval.json`, and a contract in `SKILL.md`. C3a extends all three additively.

**CLI surface:**
- `/ren:note <text>` — **unchanged** (session-scratch → `wiki/.session-notes/<session-id>.md`).
- `/ren:note --instinct <kind> <text>` — append a typed entry to the **project** `instincts.md`.
- `/ren:note --instinct <kind> --global <text>` — route to the **master** `instincts.md`.

**lib behavior (new, pure + testable):**
- Parse `--instinct <kind>` (and `--global`); `kind ∈ {worked, avoid, dont-repeat}`, else reject with the valid set.
- Resolve the target path: `--global` → `wiki_path()/instincts.md`; else the current project's
  `wiki/projects/<project>/instincts.md`. **Project resolution reuses the mechanism `wrap`/`recall`
  already use** (resolve in TDD by reading their lib + `lib/sf_paths.py`); **no current project → global +
  an explicit notice.**
- First write to a missing `instincts.md` creates it from the template (frontmatter + header); subsequent
  writes append one bullet and bump `updated:`.
- Stays within `note`'s cheap budget (single append; confirmation line prints the resolved path + scope).

**Contract update (`SKILL.md` frontmatter):** add the `instincts.md` paths to `permissions.write`, an
`--instinct`/`--global` description, and an instinct output to `required_outputs` (conditional on the flag).

---

## 5. Read surface — `/ren:recall --instincts` (extends `skills/recall/`)

`recall` (`skills/recall/lib/__init__.py`, tests in `lib/tests/test_recall.py`) already greps all of
`wiki/**` and scores hits, so `instincts.md` files are **already searchable** with no change. C3a adds:

- `--instincts` flag: restrict results to `type: instincts` pages (and ensure both project + master
  `instincts.md` are in scope). Optional light scoring boost for instinct hits.
- `recall` stays **strictly read-only**. Contract `SKILL.md` gains the flag description.

---

## 6. Page-type batch (ADR-027 — decide the shapes together)

- **`instincts`** — built (this slice): `schemas.json` entry + template + `note` writer + `recall` read.
- **`experiment-log` (B1)** — forward-declared: `schemas.json` entry + `skills/wiki-migration/` template
  with the decided body shape `{change, score_before, score_after, disposition: kept|reverted, iteration,
  ts}`. **No writer** (future B1 slice; eventually the improve-skill loop fills it). Zero instances → no
  `/ren:doctor` drift noise.
- **`verification_strategy` (C2)** — recorded-as-planned: the decided additive field for **`routine-spec`
  v2** is `verification_strategy: visual|test-run|lint|llm-judge|manual` (+ optional `tools:`). Documented
  in ADR-037 + a `schemas.json` annotation; the v1→v2 bump + `/ren:routine-init` elicitation +
  `/ren:doctor` flag is the C2 build, **not migrated here** (it's a field on an existing page-type).

---

## 7. Governance — ADR-037 + amendments

New **ADR-037: Compounding Memory Model** records:
- The **three-tier model** (hot → curated → governed sweep) and that C3a ships **tier 1 only**.
- **Amends ADR-009:** the hot tier is the new bottom layer below the manual `/wrap` consolidate. Capture is
  **explicit + cheap** (a `note` flag), consistent with the no-Stop-hook posture — it does NOT make
  consolidation automatic. The governed sweep (C3b) will be **proposal-diff-gated, never a Stop hook**.
- **Amends ADR-014:** sub-wiki taxonomy + master wiki gain `instincts.md`.
- **Amends ADR-027:** registry gains `instincts` (built) + `experiment-log` (forward-declared); records
  the `routine-spec` v2 `verification_strategy` plan.

---

## 8. Explicit non-goals (C3b / later)

- **No governed LLM consolidate/dedup/promote sweep** (hot→curated). That is C3b; proposal-diff-gated per ADR-031.
- **No `wrap` change** — `wrap`'s classifier + promotion is untouched this slice; it gains instinct-awareness in C3b.
- **No wake-up auto-surfacing** of recent instincts (a natural C3b follow-on; touches the ADR-008 hook).
- **No `experiment-log` writer**; **no `routine-spec` v2 migration/elicitation** (recorded, not built).
- No automatic/inferred capture — instincts are explicit only (keeps the deterministic-classifier discipline, ADR-031).

---

## 9. Testing (TDD) + slice

Run `skills/note/lib/tests/` and `skills/recall/lib/tests/` as their own pytest calls (basename-collision discipline).

**`note` (instinct mode):**
- `--instinct worked <text>` → appends a typed bullet to the project `instincts.md`; file created from
  template (valid frontmatter) on first write; `updated:` bumped on append.
- `--global` → routes to the master `instincts.md`.
- no current project → falls back to global + notice (does not crash).
- invalid `<kind>` → rejected with the valid set; nothing written.
- **plain `/ren:note <text>` regression** → still writes only session-scratch, no instincts touched.

**`recall`:**
- `--instincts` → returns only `type: instincts` hits; both project + master `instincts.md` in scope.
- default `recall` (no flag) → unchanged behavior (regression).

**schema/template:**
- `instincts.md` template validates against the `schemas.json` `instincts` entry.
- `experiment-log` entry is registered and its template parses.

**Slice:** `feat/c3a-instincts` off `feat/project-ingest`; `--no-ff` merge. Wire-up: ADR-037, ADR-009/014/027
amendments, `schemas.json`, CHANGELOG `[Unreleased]`, roadmap C3 row (→ C3a done / C3b pending), `wiki/log.md`.
