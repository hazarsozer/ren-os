# Changelog

## [0.8.0] - 2026-08-18 — "knowledge flows live"

The live-gate + distiller train: wire the classifier subagent into the wrap
pipeline (verdicts as data), fix the die-loudly fail path to catch scope-None
bugs and suggest unplaced items, build the wiki-distiller agent and weekly
routine to re-mine quarantined L1s, and instrument both paths with per-
producer outcome events and metrics. Plan: `docs/superpowers/specs/2026-08-18-knowledge-flows-train-design.md`.

- **Part A — wrap verdicts-as-data + die-loudly routing:** `wrap_session()`
  gains a `verdicts=` parameter for pre-computed classifier decisions (enabling
  the one-shot `uv run` flow), validated against the same shape rules as
  `classify_llm`. Scope-`None` placement bugs and classifier subagent spawn
  failures now route to the suggestions store instead of being silently
  gated out.
- **Part B — ren:ren-distiller agent, distill skill, and weekly routine:**
  New worker-class agent mines L1 narratives (including quarantined ones)
  and re-processes durable items that died to `no_llm` in live wraps,
  applying the same classifier discipline and write-door path. Watermark
  tracks last processed L1; write cap is 10 per run with carry-over logged.
- **Part C — instrumentation:** `durable_outcome` events gain a `producer`
  field (wrap | distiller), new `distiller_run` event logs mining results,
  and `metric-watch` adds `no_llm` to its watch list for wraps with
  candidates (deterministic-fallback signal).

## [0.7.9] - 2026-08-18 — "doctrine holds"

The proof-case train: run end-to-end through the full canonical route
(brainstorm → worktree → writing-plans → subagent-driven development with
per-task reviews on class-routed models → whole-branch review → finish),
fixing the three gaps that let sessions drift from that route in the
first place. Plan: `docs/superpowers/plans/2026-08-18-doctrine-holds-train.md`.

- **#69 — the guards close the generator's bypasses.** `_GIT_PUSH_RE` and
  `_RM_RE` treat `\n` as a command separator (matching the bash-wiki-write
  check), and `_has_force_refspec` strips shell quotes AND leading
  backslashes before the `+` test — `'+main'`, `"+main"`, and `\+main`
  are all forced updates once the shell is done with them. The 10 strict
  xfails pinning these in the #68 generated corpus flipped to plain green
  assertions, plus a backslash shape added. Known tradeoff (recorded
  ruling): quoted text containing a newline followed by `git push …` or
  `rm …` — e.g. a commit-message heredoc quoting those commands — now
  triggers the guards; reword the text or use a plain `-m` message.
- **#70 — the doctrine card carries the whole pipeline.** Both card
  variants (full and compact fallback) now render the seven-phase route —
  brainstorm, isolate & plan (worktree + `superpowers:writing-plans`),
  decompose, dispatch (`superpowers:subagent-driven-development`,
  test-first, class-routed subagents per `doctrine/model-classes.md`),
  per-task review, the `ren-reviewer` gate, finish — with skill names
  preserved even in the compact variant (742 chars, survives band-low
  ratios intact). `DOCTRINE_BUDGET` 500 → 650 so the full card actually
  fits its own budget. Model names never appear; classes only (test-pinned).
- **#71 — wake-up respects the harness byte cliff.** The composer renders
  to a byte ceiling (default 9,500, `REN_WAKEUP_BYTE_CEILING` override)
  under the harness's ~10KB persist threshold, orders sections by
  irreplaceability (doctrine → Waiting-on-you → identity/overview → open
  work → L1 → L2 → routines → extras), degrades tail-first when over
  (extras to pointers, then dropped, then one section up at a time —
  protected sections never touched), and opens with a sentinel line
  telling any session that does see a persisted-file preview to Read the
  full file first. The #48 token guard now folds into the same keyed
  cascade instead of collapsing the body (whole-branch review HIGH), and
  `log_surface` only records pages whose content actually survived the
  final payload — no more fake recall hits from dropped sections.

## [0.7.8] - 2026-08-18 — "sharper guards"

The post-0.7.7 fix train: every open issue was first verified against the
live tree (two were found already fixed and closed with evidence — #54,
#55), the five survivors were brainstormed, specced
(`docs/superpowers/specs/2026-08-18-post-0.7.7-fix-train-design.md`),
planner-decomposed, implemented TDD in parallel, and adversarially
reviewed (one HIGH found and fixed before approval).

- **#67 — apply_integrity learns recorded exemptions.** The doctor's
  journal↔queue reconciliation now consults
  `_APPLY_INTEGRITY_EXEMPT_SESSIONS` (session-id → recorded reason),
  seeded with `install` and the 2026-08-04 fixtrain-remediation session
  whose 8 write_ids bypassed queue persist by design. Unknown-session
  orphans still warn.
- **#62 — Live pins can no longer invite deleting the wiki spine.**
  `live_pin_pages()` stops letting an `op=UPDATE` entry introduce a
  listing (the two #58 restoration writes to `log.md`/`identity.md` no
  longer render at every wrap), and `pin.correct()` hard-refuses
  deletion of spine pages (`log.md`, `identity.md`, `index.md`, any
  `map.md`) regardless of `approved_by` — with casefolded,
  dot-segment-normalized matching after review caught a `Log.md` alias
  bypass on case-insensitive APFS.
- **#50 — one calibration acceptance rule, everywhere.**
  `MIN_CALIBRATION_SAMPLES` (5) and `PLAUSIBLE_RATIO_BAND` now live once
  in `lib/instrument/estimator.py`; estimate-side reads go through
  `_accepted_ratio` while `calibrate()` keeps the raw read so sub-floor
  blending still accumulates. Wake-up imports the shared constants;
  `calibration.py` re-exports the band for back-compat.
- **#38 — wiki-health heuristics stop crying wolf.** The contradiction
  pass excludes pointer lines (via `lib.pointer.parse_pointer_line`)
  from both sides and skips identical pairs; cross-page numeric drift is
  scoped to same-project subtrees. Both live false positives from the
  issue are reproduced in tests and confirmed silent; true positives
  stay covered.
- **#68 — the guard matrix meets a generator.** New
  `tests/hooks/test_guards_generated.py`: 1316 deterministic
  itertools-built cases (guarded shapes × separators × quoting,
  runtime-assembled) against a segment-level oracle, ~1.6s. It
  immediately caught two real guard bypasses — newline-prefix segments
  evade the push/rm separator anchoring, and a quoted `+refspec` evades
  force detection — pinned as 10 strict xfails and filed as #69.

## [0.7.7] - 2026-08-18 — "quiet signals"

The polish batch after the pre-handoff train: four long-open noise and
paper-cut issues, sized in chat (no spec doc) and approved 2026-08-18.

- **#49 — an unchanged wrap re-run says so.** `wrap_session`'s result now
  carries `l1_status`; when the L1 dedups to the synthetic never-persisted
  `noop-duplicate` entry, the wrap screen renders "session summary:
  unchanged (already saved)" instead of the misleading "(not found)" —
  which stays for genuinely missing entries.
- **#29 — scrub stops calling code a credential.** The `password-pair`
  pattern's value side now requires a secret-shaped RHS: a quoted string
  (≥6 chars) or an unquoted token that is not a call expression or a whole
  type-annotation identifier; pure numbers are additionally exempt for
  `token`/`api_key` keys only (tuning constants), never for
  `password`/`secret` (a digits-only password is a PIN). A `page_token`
  assigned from `locks.content_token(...)`, a `CHARS_PER_TOKEN`-style
  numeric constant, a `MAX_TOKENS` limit, and a type-annotated
  `chars_per_token` default no longer trigger `SecretsFound`; quoted,
  env-style, guard-word-prefixed (`none.of.your.business`), and
  numeric-PIN secrets still do (all pinned by tests, incl. the review's
  adversarial probes).
- **#31 — doctor stops scanning frozen snapshots.** New shared predicate
  `ren_paths.under_ren_state(path, wiki_root)`; `check_dangling_pointers`
  skips everything under `wiki/.ren/`, so immutable per-write snapshot
  copies can't bury real dangling pointers in live pages.
- **#33 — harness_neutrality scoped to scaffolding.** The neutrality walk
  also skips `.ren/` state, and the doctor check partitions its findings:
  coupling in AGENTS.md (the surface we generate for portability) stays a
  `warn`; harness tokens inside live L2-map *content* — project knowledge
  that legitimately mentions Claude/Anthropic — report as `info`. New
  `lint_generated_surfaces_partitioned`; the flat function keeps its shape.
- **#34 — the snapshot root has one home.** The update scripts
  (`snapshot.sh`/`restore.sh`/`prune-snapshots.sh`) resolve
  `${REN_SNAPSHOT_ROOT:-~/.claude/plugins/data/renos}` and no longer
  advertise `${CLAUDE_PLUGIN_DATA}` — observed live rendering to a
  directory (`data/ren-ren-os/`) that exists but has never received a
  snapshot, because the var is unset in the shell that runs the scripts.
  SKILL.md and the migration READMEs now name the real path, so the
  mid-incident restore flow points where the snapshots actually are.

## [0.7.6] - 2026-08-17 — "first impressions"

The pre-handoff train, release 2 of 2: the polish a fresh install sees
first. Spec: docs/superpowers/specs/2026-08-17-pre-handoff-fix-train-design.md
(Release 2) + the #66 rider from 0.7.5's final review.

- **#36 — doctor names the colliding directory.** `agent_shadowing`'s
  skip/warn messages now say which scope holds the collision — "user" or
  "project" agents dir, both when both clash — instead of blaming "user"
  unconditionally.
- **#37 — the unlinted nudge agrees with the watermark.** Wake-up's
  `_unlinted_count` now counts in the same units the lint watermark is
  stamped in (`len(journal.entries())` — malformed and non-object journal
  lines are skipped, replicated inline so the hook stays stdlib-only). A
  parity test pins the two counts against the same fixture so a future
  skip-rule change can't silently reopen the drift.
- **#66 — collision hardenings from 0.7.5's final review.** The
  identical-content noop-duplicate check now also covers existing
  `<slug>-N.md` siblings; `_free_suffix_page` no longer assumes `.md`
  (whole-name suffixing otherwise) and probes slot freedom by existence,
  never readability — an unreadable sibling can't be silently overwritten.
  The install bootstrap reference doc points at the 0.7.5 refusal.
- **#64 — the CLAUDE.md block re-renders on update and revert.** The #63
  post-apply hook moved to `lib.adapter.claude_md.rerender_for_page`;
  `revert()` of an instructions write re-renders the mapped repo's block,
  and `/ren:update`'s closing steps call the new
  `rerender_all_project_claude_md()` so adapter format changes propagate
  (spec §3(b) closed). All best-effort by contract — a render failure
  never fails the wiki operation.
- **#40 — the uv environment leaves the versioned cache dir.** Documented
  invocations set `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/<version>"`;
  `/ren:update` GCs env dirs for versions no longer in the cache
  (`gc_stale_envs`); doctor's new `check_cache_env_hygiene` warns on
  `.venv` inside STALE versioned cache dirs — the current version's venv
  is exempt, since install's `warm_environment` creates it deliberately
  for the wake-up fast path (#11 §4; the final review caught that warning
  on it would advise breaking the first-session self-heal). Cache-root
  resolution has one home: `ren_paths.plugin_cache_versions_root()`.

## [0.7.5] - 2026-08-17 — "safe hands"

The pre-handoff train, release 1 of 2: the data-loss and crash paths a
fresh install could hit, closed before the first external install. Spec:
docs/superpowers/specs/2026-08-17-pre-handoff-fix-train-design.md.

- **#58 — install refuses a populated wiki.** `stamp_wiki` now asks
  `wiki_populated_reason()` (two mechanical signals: any
  `projects/*/map.md`, or a core page carrying `ren_supersedes`) and
  raises `PopulatedWikiError` before stamping anything — the message
  points at `REN_WIKI_ROOT` for test drives. No `--force`: nothing
  legitimate stamps into a populated wiki. Detection never crashes
  bootstrap (unreadable, undecodable, and malformed-YAML pages read as
  not-populated — the final task review caught the YAMLError path).
  Half-bootstrapped re-runs stamp missing pages only (pinned by test),
  and the install SKILL gained a "Test-driving install" recipe. The
  2026-08-12 incident (four-wave skeleton re-ADD over the real wiki) is
  now a regression test asserting identity.md and log.md survive
  byte-identical.
- **#61 — durable slug collisions stop overwriting.** `apply_auto` with
  `op=ADD` over an existing page now resolves three ways: same session as
  the page's latest journal write → upsert (wrap's L1 re-ADD, unchanged);
  identical normalized content → noop-duplicate; different session AND
  different content → the write lands on the first free `<slug>-N.md`,
  the journal line carries `collision_original`, and the diverted write's
  `supersedes` is forced to `None` (it replaces nothing — the task review
  caught that the stale conflict write_id would otherwise corrupt
  revert's citer detection). The human `apply()` path and
  `resolve_and_apply` keep their existing semantics.
- **#32 — the changelog digest can't crash the update flow.**
  `changelog_digest` coerces str paths (`Path(changelog_path)`); the
  courtesy digest is now un-crashable on an argument-type detail.

## [0.7.4] - 2026-08-14 — "the standing rule"

The quarantine-exit train: Cluster B's deferred trio (#52/#51/#46) plus a
new per-project instruction surface (#63). Spec for #63:
docs/superpowers/specs/2026-08-14-project-standing-instructions-design.md.

- **#52 — a human decline sticks.** The quarantine screen's machine exit
  now consults the decision ledger before judging: a declined release holds
  the page out of `release_page_auto` until its content actually changes.
  Release suggestions carry a `content_sha256`; `decide()` re-hashes the
  page at decline time (record-time fallback if unreadable) so a page
  edited while the suggestion sat pending can't slip through; pre-train
  hash-less declines hold unconditionally (fail-closed). Both screen
  phases report held pages under `held_declined`.
- **#51 — every quarantine release is audited.** `KIND_QUARANTINE_RELEASE`
  now records on all three exit paths with a `via` discriminator
  (`machine` / `suggestion-accepted` / `human-direct`) and the justifying
  evidence dict; suggestion-accepted releases stopped discarding their
  evidence.
- **#46 — the judge sees whole pages again.** `JUDGE_MAX_TEXT_CHARS`
  4,000 → 8,000: the first live sweep routed 14/20 candidates to the human
  as `too-long` (all 4,016–5,816 chars), making the suggestions store the
  de-facto exit. 8k covers every observed page; genuinely huge pages still
  route to the human.
- **#52 rider — archive/ leaves lint scope.** `archive/` and
  `projects/<slug>/archive/` are excluded from the incremental lint like
  `raw/` — including the incremental path itself, where the final
  whole-branch review caught (with a live repro) that freshly archived
  pages still entered the sweep via the journal.
- **#63 — project standing instructions.** A rule that must bind every
  session in a repo — subagents included — gets a governed home:
  `projects/<slug>/instructions.md`, instruction-plane by pattern (always
  human diff-approved), born on first `promote_to_project` (manual-first:
  pin or an accepted suggestion; wrap's classifier untouched by decision).
  The page body renders into the repo CLAUDE.md's managed block (3k-capped
  splice, fail-closed on quarantine banners), re-rendered by a best-effort
  post-apply hook; wake-up's extras exclude the page (already injected via
  CLAUDE.md); doctor's new `standing_instructions_drift` check is the
  backstop for stale splices. Follow-ups: #64 (update/revert re-render
  triggers).
- **Release hygiene.** `bump_version.py` run restores SKILL.md
  version-literal agreement with plugin.json (#65 — the 0.7.3 release had
  left ~17 files at 0.7.2, caught by `test_repo_hygiene`).

## [0.7.3] - 2026-08-14 — "the living wiki"

The knowledge-flow release: wrap stops being a create-only producer and the
KB unfreezes. Spec: docs/superpowers/specs/2026-08-14-wrap-knowledge-flow-design.md.

- **#60 (doctrine-first slice) — wrap learns UPDATE.** The durable-item
  classifier's verdict grows scope (`project`/`global`), action
  (`create`/`update`), and `target_page` — update targets restricted in code
  to the session's mechanical eligibility set (wake-up injections +
  `/ren:recall` fetches, on-disk-verified, matched against both the wrap
  label and the harness session id from the calibration pairing file).
  Updates merge via a strict one-call `merge_update` (frontmatter must
  survive byte-identical; empty/unchanged/crashed merges gate the item out
  as `MergeError` — close-out never crashes). Updates targeting
  `ren_trust: user` pages are never auto-applied — they route to the
  suggestions store (`wrap-update:<session>:<page>`). A `durable_outcome`
  metric (seen / created project-vs-global / updated / gated-out /
  suggested / held / refused) records per wrap — the measurement that
  decides whether the full #60 wiki-distiller is still needed. The
  distiller itself stays unbuilt by decision; its interface is specced.
- **#57 — durable creates land in project scope.** Project-scoped items are
  born at `projects/<slug>/knowledge/lessons/<slug>.md` (global `lessons/`
  fallback), so #54's dormant D4 auto-pointer duty finally fires. Both
  lessons directories get folder-note hubs, maintained append-only (human
  prose is never re-rendered away; `trust: user` hubs are never touched),
  with a one-time backfill of pre-existing global lessons.
- **#39 — volatile-facts markers + freshness sweep.** New
  `lib/memory/volatile.py`: `<!-- ren-volatile: <kind> -->` markers with
  mechanical checkers for `framework-version` (via
  `ren_paths.framework_version()`) and `release-count` (git tags, resolved
  through the project registry / dev root so it works from an installed
  plugin; zero tags reads as "0"). wiki-health's sweep gains a
  `stale_facts` check — read-only by default (`apply_corrections=False`;
  wrap's close-out sweep can never write), with corrections applied one
  write per page only at `/ren:wiki-health`'s explicit apply step, only
  when the pre-marker text carries exactly one unambiguous number, and only
  on non-user-trust pages (user pages become suggestions). Unknown kinds
  are inventoried as unverifiable, never guessed at.
- **Review-hardened.** The train's final whole-branch review caught two
  Criticals the task gates couldn't see: the eligibility set keyed on
  wrap's session *label* (which never matches the harness id wake-up logs
  under — the update path would have shipped inert), and the stale-facts
  sweep silently writing during every `/ren:wrap` against wiki-health's
  documented read-only contract. Both fixed pre-merge, plus six Importants
  (marker-pair oscillation, hub clobbering, dead-checker resolution among
  them). Follow-up filed from the same review: `apply_auto` silently
  overwrites on durable slug collisions (revertible, but lossy).

## [0.7.2] - 2026-08-13 — "the legible wiki"

The graph becomes readable: hubs get names, tiers get colors. Spec:
docs/superpowers/specs/2026-08-13-folder-note-hubs-design.md.

- **#56 — folder-note hubs.** Every knowledge hub `index.md` becomes a folder
  note named after its directory (`knowledge/research/research.md`), so
  Obsidian's graph — which labels nodes by filename — shows twelve named hubs
  instead of twelve identical "index" dots. `migrations/folder-note-hubs-1/`
  (global, tree-wide, in the project-knowledge-1 mold) renames hubs, stamps
  missing `hub: true`, rewrites every inbound link style-preservingly
  (root-relative, file-relative, anchored, angle-bracketed), and rewrites the
  per-project schema.md convention line. Its `verify.py` asserts the four
  tree invariants; `/ren:update` drives it behind
  `should_run_folder_note_hubs_1()` with approval, and doctor's new
  `hub_convention` check is the single "not yet migrated" voice. wiki-health
  and lint dual-accept both hub forms during the transition. Collisions are
  left in place for manual repair, surfaced by verify. Dry-run against a copy
  of the live dogfood wiki: OK + OK.
- **Default Obsidian graph config.** Install (and update, post-migration)
  write `.obsidian/graph.json` once — only when absent, never clobbering a
  tuned config: `raw/`/`archive/` filtered out, Okabe-Ito tier colors
  (quarantined content, spine, knowledge, L1 narratives), quarantine keyed on
  the `ren-quarantine` banner token.
- **#59 resolved by decision.** The wiki's rendering target is Obsidian only;
  wiki-root-relative link paths stay (Obsidian resolves vault-absolute
  markdown links — verified live). GitHub browsability is a non-goal.
- **Review-hardened.** The train's reviews caught and fixed three over-broad
  matcher bugs in plan-mandated code (`"knowledge"`-segment matching twice,
  `endswith("index.md")` once — the last found only by the real-wiki
  dry-run, false-positiving on flux's `specs-index.md`).

## [0.7.1] - 2026-08-13 — "the door guard"

Hotfix for the #58 install-clobber incident (2026-08-12: a test /ren:install
run re-ADDed skeleton pages over the populated live wiki; both damaged pages
were restored from per-write snapshots).

- **#58 — apply_write refuses ADD-over-existing.** Root cause: the single
  sanctioned write door treated `ADD` and `UPDATE` identically, so any direct
  caller could silently clobber an existing page with fresh ADD provenance —
  the caller-side skeleton exists-check and the queue's `_check_add_race`/
  propose dedup never fire on that path. The door now raises
  `ExistingPageError` (checked under the page lease); the three queue apply
  paths opt in via `allow_existing_add=True` because their ADD semantics are
  adjudicated upstream (including wrap's documented same-session L1 re-ADD
  upsert). Re-archiving a recreated page suffixes the archive slot
  (`archive/notes-2.md`) instead of clobbering the older copy; lifecycle
  sweeps treat the refusal as a skip, never a crash. Residual #58 follow-ups
  (stage-level populated-wiki confirmation, identity-handle doctor check,
  test-run isolation) stay open on the issue.

## [0.7.0] - 2026-08-12 — "the connected wiki"

The graph release: the wiki becomes Obsidian-native. Three issues, each with
its own spec under docs/superpowers/specs/ (2026-08-12).

- **#53 — Obsidian-native pointer format.** L2 decision-map pointers are now
  markdown links (`- [topic](path#anchor) (write_id)`); `repo:` refs keep the
  arrow form; the legacy arrow-with-wiki-path stays parse-accepted until the
  next MAJOR. One shared grammar module (`lib/pointer.py`) replaces the three
  per-consumer regexes (wiki-health, doctor, remember — drift now structurally
  impossible). `assemble_l2` emits link form and stamps `l2-map` schema 2;
  `migrations/l2-map-1-to-2/` (the repo's first body-rewriting migration)
  converts existing maps, self-verifying every rewritten line with the same
  parser and driven by `/ren:update` (see its 0.7.0 update notes). Doctor now
  treats an absent `schema_version` on registered page types as v1, so
  unstamped maps are discoverable. The wiki-skeleton index template teaches
  the new grammar and stamps schema 2.
- **#54 — producer link duties.** Wrap mechanically weaves what it writes:
  the L1 narrative gains a `## Touched pages` section (applied writes only);
  `log.md` gains a linked session entry; the project map gains a capped
  `## Sessions` section; new durable project pages get auto-pointered into
  the map's Decision map, and the master index's spine links every project
  map. All duties are isolated (a failure warns, never fails the wrap),
  success flags are gated on applied-vs-held queue writes, and the
  bookkeeping writes use the `routine` writer class so they never quarantine
  human-owned pages. `remember` renders the Sessions section as a
  recent-sessions line.
- **#55 — wiki-wide orphan detection.** New `orphan_pages` sweep finding:
  every durable page nothing links to, path-resolved across both link
  conventions plus arrow pointers, with a word-bounded filename-mention
  fallback (index.md-named files excluded). Exemptions are exact-depth
  (`projects/<slug>/raw/`, root/project `archive/`) and quarantined pages
  route to the quarantine flow instead. Orphans become suggestions
  (`orphan:<page>`, deduped), with a proper accept route (decided handoff).
- **#57 filed** (follow-up): wrap durable items land in `lessons/`, so the
  #54 auto-pointer duty is dormant until durable pages can target project
  scope; carries two LOW rides-along (D2 same-session log dedup, migration
  quoted-`type:` tolerance).

## [0.6.7] - 2026-08-04 — "the fix train"

Bug-fix release: eight issues from the 0.6.6 live smoke and verification
waves, in three reviewed clusters. Spec:
docs/superpowers/specs/2026-08-03-0.6.7-fix-train-design.md.

- **#41 (CRITICAL)** — suggestions `accept()` now applies the quarantine
  screen's `quarantine_release` (via `release_page`) and `review_lint_finding`
  (decided handoff) actions; an unknown kind/action now RAISES and leaves the
  suggestion pending/retryable instead of silently deciding it.
- **#48 (CRITICAL)** — wake-up's final payload budget guard is
  head-preserving: the seed header + doctrine card survive any over-budget
  compose, only content sections are tail-truncated, and the elision is
  logged at WARNING. Calibration hardening: a chars-per-token ratio needs
  ≥5 samples to displace the fallback, and a >25% budget shift warns.
- **#42 (HIGH)** — the conflict detector no longer self-conflicts an UPDATE
  with its own target page (duplicate/contradicts exempted; the supersedes
  provenance chain unchanged) — quarantine releases stop holding on noise.
- **#47** — a wrap re-run for the same session proposes its L1 as UPDATE, not
  ADD; the ADD-race guard stays as backstop.
- **#45** — wrap SKILL.md passes the session's working directory explicitly;
  the wrap screen shouts when the L1 files under global `l1/` (no silent
  misfiling); result records `project` + `wrap_cwd`.
- **#43** — wrap normalizes L1 frontmatter to always carry `type: l1`
  (including the empty-frontmatter shape found in cluster review).
- **#44** — the wrap screen no longer offers "undo" for writes already
  reverted (filters against the journal's `revert_of` records).
- **#35** — the doctrine card's truncation pointer names the shipped file
  path instead of a prose phrase.

## [0.6.6] - 2026-08-03 — "the quarantine gets a bounded exit"

- **Quarantine screen** — bounded machine exit from quarantine: ren-wiki-lint
  screens model-trust data-plane pages at wrap close-out (deterministic
  injection scan + data-only judge, fail-closed); clean pages auto-release
  through the queue (`who="agent:quarantine-screen"`, revertible), everything
  else routes to /ren:suggestions. Wake-up nudges on backlog; sweep reports
  machine-released totals. Spec: docs/superpowers/specs/2026-08-03-quarantine-screen-design.md.

## [0.6.5] - 2026-08-02 — "the OS knows what's open and what's checked"

Two more shipped agents (`ren-wiki-lint`, `ren-planner`) join `ren-reviewer`,
plus the substrate that makes them useful: an append-only session journal to
lint incrementally, an open-work ledger so nothing open gets forgotten
between sessions, and a doctor check protecting shipped-agent names from
collision.

- **Session-summary journal + lint watermark** — `wrap` appends one
  append-only session-summary line per session to the journal; a lint
  watermark in `state_dir()` drives incremental selection so hygiene passes
  only ever look at what changed since the last clean run.
- **`ren-wiki-lint` incremental hygiene** — `run_incremental_lint` applies
  mechanically-safe fixes through the write queue, routes judgment-shaped
  findings to the suggestions store, hard-excludes `raw/`, the journal,
  frozen `log.md` days, instruction-plane pages, and `_`-prefixed pseudo
  pages, and reports a `held` disposition for proposals the queue leaves
  pending. Spawned non-blocking at wrap close-out, and named in the wake-up
  nudge when journal entries are unlinted.
  The first run on a wiki that has never been linted (e.g. straight after an
  upgrade) SEEDS the watermark at the current journal length and checks
  nothing — reported as `scope: "seeded"` — so upgrading never triggers an
  unattended rewrite of the whole wiki's history. Run with `full=True` to
  lint history deliberately.
- **Open-work ledger** — a new `open-work` page type and template; wrap
  reconciles it (`reconcile_open_work`) and wake-up renders a `## Open work`
  section. Lines are never deleted — closed lines older than 14 days move
  to `## Archive`.
- **`ren-planner`** — a wiki-aware plan decomposer for the execution
  doctrine's decompose gate: reads an approved plan plus the project wiki
  and emits atomic task briefs sized for one clean subagent context each.
- **Doctrine card v2** — the decompose gate now names `ren-planner`; the
  review gate requires the open-work line be closed before declaring done;
  `DOCTRINE_BUDGET` raised to 500 and truncation is now visible rather than
  silent; a new head-preserving compact rendering is used whenever the full
  card would be cut.
- **Doctor: `agent_shadowing` check** — warns when a user- or project-level
  `.claude/agents/<name>.md` collides with a shipped agent's filename,
  covering both `claude_user_dir()/agents` and (when the cwd resolves to a
  registered project) that project's own `.claude/agents/`.

## [0.6.4] - 2026-08-02 — "the harness ships with the plugin"

The execution discipline that lived only in the dev machine's local setup now
ships in the box: every wake-up injects a hard-gate execution doctrine
(brainstorm gate → atomic decomposition → TDD dispatch → review gate),
delegating to superpowers process skills when that plugin is installed and
falling back to a self-contained loop when it isn't.

- **Execution doctrine card** — wake-up injects a ≤50-line, 400-token process
  card as the first section; detect-and-delegate to superpowers.
- **`ren-reviewer` shipped agent** — the review gate's enforcement arm:
  verified findings with runnable repros, scope + TDD conformance, fixed
  report format. First agent RenOS ships (`agents/`).
- **Doctor: `execution_doctrine` check** — verifies card references resolve
  and warns on manual CLAUDE.md stopgap residue from pre-0.6.4 installs.

## [0.6.3] - 2026-08-01 — "wake-up actually remembers"

Eight fixes from the second dogfood pass (issues #21–#28): last-session
continuity, trust minting, the two lifecycle loops that never closed, and
the three push-guard defects that blocked publishing this very train.

- **L1 continuity is global, not project-gated** (#21) — the "What
  happened last session" read (project-local `l1/` first, global `l1/`
  fallback always) now runs whether or not a project is detected, so
  sessions from the dev root (or any non-project cwd) wake up with
  continuity. The l1-exclusion loop moved out of the gate with it: a
  no-project session no longer miscounts its own summary as a held-out
  quarantined page.
- **Ingest drafts mint `ren_trust: "model"`, not `"foreign"`** (#22) —
  they're RenOS's own subagents distilling the friend's own repo,
  queue-applied with quarantine banners, same as L1. "foreign" stays in
  the taxonomy (reserved for genuinely external, explicitly-stamped
  content) and every foreign check remains in force.
  `migrations/foreign-remint-1/` heals existing wikis (restamps only
  foreign pages with a known non-human `ren_writer`; banners untouched;
  `--check` preview; idempotent), gated on the update crossing 0.6.3.
- **Empty rank query suppresses "Possibly relevant now"** (#23) — with no
  project and no git signal, wake-up injects nothing there rather than
  whatever happened to be released.
- **Wake-up surfacing no longer counts as a decay touch** (#24) — only L3
  fetches and direct reads refresh the 90-day clock; a page the framework
  keeps injecting but nobody ever reads now decays instead of
  self-perpetuating. Surfacing stays logged for the miss metric.
- **Wrap closes the pin loop** (#25) — the wrap screen gains a "Live
  pins" section (every applied pin-written page still on disk, any
  session) and the skill asks about ones that look acted-on; confirmed
  deletes go through the queue's normal correction path. Task-shaped pins
  are documented to carry their own delete step as belt-and-braces.
- **Push guard recognizes the repo's own remote** (#26) — the maintainer
  path denylist in `pre_push_scan` stands down when every push targets
  the remote named by the plugin manifest's `repository` field (the
  single-remote reality since 0.6.2 retired the dev-backup mirror), and
  stays in force for any other remote. Secrets scan unaffected.
- **First-push secrets scan diffs against the remote base** (#27) — a new
  branch with no upstream is scanned since the merge-base with the push
  target's default branch, not the full tracked tree (which legitimately
  carries secret-shaped scrub patterns and test fixtures already on the
  remote). Full-tree scan remains only for a genuinely first publish
  (remote with no refs).
- **Push secrets scan at content granularity** (#28) — only the push's
  ADDED lines are scanned, so pre-existing secret-shaped text in a file
  the push happens to edit (scrub's own patterns, test fixtures,
  `*_token` identifiers) no longer blocks; a real secret introduced by
  the push is still caught. The overbroad `password-pair` scrub pattern
  itself is tracked separately (#29).

## [0.6.2] - 2026-08-01 — "the dogfood train"

Nine fixes from the first real fresh-machine install (MacBook, issues
#12–#20), plus an adversarial review pass over the whole train.

- **Real hierarchical project memory** (#20) — `projects/<slug>/knowledge/`
  is now the sanctioned durable subtree for project-specific pages
  (registered `project-knowledge` page type, skeleton dir, ingest drafts
  into it, L2 map points at it). New pointer rule: Decision-map pointers
  must target pages that exist (same-batch or `repo:<name>:<path>` refs),
  never invented future filenames. `migrations/project-knowledge-1/`
  relocates existing flat files (dry-run default, never overwrites,
  per-move journal). Amended in-train to the full Karpathy LLM-wiki shape:
  `knowledge/` nests to project-determined depth with a hub `index.md` per
  subdirectory (the map points at hubs, not deep leaves); each project
  declares its own taxonomy in `projects/<slug>/schema.md` (new
  `project-schema` page type — ingest drafts it before any knowledge page,
  bootstrap stamps a stub); `projects/<slug>/raw/` holds immutable source
  material (skipped by coherence scans, never injected by wake-up, valid
  pointer target). wiki-health grows `hubless_knowledge_dirs` +
  `unlinked_knowledge_pages` structural findings; the migration also
  reports (never fabricates) a missing `schema.md`.
- **Global tier actually promotion-gated** (#18) — `global/`, `decisions/`,
  `patterns/`, `research/` are instruction-plane for every producer;
  non-promotion writes hold pending instead of auto-applying. One
  canonical prefix predicate; page strings are normalized and `..`
  segments rejected so the gate can't be walked around. wiki-health flags
  global-tier pages that name exactly one project.
- **Contradiction detector grew judgment** (#16) — `contradicts` now
  requires a real signal (negated same-claim by containment, or
  single-position numeric divergence); same-batch sibling pages and L2
  maps no longer false-positive each other. Kills the wall of ~40 bogus
  holds on an 8-page batch ingest.
- **Ingested projects reach wake-up** (#15, #19) — ingest writes the
  CLAUDE.md pointer block and records repo↔slug in
  `.ren/projects.json`; `detect_project` consults the registry first, so
  a clone dir named differently from its slug is no longer orphaned.
  Doctor gains an orphaned-project check.
- **First-run honesty** (#12, #14) — the wake-up hook now emits the
  uninitialized notice for an existing-but-unstamped wiki root (and a
  distinct notice for stamped-but-empty); `uv.lock` ships in the plugin
  so the interpreter warm path works on a fresh install (with a
  non-frozen fallback).
- **Copy-paste-runnable docs** (#17) and a test suite that no longer
  writes into the real `~/.renos` (#13), with a loud leak guard.
- **Review hardening** — quarantined instruction-plane pages can be
  released again; `/ren:pin` docs no longer claim a held pin was saved;
  registry slugs validated; migration frontmatter rewrite scoped to
  column-0 keys.

## [0.6.1] - 2026-07-30 — "the economics layer"

RenOS now reasons explicitly about which model tier does which work, and
closes the loop on whether its own budget estimates are any good.

- **Capability-class routing doctrine** — `doctrine/model-classes.md` is now
  the single name→class mapping (orchestrator / worker / classifier); every
  skill and rule speaks in classes, never bare model names, so a model
  lineup change is a one-file edit instead of a grep-and-pray. Plugin
  boundary made explicit: RenOS owns economics (what model tier, what
  budget); complementary plugins own process (how the work gets done).
- **Agent-economics standing rule, injected** — "cheapest class that fits
  the task, 3-5 cap on parallel spawns" is now part of the always-on
  CLAUDE.md layer, not just skill-local guidance.
- **Two new advisory doctor checks** — a routing audit over harvested
  sessions (flags work that ran on a pricier class than the task needed),
  and a model-map staleness check (flags when `model-classes.md` hasn't
  been touched since a model lineup change).
- **Calibration loop closed** — wake-up now stamps its own budget payload;
  `/ren:wrap` harvests the real transcript token counts for that session and
  calibrates the estimator against them. Wake-up's budget math now runs off
  the calibrated ratio, with a safety clamp so a bad calibration run can't
  blow the budget out.
- **Wrap records subagent spawns** — feeds the routing audit above with
  real spawn data instead of inference from skill frontmatter alone.
- **wiki-health retrieval-eval instrument** — reports hit rate against the
  frozen fixture set, the exit-criterion-2 measurement RenOS has been
  missing since 0.5.

## [0.6.0] - 2026-07-30 — "seam & safety"

Closes [issue #11](https://github.com/hazarsozer/ren-os/issues/11) — CI now
proves the framework works on the seams it previously only assumed (cold
machines, real installed layouts), and destructive writes are audited and
guarded instead of trusted by convention.

- **Cold-machine CI job** — the wake-up hook contract (valid JSON, exit 0,
  inject-or-loud-degrade) is now asserted on a bare `python:3.9` machine with
  no deps, closing the gap where CI only ever ran with the framework's own
  dependencies already present.
- **Installed-plugin CI smoke** — the hook contract is also asserted from a
  real `CLAUDE_PLUGIN_ROOT` installed layout, not just the dev repo. This
  caught and fixed a real bug: a session on a machine with no wiki
  initialized now gets a loud "memory not initialized — run `/ren:install`"
  notice instead of silently injecting nothing.
- **Destructive-write audit** — all 21 write sites are now classified in
  `docs/audits/2026-07-destructive-writes.md`, with CI-pinned coverage so the
  classification can't silently drift. The audit caught and fixed a
  data-loss bug where `/ren:bootstrap-project` overwrote a hand-authored
  `AGENTS.md`; it's now marker-spliced, preserving user content.
- **Backup precondition** — `/ren:ingest-project` and `/ren:bootstrap-project`
  now require a configured backup before running on a wiki with grown
  content (override: `RENOS_ALLOW_NO_BACKUP=1`); fresh/skeleton wikis are
  unaffected.
- **Cold-start fix** — `/ren:install` now warms the venv and records a
  machine-scoped interpreter; wake-up prefers it, so the first session after
  install runs the fast path instead of the ~7s degraded one.

## [0.5.7] - 2026-07-18 — "runs on Macs"

Portability hotfix closing [issue #9](https://github.com/hazarsozer/ren-os/issues/9) —
RenOS was silently broken on stock macOS (bash 3.2 + BSD sed); CI never
caught it because it only ran on Linux.

- **`/ren:update` snapshot/prune works on stock macOS** — replaced the
  bash-4-only `mapfile` builtin with bash-3.2-safe `read` loops, so snapshot
  and prune no longer fail on the bash Apple ships by default.
- **Schema migrations are BSD+GNU sed portable** — rewrote the migration
  scripts' `sed` usage to work on both BSD sed (macOS) and GNU sed (Linux):
  `-i.bak` instead of bare `-i`, and `a\`-plus-newline appends instead of the
  GNU-only one-liner `/a text` form. Also fixes a silent-corruption risk
  where BSD sed strips leading blanks on `a\` continuation lines — those are
  now escaped.
- **New migrations must be written in Python** — the shell migration path is
  now legacy; see `migrations/README.md`.
- **CI now catches this class of bug** — a new
  `scripts/lint-shell-portability.py` guards against `mapfile`/`readarray`,
  bare `sed -i`, and GNU-only one-liner `sed` appends, wired into CI
  alongside a scoped `macos-latest` job that runs the shell-touching test
  clusters. Previously CI was Linux-only, so none of this was visible before
  it reached a Mac.

## [0.5.6] — 2026-07-18 — "don't touch my map"

Hotfix for a silent data-loss bug (present since 0.2, but 0.5.5 is the first
release that gives you a reason to hit it).

- **Re-running `/ren:bootstrap-project` no longer wipes a project's map** —
  bootstrap seeds a project's L2 map only when it doesn't exist yet. On an
  existing project it now leaves your grown Knowledge / Decision-map / Log
  untouched (previously it silently overwrote them with the empty
  bootstrap-day template). Re-running bootstrap to pick up the new 0.5.5
  `overview.md` page is now safe.

## [0.5.5] — 2026-07-17 — "orientation & real usage"

Wake-up now answers the questions a session actually needs instead of
handing over an undifferentiated context blob — and decay learns from what
you actually touch, not just what got written.

- **Question-shaped wake-up** — the SessionStart payload is now seven short
  answers: who you're working with (identity), what this project is (a new
  `overview.md`), what happened last session (L1), where to find project
  knowledge (the L2 map), active routines, anything waiting on your answer,
  and a small set of related pages.
- **The overview stays current on its own** — `/ren:wrap` judges whether a
  session materially changed the project's stage or direction and rewrites
  `overview.md` only when it did (≤600 tokens, a thesis not a novel) — most
  sessions leave it untouched.
- **Structural-artifact quarantine exemption widened** — L1, the overview,
  and the L2 map all now inject with their quarantine banner intact when
  quarantined (they're RenOS's own path-constrained writes, not foreign
  content); a `ren_trust: "foreign"` stamp still holds any of them out and
  counts toward the "N quarantined page(s) held out" line.
- **Decay learns from real usage** — the 90-day idle window that feeds
  archival now counts wake-up injection, page reads, and recall hits as
  "touched," not just writes, so a page you keep reading but never edit
  doesn't get swept.
- **Producer size targets** — the overview stays ≤600 tokens, the L1
  narrative targets ≤1,000 tokens and leads with outcomes, and the identity,
  overview, L1, and L2 map sections now name where the rest lives with a
  "continues in `<path>`" pointer line when they get truncated.
- **Small fixes** — the PostToolUse read-tracker and the PreToolUse write
  guard now exit cleanly on a closed/broken stdin instead of crashing.

## [0.5.4] — 2026-07-17 — "daily-driver ready"

Hotfix release closing the daily-driver readiness review
([issue #8](https://github.com/hazarsozer/ren-os/issues/8)) — all four
confirmed runtime bugs fixed, plus the review's smaller items.

- **Wake-up works on clean machines** — the SessionStart hook now
  self-heals when the system `python3` lacks the plugin's dependencies
  (re-runs itself under `uv`), and when it can't, it says so loudly in
  the session context instead of silently injecting nothing. Memory
  injection no longer dies invisibly on a fresh install.
- **`git push` unblocked in your own repos** — the maintainer-path guard
  (`tests/`, `.claude/`, `wiki/`, …) now applies only inside the RenOS
  repo itself; your projects push freely. The secrets scan checks only
  the files you're actually pushing, not the whole tracked tree.
- **Guards that actually guard** — the backup-remote confirm prompt now
  speaks Claude Code's real hook protocol (it was being silently
  ignored); quoted paths no longer slip past the wiki delete guards;
  force/rewrite checks cover every push in a chained command; and
  `--force-with-lease` (the safe idiom) no longer needs an override.
- **Small fixes** — `ls a->b` inside the wiki is no longer mistaken for
  a write; doctor no longer asks for an `ANTHROPIC_API_KEY` (RenOS uses
  no API keys); ingest-project's contract matches its documented
  behavior; corrected the Graphify link, the skill count (18), and
  routine-init's frontmatter schema version.

## [0.5.3] — 2026-07-12 — "the learning brain"

Judged semantics, trust-aware memory, and now a metabolism: the wiki
archives, decays, and consolidates — and never deletes.

- **Archive tier** — pages move to `archive/<rel>` through the single write
  door, journaled and revertible. The archive copy itself is the durable
  recovery path: restoring a page does not depend on snapshot retention,
  and archiving preserves the page's trust class (a foreign page stays
  foreign — archive never launders trust). Archived pages are held out of
  wake-up context and recall by default (`include_archived=True` to see them).
- **90-day decay at wrap** — data-plane pages with no write AND no recall
  in 90 days (and no salience boost) archive automatically, capped at 5 per
  wrap, oldest first, surfaced on the wrap screen and one revert away.
  If the recall log can't be read, decay skips entirely — under-decaying
  is the failure mode, never over-archiving.
- **Consolidation** — pairs the judge confirms as duplicates at ≥0.85
  confidence auto-merge: the older page archives with
  `reason="consolidated"`, the newer one gains a traceable
  "Merged from [[older-page]]" line. Concurrent edits abort the merge
  safely (nothing clobbered), and a partial merge is surfaced on the wrap
  screen, never silent.
- **Doctor knows the lifecycle** — `check_archive_integrity` flags orphaned
  archive pages; fresh installs now come up doctor-clean (install's founding
  writes no longer false-positive the apply-integrity check).
- **Sandbox-safe installs** — RenOS now honors `CLAUDE_CONFIG_DIR`
  (precedence: `REN_CLAUDE_DIR` > `CLAUDE_CONFIG_DIR` > `~/.claude`), so
  multi-profile and CI setups no longer risk writes into the real global
  CLAUDE.md.
- Gate-0 live proof passed 7/7 legs on a fresh install (onboarding, labeled
  recall, hostile-ingest quarantine, live judge catch, consolidation +
  revert, archive + revert, suggestions + doctor).

## [0.5.2] — 2026-07-12 — "real semantics"

The brain now understands paraphrase and contradiction: an LLM judge reads
shortlisted page pairs and rules duplicate / contradicts / supersedes /
unrelated — fail-closed to today's heuristics whenever no LLM is available.

- **Shortlist, then judge** — a deterministic candidate generator
  (`shortlist_pairs`) feeds heuristic hits and near-similar pairs (the
  paraphrases heuristics miss) to the judge, capped and ordered stably.
- **Wrap judges the session's writes** — new `semantic_findings` on the
  wrap screen: your session's pages judged against the wiki, informational
  only (consolidation lands in 0.5.3).
- **The wiki-health sweep judges too** — judge-confirmed paraphrase
  duplicates join the duplicate report; near-similar pairs judged as
  contradictions flow all the way to critical suggestions; judged
  supersedes relations get their own "for review" section; and pairs the
  judge *dismisses* stay visible in the report (the judge never makes
  evidence disappear).
- **Fail-closed everywhere** — no LLM, a judge error, or a malformed
  verdict all degrade to exact heuristic behavior; the sweep and wrap
  never break. `/ren:doctor` warns when judging has been degrading
  ("semantic judging degraded — running heuristics-only").
- **Judge quality is measured, not assumed** — a held-out 16-case eval
  fixture (4 per verdict class, paraphrases with zero shared lines,
  non-negation contradictions) scores any judge; the live drill scored
  16/16.

## [0.5.1] — 2026-07-12 — "trust taxonomy"

Provenance classes, scrub-at-scan, escaped retrieval: the wiki now knows
*who wrote what* and treats untrusted content as data, never as instructions.

- **Every page carries a trust class** — `ren_trust: user / model / foreign`
  is stamped at the single write door. Human writes are `user`, RenOS's own
  writes are `model`, and only the ingest door can mint `foreign`.
- **Existing wikis get backfilled** — upgrading past 0.5.1 runs the
  `trust-backfill-1` migration automatically (human-written → user,
  quarantined → foreign, else model; bodies untouched, re-runs are no-ops).
- **Scrub-at-scan** — instruction-shaped content ("ignore all previous
  instructions…") is detected at the ingest door, surfaced in the ingest
  result and the artifact's provenance note. Patterns are tuned to
  assistant-override intent, so ordinary prose like "you must follow the
  style guide" doesn't trip it.
- **Escaped retrieval** — foreign or quarantined content comes back from
  recall wrapped in a breakout-proof fenced block behind a
  "⚠ UNTRUSTED CONTENT" warning, with a trust label on every hit.
- **Producers refuse foreign evidence** — promotion and wiki-health
  suggestions never build on `foreign` pages, even after a quarantine
  banner is released.
- **Wake-up injection hardened** (Codex P5 + two drill-caught leaks) —
  the L1 session summary is injected only when its own stamp verifies a
  RenOS model-class write; unstamped or foreign files at the L1 path are
  held out, and stale files under `l1/` can't sneak back in via
  "Related pages". Foreign-stamped pages are excluded from extras
  discovery even after banner release.

## [0.5.0] — 2026-07-10 — "learning-brain foundations"

Boring on purpose: hygiene, plumbing, and a 12/12-confirmed external review's
fixes — the ground the 0.5.x "learning brain" train builds on.

- **Suggestion store stays small and fast** — decisions live in a compact
  append-only ledger (the never-re-nag source of truth), old decided entries
  prune after 90 days, and pending suggestions that sit unanswered for 30
  days quietly expire (an expired suggestion can come back with fresh
  evidence; a declined one never does).
- **LLM-judge plumbing** — the contract for 0.5.2's semantic
  duplicate/contradiction judging (typed verdicts, per-run cap, fail-closed
  to today's deterministic behavior). No consumers wired yet.
- **External-review fix wave** (every finding adversarially verified):
  - Page leases acquire atomically — two concurrent sessions can no longer
    both "win" the same page lock.
  - `rm -rf` of a wiki folder now counts the pages inside it — recursive
    deletes hit the same guard as multi-file deletes (symlink-safe).
  - Force-pushes spelled `git push origin +main` are caught like `--force`.
  - Session summaries land where the next wake-up actually looks — project
    wraps write project-local L1 (with fallback for existing wikis).
  - An approved ADD that would silently overwrite a page created in the
    meantime is held as a conflict instead.
  - Approving/declining an already-decided suggestion is refused instead of
    re-applied; a failed decision write after a successful apply is surfaced
    (`decision_recorded: false`) instead of lost.
  - `/ren:doctor` gains apply-integrity and suggestion-store checks;
    wiki-health no longer reports `.ren/` snapshots as live quarantined pages.

## [0.4.5] — 2026-07-10 — "suggestion-pipeline contract fixes"

Gap-review pass over the 0.4.x train — fixes where the shipped pipeline
drifted from its own ratified contracts.

- **Declines really are durable** — retrospective skill-candidate
  fingerprints are slug-normalized, so a casing/whitespace/punctuation
  re-draft of a suggestion you already declined can never re-nag.
- **Quarantined content can't drive suggestions** — the wiki-health
  knowledge scan now holds out quarantined pages, closing the last
  evidence path that bypassed the producers-refuse-quarantined-sources
  contract.
- **"Accepted" means it actually landed** — approving a suggestion applies
  the change first and records the decision only on success; an apply
  failure leaves the suggestion pending, visible, and retryable instead of
  silently lost.
- **Promotion candidates respect the significance gate** — the promotion
  producer now uses the ratified "reinforced in ≥3 of your last 5 sessions"
  recurrence window instead of a looser ad-hoc threshold.
- **Recurrence evidence is session-id clean** — session summaries missing an
  id no longer count toward the recurrence threshold.
- **Doctor watches the suggestion store** — `/ren:doctor` flags corrupt or
  torn suggestion entry files instead of letting them silently shrink the
  pending list.

## [0.4.4] — 2026-07-10 — "gate-0 findings"

Fixes from the 0.4.3 fresh-install proof run.

- **Pinned global preferences are properly typed** — a pin or correction
  targeting a `global/` page now stamps `type: preference` frontmatter, so
  the page you just approved no longer shows up as drift on the next
  `/ren:doctor`.
- **CLAUDE.md refresh suggestions are real** — the doctrine producer now
  renders what a refresh would actually write and compares it to disk;
  suggestions only appear when accepting them would change something (the
  old companion-title check could suggest no-op refreshes).
- **Known note:** headless (`claude -p`) sessions don't export plugin
  option environment variables; interactive sessions are unaffected.

## [0.4.3] — 2026-07-10 — "proof and polish"

Closes the 0.4.x "suggesting brain" train.

- **Docs truth pass** — every claim re-verified against the code: the L1/L2
  quarantine split described accurately, the wake-up payload's held-out and
  suggestion lines documented, `/ren:suggestions` added to the governance
  table, stale "not wired yet" notes resolved.
- **Per-repo CLAUDE.md pointer block is real** — bootstrap-project now
  stamps the marker-delimited pointer block via the adapter (a 0.2-era
  changelog claim that had never actually been wired), alongside AGENTS.md.
- **Recurrence gate wired** — the ratified "pattern in ≥3 of your last 5
  sessions" rule now gates retrospective skill-candidate mining directly.
- **Final whole-train review** — independent whole-branch review of all
  0.4.x changes verified: no new wiki writers, the instruction-plane
  chokepoint untouched, L1 the only quarantine exemption, never-raise hook
  contracts, coherent suggestion fingerprints, and no resurrected
  approve/reject verbs.

## [0.4.2] — 2026-07-10 — "the suggesting brain"

RenOS now learns how you work and proposes improvements back to you. The
data plane still auto-applies (journaled, revertible); your instructions
only ever change with your explicit, recorded approval.

- **Suggestion store** — durable records under `.ren/suggestions/`;
  declines are remembered and never re-asked (same contract as the
  companion picker).
- **Significance gate** — suggestions are rare and high-stakes by design:
  a pattern must recur in ≥3 of your last 5 sessions, or a contradiction
  must touch instruction-plane/load-bearing pages, to earn a question.
- **Four producers** — retrospective skill-candidates (no longer parked as
  invisible pending entries), reinforced preferences suggesting their own
  promotion to global, companion-aware CLAUDE.md refresh offers, and
  critical wiki-health contradictions held for you.
- **`/ren:suggestions`** — the single interactive surface: walks pending
  suggestions one at a time, Approve/Reject per item, full preview and
  rationale. Accepted page-writes flow through the existing human-gated
  queue door — no new write machinery.
- **Wake-up + wrap wiring** — wrap harvests producers at close-out;
  wake-up announces pending instruction suggestions with a pointer to
  `/ren:suggestions`.

## [0.4.1] — 2026-07-10 — "trust hardening"

Quarantined (LLM-written, unreviewed) content is now held out of your
context by default instead of riding in behind a banner. This is exclusion,
not sanitization — full trust-class provenance is 0.5 territory.

- **Wake-up holds out quarantined pages** — the extras channel and the L2
  project map skip quarantined pages; a count-only line says how many were
  held out. The L1 session summary is the one documented exemption (it is
  RenOS's own summary of your own session, banner intact).
- **Recall excludes quarantined pages by default** — ask explicitly to see
  held-out content and it's retrieved banner-intact.
- **Ingest offers release at close-out** — after ingesting a project, RenOS
  shows you the map and offers to release it from quarantine (a human act);
  until released it stays out of wake-up.
- **Adversarial injection test suite** — hostile instruction-shaped content
  seeded through the real write doors is proven absent from wake-up payloads
  and default recall, and retrievable only on explicit ask.

## [0.4.0] — 2026-07-10 — "foundations"

Groundwork for the 0.4.x "suggesting brain" train. No user-facing behavior
change except AGENTS.md now appearing on bootstrap.

- **Public queue read API** — `queue.all_entries()`; the wake-up hook and
  wrap no longer parse queue state files directly.
- **Applied-page dedup** — re-proposing content identical to what's already
  on the target page is a no-op instead of a duplicate write.
- **Salience expiry** — pinned-page boosts expire after 30 days; re-pin to
  refresh.
- **AGENTS.md is real** — `/ren:bootstrap-project` now writes AGENTS.md at
  the project root via the portability surface (previously advertised as
  planned).
- **L2 maps state their pointer base** — a note line clarifies pointers are
  wiki-root-relative (a foreign-harness reader resolved them wrong in the
  0.3 read-proof).
- **changelog digest boundary fix** — prerelease headers no longer glue onto
  the preceding section.
- **Test-debt sweep** — corrupted-companions doctor case, import style,
  concurrency note, stale doctrine sentence.

## [0.3.6] — 2026-07-09 — "closing the stated gaps"

Every gap the docs admitted to is now closed, not just disclosed.

- **Write gate catches `mv`-out and single-page `rm`** — moving a wiki page
  out of the wiki or deleting one page now trips the guard (was a documented
  accepted gap; `.ren/` state files are untouched).
- **Promotion rejects `..` traversal** at propose time, not just at apply.
- **Duplicate detection has a content floor** — near-empty templated pages
  can no longer flag each other.
- **"Ask me to list them" is now backed** — a deterministic full listing of
  every pending suggestion, all sessions, with previews.
- `snapshotRetain` survives absurd values like `1e400`.

## [0.3.5] — 2026-07-09 — "companions on board"

Install and update now carry the companion list with them — once each,
never nagging.

- **Companion picker at install** — `/ren:install` offers the curated
  companions (Graphify, markitdown, yt-dlp, Superpowers) interactively.
  Accepts install on the spot (tools) or hand you the command (plugins,
  restart to activate); declines are remembered forever.
- **Update reports and asks** — `/ren:update` now ends with a "what changed
  in your RenOS" digest built from the changelog, and offers only the NEW
  recommendations you haven't decided on.
- **Doctor keeps it honest** — accepted-but-missing companions surface as a
  warning; undecided ones as a pointer.

Nothing installs without an explicit yes in chat.

## [0.3.4] — 2026-07-09 — "docs truth pass"

No behavior changes — the docs now say exactly what the code does. Notable:
`AGENTS.md` generation was advertised as shipped but is a library-only
capability today (auto-wiring is 0.4 work); the data-flow statement now
accounts for ingest/retrospective worker subagents; every leftover
approval-era string ("approve it via the queue") is gone.

## [0.3.3] — 2026-07-09 — "see what you approve"

Instruction-plane promotion is the one decision still gated on you — now you
can see what you're deciding.

- **Wake-up lists pending suggestions** (up to 5, with page and reason)
  instead of announcing a bare count.
- **Wrap previews content** — every held or suggested entry shows the first
  line of what would actually be written, not just its metadata.

The conversational approval model is unchanged: answer in chat, or ignore.

## [0.3.2] — 2026-07-09 — "substrate integrity"

The write substrate's promises (snapshot, journal, one-step revert) now hold
against the two ways they silently eroded.

- **`snapshotRetain` is wired** — the setting existed since 0.2 but nothing
  read it; snapshots grew forever. Every write now prunes to your configured
  retention (default 50).
- **Shell writes into the wiki are blocked** — `echo >`, `sed -i`, `tee`,
  `cp`/`mv` into wiki pages bypassed snapshot/journal/revert without a trace.
  The write gate now catches them (best-effort by design: it stops the
  common accidental bypass, not a determined one — reads are untouched).
- Promotion targets are validated under `global/`.

## [0.3.1] — 2026-07-09 — "wiki-health grows teeth"

The ungated brain's auditor can now see the two most common kinds of memory
rot, and quarantine finally has a door out.

- **Duplicate detection on applied pages** — the wiki-health sweep reports page
  pairs sharing ≥90% of their lines, so consolidation candidates surface
  instead of accumulating silently.
- **Numeric drift detection** — "uses port 8080" vs "uses port 9090" (across
  pages or within one page) is now reported. Report-only: the sweep never
  rewrites your facts; the session asks you which value is current.
- **Quarantine release** — when you tell the session a quarantined page is
  accurate, it releases the banner through the write substrate (journaled,
  revertible). Previously quarantine had no exit at all.
- Honest docstrings: `lib/memory/semantics.py` no longer claims a human
  approver gate that v2.2 removed.

## [0.3.0] — 2026-07-08 — "the ungated brain"

**BREAKING: the memory approval queue is gone.** Spec amendment v2.2 (two-plane
governance) — a founder ruling after living with 0.2's per-write gate: a second
brain that needs your sign-off on every memory isn't compounding, it's an inbox.

**If you learned the 0.2.1 commands:** `/ren:queue`, `/ren:approve`,
`/ren:reject`, and `/ren:revert` no longer exist. You don't need replacements —
memory saves itself now, and the rare things that DO need you are asked in
plain chat (answer in words; say "undo w-…" to revert any write).

### The two planes

- **Data plane — auto-applies.** Everything descriptive (session narratives,
  lessons, pins, project maps, retrospective findings, identity answers) writes
  to the wiki the moment it's produced. The §3.10 substrate is unchanged
  underneath: every write still carries provenance, lands in the journal, takes
  a snapshot first, and is one-step revertible. LLM-authored content is still
  quarantine-marked — data, not instruction, at read time, permanently.
- **Instruction plane — human-gated, conversationally.** Anything prescriptive
  (`global/` pages, skill-candidates from retrospective) stays pending as a
  *suggestion*: the wake-up hook announces it, wrap asks about it, you answer
  in chat. Promotion through you is the only door from remembered to obeyed —
  the prompt-injection defense is structural now, not ceremonial.
- **Contradictions hold for reasoning.** A new memory that contradicts an
  existing page isn't applied silently and isn't dumped on you either — the
  model resolves it in-session and the resolution is recorded in the journal
  (`resolve_and_apply`); you're asked only on genuine ambiguity.

### New

- **`/ren:wiki-health`** — the autonomous coherence auditor that replaces
  write-time review: dangling pointers (including path-escaping ones),
  wiki-wide contradiction pairs (cross-directory; disclosed cap on huge wikis),
  mass-deletion anomaly detection, quarantine inventory. Fixes what it can with
  logged reasoning; interviews you only on ambiguity.
- **`migrations/queue-governance-2-to-3`** — releases 0.2-gated pending queue
  entries under the new policy (data-plane entries apply; suggestions/holds
  stay). Idempotent, `--check` mode; named in `/ren:update`'s 0.3 notes.
- **`scripts/bump_version.py`** — version SSOT: one command rewrites every
  version literal; a repo lint fails on drift.
- **Friend guards:** plugin-manifest regression tests (the 0.2 manifest-loss
  class can't ship again), shared `parse_worker_json` (fenced/chatty worker
  output tolerated everywhere, incl. trailing prose), doctor companion checks
  (markitdown, yt-dlp — informational, graceful absence).

### Fixed

- `semantics`: negation markers now match on word boundaries — "whenever" is
  not "never". (Previously a false `contradicts` held every fresh install's
  identity write pending. Found because v2.2 made the write path load-bearing.)
- `apply_auto` now quarantine-marks llm-auto content (parity with the approved
  path).
- Wrap's LLM gate no longer silently downgrades durable classifications when
  the worker model appends trailing prose to its JSON.

## [0.2.1] — 2026-07-08

**Fix: `/ren:approve`, `/ren:reject`, `/ren:revert` were unregistered ("Unknown
command").** The queue skill was designed to own these verbs, and every
friend-facing surface (the ingest first-session artifact, the wrap screen, queue
confirmations, the README) tells you to run them — but Claude Code only registers
skill-*named* commands, so all three died at the prompt. Found by the Gate 0 live
smoke test (clean sandbox, real plugin loader) at the exact "approve your first
memory" moment.

- New `commands/approve.md`, `commands/reject.md`, `commands/revert.md` — thin
  command entries routing to the already-tested `skills.queue.lib` functions
  (`approve_and_apply` / `reject_with_reason` / `revert_write`).
- New repo-hygiene lint: every friend-facing `/ren:<verb>` reference (skills/,
  lib/, hooks/, README) must resolve to a `skills/<verb>/` dir or a
  `commands/<verb>.md` (planned-for-0.3 verbs allowlisted). This class of
  phantom command can't ship again.
- Reworded a prose-only `/ren:apply` mention in the queue SKILL.md.

Verified live: local-marketplace install registers 20 verbs; `/ren:approve`
round-trip drives the queue flow end-to-end. 696 tests green.

## [0.2.0] — 2026-07-07

Green-field rebuild per scope v2.1 ("the measured core") — a clean repo (`renos`), not
an in-place upgrade of the prior `startup-framework` 0.1.0 line. Proven pieces were
carried and renamed (identifiers, env vars, path conventions: `sf-` → `ren-`,
`~/.startup-framework` → `~/.renos`); everything else was rebuilt against the frozen
`0.2` interfaces defined in the Phase 1 write-safety substrate.

**Dogfood fixes (2026-07-07, live fresh-install drive):**

- `stamp_wiki` now binds `framework_version` — fresh installs no longer leave a
  literal `{{framework_version}}` in every stamped page (F1).
- `install_state().l2_maps` counts only `projects/` maps — the master `index.md`
  (itself `type: l2-map`) no longer reads as "a project exists" on a virgin
  install (F3).
- L2 pointer rendering omits the `#anchor` fragment when the anchor is null —
  no more literal `…/architecture.md#None` in queued maps (F4).
- Retrospective task-shape mining skips harness-injected turns (`isMeta`,
  `<command-name>`/caveat/system-reminder markers) — no more junk
  skill-candidates like `resume-session-command` mined from every session's
  boilerplate (F5).
- install SKILL.md contract now lists the directories the skeleton actually
  stamps (F2).

**Finalize pass (2026-07-07):**

- **Hierarchical CLAUDE.md pointer layer** (`lib/adapter/claude_md.py`) — always-on
  doctrine now DELIVERED via the harness's native global→project instruction-file
  hierarchy: install manages a marker block in the user-level file (tailored
  behavioral core with attribution to Karpathy's public guidelines, dedup-aware;
  the recall doctrine; wiki navigation; a doctrine index generated from
  `lib.doctrine.loader` — its first real consumer), and ingest/bootstrap stamp a
  thin per-repo pointer block at the project's L2 map. Additive, never-overwrite:
  only the managed block is ever touched.
- **Skill execution tiers** — every SKILL.md declares
  `execution_tier: deterministic | worker | judgment`; worker skills
  (ingest-project drafting, retrospective enrichment) delegate to cheap
  worker-model subagents; judgment (queue approvals, wrap's L1 narrative) stays
  with the main model. Doctor lints the declaration (`check_execution_tiers`).
- **Retrospective scaffolds** — skill-candidate findings now include an executable
  script scaffold (`proposed_scaffold`), not just an idea.
- **markitdown companion** documented as the raw→wiki source-compile path
  (`/ren:ingest-source` verb planned for 0.3).

**Headline features:**

- **The single write queue** (`lib/memory/queue.py`) — every producer (pin, wrap,
  retrospective, routine, promotion) proposes through one door; nothing writes a wiki
  page directly. Contradiction/supersede/duplicate detection, secrets-scrub, and
  idempotent dedup all happen at the queue itself, before anything reaches disk.
- **Risk-tiered governance** (`lib/governance/tiers.py`) — reads free, a routine's
  bounded memory writes auto-apply with provenance + one-step revert, durable
  knowledge and code/config changes are diff-approved, destructive actions always ask
  and hard-refuse with no human present.
- **Write-safety substrate** — provenance on every write, per-write snapshots, an
  append-only journal, one-step revert, file leases against lost updates. This is the
  frozen foundation everything else (queue, quarantine, promotion, doctor) is built on.
- **Instrumentation with ground truth** (`lib/instrument/`) — real
  `cache_read_input_tokens` from harness transcripts (not self-reported), a calibrated
  chars/token estimator, and the mechanical L3-miss log that makes wake-up's hit rate
  computable instead of asserted.
- **L1/L2 memory + heuristic-only wake-up** — session-scoped L1 (quarantine-bannered
  until reviewed) and per-project L2 pointer-maps (`projects/<slug>/map.md`), injected
  at session start by a wake-up hook with NO LLM call anywhere in its path (unanimous
  council decision) — ranking is token-overlap + recency + path-kind heuristics only.
- **The first-session artifact** — `/ren:ingest-project` scans an existing repo and
  shows "I set up your project memory — here's what I captured" on the very first run;
  `/ren:bootstrap-project` is the empty-map sibling for brand-new projects.
- **Minimal retrospective + skill-candidate mining** (v2.1 D-2) — a deterministic pass
  over instrumentation + journal + session history proposing lessons, instruction
  tweaks, and repeated-task skill candidates through the same queue. No eval-scored
  iteration loop.
- **Governed autonomy carried forward**: `/ren:doctor`'s ten isolated health checks
  (env, wiki structure, frontmatter, schema versions, budget lint, dangling L2
  pointers, graphify status, backup config, global-tier drift, harness neutrality),
  `/ren:update`'s snapshot/migrate/verify/rollback flow, `/ren:backup`'s git-push +
  tarball fallback, and `/ren:routine-init`'s v3 schema (mandatory capability/path
  allowlists — a routine's declaration must bound WHAT it may touch, not just when it
  runs).
- **Harness-neutral knowledge layer** (v2.1) — the wiki's canonical markdown IS the
  `AGENTS.md` surface; one working proof that Codex (a foreign harness) can read a
  project's context from the same files RenOS writes. See `docs/codex-read-proof.md`.
- **Obsidian-vault-compatible wiki** (v2.1 D-1) — relative links only, no state-dir
  leakage into template content, no `{{placeholder}}`/`[[wikilink]]` collisions.

**Harvest provenance:** ported from `startup-framework` 0.1.0 by disposition — CARRY
verbatim where donor logic was proven and self-contained (e.g. `scripts/version-compare.sh`,
the `routine-spec-1-to-2` migration), CARRY-ADAPT where identifiers/paths needed
renaming but logic stayed (backup, update, the identity template), ADAPT where the new
Python-integrated checks needed a different substrate than donor's bash (doctor), and
REBUILD where 0.2's frozen interfaces (provenance, the write queue, risk tiers) had no
donor equivalent at all. The full per-component disposition ledger lives in the
donor repo's own development wiki (not shipped here, per the framework's own
dev-wiki/shipped-skeleton separation).

**Known PENDING (calendar-bound, not code):** exit criteria 1 (≥20-session cache-token
publication), 2 (retrieval hit-rate published against the frozen fixture), 3 (estimator
calibrated against real sessions), and 6 (a friend week) all need real elapsed usage
this repo's tooling already supports collecting — see README.md's "Measured numbers"
section for the honest per-criterion status.
