# Changelog

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
