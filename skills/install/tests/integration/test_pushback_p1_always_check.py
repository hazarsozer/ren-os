"""P1 pin: Stage 1 env probes run on every /sf:install invocation.

Team-lead pushback: "always run Stage 1 checks (they're cheap); skip only the
prompt-for-fix step when all green." The check itself is the cost we pay for
correctness.
"""

from __future__ import annotations

from pathlib import Path

from integration.simulator import InstallSimulator, EnvSnapshot


def test_stage_1_probes_run_on_first_install(simulator) -> None:
    simulator.run()
    assert simulator.stage1_probe_count == 1


def test_stage_1_probes_run_again_on_reinstall(
    tmp_wiki: Path,
    tmp_checkpoint: Path,
    skeleton_root: Path,
    distribution_fake,
    lifecycle_fake,
) -> None:
    first = InstallSimulator(
        wiki_root=tmp_wiki,
        checkpoint_path=tmp_checkpoint,
        skeleton_root=skeleton_root,
        distribution=distribution_fake,
        lifecycle=lifecycle_fake,
    )
    first.run()
    assert first.stage1_probe_count == 1

    second = InstallSimulator(
        wiki_root=tmp_wiki,
        checkpoint_path=tmp_checkpoint,
        skeleton_root=skeleton_root,
        distribution=type(distribution_fake)(),
        lifecycle=type(lifecycle_fake)(),
    )
    second.run()
    # P1: re-running install runs Stage 1's probes again — not stale-cached.
    assert second.stage1_probe_count == 1


def test_stage_1_detects_env_change_between_runs(
    tmp_wiki: Path,
    tmp_checkpoint: Path,
    skeleton_root: Path,
    distribution_fake,
    lifecycle_fake,
) -> None:
    """Between two runs, gh auth goes from logged-in to logged-out.
    P1 demands the second run catches it."""
    first = InstallSimulator(
        wiki_root=tmp_wiki,
        checkpoint_path=tmp_checkpoint,
        skeleton_root=skeleton_root,
        distribution=distribution_fake,
        lifecycle=lifecycle_fake,
        env=EnvSnapshot(),  # default: all green
    )
    first.run()
    assert first.aborted_at is None

    second = InstallSimulator(
        wiki_root=tmp_wiki,
        checkpoint_path=tmp_checkpoint,
        skeleton_root=skeleton_root,
        distribution=type(distribution_fake)(),
        lifecycle=type(lifecycle_fake)(),
        env=EnvSnapshot(gh_auth=False),
    )
    second.run()
    # Stage 1 must surface the failure — not silently re-trust the prior green.
    assert second.aborted_at == 1
    assert second.state["stage_artifacts"]["1"]["env_ok"] is False
    assert second.state["stage_artifacts"]["1"]["checks"]["gh_auth"] is False
