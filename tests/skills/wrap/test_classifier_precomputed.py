import pytest

from skills.wrap.lib.classifier import (
    ClassifierError,
    PlacementError,
    decision_from_data,
    gate_precomputed,
)


def test_valid_durable_create():
    d = decision_from_data(
        {"verdict": "durable", "reason": "r", "scope": "project",
         "action": "create", "target_page": None}
    )
    assert d.verdict == "durable" and d.scope == "project" and d.action == "create"


def test_valid_update_in_eligibility():
    d = decision_from_data(
        {"verdict": "durable", "reason": "r", "scope": "project",
         "action": "update", "target_page": "projects/x/map.md"},
        eligible_targets=("projects/x/map.md",),
    )
    assert d.action == "update" and d.target_page == "projects/x/map.md"


def test_scope_none_durable_raises_placement_error():
    # The 2026-08-14 live bug: durable verdict, scope None → must be
    # PlacementError (routable to suggestions), NOT a silent gate-out.
    with pytest.raises(PlacementError) as ei:
        decision_from_data(
            {"verdict": "durable", "reason": "r", "scope": None,
             "action": "create", "target_page": None}
        )
    assert ei.value.claimed_scope is None
    assert ei.value.reason  # human-readable why


def test_update_target_outside_eligibility_raises_placement_error():
    with pytest.raises(PlacementError):
        decision_from_data(
            {"verdict": "durable", "reason": "r", "scope": "project",
             "action": "update", "target_page": "projects/other/map.md"},
            eligible_targets=("projects/x/map.md",),
        )


def test_non_durable_bad_scope_is_plain_classifier_error():
    # Placement only matters for durable verdicts; garbage on a discard
    # verdict is ordinary malformation.
    with pytest.raises(ClassifierError) as ei:
        decision_from_data({"verdict": "discard", "reason": 3})
    assert not isinstance(ei.value, PlacementError)


def test_unknown_verdict_is_plain_classifier_error():
    with pytest.raises(ClassifierError) as ei:
        decision_from_data({"verdict": "maybe", "reason": "r"})
    assert not isinstance(ei.value, PlacementError)


def test_gate_precomputed_valid_passes_through():
    d = gate_precomputed(
        "an item",
        {"verdict": "session-only", "reason": "r", "scope": "global",
         "action": "create", "target_page": None},
    )
    assert d.verdict == "session-only"


def test_gate_precomputed_placement_error_propagates():
    with pytest.raises(PlacementError):
        gate_precomputed(
            "an item",
            {"verdict": "durable", "reason": "r", "scope": None,
             "action": "create", "target_page": None},
        )


def test_gate_precomputed_garbage_falls_back_deterministic(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_WIKI_ROOT", str(tmp_path))
    d = gate_precomputed("an item", "not even a dict")
    assert d.verdict in {"session-only", "discard"}  # never durable
