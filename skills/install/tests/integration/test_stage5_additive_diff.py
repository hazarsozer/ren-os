"""Stage 5 additive-diff — framework version bump adds a new template; loader
surfaces it without overwriting existing files."""

from __future__ import annotations

from pathlib import Path


def test_simulated_v1_1_new_template_lands_additively(
    simulator, tmp_wiki: Path,
) -> None:
    """First install on v1.0 → wiki has the standard skeleton. Simulate v1.1
    by manually deleting one expected subdirectory's .gitkeep, then running
    install again — the missing entry shows up in additive_changes_applied."""
    simulator.run()
    assert simulator.aborted_at is None

    # "Remove" a recent template addition to simulate this wiki being from
    # an earlier framework version (missing the new file).
    target = tmp_wiki / "alternatives" / ".gitkeep"
    assert target.exists()
    target.unlink()

    from integration.simulator import InstallSimulator

    second = InstallSimulator(
        wiki_root=tmp_wiki,
        checkpoint_path=simulator.checkpoint_path,
        skeleton_root=simulator.skeleton_root,
        distribution=type(simulator.distribution)(),
        lifecycle=type(simulator.lifecycle)(),
    )
    second.run()

    # Per stage-5 contract: missing file shows as additive_changes_applied.
    applied = second.state["stage_artifacts"]["5"]["additive_changes_applied"]
    assert "alternatives/.gitkeep" in applied
    # Existing files untouched.
    assert (tmp_wiki / "index.md").exists()
    assert (tmp_wiki / "log.md").exists()


def test_stage_5_first_run_records_all_writes(simulator) -> None:
    simulator.run()
    applied = simulator.state["stage_artifacts"]["5"]["additive_changes_applied"]
    # Fresh install: index.md, log.md, LICENSES.md, plus the 5 .gitkeep files.
    assert "index.md" in applied
    assert "log.md" in applied
    assert "LICENSES.md" in applied
    assert any(f.endswith(".gitkeep") for f in applied)
