# sf-install integration tests

These tests pin the **contracts** sf-install consumes from peer skills. They're not unit tests of any Python implementation (sf-install is a SKILL.md, not a Python module) — they're executable specifications that:

1. Walk the 7-stage `/ren:install` procedure stage-by-stage via a thin simulator.
2. Exercise that procedure against fakes for `distribution` and `lifecycle`.
3. Assert the procedure makes the right calls in the right order with the right arguments.
4. **Fail loudly when a peer's real impl drifts from the documented API.**

When a real Claude Code session runs `/ren:install`, the AI follows the steps in `skills/sf-install/SKILL.md` + the per-stage references. The AI's calls into `distribution`, `lifecycle` should match what the simulator does. If they don't, this harness is the canary.

> Solo-first (ADR-031): the Activity Feed layer was removed. There is no `feed` fake and no joiner test — Stage 3 is conditional-plugins-only and Stage 4 writes only the local `wiki/identity.md`.

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
│   ├── distribution_fake.py  — pinned-version registry + LICENSES regen surface
│   └── lifecycle_fake.py     — doctor.report() shape stub
├── simulator.py              — InstallSimulator that walks the 7 stages
├── test_fresh_machine.py
├── test_daily_loop_e2e.py
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
| `test_daily_loop_e2e.py` | Install → interview → wake-up → note → wrap against REAL peer impls | First-day journey behavior (solo-first) |
| `test_idempotent_reinstall.py` | Re-run on a fully completed install — all stages no-op | Resume-protocol idempotency |
| `test_stage5_additive_diff.py` | Framework v+1 ships a new template; Stage 5 surfaces additive diff | P2 (additive-only, no overwrite) |
| `test_pushback_p1_always_check.py` | Stage 1 probes run even when checkpoint marks completed | P1 (always-check) |
| `test_pushback_p2_additive_only.py` | Stage 5 against existing wiki never overwrites | P2 (additive-only) |
| `test_pushback_p3_no_auto_invoke.py` | Stage 7 acknowledgment doesn't trigger any other slash command | P3 (manual handoff) |
| `test_contract_drift.py` | Each peer fake's call site uses the documented signature | Cross-team contracts (distribution + lifecycle) |

## Fakes

Each fake re-implements the **contract surface** sf-install consumes. Where peer skills export their own `_fake` variants, we use them directly. Where they don't, we hand-roll fakes that match the locked API.

After the solo-first pivot (ADR-031), sf-install's only peer surfaces are `distribution` (pinned-version registry + LICENSES regen) and `lifecycle` (`doctor.report()`). There is no `feed` surface — the Activity Feed module was removed.

If a peer changes their real API and forgets to update their `_fake`, `test_contract_drift.py` catches it: the test imports the peer's real symbol AND the fake, compares signatures, and fails on mismatch.

## Adding a new test

1. Decide which scenario / contract you're pinning.
2. Use the `InstallSimulator` fixture from `conftest.py` so you don't re-walk the stages by hand.
3. Configure the fakes' simulated responses via their `inject_*` methods.
4. Run the simulator; assert on its public `state` + the fakes' `calls` recordings.
5. If the new test exposes a contract gap (something sf-install needs but no fake models), update both the fake AND `references/stage-<N>-*.md` to document the assumption.

## When to update vs. when to fail

If a peer changes their API:

- **Documented intentional change** (e.g. team-lead-approved signature lock) → update the fake to match + update the simulator + update the relevant `stage-<N>-*.md` ref. Tests should turn green again.
- **Undocumented drift** (e.g. impl renamed without coordinator approval) → keep the test failing. Surface to team-lead with the drift report. Don't paper over the contract.

The whole point of `test_contract_drift.py` is to make this distinction loud.
