# Video-Ingest Improvements — Synthesis (2026-06-21)

> Produced by the overnight autonomous loop. Three YouTube videos ingested (yt-dlp auto-captions → cleaned transcripts), one analysis subagent each, grounded on the RenOS thesis + the already-built/parked/out-of-scope lists. This is the **parked menu** of net-new worthy improvements for your review — none were auto-built (see § Why all parked).

## Sources
| ID | Title | Channel |
|----|-------|---------|
| 7zZy1QTvokM | Stop Prompting Claude. Use Karpathy's Method Instead. | Austin Marchese |
| 4JpwNnw0-jI | This "Karpathy System" could 701x your AI Workflows (86K stars) — *Auto Research* | Dream Labs AI |
| EuzYhzB0vbI | Finally. Agent Loops Clearly Explained. | Nate Herk |

## Why all parked (not auto-built)
Your policy was *build worthy+safe, spec-and-park the big ones*. On scrutiny, **every** surviving worthy idea touches a **governed surface**: the **ADR-036 self-improvement/eval engine** (5 of 7), a **new page-type / schema change** (experiment-log; routine-spec field — ADR-027/N+3 deprecation), or **hook infrastructure** (path-guard). None is a cleanly-isolated module. They also form **one coherent theme** — *harden + extend the self-improvement loop* — best sequenced together rather than piecemeal-built into the framework's most delicate subsystem overnight. Hence: parked as a menu with a recommended build order. The two Karpathy videos largely re-derive RenOS's existing bike-method (ADR-036); the genuinely net-new parts are below.

---

## Theme A — Harden the eval loop (all touch ADR-036)

### A1. Tamper-proof "locked scorer" (anti-Goodhart) — HIGH VALUE
- **What (4JpwNnw0-jI):** Karpathy's Auto Research splits the eval into a *separate, agent-inaccessible* file — the improver agent optimizes the asset but **cannot read/edit the scoring logic**, preventing "optimize the score, not the goal." RenOS's eval judge currently runs in the same context as the skill-writing subagent.
- **Touches:** ADR-036 amendment (tamper-isolation as a first-class invariant) + possibly a `skill-rubric` sub-page the improver is never handed.
- **My take:** the single most valuable idea here — it directly serves the *governable, trustworthy* self-improvement thesis. Recommend building **second** (after the cheap gate below), as an ADR-036 amendment.

### A2. Cross-model critic (`--critic-model`)
- **What (7zZy1QTvokM):** a *second, different* model as the eval critic ("run the final output by Codex/Gemini; only ship if both agree") — catches what the generating model misses.
- **Touches:** ADR-036 (two-phase judge contract) + a CLI/MCP call-out (could reuse the existing Gemini token-saving pattern in `Dev/CLAUDE.md`).
- **My take:** worthy; pairs naturally with A1 (a locked scorer judged by a *different* model is strongly anti-Goodhart). ADR-036 amendment.

### A3. Eval-readiness fit-check gate — LOWEST RISK
- **What (4JpwNnw0-jI):** before an improve-skill run, check the six Auto-Research preconditions (objective metric, fast feedback, write access, high-volume signal, cheap-to-fail, consistent measuring stick). Abort early on subjective/slow-to-score skills to avoid wasted eval-run budget.
- **Touches:** improve-skill preflight (ADR-012/036 gate set) — a warning gate, additive.
- **My take:** the cheapest + safest of the set; a natural 7th preflight gate. **Recommend building first** on greenlight.

### A4. Eval-reference exemplar (`--reference <wiki-path>`)
- **What (7zZy1QTvokM):** pull a past artifact (e.g. last month's report) into the judge prompt as a "this is what good looks like" exemplar for format/quality grounding.
- **Touches:** the eval judge prompt (ADR-036 eval design) — additive flag.
- **My take:** worthy, low-ish risk; bundle with A3 as the "cheap eval-loop polish" pair.

## Theme B — Compound the improvement history

### B1. Experiment-log as a wiki artifact (new page-type)
- **What (4JpwNnw0-jI):** Auto Research keeps a human-inspectable log of every variant tried + score + kept/discarded. RenOS tracks eval scores ephemerally (printed, not persisted).
- **Touches:** **NEW page-type** (`skill-experiments`) or a skill-page appendix — schema change, ADR-027 N+3 commitment.
- **My take:** strongly aligned with "governable compounding" (auditable improvement history) — but it's a page-type decision (same class as C3's parked `instincts` page-type). Sequence it **with C3's page-type batch** so you decide page-types together.

## Theme C — Glue / safety

### C1. Protected-path PreToolUse guard (`ren:guard`)
- **What (7zZy1QTvokM):** "a CLAUDE.md rule is a request; a hook is a rule." A PreToolUse hook hard-blocks Edit/Write/Bash against a user-declared `protected_paths` manifest.
- **Touches:** hook infrastructure (sf-lifecycle; adjacent to ADR-008) + a config convention + an install-interview question ("always / ask-first / never-do" buckets).
- **My take:** generically useful but only loosely tied to the wiki-SSOT thesis; it's a CC-safety feature. Lower priority. Build only if you want the guardrail UX.

### C2. `verification_strategy` field on routine-spec page-type
- **What (EuzYhzB0vbI):** Nate's "the loop is only as good as its done-check" → add a `verification_strategy: visual|test-run|lint|llm-judge|manual` (+ `tools:`) field to the existing `routine-spec` page-type, elicited by `/ren:routine-init`; `/ren:doctor --wiki-health` flags routines missing it.
- **Touches:** schema change to an existing page-type (ADR-027) — small but governed.
- **My take:** clean and useful; nicely extends H1's WIKI-HEALTH check. Sequence with the page-type/schema batch.

---

## Recommended build order (on greenlight)
1. **A3 + A4** (eval-readiness gate + reference exemplar) — ✅ **BUILT 2026-06-27** (`feat/eval-loop-polish-a3a4`): advisory readiness gate (`preflight.eval_readiness_notes`) + opt-in `--reference` exemplar (`eval_runner.load_reference_exemplar`); strictly additive, ADR-036 amended, improve-skill 190+1skip.
2. **A1 + A2** (locked scorer + cross-model critic) — the high-value anti-Goodhart pair; one ADR-036 amendment + slice.
3. **B1 + C2** (experiment-log + verification field) — batch with C3's page-type/schema decisions (decide all page-types at once, per ADR-027).
4. **C1** (path-guard) — optional, only if you want the guardrail UX.

## Cross-checked & rejected (already built/parked/out-of-scope)
Agile-specking, hard-stop caps, dedicated-scorer subagent, multi-agent swarms, RAO-loop mechanics, 24/7 agents — all duplicate the existing bike-method (ADR-036/C5), the cadence ladder (C4), the parked multi-agent orchestration, or the no-daemon out-of-scope line (ADR-003).
