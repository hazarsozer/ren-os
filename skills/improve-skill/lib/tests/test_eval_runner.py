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
    REPO_ROOT / "skills" / "improve-skill",
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
    def test_raises_eval_backend_not_configured(self, monkeypatch):
        import shutil
        monkeypatch.setattr(shutil, "which", lambda _: None)
        with pytest.raises(EvalBackendNotConfiguredError, match="configured eval backend"):
            run_evals("sf-wrap")

    def test_error_is_runtimeerror_subclass(self):
        """The typed error subclasses RuntimeError so broad 'eval failed' guards
        still treat it as a runtime failure."""
        assert issubclass(EvalBackendNotConfiguredError, RuntimeError)

    def test_message_flags_experimental(self, monkeypatch):
        import shutil
        monkeypatch.setattr(shutil, "which", lambda _: None)
        with pytest.raises(EvalBackendNotConfiguredError) as exc:
            run_evals("sf-wrap")
        assert "EXPERIMENTAL" in str(exc.value)

    def test_message_references_design_doc(self, monkeypatch):
        import shutil
        monkeypatch.setattr(shutil, "which", lambda _: None)
        with pytest.raises(EvalBackendNotConfiguredError) as exc:
            run_evals("sf-wrap")
        assert "references/eval-runner.md" in str(exc.value)


# ---------------------------------------------------------------------------
# run_evals — real backend (own LLM-judge, injected runner)
# ---------------------------------------------------------------------------

from ..claude_cli import ClaudeRun
from ..types import ApiUsage


class _FakeRunner:
    """Mimics claude_cli.run_print. Maps a prompt-substring -> ClaudeRun."""
    def __init__(self, skill_text="DONE", activated=("wrap",), judge_true=True,
                 is_error=False):
        self.skill_text = skill_text
        self.activated = activated
        self.judge_true = judge_true
        self.is_error = is_error
        self.calls = []

    def __call__(self, prompt, *, bare, model=None, detect_activation=False,
                 max_budget_usd=None, timeout_seconds=300, cwd=None, env=None):
        self.calls.append({"prompt": prompt, "bare": bare, "detect_activation": detect_activation})
        if detect_activation:  # a skill-run
            return ClaudeRun(self.skill_text, ApiUsage(20, 5), activated=self.activated,
                             is_error=self.is_error)
        # a judge call: answer TRUE/FALSE
        return ClaudeRun("TRUE" if self.judge_true else "FALSE", ApiUsage(8, 1))


def _write_eval(tmp_path, name, tests, non_triggers=None):
    d = tmp_path / "skills" / name / "eval"
    d.mkdir(parents=True)
    import json as _j
    (d / "eval.json").write_text(_j.dumps({"name": name, "tests": tests, "non_triggers": non_triggers or []}))
    return tmp_path / "skills"


class TestRunEvalsBackend:
    def test_all_pass_when_judge_true_and_activated(self, tmp_path):
        skills_root = _write_eval(tmp_path, "wrap",
            [{"id": "t1", "prompt": "p", "binary_assertions": ["a", "b"], "trigger_test": True}])
        fake = _FakeRunner(activated=("wrap",), judge_true=True)
        res = run_evals("wrap", skills_root=skills_root, _runner=fake)
        assert res.total == 3          # 2 assertions + 1 trigger-activation
        assert res.passed == 3
        assert res.score == 1.0
        assert res.usage.output_tokens > 0   # usage aggregated

    def test_failing_assertion_recorded(self, tmp_path):
        skills_root = _write_eval(tmp_path, "wrap",
            [{"id": "t1", "prompt": "p", "binary_assertions": ["a"]}])
        fake = _FakeRunner(judge_true=False)
        res = run_evals("wrap", skills_root=skills_root, _runner=fake)
        assert res.score == 0.0
        assert res.failing_assertion_ids == ("t1:0",)

    def test_non_trigger_fails_when_skill_activates(self, tmp_path):
        skills_root = _write_eval(tmp_path, "wrap",
            [{"id": "t1", "prompt": "p", "binary_assertions": ["a"]}],
            non_triggers=[{"id": "nt1", "prompt": "off-topic"}])
        fake = _FakeRunner(activated=("wrap",), judge_true=True)  # wrongly activates on the non-trigger too
        res = run_evals("wrap", skills_root=skills_root, _runner=fake)
        # 1 assertion (pass) + 1 non-trigger (fail: it activated) = 1/2
        assert res.total == 2 and res.passed == 1

    def test_timeout_scores_zero(self, tmp_path):
        skills_root = _write_eval(tmp_path, "wrap",
            [{"id": "t1", "prompt": "p", "binary_assertions": ["a"]}])
        def timed_out_runner(prompt, *, detect_activation=False, **k):
            return ClaudeRun("", ApiUsage(0, 0), timed_out=True)
        res = run_evals("wrap", skills_root=skills_root, _runner=timed_out_runner)
        assert res.score == 0.0

    def test_is_error_scores_zero(self, tmp_path):
        """is_error=True on a skill-run (e.g. auth/API error) is treated like a timeout."""
        skills_root = _write_eval(tmp_path, "wrap",
            [{"id": "t1", "prompt": "p", "binary_assertions": ["a"]}])
        fake = _FakeRunner(is_error=True)
        res = run_evals("wrap", skills_root=skills_root, _runner=fake)
        assert res.score == 0.0

    def test_backend_absent_raises(self, tmp_path, monkeypatch):
        skills_root = _write_eval(tmp_path, "wrap",
            [{"id": "t1", "prompt": "p", "binary_assertions": ["a"]}])
        import shutil
        monkeypatch.setattr(shutil, "which", lambda _: None)  # no claude on PATH
        with pytest.raises(EvalBackendNotConfiguredError):
            run_evals("wrap", skills_root=skills_root)  # default runner, no binary

    def test_non_trigger_error_does_not_inflate_passed(self, tmp_path):
        """A non-trigger run that returns is_error=True must not count as passed."""
        skills_root = _write_eval(
            tmp_path, "wrap",
            [{"id": "t1", "prompt": "p", "binary_assertions": ["a"]}],
            non_triggers=[{"id": "nt1", "prompt": "off-topic"}],
        )
        # judge_true=True passes the assertion; skill does NOT activate on the
        # regular test (activated=() so trigger logic stays neutral here).
        # For the non-trigger run, is_error=True simulates a failed invocation.
        call_index = [0]

        def mixed_runner(prompt, *, detect_activation=False, **kwargs):
            call_index[0] += 1
            if detect_activation:
                # First skill-run (regular test): success, not activated
                # Second skill-run (non-trigger): is_error=True
                if call_index[0] == 1:
                    return ClaudeRun("DONE", ApiUsage(20, 5), activated=())
                return ClaudeRun("", ApiUsage(0, 0), is_error=True)
            # judge call: assertion passes
            return ClaudeRun("TRUE", ApiUsage(8, 1))

        res = run_evals("wrap", skills_root=skills_root, _runner=mixed_runner)
        # total = 1 assertion + 1 non-trigger = 2
        # passed = 1 (assertion) + 0 (non-trigger errored, not credited) = 1
        assert res.total == 2
        assert res.passed == 1
        assert res.score == 0.5

    def test_run_evals_runs_skill_from_plugin_root_cwd(self, tmp_path):
        # A non-trigger is included so BOTH skill-run call sites in run_evals run:
        # the _run_skill helper (for the regular test) and the non-trigger loop.
        skills_root = _write_eval(tmp_path, "wrap",
            [{"id": "t1", "prompt": "p", "binary_assertions": ["a"]}],
            non_triggers=[{"id": "nt1", "prompt": "off-topic"}])
        skill_run_cwds = []

        def recording_runner(prompt, *, bare, model=None, detect_activation=False,
                             max_budget_usd=None, timeout_seconds=300, cwd=None, env=None):
            if detect_activation:                       # a skill-run
                skill_run_cwds.append(cwd)
                return ClaudeRun("DONE", ApiUsage(20, 5), activated=("wrap",))
            return ClaudeRun("TRUE", ApiUsage(8, 1))    # a judge call

        run_evals("wrap", skills_root=skills_root, _runner=recording_runner)
        # Both the regular-test run and the non-trigger run happened.
        assert len(skill_run_cwds) == 2
        # plugin-active CWD = the repo/worktree root = parent of skills/.
        # Every skill-run (both call sites) must run from the plugin root.
        for cwd in skill_run_cwds:
            assert Path(cwd).resolve() == tmp_path.resolve()

    def test_non_trigger_timeout_does_not_inflate_passed(self, tmp_path):
        """A non-trigger run that times out must not count as passed."""
        skills_root = _write_eval(
            tmp_path, "wrap",
            [{"id": "t1", "prompt": "p", "binary_assertions": ["a"]}],
            non_triggers=[{"id": "nt1", "prompt": "off-topic"}],
        )
        call_index = [0]

        def mixed_runner(prompt, *, detect_activation=False, **kwargs):
            call_index[0] += 1
            if detect_activation:
                if call_index[0] == 1:
                    return ClaudeRun("DONE", ApiUsage(20, 5), activated=())
                return ClaudeRun("", ApiUsage(0, 0), timed_out=True)
            return ClaudeRun("TRUE", ApiUsage(8, 1))

        res = run_evals("wrap", skills_root=skills_root, _runner=mixed_runner)
        assert res.total == 2
        assert res.passed == 1
        assert res.score == 0.5


class _VaryingRunner:
    """Skill-runs return successive `outputs`; judge returns TRUE iff the judged
    output contains 'GOOD'. Lets a test distinguish 'judge each run' from the old
    'judge runs[0] only'."""
    def __init__(self, outputs, activated=("wrap",)):
        self.outputs = list(outputs)
        self.activated = activated
        self._i = 0

    def __call__(self, prompt, *, bare, model=None, detect_activation=False,
                 max_budget_usd=None, timeout_seconds=300, cwd=None, env=None):
        if detect_activation:                       # a skill-run
            out = self.outputs[self._i]
            self._i += 1
            return ClaudeRun(out, ApiUsage(20, 5), activated=self.activated)
        return ClaudeRun("TRUE" if "GOOD" in prompt else "FALSE", ApiUsage(8, 1))


class TestEvalRunsVariance:
    def test_eval_runs_judges_each_run_not_just_first(self, tmp_path):
        # runs[0]='BAD' DISAGREES with the GOOD majority. Old code (judge runs[0]
        # x3) -> [F,F,F] -> FAIL. New code (judge each run) -> [F,T,T] -> PASS.
        skills_root = _write_eval(tmp_path, "wrap",
            [{"id": "t1", "prompt": "p", "binary_assertions": ["output is acceptable"]}])
        fake = _VaryingRunner(outputs=["BAD", "GOOD", "GOOD"])
        res = run_evals("wrap", skills_root=skills_root, _runner=fake, eval_runs=3)
        assert res.total == 1 and res.passed == 1 and res.score == 1.0

    def test_eval_runs_majority_fail_when_runs_disagree(self, tmp_path):
        # runs[0]='GOOD' but majority is BAD. Old -> [T,T,T] PASS; new -> [T,F,F] FAIL.
        skills_root = _write_eval(tmp_path, "wrap",
            [{"id": "t1", "prompt": "p", "binary_assertions": ["output is acceptable"]}])
        fake = _VaryingRunner(outputs=["GOOD", "BAD", "BAD"])
        res = run_evals("wrap", skills_root=skills_root, _runner=fake, eval_runs=3)
        assert res.passed == 0 and res.failing_assertion_ids == ("t1:0",)
