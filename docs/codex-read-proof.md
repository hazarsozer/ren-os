# Codex read proof

Spec §3.9 A-9 (load-bearing, exit criterion 5): knowledge-layer files must
contain zero Claude-Code-specific structure — the canonical markdown itself
**is** the `AGENTS.md` surface (a thin pointer file, not a generated copy of
the wiki), and RenOS 0.2 ships **one working proof** that a foreign harness —
Codex — can actually read a project's context from those same files. Write
gates stay OS-side; foreign harnesses are read-only in 0.2.

## Design rationale

- **Canonical files as the surface, not generated copies.** `AGENTS.md` is
  rendered by `lib.portability.agents_surface.render_agents_md` and written
  directly to the repo root (`write_agents_md`) — it is short, orientation-only,
  and links into the real wiki pages (the project's L2 map, or the master
  index when unscoped, plus the global doctrine/preferences tier). It is never
  a dump of wiki content into a second file; that would create a second,
  driftable source of truth, exactly what a "canonical surface" is supposed to
  prevent.
- **Zero Claude-specific tokens, enforced.** `lint_harness_neutral` /
  `lint_generated_surfaces` check every surface WE generate (AGENTS.md itself,
  plus machine-assembled `l2-map` wiki pages) for harness-coupling markers
  (`claude`, `anthropic`, `CLAUDE_PLUGIN`, `SessionStart`, `hookSpecificOutput`,
  `/ren:`). A friend's own hand-written wiki prose is exempt — their content is
  theirs; the enforcement only applies to what our code generates for a
  foreign harness to read.
- **Foreign harnesses are read-only in 0.2.** `AGENTS.md` says so explicitly:
  a coding agent reading this file should treat every wiki page as read-only.
  Durable writes go through the write-queue (Task 2.1) regardless of which
  harness is driving the session; 0.2 does not attempt a foreign-harness write
  path.

## What the proof script does

`scripts/codex_read_proof.sh [target-repo-dir]`:

1. Checks whether the `codex` CLI is on `PATH`.
   - **Not installed:** prints `PENDING-HUMAN: codex CLI not installed — run
     this script on a machine with Codex; the proof procedure is documented in
     docs/codex-read-proof.md` and exits **3** — a distinct code so CI treats
     this as "pending a human with Codex installed," not a build failure. The
     proof cannot be faked or silently marked passing without a real Codex run.
2. If installed: `cd`s into the target repo (default `.`), confirms an
   `AGENTS.md` exists there, then runs:

   ```
   codex exec "Read AGENTS.md and the files it links; then answer: what is
   this project, and what are its three most important decisions? Cite which
   linked file each point came from."
   ```

   capturing raw output to `docs/codex-read-proof-output.txt`.
3. **Pass condition:** the captured output is non-empty AND cites the
   basename of at least one file `AGENTS.md` links to (a mechanical proxy for
   "Codex actually followed the links," not just hallucinated a plausible
   answer). Prints `PASS`/`FAIL` and exits 0/1 accordingly.

## What counts as a genuine pass (human judgment, beyond the mechanical check)

The mechanical citation check above is necessary but not sufficient. A human
reviewing `docs/codex-read-proof-output.txt` should additionally confirm:

- Codex oriented **from `AGENTS.md` alone** — no Claude-Code-specific files,
  hooks, or plugin state were needed for it to find and read the linked wiki
  pages.
- The three decisions/points Codex cites are **actually present** in the
  linked pages (not invented) and **correctly attributed** to the page each
  came from.
- Nothing in Codex's own read path required interpreting a Claude-Code
  convention (slash commands, hook output shapes, etc.) — if it did, that's a
  portability leak `lint_generated_surfaces` should also have caught.

## Result

**PASS — demonstrated live 2026-07-06** (exit criterion 5).

- Environment: codex-cli 0.139.0 (model gpt-5.5), read-only sandbox, against a
  fresh fixture wiki (project "falcon": L2 map + two decision pages + global
  preferences) and an `AGENTS.md` rendered by `lib.portability.agents_surface`
  (harness-neutrality lint: zero offenders).
- Behavior: Codex oriented from `AGENTS.md` alone, followed the map to both
  decision pages and the global tier, and answered "what is this project and
  its three most important decisions" correctly **with per-file citations** —
  it even distinguished a convention (uv/pytest, from preferences) from a
  formal decision record. Transcript: `docs/codex-read-proof-output.txt`.
- Two operational notes from the live run:
  1. Codex refuses untrusted non-git directories — the target repo must be a
     git repo (any real project is; the fixture needed `git init`).
  2. `lint_harness_neutral` scans rendered ABSOLUTE link paths, so a wiki
     located under a path containing "claude" (e.g. `/tmp/claude-*/…`)
     false-positives the lint. Cosmetic at 0.2 scale; noted for 0.3.
- Honesty note: Codex initially mis-resolved the map's RELATIVE pointer paths
  (resolving them against `projects/<slug>/` instead of the wiki root) and
  failed twice before recovering with `find`. The proof's conclusion stands —
  it read and cited the right pages — but pointer-path relativity is a real
  ambiguity in the L2-map format, tracked for the 0.4 planning cycle.
