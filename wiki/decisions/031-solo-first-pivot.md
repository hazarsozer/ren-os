---
title: "ADR-031: Solo-First Pivot — Remove the Activity Feed; Reorganize Under the Four C's; Ship a Deterministic Classifier"
status: accepted
date: 2026-05-30
sunset-review: 2027-05-30
references-pages: [nate-herk-ai-os, py-harness-engineering, codex-review, simon-scrapes-self-improving-skills]
affects-components: [feed, hooks, wake-up, consolidate, install, onboarding, interview, doctor, distribution, schemas, lib, skills, docs]
relates-to: [008-wake-up-hook, 009-consolidate-via-wrap, 011-skill-schema, 014-project-sub-wiki-taxonomy, 027-schema-versioning, 029-test-against-real-contract-instances, 030-test-installed-runtime]
supersedes: [017, 018, 020, 021]
amends:
  - "ADR-015 (Onboarding): Stage 3 is no longer Activity-Feed setup — it is conditional-plugins-only; Stage 4 writes only wiki/identity.md (no feed identity push/rename). `gh` stays a soft requirement, reframed as /sf:doctor's update check."
  - "ADR-019 (Framework Distribution): the 4-repo distinction (marketplace / activity-feed / dev-wiki / friend-wiki) collapses to 2 (marketplace / per-friend wiki). No activity-feed repo."
  - "ADR-022 (Identity Interview): the interview keeps the `handle:` field (reframed as a personal short-name) but no longer pushes a public summary to a shared feed. No feed identity sync."
  - "ADR-023 (V1 Scope Fence): the Activity Feed is no longer a built-in v1 feature; it is a deferred layer (see Preservation)."
  - "ADR-028 (Locked Build-Time Contracts): the split feed-write API and FEED_LOCAL_ONLY_FILES contract are retired with the feed module. The framework-root / wiki-path / handle / schema contracts move to lib.sf_paths (unchanged semantics)."
  - "ADR-030 (Test the Installed-Plugin Runtime): the installed-runtime test is now C1-only (wiki injection). The C2 feed-load assertion is removed; the CLAUDE_PLUGIN_OPTION_WIKIROOT tier is promoted to the headline F1 test."
---

# ADR-031: Solo-First Pivot

## Context

The startup-framework was designed as a multi-user "friend group" plugin whose only cross-friend layer was the **Activity Feed** (ADR-018: shared GitHub repo of per-friend `<handle>.log.md` logs, written by `/sf:wrap`, read by the wake-up hook). It reached SHIP-READY, then an independent **Codex review** (`wiki/codex-review.md`) surfaced seven findings (F1–F7). Four of the seven were entirely about the feed (F3 wiki-files-as-feed-attribution, F4 handle path-traversal, F6 privacy-doc drift) or were dominated by it (F1 `wikiRoot`/`activityFeedLocalClone` options ignored by the feed config layer).

Separately, we ingested **Nate Herk's "Building an AI Operating System on Claude Code"** (`wiki/research/nate-herk-ai-os.md`), which independently validated the framework's whole thesis (files-and-folders context + skills + cadence) and offered three framings we adopt below.

Two facts forced a reframe:

1. **The builder is solo.** There is no friend group. The Activity Feed is speculative complexity built for a user base that does not exist — the textbook YAGNI. It is also the single largest source of the remaining ship risk (the four feed-related Codex findings).
2. **The feed is load-bearing in the wrong way.** `feed/config.py` owned not just feed helpers but the framework-root / wiki-path / handle / schema resolution the *whole* framework imports (the wake-up hook, `/sf:recall`, `/sf:wrap`, the install conftest, `wiki-migration`'s version parity). A naive `git rm feed/` would have broken five non-feed consumers.

## Decision

**Pivot to a solo-first base framework.** Remove the Activity Feed / multi-user layer from the *shipped* framework. Multi-user becomes a **deferred** layer, preserved in git history + a baseline tag, **not rebuilt now**.

Concretely:

1. **Extract the load-bearing core first, then delete the feed.** The framework-root / wiki-path / handle / schema resolution moves out of `feed/config.py` into a new top-level **`lib/sf_paths.py`** — the durable single source of truth. `feed/config.py` became a thin shim, then `feed/` was removed wholesale. This *is* the F1 fix: `wiki_path()` now resolves three tiers (`SF_WIKI_ROOT` → `CLAUDE_PLUGIN_OPTION_WIKIROOT` → `framework_root()/wiki`) independently of `framework_root()`, so the advertised `wikiRoot` plugin option is honored on its own (closing the latent split where the Python reader silently read the *default* wiki).

2. **Remove every feed surface.** The `feed/` module, the feed-only skills (`activity-feed`, `sf-catch-up`, `sf-disable-feed`), the `/sf:wrap` feed-write glue, and the feed-entry schema page-type are all deleted. `/sf:wrap` is now wiki-only; the wake-up hook is pure wiki injection; `/sf:recall` greps the local wiki only; `/sf:doctor` no longer checks a feed; the installed-runtime test is C1-only.

3. **Reorganize under Nate's Four C's** (Context → Connections → Capabilities → Cadence) as the organizing spine, and adopt three of his framings:
   - **"Keys ≠ instructions"** — a README promise of "quiet by default" is just an *instruction*; capabilities are what actually run. This motivates a read-only **permission audit** (`/sf:doctor --permissions`, the Connections layer) and sharpens the privacy posture: there is no automatic push to surface anymore, because there is no feed.
   - **"Bike method"** (phased, earned trust) — the cleanest argument for shipping the `/sf:wrap` classifier and `/sf:improve-skill` as **EXPERIMENTAL** (training wheels stay on until real runs earn autonomy).
   - **Four C's** as legibility — better *words* for the structure we already have.

4. **F2 → a deterministic default that actually works.** `/sf:wrap`'s `classify()` (previously a `NotImplementedError` stub whose default path crashed) is now a **conservative deterministic heuristic** (EXPERIMENTAL): it scans the combined transcript (session log + `/sf:note` pins; pins dominate) for deliberate, word-boundary signal phrases, biases hard to `none`, never raises, and proposes artifacts only for fired `decision`/`pattern`. It takes **no file-change-count input** — that input is what produced the F3 confusion (wiki-maintenance files mislabelled as project files). The LLM classifier path (`build_classifier_prompt` + `parse_classifier_output`) is kept as composable primitives for a future upgrade.

## Codex findings → fate

| Finding | Fate under solo-first |
|---|---|
| F1 (plugin options ignored) | **Fixed** as the `lib/sf_paths.py` extraction + 3-tier `wiki_path()`. |
| F2 (production-default stubs) | **Fixed**: deterministic classifier for `/sf:wrap`; honest fail-fast for `/sf:improve-skill` (separate commit). |
| F3 (wiki files as feed attribution) | **Mooted** by feed removal. The classifier deliberately takes no file-change input. |
| F4 (handle path-traversal across feed APIs) | **Mooted** by feed removal (no feed write paths). Handle validation stays in `lib.sf_paths`. |
| F5 (publish copies ignored artifacts) | **Fixed**: `publish.sh` snapshots tracked files via `git ls-files` + an artifact guard. |
| F6 (feed privacy-doc drift) | **Mooted** by feed removal. |
| F7 (unquoted `attribution:` YAML) | **Fixed**: value quoted; `lint-yaml-frontmatter.py` exits 0. |

## Structural decisions made during implementation

Recorded here because they are load-bearing and were not in the original brief:

- **`hooks/wake-up/lib` → `hooks/wake-up/wakeup` rename.** A repo-root `lib/` package and a hook-local `lib/` package cannot coexist as top-level names on one `sys.path` — once the plugin root is inserted, a bare `from lib import compose_wake_up_context` would resolve to repo-root `lib` and shadow the hook helper. Renaming the hook package to `wakeup` makes both `import lib.sf_paths` and the hook's compose import unambiguous.
- **Feed removal was made atomic in one commit** (module + feed-only skills + the `/sf:wrap` feed-write glue + the installed-runtime C1-only rewrite) rather than the originally-planned three-commit split. The split would have left intermediate commits RED (the feed-import guard non-empty, the installed-runtime fixture materializing a deleted `feed/`, sf-install/sf-wrap tests broken by half-removed APIs). Atomic removal keeps every commit green and the `grep "from feed|import feed"` guard empty at every step.
- **The wake-up hook's `_resolve_wiki_root()` now delegates to `lib.sf_paths.wiki_path()`** (with a defensive inline fallback), so the Python reader and the shell scripts share one resolver.

## Preservation (not deletion)

The full pre-pivot tree — including the complete Activity Feed implementation, the feed-only skills, and the multi-user wiki layer — is preserved in:

- the **`baseline-v1.0-full-wiki`** git tag, and
- the branch's git history prior to the solo-first commits.

Multi-user can return as a deferred layer without re-deriving it from scratch. There is **no schema migration**: the `feed-entry` page-type is **retired**, not migrated — there are no feed files in a solo install to migrate, and the type is removed from `schemas.json` (so `compute-migration-chain.sh` never walks it).

## Alternatives rejected

1. **Keep the feed, just fix the four findings.** Rejected: it hardens speculative complexity for a non-existent user base and leaves the largest ship risk in place. YAGNI.
2. **Replace the feed with a lighter cross-user plugin now.** Rejected: still speculative; solo-first means *no* cross-user layer until there is a second user.
3. **Delete `feed/` wholesale in one step.** Rejected: breaks five non-feed consumers of `feed.config`. The extract-then-delete sequence (`lib/sf_paths.py` first) is mandatory.
4. **Keep `classify()` as a stub and mark the skill experimental.** Rejected: the default path *crashed* (the stub raised, and `/sf:improve-skill`'s baseline eval ran before the proposer's clean exit). A deterministic default that works — even modestly — is the honest minimum (F2).

## Consequences

- The ship gate drops from seven Codex findings to four local, deterministic, low-risk ones (F1′, F2, F5, F7) — all resolved by this pivot's commits.
- The framework gains legibility (Four C's), a permission audit, a session-insights skill, and a `/sf:wrap` default path that actually runs.
- ADRs 017/018/020/021 are **superseded** (the per-friend-wiki *sharing* posture, the feed itself, the joiner/leaver experience, and the feed privacy boundaries no longer describe the shipped framework). ADRs 015/019/022/023/028/030 are **amended** (they bake in feed specifics alongside still-valid non-feed contracts; see frontmatter).
