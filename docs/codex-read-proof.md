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

**PENDING — run `scripts/codex_read_proof.sh`.**

The live proof run (with a real Codex install, against this repo's own
`AGENTS.md`) is deferred to final verification, per the orchestrator's plan —
this document and the script are the substrate; the actual run and its
recorded output land here once executed.
