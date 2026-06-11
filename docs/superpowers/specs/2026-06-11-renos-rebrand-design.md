# RenOS Rebrand — Design Spec

> **Status:** Approved design (2026-06-11). Brainstormed via `superpowers:brainstorming`. Completes the
> **product-rename** half of roadmap slice **F1** (the namespace *defect fix* `/sf:` already shipped +
> merged; this gives the product its real identity). The mechanical execution is deferred to a
> `superpowers:writing-plans` session that takes THIS spec as input.

---

## 1. The name

**RenOS** — from **仁 (rén)**, the Confucian word for **humaneness**: the irreducible human core of any
system.

- **Product / displayName:** `RenOS`
- **Command namespace (plugin `name`):** `ren` → commands are `/ren:wrap`, `/ren:doctor`, `/ren:install`, …
- **Repo + marketplace id:** `ren-os` → install is `/plugin install ren@ren-os`
- Always brand as **"RenOS"**, never bare "Ren" (pop-culture-noisy: Kylo Ren, Ren & Stimpy).

### Brand story (seed for README + positioning)

> ## RenOS
> *from **仁 (rén)** — the Confucian word for **humaneness**: the irreducible human core of any system.*
>
> Claude Code now ships the muscle — scheduled routines, agent teams, background memory. **RenOS** is
> the thin, governable layer that aims all of it at a single source of truth you actually own: a
> transparent wiki you can read, override, and steer. The machine runs the muscle; **you stay the mind.**
>
> Most memory systems consolidate in the dark and hand you a black box. RenOS keeps the brain in the
> open and in your hands. **Ship the engine — you bring the 仁.**
>
> **Tagline:** *The agentic OS with a human core.*

The 仁 motif is intentional but light — a single framed mention in the README header + the tagline;
not sprinkled everywhere.

## 2. Why this fits the positioning

The framework's thesis (`2026-06-08-nate-herk-ingest-positioning-design.md`): a **governable wiki = single
source of truth + thin glue over Claude Code's native primitives**; *"ship the engine — the user brings
the brain."* RenOS encodes exactly that split: the **OS** is the engine/glue over native muscle; **Ren
(仁)** is the human core the user brings. The name *is* the pitch.

## 3. Availability (checked 2026-06-11)

- **GitHub:** clear — no significant `RenOS` / `ren-os` project. (`ReNO` is an unrelated 2024 ML paper,
  different domain + capitalisation; `RenosCoin` is a dormant 2022 crypto repo.) `ren-os` repo name free.
- **npm:** `renos` is taken (v1.0.5) — **irrelevant**: this is a Claude Code plugin (markdown + Python),
  not an npm package. Only matters if an npm presence is ever wanted → use `ren-os` then.

## 4. The rebrand scope

The transformation is `sf → ren` on the **live surface**, leaving **frozen history** factually intact.

### Flip `sf → ren`

| Area | Specifics |
|---|---|
| **Manifests** | `.claude-plugin/plugin.json`: `name: sf→ren`, `displayName: "Startup Framework"→"RenOS"`, description + keywords → RenOS/second-brain framing. `.claude-plugin/marketplace.json`: top-level `name: sf-marketplace→ren-os`, plugin-entry `name: sf→ren`, descriptions/keywords. Repo URL refs `hazarsozer/sf-marketplace → hazarsozer/ren-os` (homepage/repository fields). |
| **Functional literals** | plugin data-dir `sf-sf-marketplace → ren-ren-os` (= `<plugin-name>-<marketplace-name>`; 3 update scripts + `docs/RECOVERY.md`). Install-id `sf@sf-marketplace → ren@ren-os` (~7 doc lines + `SHIP_CHECKLIST`). `doctor/scripts/check-plugins.sh` cache lookups `sf → ren`. |
| **User-facing `/sf:`** | `README.md`, all 12 `skills/*/SKILL.md` (descriptions + bodies), `skills/install/references/stage-7-walkthrough.md`, `doctor` output strings, the **shipped** `wiki-skeleton/` templates, the current CHANGELOG entry, `docs/` user guides. |
| **Brand copy** | README header + tagline = the §1 story; replace "Startup Framework" displayName everywhere it's user-facing. |

> Skill **directories stay** (`skills/wrap`, `skills/doctor`, …) — the command *verb* is the dir name;
> only the *namespace prefix* (plugin `name`) changes. No `git mv` of skill dirs this time.

### Keep factual (do NOT blind-replace)

These are dated historical records; replacing `sf`/`/sf:` in them would falsify the trail:

- `wiki/log.md` — frozen chronological entries.
- `wiki/decisions/013-*` (the `/sf:` namespace ADR) and any ADR that recorded `sf` — **superseded by a
  new ADR, not edited** (see §5).
- `docs/superpowers/2026-05-31-v1-remediation-report.md`, `docs/superpowers/plans/2026-05-31-*`,
  `docs/superpowers/specs/2026-05-31-*`, `docs/superpowers/specs/2026-06-08-*` — historical artifacts.
- The roadmap's existing **Status log** entries (dated) stay; forward-looking sections may say RenOS.

> **Consequence for the plan:** the raw `grep '/sf:'` count (~2,874 across 321 files) is **not** the
> flip set — it includes the frozen docs above. The execution plan must **curate** the flip set to the
> live/user-facing surface and explicitly exclude the historical paths. This is a careful sweep, not a
> global `sed`.

## 5. Governance — new ADR

File **ADR-033 "Rebrand to RenOS; command namespace `sf → ren`"**, which **supersedes ADR-013** (the
`/sf:` namespace decision). It records: the name + 仁 rationale, the trio (`RenOS` / `ren` / `ren-os`),
the flip-vs-freeze rule (§4), that skill dirs are unchanged, and the pre-republish timing (§6). ADR-013
is marked superseded, not edited.

## 6. Timing

Do the in-repo rebrand **now, before the first re-publish.** The `/sf:` namespace fix was merged but
**never published** (F1 Phase 5 is still pending), so users have never seen `/sf:`. Rebranding now means
`ren` / `RenOS` is the **only** public surface they ever encounter — no churn. This **pairs with Phase 5**:
the re-publish ships `RenOS` as the true first public release.

- The **GitHub repo rename** (`sf-marketplace → ren-os`) is outward-facing → the **maintainer** does it
  on GitHub (which sets up redirects); the plan updates all in-repo URL references so they're ready.
- Local one-time: an installed `~/.claude/data/sf-sf-marketplace/` (if present) moves to `ren-ren-os/`.

## 7. Roadmap placement

Completes **F1's rename intent** (the product-name half). After this lands, F1 = fully done except the
human-gated Phase 5 re-publish, which now publishes RenOS. Does not block the capability slices
(A1/C1/C4…) — but is cheap and high-leverage to finish first since it rides the unpublished state.

## 8. Risks / open items

- **History falsification** — mitigated by the curated flip-set + exclude-list (§4); the plan must
  encode the exclusions, not run a blanket replace.
- **Internal data-dir `ren-ren-os`** is slightly repetitive but invisible to users — accepted.
- **Re-publish dependency** — `/ren:` only reaches users at Phase 5; until then an installed copy shows
  the old surface. Verify empirically (`/ren` autocomplete) after publishing.
- **Test/eval label coupling** — `eval.json#name` fields and `run_evals("wrap")`-style args are decoupled
  labels (not namespaced), so they're unaffected; the plan confirms with a green test sweep + `claude
  plugin validate --strict`, mirroring the Phase-4 gate.

## 9. Next step

`superpowers:writing-plans` on this spec → a mechanical rebrand execution plan (curated `sf→ren` sweep +
manifests + functional literals + ADR-033 + the green-gate verification), to run before Phase 5.
