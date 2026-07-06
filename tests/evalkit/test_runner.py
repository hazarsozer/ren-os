"""
Tests for lib.evalkit.runner — G10 retrieval eval harness (Task 3.4).

Run with: uv run pytest tests/evalkit/test_runner.py -v
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from lib.evalkit.runner import EvalReport, run_gate_eval, run_retrieval_eval

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
MINI_WIKI = FIXTURES_DIR / "mini_wiki"
RETRIEVAL_FIXTURE = FIXTURES_DIR / "retrieval_fixture.json"

_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    """
    the a an and or but for to of in on at by with from into this that these
    those is are was were be been being do does did done will would can could
    should shall may might must not no we our it its as after before over
    under up down still since so what why how when who which where
    """.split()
)


def _naive_rank(query: str, candidate_pages: list[str], wiki_root: Path) -> list[str]:
    """Naive token-overlap ranker used ONLY in this test — proves the fixture
    is answerable-by-construction. Never shipped as a real ranker."""
    query_tokens = {w for w in _WORD_RE.findall(query.lower()) if w not in _STOPWORDS}

    scored = []
    for page in candidate_pages:
        text = (wiki_root / page).read_text(encoding="utf-8").lower()
        page_tokens = {w for w in _WORD_RE.findall(text) if w not in _STOPWORDS}
        score = len(query_tokens & page_tokens)
        scored.append((score, page))

    # Stable, deterministic: sort by score descending, then page path ascending.
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [page for _, page in scored]


# --- hit/miss counting + hit_rate math on a hand-built mini fixture --------


def test_hit_miss_counting_and_hit_rate_math(tmp_path):
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    (wiki_root / "a.md").write_text("about apples\n", encoding="utf-8")
    (wiki_root / "b.md").write_text("about bananas\n", encoding="utf-8")
    (wiki_root / "c.md").write_text("about cherries\n", encoding="utf-8")

    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [
                    {"query": "q-a", "expected_page": "a.md"},
                    {"query": "q-b", "expected_page": "b.md"},
                    {"query": "q-c", "expected_page": "c.md"},
                ],
            }
        ),
        encoding="utf-8",
    )

    # Deterministic stub ranker: always ranks a.md and b.md correctly (as the
    # top hit), but always ranks c.md query behind a wrong page -> 1 miss.
    def ranker(query, candidate_pages, wiki_root_):
        if query == "q-a":
            return ["a.md", "b.md", "c.md"]
        if query == "q-b":
            return ["b.md", "a.md", "c.md"]
        return ["a.md", "b.md", "c.md"]  # q-c: c.md never returned first -> still in top-3 though

    report = run_retrieval_eval(ranker, fixture_path, wiki_root, k=3)

    assert isinstance(report, EvalReport)
    assert report.total == 3
    # With k=3 and only 3 candidates, c.md is always in top-3 regardless of
    # order, so this stub actually hits all 3. Use a k=1 gate to force a miss
    # and prove the counting/hit_rate math over a non-trivial case:
    report_k1 = run_retrieval_eval(ranker, fixture_path, wiki_root, k=1)
    assert report_k1.total == 3
    assert report_k1.hits == 2  # q-a and q-b hit at rank 1; q-c does not
    assert report_k1.hit_rate == pytest.approx(2 / 3)
    assert len(report_k1.failures) == 1
    assert report_k1.failures[0]["expected"] == "c.md"


# --- k respected: expected at rank 4 with k=3 -> miss -----------------------


def test_k_is_respected_rank_four_is_a_miss_at_k_three(tmp_path):
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    for name in ("p1.md", "p2.md", "p3.md", "p4.md"):
        (wiki_root / name).write_text(f"content of {name}\n", encoding="utf-8")

    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {"version": 1, "cases": [{"query": "find p4", "expected_page": "p4.md"}]}
        ),
        encoding="utf-8",
    )

    def ranker(query, candidate_pages, wiki_root_):
        return ["p1.md", "p2.md", "p3.md", "p4.md"]  # expected at rank 4 (index 3)

    report = run_retrieval_eval(ranker, fixture_path, wiki_root, k=3)

    assert report.hits == 0
    assert report.total == 1
    assert report.hit_rate == 0.0
    assert report.failures[0]["got"] == ["p1.md", "p2.md", "p3.md"]
    assert report.failures[0]["expected"] == "p4.md"

    # Widening k to 4 turns it into a hit — proves k is actually load-bearing.
    report_wide = run_retrieval_eval(ranker, fixture_path, wiki_root, k=4)
    assert report_wide.hits == 1


# --- failures list carries query/expected/got-top-k -------------------------


def test_failures_carry_query_expected_and_got_top_k(tmp_path):
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    (wiki_root / "right.md").write_text("right page\n", encoding="utf-8")
    (wiki_root / "wrong1.md").write_text("wrong page one\n", encoding="utf-8")
    (wiki_root / "wrong2.md").write_text("wrong page two\n", encoding="utf-8")

    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [{"query": "the query text", "expected_page": "right.md"}],
            }
        ),
        encoding="utf-8",
    )

    def ranker(query, candidate_pages, wiki_root_):
        return ["wrong1.md", "wrong2.md"]  # never returns right.md at all

    report = run_retrieval_eval(ranker, fixture_path, wiki_root, k=2)

    assert report.failures == [
        {
            "query": "the query text",
            "expected": "right.md",
            "got": ["wrong1.md", "wrong2.md"],
        }
    ]


# --- fixture version validation ----------------------------------------------


def test_unknown_fixture_version_raises_value_error(tmp_path):
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    (wiki_root / "x.md").write_text("x\n", encoding="utf-8")

    bad_fixture = tmp_path / "bad_fixture.json"
    bad_fixture.write_text(
        json.dumps({"version": 99, "cases": []}), encoding="utf-8"
    )

    def ranker(query, candidate_pages, wiki_root_):
        return candidate_pages

    with pytest.raises(ValueError):
        run_retrieval_eval(ranker, bad_fixture, wiki_root)


def test_missing_fixture_version_raises_value_error(tmp_path):
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()

    bad_fixture = tmp_path / "no_version.json"
    bad_fixture.write_text(json.dumps({"cases": []}), encoding="utf-8")

    def ranker(query, candidate_pages, wiki_root_):
        return candidate_pages

    with pytest.raises(ValueError):
        run_retrieval_eval(ranker, bad_fixture, wiki_root)


# --- answerable-by-construction: naive ranker scores >= 10/12 --------------


def test_naive_ranker_scores_at_least_ten_of_twelve_on_real_fixture():
    report = run_retrieval_eval(_naive_rank, RETRIEVAL_FIXTURE, MINI_WIKI, k=3)

    assert report.total == 12
    assert report.hits >= 10, f"naive ranker only hit {report.hits}/12 — fixture may be mis-keyed: {report.failures}"
    assert report.hit_rate == pytest.approx(report.hits / 12)


# --- gate eval ---------------------------------------------------------------


def test_gate_eval_accept_case_passes():
    def gate(input_: str) -> str:
        return "accept"

    report = run_gate_eval(gate, [{"input": "safe text", "expect": "accept"}])
    assert report.total == 1
    assert report.hits == 1
    assert report.hit_rate == 1.0
    assert report.failures == []


def test_gate_eval_refuse_case_passes():
    def gate(input_: str) -> str:
        return "refuse"

    report = run_gate_eval(gate, [{"input": "dangerous text", "expect": "refuse"}])
    assert report.total == 1
    assert report.hits == 1
    assert report.failures == []


def test_gate_eval_crashing_gate_refuse_case_passes():
    def crashing_gate(input_: str) -> str:
        raise RuntimeError("boom")

    report = run_gate_eval(crashing_gate, [{"input": "anything", "expect": "refuse"}])
    assert report.total == 1
    assert report.hits == 1
    assert report.failures == []


def test_gate_eval_crashing_gate_accept_case_fails():
    def crashing_gate(input_: str) -> str:
        raise RuntimeError("boom")

    report = run_gate_eval(crashing_gate, [{"input": "anything", "expect": "accept"}])
    assert report.total == 1
    assert report.hits == 0
    assert len(report.failures) == 1
    assert report.failures[0]["expected"] == "accept"
    assert "boom" in report.failures[0]["got"]


def test_gate_eval_empty_cases_total_zero_rate_zero():
    report = run_gate_eval(lambda x: "accept", [])
    assert report.total == 0
    assert report.hits == 0
    assert report.hit_rate == 0.0
    assert report.failures == []


def test_gate_eval_non_accept_refuse_return_value_scores_as_refuse():
    def weird_gate(input_: str) -> str:
        return "maybe"

    accept_report = run_gate_eval(weird_gate, [{"input": "x", "expect": "accept"}])
    assert accept_report.hits == 0

    refuse_report = run_gate_eval(weird_gate, [{"input": "x", "expect": "refuse"}])
    assert refuse_report.hits == 1
