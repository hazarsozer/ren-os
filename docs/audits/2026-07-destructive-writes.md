# Destructive-write audit — 2026-07 (issue #11 §2)

RenOS's value proposition is durable memory, yet two of the last four releases
fixed data-destroying bugs. The worst — `/ren:bootstrap-project` silently
overwriting a grown project L2 map with the empty bootstrap-day template,
latent since 0.2, fixed in 0.5.6 ("don't touch my map") — had a recognizable
shape:

> **the bug class: a template or generated write meets an existing file.**

This audit enumerates *every* write primitive in the shipped code that can
meet an existing file and classifies it. It is a live ledger, not a one-off:
`tests/audit/test_destructive_write_paths.py` fails if a new write site
appears in `lib/` or `skills/` without a row here, and fails if any row is
marked `VIOLATION` without `FIXED`.

## Method

Sweep (run from the repo root, `__pycache__` and tests excluded):

```
grep -rnE 'write_text\(|write_bytes\(|open\(.+["'"'"']w["'"'"']|shutil\.copy|shutil\.move|shutil\.rmtree|os\.replace|os\.rename|\.rename\(|\.unlink\(|rm -rf|cp -a|mv ' lib skills
```

`open(..., "a")` (append-only, e.g. `lib/memory/journal.py`) is deliberately
out of scope: appending cannot truncate. `shutil.copy*`, `shutil.move`,
`os.rename` and `Path.rename` have zero hits in Python code — the only
`shutil.rmtree` is the snapshot-store prune (#7). The shell tree operations
(`rm -rf`, `cp -a`) live entirely in `skills/update/scripts/`: **three**
scripts, not one — `snapshot.sh` (#19), `restore.sh` (#20, which deletes the
whole wiki tree before restoring it), and `prune-snapshots.sh` (#21). All three
are classified below. The shell patterns are part of the covering test's sweep
too, so a new `rm -rf` in a shipped script fails the suite until it is
classified here.

## Classification vocabulary

| Class | Meaning |
|---|---|
| `additive` | Checks existence first, appends, or splices inside its own markers — pre-existing bytes always survive |
| `queue-mediated` | Goes through `lib/memory/queue.py` → `lib/memory/write_apply.py` (lease, snapshot, journal, revert path) |
| `confirmed` | Happens only behind an explicit user action targeting that exact file |
| `scratch/state` | Writes framework state, not user knowledge: `state_dir()` JSON, metrics, queue/suggestion entry files, lock files, snapshot store. Losing one costs bookkeeping, never a page a human wrote |
| **`VIOLATION`** | Can truncate/overwrite content a human grew, with none of the above properties |

**On "user knowledge" vs "framework state".** The honest line: a file holds
user knowledge if a human's words can only be recovered from it. Wiki pages
under `wiki_root()` (`index.md`, `log.md`, `identity.md`, `projects/*/map.md`,
`projects/*/overview.md`, lessons, decisions) qualify. `state_dir()/*.json`
(install record, estimator ratio, metric-watch history, companion decisions,
queue and suggestion entry files, lock files) does not — every one is
regenerable or purely bookkeeping. Two edge cases worth naming rather than
hand-waving: **companion decisions** (`companions/choices.json`) and
**suggestion decision records** are *human decisions*, so losing them is worse
than losing a metric — but both are atomically written, additively merged
(read-modify-write over the whole dict), and never truncated by a template, so
they stay `scratch/state`. Repo-side generated pointer files (`AGENTS.md`,
`CLAUDE.md`) are regenerable *as far as RenOS's own block goes* — but the file
they live in may be the human's, which is precisely where this audit found its
one violation.

## The single door

`lib/memory/write_apply.py::apply_write` is the only function that writes a
wiki page. Everything wiki-side in the table below either *is* that function
or routes through it. Notably `lib/skeleton.py::stamp_skeleton` (the template
stamper — the 0.5.6 bug's neighborhood) contains **no** write primitive of its
own: it checks `target.exists()` per entry and hands rendered content to
`apply_write`. `skills/bootstrap-project/lib` likewise checks
`page_abs.exists()` before proposing the L2 map (that check *is* the 0.5.6
fix), and `skills/ingest-project/lib` and `skills/wiki-migration/lib` contain
no write primitives at all.

## Audit table

| # | Site | Primitive | Class | Reasoning |
|---|---|---|---|---|
| 1 | `lib/memory/write_apply.py:97-98` | `write_text` + `os.replace` | queue-mediated | THE door. Inside `locks.lease`, after `expect_token` check, after `snapshot.take` of prior bytes, journaled last. Overwrite is the point; revert is always available. |
| 2 | `lib/memory/write_apply.py:100` | `unlink(missing_ok=True)` | queue-mediated | `op="DELETE"`, same lease/snapshot/journal envelope. |
| 3 | `lib/memory/queue.py:155-156` | `write_text` + `os.replace` | scratch/state | `_persist` of a queue entry JSON under `state_dir()`. Atomic temp+replace; holds no page content a human authored (the proposal body is a copy en route to a page). |
| 4 | `lib/memory/queue.py:407, 476, 532` | via `apply_write` | queue-mediated | `apply_pending` / `apply_auto` / contradiction-resolved apply. ADD proposals additionally run `_check_add_race` (codex D5), which refuses to clobber a page created out-of-band between propose and apply — the same "ADD assumed absence" defense as 0.5.6, one layer up. |
| 5 | `lib/memory/snapshot.py:63` | `write_text("")` | scratch/state | ABSENT marker in the snapshot store, keyed by `write_id`; path is unique per write. |
| 6 | `lib/memory/snapshot.py:85, 96` | `unlink`, `write_bytes`+`os.replace` | confirmed | `restore()` — overwriting the live page is the *purpose*, and it only runs from an explicit revert (`/ren:revert`) naming that `write_id`. Atomic. |
| 7 | `lib/memory/snapshot.py::prune` | `shutil.rmtree` of old `w-*` dirs | scratch/state | Retention over the snapshot store (`snapshotRetain`); ULID-sorted, newest kept. Never touches live pages. |
| 8 | `lib/memory/locks.py:127, 138, 143` | `os.fdopen(..., "w")`, `unlink` | scratch/state | Lease files. `O_EXCL` create, unlink on release/stale-break. (On the 0.6 do-not-fix list — deliberately unchanged.) |
| 9 | `lib/adapter/claude_md.py:268-269` | `write_text` + `os.replace` | additive | `_atomic_write`, reached only from `apply_block`, which splices strictly between `<!-- ren:begin -->` / `<!-- ren:end -->`. Content outside the markers is byte-preserved; torn markers return `"conflict"` and touch nothing. This is the pattern the violation below was fixed with. |
| 10 | `lib/portability/agents_surface.py::write_agents_md` | (was `write_text`) now `apply_block` | **VIOLATION — FIXED** | See below. |
| 11 | `lib/companions/__init__.py:121-122` | `write_text` + `os.replace` | scratch/state | `record_choice` — read-modify-write of the whole choices dict, atomic. Additive per key; last-writer-wins across concurrent sessions is documented and accepted for a single-user tool. |
| 12 | `lib/suggestions/__init__.py:84-85` | `write_text` + `os.replace` | scratch/state | `_persist` of one suggestion JSON, path keyed by its own `sid`. |
| 13 | `lib/suggestions/__init__.py:226` | `unlink(missing_ok=True)` | scratch/state | Retention prune of *decided* suggestions past the cutoff; the durable record of the decision is the append-only `decisions.jsonl` ledger, which this never touches. |
| 14 | `lib/instrument/estimator.py:106-107` | `write_text` + `os.replace` | scratch/state | Blended chars-per-token ratio in `state_dir()`; recomputes from future samples if lost. |
| 15 | `skills/install/lib/__init__.py:163-164` | `write_text` + `os.replace` | scratch/state | `record_install` → `state_dir()/install.json` (version + timestamp). |
| 16 | `skills/metric-watch/lib/__init__.py:69` | `write_text` | scratch/state | `state_dir()/metric-watch.json` fire-once bookkeeping; read-modify-write of the whole dict, no user knowledge. Non-atomic (no temp+replace) — a crash mid-write costs one budget-alert suppression flag, so it is left alone rather than churned. |
| 17 | `skills/backup/lib/__init__.py:142` | `unlink` | scratch/state | `prune_old_tarballs` — retention over `wiki-*.tar.gz` backups, keeps the newest `keep`; strict filename regex, never the wiki itself. |
| 18 | `skills/backup/lib/__init__.py:343` | `unlink` | scratch/state | Removes the *partial tarball this call just created* after a `tarfile` failure. |
| 19 | `skills/update/scripts/snapshot.sh:59-64, 74` | `cp -a` / `cp -al`, `rm -rf` | scratch/state | Pre-update wiki snapshot into `wiki-snapshots/<name>/` (fresh timestamped dir, never an existing one), plus retention `rm -rf` of the oldest snapshot dirs. Reads the wiki, never writes into it. The `cp -a` default over `cp -al` is itself a defense against this bug class (hard-linked snapshots would share inodes with the live wiki and be corrupted by any naive truncate-and-rewrite). |
| 20 | `skills/update/scripts/restore.sh:51-52` (and `:78`) | `rm -rf "$WIKI_ROOT"` + `cp -a`, `cp -a` per page | confirmed | The largest blast radius in the codebase: `--whole` **deletes the entire live wiki tree** and replaces it with the snapshot. Classified `confirmed` because the script is only reachable from `/ren:update --restore-snapshot`, where the friend picks a specific snapshot out of the `--list` picker, and `--whole` refuses (`exit 2`) unless that snapshot directory exists. Destroying current content *is* restore, same reasoning as #6. Two properties recorded rather than changed (pre-existing behavior, surgical constraint): (a) the pre-restore stash at `:47` is **best-effort only** — `if cp -al … \|\| cp -a …; then` gates only the `echo`, so if both copies fail the `rm -rf` still runs and the pre-restore state is unrecoverable; (b) `--page` (`:78`) overwrites one live page with no existence check, also by design. |
| 21 | `skills/update/scripts/prune-snapshots.sh:47, 64` | `rm -rf` | scratch/state | Retention over `${CLAUDE_PLUGIN_DATA}/wiki-snapshots/`: oldest `v*-pre-update-*` dirs (`:47`) and oldest `STASH-broken-*` dirs (`:64`) beyond `snapshotRetain`. Both `find` globs are `-maxdepth 1` under the snapshot base with strict name patterns, so nothing outside the snapshot store is reachable and the live wiki is never touched. `--dry-run` reports without deleting. |
| 22 | `lib/instrument/calibration.py::_write_text_atomic` | `write_text` + `os.replace` | scratch/state | `state_dir()/metrics/last_injection.json` — the scratch pairing file wake-up overwrites each session (0.6.1 E5a), holding `{"session": <harness session_id>, "text": <payload>}`. Overwrite IS the contract (exactly one session, never a history); nothing user-authored can live at that path, and losing it costs at most one skipped calibration. **Confidentiality note (not a destructive-write concern):** `text` is a VERBATIM COPY of the wiki content wake-up surfaced, living OUTSIDE the wiki — so it is outside the wiki backup/scrub regime (`/ren:backup` doesn't capture it; wiki-side redaction/quarantine changes don't retroactively reach it). Bounded to one session's payload and overwritten on the next SessionStart, so the exposure window is one session; degrade payloads are never persisted at all. Anything stricter (scrub-on-read, or storing only the char count) is a 0.6.2 call. |

Counts: 22 sites — `queue-mediated` 4, `additive` 1, `confirmed` 2,
`scratch/state` 14, **`VIOLATION` 1 (fixed)**.

## VIOLATION 1 — `write_agents_md` truncated a pre-existing AGENTS.md

**Site:** `lib/portability/agents_surface.py::write_agents_md`, reached from
`skills/bootstrap-project/lib::bootstrap` whenever `repo_root` is given.

**Before:** `path.write_text(content)` — unconditional. The old docstring
called this "idempotent: re-running overwrites the prior content", which is
true for a file RenOS itself generated and false for the case that matters.

**Failure scenario:** a friend runs `/ren:bootstrap-project` in a repo that
already has a hand-authored `AGENTS.md` (a cross-agent convention — plenty of
repos, including ones written for other tools, ship one). Their build rules,
directory conventions, and review instructions are replaced by RenOS's
pointer stub. No snapshot, no journal line, no revert path: the file is
repo-side, so it never went through `write_apply`. If it wasn't committed,
it's gone. Same shape as the 0.5.6 map bug, in a different plane.

**Fix (test-first):** route the write through
`lib.adapter.claude_md.apply_block`, the marker-scoped splice already used and
tested for the CLAUDE.md pointer layer — no new mechanism. Resulting behavior:

- no file → our block is the file (unchanged from before);
- existing file without our markers → our block is **appended**, their bytes
  preserved verbatim;
- existing file with our markers → only the block between them is rewritten
  (so refreshes still don't accumulate, which the pre-existing rerun test
  pins);
- torn markers → nothing is touched, `"conflict"` reported.

Pinned by `tests/audit/test_destructive_write_paths.py::test_write_agents_md_preserves_pre_existing_hand_authored_file`
(failed before the fix, passes after).

## Borderline calls, recorded not refactored

- **`snapshot.restore` (#6)** overwrites a live page with no existence check.
  Classified `confirmed`, not a violation: destroying current content is the
  literal definition of revert, and it is only reachable from a user naming a
  `write_id`.
- **`queue.apply_*` with `op="UPDATE"` (#4)** replaces a page wholesale. Not a
  violation: `expect_token`/`_check_add_race` guard the read-modify-write
  window, and the callers that build UPDATE content
  (`lib/memory/lifecycle.py::consolidate`, `lib/memory/archive.py`) derive it
  from the page's *current* bytes rather than from a template — the
  distinction that separates a merge from a truncation.
- **`metric-watch` state (#16)** is the only non-atomic write in the ledger.
  Deliberately left: it holds a suppression flag, and rewriting it would be
  churn against the "surgical" constraint.
- **`skills/backup` unlinks (#17, #18)** delete user-facing artifacts
  (tarballs), but both are bounded retention/cleanup of files the skill itself
  created, with the live wiki untouched.
| 23 | `lib/ren_paths.py::record_project_repo` | `write_text` + `os.replace` | scratch/state | `state_dir()/projects.json` — the repo-path↔slug registry (issue #19), written at ingest/bootstrap time. Merge-then-atomic-replace: the existing registry is loaded and only the one slug's entry is set, so other projects' mappings survive; a corrupt/unreadable file degrades to `{}` (rebuilt on the next ingest) rather than raising. Nothing user-authored lives at that path, and losing it only falls detection back to dir-name matching. |
