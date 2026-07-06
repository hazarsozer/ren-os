"""
Tests for skills.routine-init.lib — routine-spec v3 schema validation +
allowlist enforcement (Task 6.3).

Run with: uv run pytest tests/skills/routine_init/test_routine_spec.py -v
"""

from __future__ import annotations

import importlib

routine_init_lib = importlib.import_module("skills.routine-init.lib")
validate_routine_spec = routine_init_lib.validate_routine_spec
check_proposal_against_allowlist = routine_init_lib.check_proposal_against_allowlist


def _valid_spec(**overrides):
    spec = {
        "schema_version": 3,
        "allowlist": {"paths": ["projects/myproj/**"], "capabilities": ["recall", "queue-propose"]},
        "failure_handler": "notify-journal",
        "exit_criterion": "Stop after 30 days or when the project is archived.",
    }
    spec.update(overrides)
    return spec


# ------------------------------------------------------------ validate_routine_spec


def test_v3_spec_validates():
    result = validate_routine_spec(_valid_spec())
    assert result.valid is True
    assert result.errors == []


def test_missing_allowlist_fails():
    spec = _valid_spec()
    del spec["allowlist"]
    result = validate_routine_spec(spec)
    assert result.valid is False
    assert any("allowlist" in e for e in result.errors)


def test_allowlist_not_a_mapping_fails():
    result = validate_routine_spec(_valid_spec(allowlist=["not", "a", "mapping"]))
    assert result.valid is False


def test_empty_allowlist_paths_fails_for_new_spec():
    result = validate_routine_spec(_valid_spec(allowlist={"paths": [], "capabilities": []}))
    assert result.valid is False
    assert any("non-empty" in e for e in result.errors)


def test_empty_allowlist_paths_is_warning_for_migrated_spec():
    result = validate_routine_spec(
        _valid_spec(allowlist={"paths": [], "capabilities": []}), migrated=True
    )
    assert result.valid is True
    assert any("empty" in w for w in result.warnings)


def test_global_star_star_in_paths_fails():
    result = validate_routine_spec(_valid_spec(allowlist={"paths": ["global/**"], "capabilities": []}))
    assert result.valid is False
    assert any("global" in e for e in result.errors)


def test_global_prefix_in_paths_fails():
    result = validate_routine_spec(
        _valid_spec(allowlist={"paths": ["global/policy.md"], "capabilities": []})
    )
    assert result.valid is False


def test_bare_global_in_paths_fails():
    result = validate_routine_spec(_valid_spec(allowlist={"paths": ["global"], "capabilities": []}))
    assert result.valid is False


def test_missing_capabilities_list_fails():
    spec = _valid_spec()
    del spec["allowlist"]["capabilities"]
    result = validate_routine_spec(spec)
    assert result.valid is False
    assert any("capabilities" in e for e in result.errors)


def test_empty_exit_criterion_fails():
    result = validate_routine_spec(_valid_spec(exit_criterion=""))
    assert result.valid is False
    assert any("exit_criterion" in e for e in result.errors)


def test_missing_exit_criterion_fails():
    spec = _valid_spec()
    del spec["exit_criterion"]
    result = validate_routine_spec(spec)
    assert result.valid is False


def test_whitespace_only_exit_criterion_fails():
    result = validate_routine_spec(_valid_spec(exit_criterion="   "))
    assert result.valid is False


def test_invalid_failure_handler_fails():
    result = validate_routine_spec(_valid_spec(failure_handler="email me@example.com"))
    assert result.valid is False
    assert any("failure_handler" in e for e in result.errors)


def test_wrong_schema_version_fails():
    result = validate_routine_spec(_valid_spec(schema_version=2))
    assert result.valid is False
    assert any("schema_version" in e for e in result.errors)


# ------------------------------------------------- check_proposal_against_allowlist


class _FakeProposal:
    def __init__(self, page):
        self.page = page


def test_check_allowlist_matches():
    spec = _valid_spec(allowlist={"paths": ["projects/myproj/**"], "capabilities": []})
    assert check_proposal_against_allowlist(spec, _FakeProposal("projects/myproj/map.md")) is True


def test_check_allowlist_non_match():
    spec = _valid_spec(allowlist={"paths": ["projects/myproj/**"], "capabilities": []})
    assert check_proposal_against_allowlist(spec, _FakeProposal("projects/other/map.md")) is False


def test_check_allowlist_denies_global_even_if_pattern_would_match():
    # A permissive pattern that WOULD fnmatch a global/ page must still be denied.
    spec = _valid_spec(allowlist={"paths": ["**"], "capabilities": []})
    assert check_proposal_against_allowlist(spec, _FakeProposal("global/policy.md")) is False


def test_check_allowlist_accepts_plain_dict_proposal():
    spec = _valid_spec(allowlist={"paths": ["projects/x/**"], "capabilities": []})
    assert check_proposal_against_allowlist(spec, {"page": "projects/x/notes.md"}) is True


def test_check_allowlist_no_page_returns_false():
    spec = _valid_spec()
    assert check_proposal_against_allowlist(spec, _FakeProposal(None)) is False


def test_check_allowlist_empty_paths_matches_nothing():
    spec = _valid_spec(allowlist={"paths": [], "capabilities": []})
    assert check_proposal_against_allowlist(spec, _FakeProposal("projects/x/anything.md")) is False
