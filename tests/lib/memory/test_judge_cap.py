"""#46: the 4,000-char cap routed 14/20 screened candidates to the human as
`too-long` (all only marginally over: 4,016-5,816 chars) — the suggestions
store became the de-facto quarantine exit. 8,000 covers every observed page
with headroom while keeping the judge on WHOLE pages (no excerpt judging)."""

from lib.memory.judge import JUDGE_MAX_TEXT_CHARS, build_judge_prompt


def test_cap_is_8000():
    assert JUDGE_MAX_TEXT_CHARS == 8_000


def test_truncate_keeps_tail_at_new_cap():
    text = "x" * 100 + "T" * 8_000
    prompt = build_judge_prompt(text, "b")
    assert "T" * 8_000 in prompt        # full 8k tail survives
    assert "x" * 100 not in prompt      # 100 head chars truncated away
