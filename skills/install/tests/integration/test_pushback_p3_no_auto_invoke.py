"""P3 pin: Stage 7 acknowledgment does NOT trigger any other slash command.

Team-lead: "Default to Option 2 (manual /ren:install). The plugin's install hook
does NOT auto-invoke /ren:install at PostInstall time — friend types the three
explicit commands per ADR-019. Stage 7 walkthrough prints the tour but does not
execute any of the listed slash commands."
"""

from __future__ import annotations


def test_stage_7_does_not_auto_invoke_any_slash_command(simulator) -> None:
    simulator.run()
    assert simulator.auto_invoked_commands == [], (
        f"Stage 7 auto-invoked: {simulator.auto_invoked_commands} — should be []"
    )


def test_stage_7_walkthrough_acknowledged_state(simulator) -> None:
    simulator.run()
    # Stage 7 records the acknowledgment — but its only side effect is checkpoint
    # state, not a slash-command call.
    assert simulator.state["stage_artifacts"]["7"]["walkthrough_acknowledged"] is True


def test_full_install_calls_no_slash_command_outside_stages(simulator) -> None:
    """End-to-end: at no point does the simulator invoke a slash command
    on the friend's behalf."""
    simulator.run()
    assert simulator.auto_invoked_commands == []
