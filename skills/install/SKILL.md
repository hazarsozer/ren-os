---
name: install
description: |
  Use for first-time setup of RenOS, or to resume a partial setup. Triggers
  on the /ren:install slash command. Idempotent guided flow: environment
  check, wiki bootstrap, optional interview, backup nag, companion offers,
  first project, then a closing summary of what's now possible. Every stage
  is skippable except wiki bootstrap; re-running skips whatever's already
  done.
version: 0.5.5
license: MIT

framework_version: "0.5.5"
schema_version: 1
type: skill
execution_tier: judgment

contract:
  required_outputs:
    - "Master wiki stamped at wiki_root() (index.md, log.md, identity.md, LICENSES.md, research/, decisions/, alternatives/, patterns/, projects/)"
    - "RenOS managed block present in claude_user_dir()/CLAUDE.md (markers only — content outside them untouched)"
    - "A closing summary naming what the friend can now do (pin/recall/wrap/remember)"
    - "state_dir()/install.json recording the installed version"
  budgets:
    turns: 10
    files_written: 20
    duration_seconds: 300
  permissions:
    read:
      - "~/.renos/wiki/**"
    write:
      - "~/.renos/wiki/**"
      - "~/.renos/wiki/.ren/install.json"
      - "~/.claude/CLAUDE.md"
    execute:
      - "uv tool install *"
  completion_conditions:
    - "install_state(wiki_root()).wiki_stamped is True"
    - "state_dir()/install.json exists with the current framework_version"
  output_paths:
    - "~/.renos/wiki/"
    - "~/.renos/wiki/.ren/install.json"
    - "~/.claude/CLAUDE.md"

tags: [onboarding, install, idempotent, first-session]
related_skills: [interview, ingest-project, bootstrap-project, backup]
references_required: []
references_on_demand: ["references/stage-wiki-bootstrap.md", "references/stage-walkthrough.md"]
---

# install

First-time setup, or resuming a partial one. `skills.install.lib.install_state()` is read at the start of EVERY stage below — a stage that's already done (per real on-disk state) is skipped, never redone or asked about twice. Exit criterion 6: a friend can install → onboard (within the question budget) → see the first-session artifact → work a week → update — without the founder present. This flow is that path.

## Stages (idempotent — check `install_state()` before each)

1. **Doctor quick-pass.** A fast environment sanity check (framework version reachable, wiki root resolvable). Not a full `/ren:doctor` run — just enough to know setup can proceed.
2. **Stamp wiki** — `skills.install.lib.stamp_wiki()`. Additive-only (per `lib.skeleton`'s contract): if `install_state().wiki_stamped` is already `True`, this is a no-op report, not a re-stamp. This is the ONE non-skippable stage — nothing else here means anything without a wiki root to write into.
3. **Global instruction layer** — `lib.adapter.claude_md.write_global_claude_md()`. Writes/refreshes the RenOS managed block (between `<!-- ren:begin -->`/`<!-- ren:end -->` markers) in the user-level `CLAUDE.md`: the tailored behavioral core (omitted automatically if the friend's file already carries the Karpathy guidelines), the recall doctrine, wiki navigation, and the doctrine index (generated from `lib.doctrine.loader` — this is how always-on doctrine reaches every session). ONLY the marker block is ever touched — everything else in the friend's file is preserved byte-for-byte. If it returns `"conflict"` (torn markers from a hand edit), tell the friend which file to fix and move on; never force it. Skip silently when `install_state().global_claude_md` is `True` and the framework version hasn't changed.
4. **Interview** — delegates entirely to `/ren:interview` (see that skill). MAY BE SKIPPED ENTIRELY: if the friend says "skip to coding" (or equivalent), print exactly which defaults were assumed (`skills.interview.lib.QUESTIONS`' `default` values) and move on. `identity.md` already exists as a stub after stage 2 either way (the skeleton's `copy_if_missing` stamp) — the interview only UPDATEs it with real answers.
5. **Backup setup offer.** If `install_state().backup_configured` is `True`, skip silently. Otherwise offer to configure a `backup` git remote (see `/ren:backup`) and note that install nags until it's configured — this is the one recurring nag in the flow, per spec §3.9 "backup first-class."
6. **Companions** — skippable. Call `lib.companions.pending_offers()`. If empty
   (everything already installed or decided), say so in one line and move on.
   Otherwise present each offer conversationally — title, one-line pitch, and
   the install hint — and ask which the friend wants. This is a multi-pick,
   not per-item nagging.
   - Accepted **tool** (`kind == "tool"`): run its `install_hint` command for
     them (it is always a `uv tool install …`), confirm it landed
     (`shutil.which`), then `lib.companions.record_choice(cid, "accepted")`.
   - Accepted **plugin** (`kind == "plugin"`): show the `install_hint` for the
     friend to run themselves (plugin installs need a session restart to
     activate — say so plainly), then `record_choice(cid, "accepted")`.
   - Declined: `record_choice(cid, "declined")` — a durable no; RenOS never
     asks about that companion again.
   - Stage skipped entirely: record nothing — the same offers reappear at the
     next `/ren:install` or `/ren:update`.
   Nothing is ever installed without an explicit yes in chat.
7. **First project.** Offer `/ren:ingest-project <path>` (an existing repo) or `/ren:bootstrap-project <name>` (a fresh idea) — either one ends with the FIRST-SESSION ARTIFACT (Task 4.4's `ingest()`/L2-map assembly): "I set up your project memory — here's what I captured," rendered from the real map that was just written. This is the cheapest trust-builder in the whole system (spec §3.8 A-10) — don't skip presenting it even if the friend picks "skip everything else."
8. **Record + closing summary.** `skills.install.lib.record_install(current_framework_version)`, then a short summary: what you can do now — `/ren:pin` (remember something), `/ren:recall` (look something up), `/ren:wrap` (end-of-session consolidation), and re-running `/ren:interview` anytime to fill in more identity detail.

## Idempotency contract

Every stage above is a no-op if `install_state()` already reports it done — re-running `/ren:install` from any point (interrupted session, friend re-invokes out of habit) picks up exactly where it left off. There is no separate "resume" command; `install_state()` inspecting real files IS the resume mechanism (donor's InstallSimulator existed to fake this same idea in tests; RenOS drives it against real state instead).

## Design notes

- Donor's 7-stage flow (env, required plugins, conditional plugins, identity, wiki bootstrap, doctor verify, walkthrough) maps to 8 stages here — RenOS ships as one plugin, so donor's plugin-negotiation stages don't apply; the global instruction layer (stage 3, finalize-v0.2 agenda item 1) takes their slot as the doctrine-delivery stage. Stage 6 (companions, 0.3.5) is new and has no donor counterpart — it offers the recommended companion tools/plugins from `lib.companions`.
- The question budget (`skills.install.lib.QUESTION_BUDGET = 10`) is enforced by `skills.interview.lib.QUESTIONS`'s length, not re-checked here — install just delegates and trusts the cap.
