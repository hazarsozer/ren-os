# F1 — Foundation + Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended)
> or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`)
> syntax for tracking.

**Goal:** Make the shipped v1.0 plugin correct, renamed to the working `/sf:` command namespace, and
repositioned toward the second-brain-OS framing — the foundation every later rebuild slice builds on.

**Architecture:** F1 is **not a rewrite.** It executes the existing, fully-specified **Plan B**
(`docs/superpowers/plans/2026-05-31-v1-remediation.md` — 108 steps, TDD, no placeholders) **end to
end, in its existing order**, with **three pivot deltas** layered on top. Re-authoring Plan B's tasks
here would violate DRY and risk drift; this document is the authoritative *delta + sequencing* over it.

**Tech Stack:** Python 3 stdlib (`uv run pytest` per skill dir), Bash test scripts, JSON manifests,
`claude plugin validate --strict`. No new dependencies.

**Roadmap position:** Slice **F1** in `docs/superpowers/plans/2026-06-11-agentic-os-rebuild-roadmap.md`
(the universal unblocker — every later slice inherits the `sf` namespace this lands).

---

## ⚠️ Authoritative decisions (read before any task)

1. **Execute Plan B verbatim except where a DELTA below says otherwise.** Plan B's "Review
   Corrections & Decisions" block (its lines 13–68) remains authoritative — including **namespace
   LAST** (Phases 1–3 on current `skills/sf-*` paths, rename in Phase 4, re-verify/publish in Phase 5),
   **`wiki-migration` dir kept**, **kickoff field dropped**, **`alternatives/` removed from skeleton
   manifest**, and the **worktree** instruction.
2. **Command namespace = `sf`.** Plan B Task 4.2 sets `plugin.json` `name: startup-framework → sf`,
   resolving the ADR-013 defect so commands ship as `/sf:wrap`. No change.
3. **`displayName` = "Startup Framework" is KEPT.** A product rebrand is deferred (see roadmap §Naming).
   F1 repositions *messaging only*.
4. **This is a foundation slice — no new capabilities.** Do not pull cadence/memory/code-map work into
   F1; those are slices C1–C5/H1–H2.

---

## The three deltas over Plan B

### DELTA-1 — SKIP Plan B Task 2.8 (standalone)
Plan B **Task 2.8** ("Replace friend-group framing with solo-first," its lines 857–882) does a surgical
`friend → builder` token swap in the manifests. **Do not run it as written.** Its goal (purge the
pre-pivot framing) is **absorbed and superseded** by DELTA-2, which rewrites the same lines toward the
second-brain-OS positioning in one stroke. Running both would double-edit the same lines.

### DELTA-2 — NEW Task 4.2b: Positioning-messaging refresh
A new task inserted in Phase 4 **immediately after Plan B Task 4.2** (same manifest files, post-rename).
Fully specified below. It repositions the public description + keywords in both manifests + the README
tagline, and verifies the pre-pivot framing tokens are gone (subsuming DELTA-1's intent).

### DELTA-3 — Naming confirmed, product rebrand deferred
Namespace `sf` (DELTA via Plan B 4.2) is the only naming change in F1. The product/brand rename is
**out of scope** for F1 (roadmap §Naming). When Phase 5 Task 5.2 writes the `[1.1.0]` CHANGELOG entry,
add one line noting the positioning reframe (see DELTA-2 Step 5).

---

## Execution sequence (Plan B, annotated)

Run Plan B's tasks in this exact order. ✅ = execute as written in Plan B; ⛔ = skip; ➕ = new task here.

| Phase | Tasks | Action |
|-------|-------|--------|
| **1 — Python correctness** | 1.1, 1.2, 1.3, 1.4, 1.5, 1.6 | ✅ all as written |
| **2 — Doc/contract drift** | 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7 | ✅ as written |
| | **2.8** | ⛔ **SKIP** (DELTA-1 — absorbed by 4.2b) |
| **3 — Security/privacy** | 3.1, 3.2, 3.3 | ✅ as written |
| **4 — Namespace rename** | 4.1, 4.2 | ✅ as written |
| | **4.2b** | ➕ **NEW — DELTA-2 (full spec below)** |
| | 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9 | ✅ as written (4.9 verification gate now also covers 4.2b's files) |
| **5 — Re-verify + publish** | 5.1, 5.2 (➕ positioning line), 5.3 | ✅ as written (+ DELTA-2 Step 5) |

> **Conflict check:** DELTA-2 touches only `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
> and `README.md`. Task 4.1 renames `skills/` dirs (not these files); Task 4.2 edits the manifests' `name`
> field on different lines (3 / 12) than DELTA-2's description+keywords. No overlap. Plan B Task 2.7 edits
> a different README line (the CC version floor) than DELTA-2's tagline. Clean.

---

## ➕ Task 4.2b: Positioning-messaging refresh (the one net-new task)

**Files:**
- Modify: `.claude-plugin/plugin.json` (description line 6, keywords lines 14–21)
- Modify: `.claude-plugin/marketplace.json` (top description line 4, plugin description line 14, keywords lines 22–29)
- Modify: `README.md` (opening tagline, lines 3–5)

> **Nature:** mechanical edit + verification gate (not red-green TDD — manifests aren't unit-tested;
> they're gated by `claude plugin validate --strict` + a remnant grep, matching Plan B's house style
> for manifest tasks). Runs in Phase 4 after the `name` flip (4.2), so it edits the already-renamed manifests.

- [ ] **Step 1: `plugin.json` description (line 6)** — keep the functional drift note; reposition the lead clause.

```
# .claude-plugin/plugin.json line 6
-  "description": "Per-friend wiki + curated stack + self-improving skills. The plugin's source-of-truth version lives in this field; the marketplace entry omits version to avoid drift (per CC docs, plugin.json wins silently when both are set).",
+  "description": "A governable second-brain OS for Claude Code — a compounding wiki as your single source of truth + thin glue over native primitives (Routines, Memory, Agents). The plugin's source-of-truth version lives in this field; the marketplace entry omits version to avoid drift (per CC docs, plugin.json wins silently when both are set).",
```

- [ ] **Step 2: `plugin.json` keywords (lines 14–21)** — drop `friend-group`/`ideation`/`startup`; add the positioning terms.

```
# .claude-plugin/plugin.json keywords array
   "keywords": [
     "wiki",
     "memory",
-    "friend-group",
-    "startup",
-    "ideation",
+    "second-brain",
+    "agentic-os",
+    "knowledge-base",
     "claude-code"
   ],
```

- [ ] **Step 3: `marketplace.json` descriptions (lines 4 and 14)**

```
# .claude-plugin/marketplace.json line 4 (top-level marketplace description)
-  "description": "Startup Framework — private friend-group distribution. Per-friend hierarchical wiki + curated plugin stack + self-improving skills.",
+  "description": "Startup Framework — a governable second-brain OS for Claude Code. A compounding wiki as your single source of truth + thin glue over native primitives. Solo-first, fully local — you own the brain.",
```
```
# .claude-plugin/marketplace.json line 14 (plugins[0].description)
-      "description": "Per-friend hierarchical wiki + curated plugin stack + skill self-improvement. See README.md for the full feature surface.",
+      "description": "A governable second-brain OS for Claude Code: a compounding wiki (your single source of truth) + thin glue over native primitives (Routines, Memory, Agents). See README.md for the full feature surface.",
```

- [ ] **Step 4: `marketplace.json` keywords (lines 22–29)** — match plugin.json.

```
# .claude-plugin/marketplace.json plugins[0].keywords array
       "keywords": [
         "wiki",
         "memory",
-        "friend-group",
-        "ideation",
-        "startup",
+        "second-brain",
+        "agentic-os",
+        "knowledge-base",
         "claude-code"
       ],
```

- [ ] **Step 5: `README.md` tagline (lines 3–5)** — reposition the opening blockquote. Leave the body
  (the Four C's section, the "friends each run their own copy" solo-first note) for a later content pass.

```
# README.md lines 3-5
-> A private Claude Code plugin that turns every session into a compounding system:
-> a per-project hierarchical wiki (long-term memory) + a curated plugin stack +
-> self-improving skills — all wired into one daily loop.
+> A governable second-brain OS for Claude Code: a compounding wiki as your single
+> source of truth + thin glue over native primitives (Routines, Memory, Agents).
+> Ship the engine — you bring the brain.
```

- [ ] **Step 6: Verify the pre-pivot framing is gone + manifests still valid**

Run:
```bash
grep -rn 'friend' .claude-plugin/                       # expect: NO output (rcChannel "Friends" is capital-F, unmatched)
grep -rn 'friend-group\|Per-friend\|per-friend' .claude-plugin/ README.md   # expect: NO output
claude plugin validate ./ --strict                      # expect: OK
```
Expected: all three clean. (If `grep 'friend'` hits `plugin.json` line ~48 `rcChannel` "Friends who
want early access" — that is capital-F and won't match a lowercase `friend` search; if a lowercase
remnant appears, fix it before commit.)

- [ ] **Step 7: Commit**

```bash
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json README.md
git commit -m "docs(positioning): reframe manifest + README messaging to second-brain OS"
```

- [ ] **Step 8: Phase-5 CHANGELOG note (deferred to Plan B Task 5.2)** — when Task 5.2 writes the
  `[1.1.0]` entry, add under `### Changed`:
  `- Repositioned plugin/marketplace messaging toward the governable second-brain-OS framing (namespace defect fixed: commands now ship as /sf:*).`

---

## Self-review / spec coverage

- **Spec coverage (vs. the pivot's "re-scope Track B"):** ✅ Plan B's STILL-VALID ~80% executes
  unchanged (Phases 1–3, 5 + rename Phase 4). ✅ The one wasted item (2.8) is folded (DELTA-1 + 4.2b).
  ✅ Namespace defect (spec §7 "namespace stays short") resolved via Plan B 4.2 = `sf`. ✅ Positioning
  reframe (spec §7) landed via 4.2b without committing to a product rename (deferred per roadmap).
- **Placeholder scan:** none — DELTA-2 ships exact before/after for every line; all other work is
  Plan B's already-complete tasks referenced by ID.
- **Type/consistency:** the only new identifiers are JSON string literals + keyword tokens; the `sf`
  namespace value matches Plan B Task 4.2 (`name: "sf"`). README tagline language mirrors the roadmap
  thesis verbatim ("second-brain OS", "single source of truth", "thin glue over native primitives",
  "ship the engine — you bring the brain").
- **Ordering safety:** DELTA-2 sits after 4.2 (post-rename), edits non-overlapping lines vs. 4.1/4.2/2.7,
  and is re-checked by Plan B's Task 4.9 verification gate + Task 5.1 full sweep.

---

## Done when

- All Plan B Phase 1–5 tasks green at the renamed `skills/<verb>` paths (Plan B Tasks 4.9 + 5.1 gates).
- `claude plugin validate ./ --strict` passes; `grep -rn 'friend' .claude-plugin/` is empty.
- `/sf:` autocomplete confirmed at install (Plan B Task 5.3) before the human-gated publish.
- Version bumped to 1.1.0 with the positioning line in the CHANGELOG.
