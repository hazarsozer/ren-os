"""P2 pin: Stage 5 NEVER overwrites existing wiki files.

Team-lead pushback: "diff skeleton-template-set vs existing wiki, show what would
be added (never overwritten), require explicit approve. Existing files are NEVER
touched."
"""

from __future__ import annotations

from pathlib import Path


def test_stage_5_does_not_overwrite_hand_edited_index_md(
    simulator, tmp_wiki: Path,
) -> None:
    """Run install once, friend edits index.md, run install again. The hand-edit
    survives byte-for-byte."""
    simulator.run()

    index_md = tmp_wiki / "index.md"
    assert index_md.exists()
    hand_edit = "## My custom section\n\nA section I added by hand.\n"
    body = index_md.read_text(encoding="utf-8") + hand_edit
    index_md.write_text(body, encoding="utf-8")
    snapshot = index_md.read_text(encoding="utf-8")
    snapshot_mtime = index_md.stat().st_mtime

    # Re-run the orchestrator. P2: Stage 5 must NOT touch index.md.
    from integration.simulator import InstallSimulator

    second = InstallSimulator(
        wiki_root=tmp_wiki,
        checkpoint_path=simulator.checkpoint_path,
        skeleton_root=simulator.skeleton_root,
        distribution=type(simulator.distribution)(),
        lifecycle=type(simulator.lifecycle)(),
    )
    second.run()

    assert index_md.read_text(encoding="utf-8") == snapshot
    # mtime should also be unchanged (loader never touched the file)
    assert index_md.stat().st_mtime == snapshot_mtime


def test_stage_5_records_zero_overwrites(simulator, tmp_wiki: Path) -> None:
    """The simulator's stage5_overwrites list MUST remain empty."""
    simulator.run()
    assert simulator.stage5_overwrites == [], (
        f"Stage 5 overwrote files: {simulator.stage5_overwrites}"
    )


def test_stage_5_writes_only_missing_files_on_reinstall(
    simulator, tmp_wiki: Path,
) -> None:
    """First install creates the skeleton. Re-run: stage_artifacts.5
    additive_changes_applied is empty (nothing new to add)."""
    simulator.run()
    first_applied = simulator.state["stage_artifacts"]["5"]["additive_changes_applied"]
    assert first_applied  # first run wrote at least index.md and log.md

    from integration.simulator import InstallSimulator

    second = InstallSimulator(
        wiki_root=tmp_wiki,
        checkpoint_path=simulator.checkpoint_path,
        skeleton_root=simulator.skeleton_root,
        distribution=type(simulator.distribution)(),
        lifecycle=type(simulator.lifecycle)(),
    )
    second.run()
    second_applied = second.state["stage_artifacts"]["5"]["additive_changes_applied"]
    assert second_applied == [], (
        f"Stage 5 wrote files on re-install: {second_applied} — should be []"
    )


def test_stage_5_creates_dirs_if_missing_but_idempotent(
    simulator, tmp_wiki: Path,
) -> None:
    """Subdirectories exist after first run; subsequent runs must not re-write
    .gitkeep or fail."""
    simulator.run()
    for sub in ("research", "decisions", "alternatives", "patterns", "projects"):
        assert (tmp_wiki / sub).is_dir()

    from integration.simulator import InstallSimulator

    second = InstallSimulator(
        wiki_root=tmp_wiki,
        checkpoint_path=simulator.checkpoint_path,
        skeleton_root=simulator.skeleton_root,
        distribution=type(simulator.distribution)(),
        lifecycle=type(simulator.lifecycle)(),
    )
    second.run()
    assert second.aborted_at is None
