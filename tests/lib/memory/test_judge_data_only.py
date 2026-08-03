"""
Tests for lib.memory.judge data-only verdict primitives (quarantine screen,
spec docs/superpowers/specs/2026-08-03-quarantine-screen-design.md).
Pure functions — no wiki, no env fixtures needed.

Run with: uv run pytest tests/lib/memory/test_judge_data_only.py -v
"""

from __future__ import annotations

import pytest

from lib.memory import judge
from lib.memory.quarantine import UNTRUSTED_WARNING


class TestBuildDataOnlyPrompt:
    def test_prompt_contains_escaped_fence_and_warning(self):
        prompt = judge.build_data_only_prompt("plain page body")
        assert UNTRUSTED_WARNING in prompt
        assert "plain page body" in prompt
        assert '"data_only"' in prompt  # the JSON contract is spelled out

    def test_page_backtick_fences_cannot_break_out(self):
        content = "before\n```\nfake fence\n```\nafter"
        prompt = judge.build_data_only_prompt(content)
        # escape_untrusted must wrap with a LONGER fence than any run inside
        assert "````" in prompt

    def test_overlong_content_is_truncated(self):
        prompt = judge.build_data_only_prompt("x" * 1_000_000)
        assert len(prompt) < 500_000


class TestParseDataOnlyVerdict:
    def test_valid_verdict_parses(self):
        v = judge.parse_data_only_verdict(
            {"data_only": True, "confidence": 0.93, "reason": "facts only"}
        )
        assert v.data_only is True
        assert v.confidence == 0.93
        assert v.reason == "facts only"

    @pytest.mark.parametrize(
        "bad",
        [
            {},  # missing everything
            {"data_only": "true", "confidence": 0.9, "reason": "r"},  # str not bool
            {"data_only": 1, "confidence": 0.9, "reason": "r"},  # int not bool
            {"data_only": True, "confidence": True, "reason": "r"},  # bool confidence
            {"data_only": True, "confidence": 1.5, "reason": "r"},  # out of range
            {"data_only": True, "confidence": 0.9, "reason": 7},  # non-str reason
            "not a dict",
            None,
        ],
    )
    def test_malformed_verdicts_raise_judge_error(self, bad):
        with pytest.raises(judge.JudgeError):
            judge.parse_data_only_verdict(bad)

    def test_reason_defaults_to_empty_string(self):
        v = judge.parse_data_only_verdict({"data_only": False, "confidence": 0.8})
        assert v.reason == ""
