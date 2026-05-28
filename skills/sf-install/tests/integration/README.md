# sf-install integration tests

These tests pin the **contracts** sf-install consumes from peer skills. They're not unit tests of any Python implementation (sf-install is a SKILL.md, not a Python module) — they're executable specifications that:

1. Walk the 7-stage `/sf:install` procedure stage-by-stage via a thin simulator.
2. Exercise that procedure against fakes for `feed`, `distribution`, and `lifecycle`.
3. Assert the procedure makes the right calls in the right order with the right arguments.
4. **Fail loudly when a peer's real impl drifts from the documented API.**

When a real Claude Code session runs `/sf:install`, the AI follows the steps in `skills/sf-install/SKILL.md` + the per-stage references. The AI's calls into `feed`, `distribution`, `lifecycle` should match what the simulator does. If they don't, this harness is the canary.

## Run

From the repo root:

```bash
python3 -m pytest skills/sf-install/tests/integration/ -v
```

Stdlib + pytest only. No external services touched (fakes simulate everything).

## Layout

```
integration/
├── README.md                 — this file
├── __init__.py
├── conftest.py               — pytest fixtures (tmp wiki + checkpoint path, fakes registry)
├── fakes/
│   ├── __init__.py
│   ├── feed_fake.py          — implements the feed contract surface sf-install uses
│   ├── distribution_fake.py  — pinned-version registry + LICENSES regen surface
│   └── lifecycle_fake.py     — doctor.report() shape stub
├── simulator.py              — InstallSimulator that walks the 7 stages
├── test_fresh_machine.py
├── test_joiner.py
├── test_idempotent_reinstall.py
├── test_stage5_additive_diff.py
├── test_pushback_p1_always_check.py
├── test_pushback_p2_additive_only.py
├── test_pushback_p3_no_auto_invoke.py
└── test_contract_drift.py
```

## What each test covers

| Test file | Scenario | Pushback / contract it pins |
|---|---|---|
| `test_fresh_machine.py` | Fresh-machine install, all 7 stages run to completion | End-to-end happy path |
| `test_joiner.py` | Existing Activity Feed; Stage 3 detects + clones; no bootstrap | feed.detect_repo_state + feed.clone_existing |
| `test_idempotent_reinstall.py` | Re-run on a fully completed install — all stages no-op | Resume-protocol idempotency |
| `test_stage5_additive_diff.py` | Framework v+1 ships a new template; Stage 5 surfaces additive diff | P2 (additive-only, no overwrite) |
| `test_pushback_p1_always_check.py` | Stage 1 probes run even when checkpoint marks completed | P1 (always-check) |
| `test_pushback_p2_additive_only.py` | Stage 5 against existing wiki never overwrites | P2 (additive-only) |
| `test_pushback_p3_no_auto_invoke.py` | Stage 7 acknowledgment doesn't trigger any other slash command | P3 (manual handoff) |
| `test_contract_drift.py` | Each peer fake's call site uses the documented signature | All cross-team contracts |

## Fakes

Each fake re-implements the **contract surface** sf-install consumes. Where peer skills export their own `_fake` variants (e.g. `feed.feed_write_session_start_fake`, `feed.feed_write_session_end_fake`, `feed.feed_read_friends_tails_fake` — the writer split that landed in feed-2's refactor), we use them directly. Where they don't, we hand-roll fakes that match the locked API.

sf-install itself doesn't call the writer functions (those are lifecycle-2's `/sf:wrap` territory) — sf-install's feed surface is `feed_detect_repo_state` / `feed_bootstrap_first_friend` / `feed_clone_existing` / `feed_upsert_identity` / `rename_handle`, all of which are unchanged across the refactor.

If a peer changes their real API and forgets to update their `_fake`, `test_contract_drift.py` catches it: the test imports the peer's real symbol AND the fake, compares signatures, and fails on mismatch.

## Adding a new test

1. Decide which scenario / contract you're pinning.
2. Use the `InstallSimulator` fixture from `conftest.py` so you don't re-walk the stages by hand.
3. Configure the fakes' simulated responses via their `inject_*` methods (e.g. `feed_fake.inject_detect_response(...)`).
4. Run the simulator; assert on its public `state` + the fakes' `calls` recordings.
5. If the new test exposes a contract gap (something sf-install needs but no fake models), update both the fake AND `references/stage-<N>-*.md` to document the assumption.

## When to update vs. when to fail

If a peer changes their API:

- **Documented intentional change** (e.g. team-lead-approved signature lock) → update the fake to match + update the simulator + update the relevant `stage-<N>-*.md` ref. Tests should turn green again.
- **Undocumented drift** (e.g. impl renamed without coordinator approval) → keep the test failing. Surface to team-lead with the drift report. Don't paper over the contract.

The whole point of `test_contract_drift.py` is to make this distinction loud.
