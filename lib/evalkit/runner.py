"""
lib.evalkit.runner — G10 retrieval eval harness (Task 3.4, RenOS 0.2 Phase 3).

Spec §3.9: "frozen retrieval-eval fixture (10-20 versioned query->expected-page
pairs) - hit-rate is computed against the fixture and the §3.2 mechanical miss
log, never LLM self-report" + "an eval for every LLM-gated path (wrap classifier
first) with pass/fail assertions" (council A-5).

Two deterministic, LLM-free scorers:
  - `run_retrieval_eval` — hit-rate of a ranker against a frozen fixture of
    query -> expected-page pairs. This is what Phase 5's real wake-up ranker
    (and any future retrieval component) gets scored against; the fixture at
    `tests/fixtures/retrieval_fixture.json` + `tests/fixtures/mini_wiki/` is the
    frozen substrate, versioned so a schema change is a deliberate bump, not a
    silent drift.
  - `run_gate_eval` — pass/fail scoring for any LLM-gated accept/refuse path
    (the wrap classifier being the first). FAIL-CLOSED is the scored contract:
    a gate that raises, or returns anything other than the literal strings
    "accept"/"refuse", is scored as "refuse" — so a crashing gate passes every
    refuse-case and fails every accept-case. A gate that fails safe should not
    also fail its own eval.

Nothing here calls an LLM, ever. Ranking/gating implementations under test are
supplied by the caller as plain callables; this module only counts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

_SUPPORTED_FIXTURE_VERSION = 1


@dataclass(frozen=True)
class EvalReport:
    total: int
    hits: int              # (or passes, for gate evals)
    hit_rate: float        # 0.0 when total == 0
    failures: list[dict]


def _load_fixture(fixture_path: Path) -> list[dict]:
    """Load and version-check a retrieval fixture file.

    Raises ValueError if the file's top-level "version" isn't the one
    `_SUPPORTED_FIXTURE_VERSION` this runner knows how to score — a fixture
    schema bump must be a deliberate, visible decision, not silently misread.
    """
    fixture_path = Path(fixture_path)
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    version = data.get("version")
    if version != _SUPPORTED_FIXTURE_VERSION:
        raise ValueError(
            f"{fixture_path}: unsupported fixture version {version!r} "
            f"(this runner only supports version {_SUPPORTED_FIXTURE_VERSION})"
        )
    return list(data.get("cases", []))


def run_retrieval_eval(
    ranker_fn: Callable[[str, list[str], Path], list[str]],
    fixture_path: Path,
    wiki_root: Path,
    k: int = 3,
) -> EvalReport:
    """Score `ranker_fn` against the frozen fixture at `fixture_path`.

    `candidate_pages` passed to `ranker_fn` is every `*.md` under `wiki_root`,
    as wiki-relative posix-style path strings. A case is a HIT iff its
    `expected_page` appears anywhere in `ranker_fn`'s top-`k` returned pages.
    Deterministic — no LLM anywhere in this path.
    """
    wiki_root = Path(wiki_root)
    cases = _load_fixture(fixture_path)
    candidate_pages = sorted(
        p.relative_to(wiki_root).as_posix() for p in wiki_root.rglob("*.md")
    )

    hits = 0
    failures: list[dict] = []

    for case in cases:
        query = case["query"]
        expected = case["expected_page"]
        ranked = list(ranker_fn(query, candidate_pages, wiki_root))
        top_k = ranked[:k]
        if expected in top_k:
            hits += 1
        else:
            failures.append({"query": query, "expected": expected, "got": top_k})

    total = len(cases)
    return EvalReport(
        total=total,
        hits=hits,
        hit_rate=(hits / total) if total else 0.0,
        failures=failures,
    )


def run_gate_eval(gate_fn: Callable[[str], str], cases: list[dict]) -> EvalReport:
    """Score `gate_fn` against `cases` (each `{"input": str, "expect": "accept"|"refuse"}`).

    Fail-closed scoring contract: if `gate_fn` raises, or returns anything
    other than the literal string "accept" or "refuse", the call is scored as
    "refuse" — never as an error, never as "accept". So a crashing/misbehaving
    gate passes every `expect: "refuse"` case and fails every
    `expect: "accept"` case, matching the safety property a gate is supposed
    to have (when in doubt, refuse).
    """
    hits = 0
    failures: list[dict] = []

    for case in cases:
        input_ = case["input"]
        expect = case["expect"]

        try:
            raw_got: Any = gate_fn(input_)
        except Exception as exc:  # noqa: BLE001 - deliberately broad: any crash scores "refuse"
            raw_got = f"<exception: {type(exc).__name__}: {exc}>"

        scored = raw_got if raw_got in ("accept", "refuse") else "refuse"

        if scored == expect:
            hits += 1
        else:
            failures.append({"input": input_, "expected": expect, "got": raw_got})

    total = len(cases)
    return EvalReport(
        total=total,
        hits=hits,
        hit_rate=(hits / total) if total else 0.0,
        failures=failures,
    )


__all__ = ["EvalReport", "run_retrieval_eval", "run_gate_eval"]
