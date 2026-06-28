"""Fresh-machine install — all 7 stages run to completion."""

from __future__ import annotations

import json
from pathlib import Path


def test_fresh_machine_runs_all_seven_stages(simulator) -> None:
    simulator.run()

    assert simulator.aborted_at is None, (
        f"unexpected abort at stage {simulator.aborted_at}: {simulator.abort_reason}"
    )
    assert simulator.state["completed_stages"] == [1, 2, 3, 4, 5, 6, 7]


def test_fresh_machine_writes_valid_checkpoint(simulator, tmp_checkpoint: Path) -> None:
    simulator.run()

    assert tmp_checkpoint.exists()
    state = json.loads(tmp_checkpoint.read_text(encoding="utf-8"))
    assert state["schema_version"] == 1
    assert state["framework_version"] == "0.1.0"
    assert "started_at" in state
    assert "last_updated_at" in state
    assert state["completed_stages"] == [1, 2, 3, 4, 5, 6, 7]


def test_fresh_machine_writes_identity_md(simulator, tmp_wiki: Path) -> None:
    simulator.run()

    identity_md = tmp_wiki / "identity.md"
    assert identity_md.exists()

    body = identity_md.read_text(encoding="utf-8")
    assert "handle: eval-friend" in body
    assert 'name: "Eval Friend"' in body
    assert "phase: ideation" in body
    assert "schema_version: 1" in body


def test_fresh_machine_stage_2_installs_all_six_plugins(simulator, distribution_fake) -> None:
    simulator.run()

    installed = simulator.state["stage_artifacts"]["2"]["plugins_installed"]
    names = [p["name"] for p in installed]
    assert names == list(simulator.REQUIRED_PLUGIN_NAMES)
    assert ("read_pinned_registry",) in [tuple(c) for c in distribution_fake.calls]


def test_fresh_machine_stage_5_creates_full_skeleton(simulator, tmp_wiki: Path) -> None:
    simulator.run()

    assert (tmp_wiki / "index.md").exists()
    assert (tmp_wiki / "log.md").exists()
    assert (tmp_wiki / "LICENSES.md").exists()
    assert (tmp_wiki / "identity.md").exists()  # Stage 4 wrote this; Stage 5 left alone

    for sub in ("research", "decisions", "alternatives", "patterns", "projects"):
        path = tmp_wiki / sub
        assert path.is_dir(), f"expected directory {path}"
        assert (path / ".gitkeep").exists(), f"expected .gitkeep in {path}"


def test_fresh_machine_stage_6_passes_doctor(simulator, lifecycle_fake) -> None:
    simulator.run()

    assert simulator.state["stage_artifacts"]["6"]["doctor_passed"] is True
    assert ("doctor_report",) in [tuple(c) for c in lifecycle_fake.calls]


def test_fresh_machine_stage_7_acknowledges_walkthrough(simulator) -> None:
    simulator.run()

    assert simulator.state["stage_artifacts"]["7"]["walkthrough_acknowledged"] is True
    assert "acknowledged_at" in simulator.state["stage_artifacts"]["7"]
