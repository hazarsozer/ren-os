# Changelog

## [0.2.0] — Unreleased

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
