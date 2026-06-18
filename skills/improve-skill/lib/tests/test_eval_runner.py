"""
Tests for skills.sf_improve_skill.lib.eval_runner.

Covers the pure-logic helpers:
  - load_eval_spec (with real shipped eval.json files as fixtures)
  - filter_tests_by_ids (subset semantics)
  - compute_total_assertions (counts including trigger + non-trigger contributions)
  - make/parse_failing_assertion_id (round-trip)
  - empty_eval_result (degenerate state)
  - run_evals (default path raises the typed EvalBackendNotConfiguredError)

Per the load-bearing pattern from learnings.md (#1 in the test-against-real-
instances tradition): includes the same parametrized canonical fixtures as
test_preflight.py, asserting the loader cleanly consumes every framework-
shipped eval.json.

Run with:
    python3 -m pytest skills/improve-skill/lib/tests/test_eval_runner.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ..eval_runner import (
    EvalBackendNotConfiguredError,
    EvalSpec,
    EvalTest,
    NonTrigger,
    compute_total_assertions,
    empty_eval_result,
    filter_tests_by_ids,
    load_eval_spec,
    make_failing_assertion_id,
    parse_failing_assertion_id,
    run_evals,
)
from ..types import EvalResult


REPO_ROOT = Path(__file__).resolve().parents[4]

CANONICAL_SKILL_DIRS = [
    REPO_ROOT / "skills" / "install",
    REPO_ROOT / "skills" / "interview",
    REPO_ROOT / "skills" / "bootstrap-project",
    REPO_ROOT / "skills" / "wrap",
]


# ---------------------------------------------------------------------------
# load_eval_spec — pure parsing
# ---------------------------------------------------------------------------


class TestLoadEvalSpec:
    def test_minimal_eval_loads(self, tmp_path: Path):
        skill_dir = tmp_path / "skills" / "minimal"
        eval_dir = skill_dir / "eval"
        eval_dir.mkdir(parents=True)
        (eval_dir / "eval.json").write_text(
            json.dumps(
                {
                    "name": "minimal",
                    "tests": [
                        {
                            "id": "t1",
                            "prompt": "do the thing",
                            "binary_assertions": ["output is non-empty"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        spec = load_eval_spec(skill_dir)
        assert spec.name == "minimal"
        assert len(spec.tests) == 1
        assert spec.tests[0].id == "t1"
        assert spec.tests[0].prompt == "do the thing"
        assert spec.tests[0].binary_assertions == ("output is non-empty",)
        assert spec.tests[0].trigger_test is False
        assert spec.non_triggers == ()

    def test_name_falls_back_to_dirname(self, tmp_path: Path):
        skill_dir = tmp_path / "skills" / "no-name-field"
        eval_dir = skill_dir / "eval"
        eval_dir.mkdir(parents=True)
        (eval_dir / "eval.json").write_text(
            json.dumps(
                {
                    "tests": [{"id": "t1", "binary_assertions": ["x"]}]
                }
            ),
            encoding="utf-8",
        )
        spec = load_eval_spec(skill_dir)
        assert spec.name == "no-name-field"

    def test_loads_non_triggers(self, tmp_path: Path):
        skill_dir = tmp_path / "skills" / "with-nt"
        eval_dir = skill_dir / "eval"
        eval_dir.mkdir(parents=True)
        (eval_dir / "eval.json").write_text(
            json.dumps(
                {
                    "name": "s",
                    "tests": [{"id": "t1", "binary_assertions": ["x"]}],
                    "non_triggers": [
                        {
                            "id": "nt-1",
                            "prompt": "irrelevant",
                            "expected_outcome": "skill_not_activated",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        spec = load_eval_spec(skill_dir)
        assert len(spec.non_triggers) == 1
        assert spec.non_triggers[0].id == "nt-1"
        assert spec.non_triggers[0].expected_outcome == "skill_not_activated"

    def test_extra_fields_ignored(self, tmp_path: Path):
        skill_dir = tmp_path / "skills" / "with-extras"
        eval_dir = skill_dir / "eval"
        eval_dir.mkdir(parents=True)
        (eval_dir / "eval.json").write_text(
            json.dumps(
                {
                    "name": "s",
                    "description": "extra; ignored",
                    "_status": "scaffold",
                    "$schema": "...",
                    "tests": [
                        {
                            "id": "t1",
                            "binary_assertions": ["x"],
                            "fixture": "ignored-fixture-path",
                            "expected_output_summary": "kept",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        spec = load_eval_spec(skill_dir)
        assert spec.name == "s"
        assert spec.tests[0].expected_output_summary == "kept"
        # No exception from $schema / _status / description

    def test_malformed_tests_field_raises(self, tmp_path: Path):
        skill_dir = tmp_path / "skills" / "bad-tests"
        eval_dir = skill_dir / "eval"
        eval_dir.mkdir(parents=True)
        (eval_dir / "eval.json").write_text(
            json.dumps({"name": "s", "tests": "not-a-list"}),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="must be a list"):
            load_eval_spec(skill_dir)

    def test_test_not_dict_raises(self, tmp_path: Path):
        skill_dir = tmp_path / "skills" / "bad-test-item"
        eval_dir = skill_dir / "eval"
        eval_dir.mkdir(parents=True)
        (eval_dir / "eval.json").write_text(
            json.dumps({"name": "s", "tests": ["not-a-dict"]}),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="each test must be a dict"):
            load_eval_spec(skill_dir)


# ---------------------------------------------------------------------------
# Canonical fixture conformance — same pattern as test_preflight.py
# ---------------------------------------------------------------------------


class TestLoadCanonicalFixtures:
    """Every framework-shipped eval.json must load cleanly into EvalSpec."""

    @pytest.mark.parametrize(
        "skill_dir",
        CANONICAL_SKILL_DIRS,
        ids=lambda p: p.name,
    )
    def test_canonical_fixture_loads(self, skill_dir: Path):
        if not (skill_dir / "eval" / "eval.json").is_file():
            pytest.skip(f"fixture missing: {skill_dir}/eval/eval.json")

        spec = load_eval_spec(skill_dir)
        # Sanity: every shipped eval has at least one test
        assert len(spec.tests) > 0, f"{skill_dir.name} has no tests"
        # Sanity: every test has at least one binary_assertion
        for test in spec.tests:
            assert len(test.binary_assertions) > 0, (
                f"{skill_dir.name} test {test.id!r} has zero binary_assertions"
            )
            for a in test.binary_assertions:
                assert isinstance(a, str), (
                    f"{skill_dir.name} test {test.id!r} has non-string assertion: {a!r}"
                )

    def test_compute_total_assertions_against_shipped(self):
        """Sanity: every shipped eval reports a positive total."""
        for skill_dir in CANONICAL_SKILL_DIRS:
            if not (skill_dir / "eval" / "eval.json").is_file():
                continue
            spec = load_eval_spec(skill_dir)
            total = compute_total_assertions(spec)
            assert total > 0, f"{skill_dir.name} has zero total assertions"


# ---------------------------------------------------------------------------
# filter_tests_by_ids
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_spec() -> EvalSpec:
    return EvalSpec(
        name="sample",
        tests=(
            EvalTest(id="t1", prompt="", binary_assertions=("a",)),
            EvalTest(id="t2", prompt="", binary_assertions=("b", "c")),
            EvalTest(id="t3", prompt="", binary_assertions=("d",)),
        ),
        non_triggers=(NonTrigger(id="nt-1", prompt=""),),
    )


class TestFilterTestsByIds:
    def test_none_returns_unchanged(self, sample_spec: EvalSpec):
        result = filter_tests_by_ids(sample_spec, None)
        assert result is sample_spec  # same instance (no filtering performed)

    def test_subset_filters_correctly(self, sample_spec: EvalSpec):
        result = filter_tests_by_ids(sample_spec, ["t1", "t3"])
        assert [t.id for t in result.tests] == ["t1", "t3"]

    def test_non_triggers_preserved(self, sample_spec: EvalSpec):
        result = filter_tests_by_ids(sample_spec, ["t1"])
        assert result.non_triggers == sample_spec.non_triggers

    def test_unmatched_subset_raises(self, sample_spec: EvalSpec):
        with pytest.raises(ValueError, match="matched zero tests"):
            filter_tests_by_ids(sample_spec, ["nonexistent"])

    def test_partial_match_keeps_only_known(self, sample_spec: EvalSpec):
        result = filter_tests_by_ids(sample_spec, ["t1", "nonexistent"])
        # t1 matches, nonexistent silently skipped (we don't error on superset)
        assert [t.id for t in result.tests] == ["t1"]


# ---------------------------------------------------------------------------
# compute_total_assertions
# ---------------------------------------------------------------------------


class TestComputeTotalAssertions:
    def test_simple_count(self, sample_spec: EvalSpec):
        # t1=1 + t2=2 + t3=1 + 1 non_trigger = 5
        assert compute_total_assertions(sample_spec) == 5

    def test_trigger_test_adds_one(self):
        spec = EvalSpec(
            name="s",
            tests=(
                EvalTest(id="t1", prompt="", binary_assertions=("a",), trigger_test=True),
            ),
        )
        # 1 assertion + 1 trigger-activation check = 2
        assert compute_total_assertions(spec) == 2

    def test_non_trigger_adds_one(self):
        spec = EvalSpec(
            name="s",
            tests=(EvalTest(id="t1", prompt="", binary_assertions=("a",)),),
            non_triggers=(NonTrigger(id="nt1", prompt=""), NonTrigger(id="nt2", prompt="")),
        )
        # 1 assertion + 2 non_trigger activation-checks = 3
        assert compute_total_assertions(spec) == 3

    def test_empty_spec_zero(self):
        spec = EvalSpec(name="s", tests=())
        assert compute_total_assertions(spec) == 0


# ---------------------------------------------------------------------------
# make / parse_failing_assertion_id
# ---------------------------------------------------------------------------


class TestFailingAssertionIdRoundTrip:
    @pytest.mark.parametrize(
        ("test_id", "index"),
        [
            ("simple-test", 0),
            ("simple-test", 1),
            ("simple-test", 42),
            ("test-with-dashes", 3),
            ("test_with_underscores", 7),
            ("test.with.dots", 0),
        ],
    )
    def test_round_trip(self, test_id: str, index: int):
        packed = make_failing_assertion_id(test_id, index)
        back_id, back_index = parse_failing_assertion_id(packed)
        assert back_id == test_id
        assert back_index == index

    def test_make_empty_id_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            make_failing_assertion_id("", 0)

    def test_make_negative_index_raises(self):
        with pytest.raises(ValueError, match=">= 0"):
            make_failing_assertion_id("t1", -1)

    def test_parse_no_colon_raises(self):
        with pytest.raises(ValueError, match="no colon"):
            parse_failing_assertion_id("just-text")

    def test_parse_empty_test_id_raises(self):
        with pytest.raises(ValueError, match="Empty test_id"):
            parse_failing_assertion_id(":3")

    def test_parse_non_integer_index_raises(self):
        with pytest.raises(ValueError, match="must be an integer"):
            parse_failing_assertion_id("t1:not-a-number")

    def test_parse_negative_index_raises(self):
        with pytest.raises(ValueError, match="must be >= 0"):
            parse_failing_assertion_id("t1:-5")

    def test_parse_handles_colon_in_test_id(self):
        """Robust: if a test_id contains a colon, the LAST colon is the separator."""
        # e.g. a test_id "namespace:t1" with index 3 packs as "namespace:t1:3"
        back_id, back_index = parse_failing_assertion_id("namespace:t1:3")
        assert back_id == "namespace:t1"
        assert back_index == 3


# ---------------------------------------------------------------------------
# empty_eval_result
# ---------------------------------------------------------------------------


class TestEmptyEvalResult:
    def test_default(self):
        result = empty_eval_result()
        assert isinstance(result, EvalResult)
        assert result.score == 0.0
        assert result.passed == 0
        assert result.total == 0
        assert result.failing_assertion_ids == ()
        assert result.raw_output == ""
        assert not result.all_pass

    def test_with_reason(self):
        result = empty_eval_result("subset filtered to zero tests")
        assert "subset" in result.raw_output

    def test_eval_result_has_default_usage(self):
        from ..types import ApiUsage
        r = empty_eval_result()
        assert r.usage == ApiUsage(0, 0)


# ---------------------------------------------------------------------------
# run_evals — honest fail-fast (EXPERIMENTAL: requires a configured backend)
# ---------------------------------------------------------------------------


class TestRunEvalsRequiresBackend:
    def test_raises_eval_backend_not_configured(self):
        with pytest.raises(EvalBackendNotConfiguredError, match="configured eval backend"):
            run_evals("sf-wrap")

    def test_error_is_runtimeerror_subclass(self):
        """The typed error subclasses RuntimeError so broad 'eval failed' guards
        still treat it as a runtime failure."""
        assert issubclass(EvalBackendNotConfiguredError, RuntimeError)

    def test_message_flags_experimental(self):
        try:
            run_evals("sf-wrap")
        except EvalBackendNotConfiguredError as exc:
            assert "EXPERIMENTAL" in str(exc)

    def test_message_references_design_doc(self):
        try:
            run_evals("sf-wrap")
        except EvalBackendNotConfiguredError as exc:
            assert "references/eval-runner.md" in str(exc)
