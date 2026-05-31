"""
Tests for skills.sf_wrap.lib.classifier.

Pure-logic coverage:
  - build_classifier_prompt: project label injection, transcript truncation,
    type validation
  - parse_classifier_output: schema validation, label whitelisting,
    candidate_artifacts shape, JSON recovery from fenced/prefixed LLM output
  - classify(): the default deterministic heuristic (EXPERIMENTAL) — biases to
    `none`, never raises, pins dominate, artifacts only for decision/pattern

Per dotfiles python/testing.md (pytest). Run with:
    python3 -m pytest skills/wrap/lib/tests/test_classifier.py -v
"""

from __future__ import annotations

import json

import pytest

from ..classifier import (
    MAX_TRANSCRIPT_CHARS,
    VALID_LABELS,
    build_classifier_prompt,
    classify,
    parse_classifier_output,
)
from ..types import ClassifierResult


# ---------------------------------------------------------------------------
# VALID_LABELS sanity
# ---------------------------------------------------------------------------


class TestValidLabels:
    def test_seven_labels(self):
        assert VALID_LABELS == frozenset(
            {
                "none",
                "decision",
                "pattern",
                "lesson",
                "stack_change",
                "milestone",
                "purpose_shift",
            }
        )

    def test_label_count_pins_seven(self):
        """If we add or remove a label, this test should fail to force a
        deliberate doc + classifier-prompt update."""
        assert len(VALID_LABELS) == 7


# ---------------------------------------------------------------------------
# build_classifier_prompt
# ---------------------------------------------------------------------------


class TestBuildClassifierPrompt:
    def test_minimal_prompt_includes_required_sections(self):
        prompt = build_classifier_prompt("user did stuff", project_name="sidecar")
        # The seven label names appear in the prompt's documentation block
        for label in VALID_LABELS:
            assert label in prompt, f"label {label!r} missing from prompt"
        # The transcript is appended verbatim
        assert "user did stuff" in prompt
        # The project is named
        assert "sidecar" in prompt
        # The JSON output schema fields are documented
        assert "labels" in prompt
        assert "reasoning" in prompt
        assert "candidate_artifacts" in prompt

    def test_unscoped_project_renders_unscoped(self):
        prompt = build_classifier_prompt("...", project_name=None)
        assert "unscoped" in prompt

    def test_explicit_project_preserved_verbatim(self):
        prompt = build_classifier_prompt("...", project_name="restore")
        assert "Active project: restore" in prompt

    def test_truncates_oversized_transcript(self):
        # Build a transcript larger than the cap
        oversized = "A" * (MAX_TRANSCRIPT_CHARS + 5000)
        prompt = build_classifier_prompt(oversized, project_name="x")
        # The truncation marker appears
        assert "earlier turns truncated" in prompt
        # Only the tail of the original survived
        assert prompt.count("A") <= MAX_TRANSCRIPT_CHARS + 10  # some slop for the marker

    def test_under_cap_transcript_passes_through(self):
        small = "small transcript"
        prompt = build_classifier_prompt(small, project_name="x")
        assert "earlier turns truncated" not in prompt
        assert small in prompt

    def test_non_string_transcript_raises(self):
        with pytest.raises(TypeError, match="str"):
            build_classifier_prompt(12345, project_name=None)  # type: ignore[arg-type]

    def test_bias_toward_none_explicit_in_prompt(self):
        """Pin: the prompt must instruct bias toward 'none'. If this regresses,
        the signal-threshold discipline collapses."""
        prompt = build_classifier_prompt("...", project_name=None)
        assert "bias toward `none`" in prompt.lower() or "bias toward 'none'" in prompt.lower()

    def test_json_only_instruction_present(self):
        """Pin: the prompt must say "JSON ONLY" so the parser's recovery path
        is rarely exercised."""
        prompt = build_classifier_prompt("...", project_name=None)
        assert "JSON ONLY" in prompt or "JSON only" in prompt.lower()


# ---------------------------------------------------------------------------
# parse_classifier_output — valid cases
# ---------------------------------------------------------------------------


class TestParseValid:
    def test_minimal_none_parses(self):
        raw = json.dumps(
            {
                "labels": ["none"],
                "reasoning": "Routine refactor; no architectural decisions.",
                "candidate_artifacts": [],
            }
        )
        result = parse_classifier_output(raw)
        assert result.labels == ("none",)
        assert "Routine" in result.reasoning
        assert result.candidate_artifacts == ()
        assert not result.has_signal

    def test_single_label_with_artifact(self):
        raw = json.dumps(
            {
                "labels": ["decision"],
                "reasoning": "User locked the choice of Postgres over MongoDB.",
                "candidate_artifacts": [
                    {
                        "label": "decision",
                        "proposed_title": "postgres-over-mongo",
                        "proposed_summary": "Chose Postgres for the user store; <300 chars summary.",
                        "target_file": "wiki/projects/sidecar/decisions/postgres-over-mongo.md",
                    }
                ],
            }
        )
        result = parse_classifier_output(raw)
        assert result.labels == ("decision",)
        assert result.has_signal
        assert len(result.candidate_artifacts) == 1
        assert result.candidate_artifacts[0].proposed_title == "postgres-over-mongo"

    def test_multi_label(self):
        raw = json.dumps(
            {
                "labels": ["decision", "lesson"],
                "reasoning": "Decision made + a related gotcha discovered.",
                "candidate_artifacts": [
                    {
                        "label": "decision",
                        "proposed_title": "x",
                        "proposed_summary": "x",
                        "target_file": "x",
                    }
                ],
            }
        )
        result = parse_classifier_output(raw)
        assert set(result.labels) == {"decision", "lesson"}
        assert result.has_signal

    def test_missing_reasoning_defaults_to_empty(self):
        raw = json.dumps({"labels": ["none"], "candidate_artifacts": []})
        result = parse_classifier_output(raw)
        assert result.reasoning == ""

    def test_missing_artifacts_defaults_to_empty(self):
        raw = json.dumps({"labels": ["none"], "reasoning": ""})
        result = parse_classifier_output(raw)
        assert result.candidate_artifacts == ()


# ---------------------------------------------------------------------------
# parse_classifier_output — invalid cases
# ---------------------------------------------------------------------------


class TestParseInvalid:
    def test_not_a_string(self):
        with pytest.raises(ValueError, match="must be str"):
            parse_classifier_output(123)  # type: ignore[arg-type]

    def test_malformed_json(self):
        with pytest.raises(ValueError, match="not valid JSON"):
            parse_classifier_output("{not valid json}")

    def test_top_level_not_object(self):
        with pytest.raises(ValueError, match="JSON object"):
            parse_classifier_output(json.dumps([1, 2, 3]))

    def test_missing_labels(self):
        raw = json.dumps({"reasoning": "..."})
        with pytest.raises(ValueError, match="'labels' must be a non-empty list"):
            parse_classifier_output(raw)

    def test_empty_labels(self):
        raw = json.dumps({"labels": [], "reasoning": ""})
        with pytest.raises(ValueError, match="non-empty list"):
            parse_classifier_output(raw)

    def test_non_string_label(self):
        raw = json.dumps({"labels": [123], "reasoning": ""})
        with pytest.raises(ValueError, match="items must be strings"):
            parse_classifier_output(raw)

    def test_unknown_label_rejected(self):
        raw = json.dumps({"labels": ["something-fake"], "reasoning": ""})
        with pytest.raises(ValueError, match="unknown label"):
            parse_classifier_output(raw)

    def test_none_with_artifacts_rejected(self):
        """Pin: schema discipline — when labels is exactly ['none'],
        candidate_artifacts MUST be empty. If the LLM produces artifacts
        despite 'none', that's a contradiction and we surface it."""
        raw = json.dumps(
            {
                "labels": ["none"],
                "reasoning": "...",
                "candidate_artifacts": [
                    {
                        "label": "none",
                        "proposed_title": "ghost",
                        "proposed_summary": "shouldn't exist",
                        "target_file": "wiki/x.md",
                    }
                ],
            }
        )
        with pytest.raises(ValueError, match="must be empty when labels is exactly"):
            parse_classifier_output(raw)

    def test_non_string_reasoning(self):
        raw = json.dumps({"labels": ["none"], "reasoning": 42})
        with pytest.raises(ValueError, match="'reasoning' must be a string"):
            parse_classifier_output(raw)

    def test_artifact_unknown_label(self):
        raw = json.dumps(
            {
                "labels": ["decision"],
                "reasoning": "...",
                "candidate_artifacts": [
                    {
                        "label": "fake-label",
                        "proposed_title": "x",
                        "proposed_summary": "x",
                        "target_file": "x",
                    }
                ],
            }
        )
        with pytest.raises(ValueError, match="must be a valid SignalLabel"):
            parse_classifier_output(raw)

    def test_artifact_empty_title(self):
        raw = json.dumps(
            {
                "labels": ["decision"],
                "reasoning": "",
                "candidate_artifacts": [
                    {
                        "label": "decision",
                        "proposed_title": "",
                        "proposed_summary": "x",
                        "target_file": "x",
                    }
                ],
            }
        )
        with pytest.raises(ValueError, match="proposed_title must be a non-empty string"):
            parse_classifier_output(raw)

    def test_artifact_missing_summary(self):
        raw = json.dumps(
            {
                "labels": ["decision"],
                "reasoning": "",
                "candidate_artifacts": [
                    {
                        "label": "decision",
                        "proposed_title": "x",
                        "target_file": "x",
                    }
                ],
            }
        )
        with pytest.raises(ValueError, match="proposed_summary must be a non-empty string"):
            parse_classifier_output(raw)


# ---------------------------------------------------------------------------
# parse_classifier_output — defensive recovery from non-strict LLM output
# ---------------------------------------------------------------------------


class TestParseRecovery:
    def test_recovers_from_json_fence(self):
        """LLM may wrap in ```json ... ``` despite the JSON-only instruction."""
        wrapped = '```json\n{"labels": ["none"], "reasoning": "x"}\n```'
        result = parse_classifier_output(wrapped)
        assert result.labels == ("none",)

    def test_recovers_from_bare_fence(self):
        wrapped = '```\n{"labels": ["none"], "reasoning": "x"}\n```'
        result = parse_classifier_output(wrapped)
        assert result.labels == ("none",)

    def test_recovers_from_preamble(self):
        """LLM may add a preamble like 'Here is the classification:'."""
        wrapped = 'Here is the classification:\n{"labels": ["none"], "reasoning": "x"}'
        result = parse_classifier_output(wrapped)
        assert result.labels == ("none",)

    def test_recovers_from_trailing_prose(self):
        wrapped = '{"labels": ["none"], "reasoning": "x"}\n\nHope that helps!'
        result = parse_classifier_output(wrapped)
        assert result.labels == ("none",)

    def test_strips_outer_whitespace(self):
        wrapped = '   \n\n{"labels": ["none"], "reasoning": "x"}\n   '
        result = parse_classifier_output(wrapped)
        assert result.labels == ("none",)


# ---------------------------------------------------------------------------
# classify() — default deterministic heuristic (EXPERIMENTAL)
# ---------------------------------------------------------------------------


class TestClassifyDeterministic:
    """The default production classify() — conservative deterministic heuristic.
    Never raises; biases hard to `none`; pins dominate; artifacts only for the
    page-creating labels (decision/pattern)."""

    def test_routine_session_is_none_no_artifacts(self):
        transcript = (
            "Fixed a typo in the login button. Ran the tests, they pass. "
            "Refactored a helper and added a unit test. Checked the logs."
        )
        result = classify(transcript, project_name="sidecar")
        assert result.labels == ("none",)
        assert result.candidate_artifacts == ()
        assert not result.has_signal

    def test_decision_phrase_fires_decision_with_one_artifact(self):
        transcript = (
            "After comparing options, we decided to use Postgres over Mongo "
            "for the session store."
        )
        result = classify(transcript, project_name="sidecar")
        assert "decision" in result.labels
        assert result.has_signal
        arts = [a for a in result.candidate_artifacts if a.label == "decision"]
        assert len(arts) == 1
        a = arts[0]
        assert a.proposed_title and a.proposed_title == a.proposed_title.lower()
        assert " " not in a.proposed_title  # kebab
        assert 0 < len(a.proposed_summary) <= 300
        assert a.target_file.startswith("wiki/projects/sidecar/decisions/")

    def test_gotcha_fires_lesson_with_no_artifact(self):
        transcript = (
            "gotcha: Stripe webhook metadata.email has trailing whitespace — "
            "strip before lookup."
        )
        result = classify(transcript, project_name="sidecar")
        assert "lesson" in result.labels
        # lesson is not a page-creating label → no candidate artifact
        assert result.candidate_artifacts == ()

    def test_routine_decided_phrase_in_log_does_not_fire(self):
        """A casual 'decided to' that isn't a deliberate project choice stays
        `none` (bias-to-none discipline)."""
        result = classify("I decided to grab a coffee; the build is green.", project_name="x")
        assert result.labels == ("none",)

    def test_pin_escalation_fires_when_log_is_routine(self):
        """A routine log + a deliberate /sf:note pin escalates (pins dominate)."""
        transcript = (
            "Spent the session fixing flaky tests and bumping a dependency.\n\n"
            "## Pinned notes from /sf:note\n\n"
            "decision: going with Tailwind for the design system"
        )
        result = classify(transcript, project_name="sidecar")
        assert "decision" in result.labels

    def test_pin_loose_keyword_fires_only_from_pins(self):
        """A bare keyword (lower threshold) fires in a pin but NOT in the raw log."""
        log_only = "I decided to grab a coffee and the build is green."
        assert classify(log_only, project_name=None).labels == ("none",)
        with_pin = log_only + "\n\n## Pinned notes\n\nremember the postgres decision"
        assert "decision" in classify(with_pin, project_name=None).labels

    def test_multi_label_capped_at_two(self):
        transcript = (
            "we decided to use Redis for caching. gotcha: TTLs are in seconds not ms. "
            "Also migrating from Pages Router to App Router. milestone: Phase 1 is done."
        )
        result = classify(transcript, project_name="sidecar")
        assert 1 <= len(result.labels) <= 2
        assert "none" not in result.labels

    def test_none_implies_empty_artifacts(self):
        result = classify("just routine coding today", project_name="x")
        assert result.labels == ("none",)
        assert result.candidate_artifacts == ()

    def test_never_raises_on_empty_or_non_string(self):
        assert classify("", project_name=None).labels == ("none",)
        assert classify("   \n  ", project_name=None).labels == ("none",)
        assert classify(None, project_name=None).labels == ("none",)  # type: ignore[arg-type]

    def test_unscoped_decision_targets_master_wiki(self):
        result = classify(
            "we decided to standardize on uv for all python projects",
            project_name=None,
        )
        arts = [a for a in result.candidate_artifacts if a.label == "decision"]
        assert arts and arts[0].target_file.startswith("wiki/decisions/")

    def test_result_is_valid_classifier_result(self):
        """Whatever fires, the output is a well-formed ClassifierResult."""
        result = classify("we decided to use Redis", project_name="x")
        assert isinstance(result, ClassifierResult)
        assert all(isinstance(l, str) for l in result.labels)
        assert isinstance(result.reasoning, str) and result.reasoning


# ---------------------------------------------------------------------------
# ClassifierResult sanity
# ---------------------------------------------------------------------------


class TestClassifierResult:
    def test_has_signal_true_when_any_non_none(self):
        result = ClassifierResult(labels=("decision",), reasoning="")
        assert result.has_signal

    def test_has_signal_false_when_only_none(self):
        result = ClassifierResult(labels=("none",), reasoning="")
        assert not result.has_signal

    def test_has_signal_true_when_multi_label_includes_non_none(self):
        result = ClassifierResult(labels=("none", "lesson"), reasoning="")
        assert result.has_signal

    def test_immutable(self):
        result = ClassifierResult(labels=("none",), reasoning="")
        with pytest.raises(Exception):
            result.reasoning = "modified"  # type: ignore[misc]
