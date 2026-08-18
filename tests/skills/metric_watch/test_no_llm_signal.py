"""
Tests for `skills.metric-watch.lib._check_no_llm_with_candidates` (Task 6:
weekly routine spec + metric-watch `no_llm` signal) and the
`wiki-skeleton/routines/distiller-weekly.md` routine-spec page it drives.

Spec §4.1: after the wiring fix, a wrap that HAD candidates (`seen > 0`) but
ran without any classifier ("no_llm" event) is a defect signal, not
background noise — the watch surfaces it instead of it going unnoticed.

Import mechanism copied from `tests/skills/metric_watch/test_watch.py`
(hyphenated dir name via `importlib.import_module`). The routine-spec page
loader is copied from `tests/skills/wrap/test_open_work.py`'s `_frontmatter`
helper (`tests/skills/routine_init/` has no page loader of its own — its
tests build spec dicts directly).

Run with: uv run pytest tests/skills/metric_watch/test_no_llm_signal.py -v
"""

from __future__ import annotations

import importlib
import pathlib

import pytest
import yaml

from lib.instrument import collect

mw = importlib.import_module("skills.metric-watch.lib")


@pytest.fixture
def wiki(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_WIKI_ROOT", str(tmp_path / "wiki"))
    (tmp_path / "wiki").mkdir()
    return tmp_path / "wiki"


def test_no_llm_with_candidates_flags(wiki):
    collect.record(collect.KIND_CLASSIFIER_EVENT,
                   {"event": "no_llm", "item_preview": "x"})
    collect.record(collect.KIND_DURABLE_OUTCOME,
                   {"session": "s1", "producer": "wrap", "seen": 2,
                    "created": 0, "created_project": 0, "created_global": 0,
                    "updated": 0, "gated_out": 0, "suggested": 0,
                    "held": 0, "refused": 0, "unplaced": 2})
    finding = mw._check_no_llm_with_candidates({})
    assert finding is not None
    assert "no_llm" in str(finding).lower() or "classifier" in str(finding).lower()


def test_no_candidates_no_finding(wiki):
    collect.record(collect.KIND_DURABLE_OUTCOME,
                   {"session": "s2", "producer": "wrap", "seen": 0,
                    "created": 0, "created_project": 0, "created_global": 0,
                    "updated": 0, "gated_out": 0, "suggested": 0,
                    "held": 0, "refused": 0, "unplaced": 0})
    assert mw._check_no_llm_with_candidates({}) is None


def test_no_llm_event_without_wrap_candidates_no_finding(wiki):
    collect.record(collect.KIND_CLASSIFIER_EVENT, {"event": "no_llm", "item_preview": "x"})
    assert mw._check_no_llm_with_candidates({}) is None


def test_watermark_suppresses_already_seen_pair_on_next_run(wiki):
    collect.record(collect.KIND_CLASSIFIER_EVENT, {"event": "no_llm", "item_preview": "x"})
    collect.record(collect.KIND_DURABLE_OUTCOME,
                   {"session": "s1", "producer": "wrap", "seen": 2,
                    "created": 0, "created_project": 0, "created_global": 0,
                    "updated": 0, "gated_out": 0, "suggested": 0,
                    "held": 0, "refused": 0, "unplaced": 2})
    state: dict = {}
    first = mw._check_no_llm_with_candidates(state)
    assert first is not None

    second = mw._check_no_llm_with_candidates(state)
    assert second is None


def test_no_llm_finding_wired_into_watch(wiki, monkeypatch):
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(wiki.parent))
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(wiki.parent / "plugin-data"))
    (wiki.parent / "plugin-data" / "backups").mkdir(parents=True, exist_ok=True)
    (wiki.parent / "plugin-data" / "backups" / "wiki-2026-01-01.tar.gz").write_bytes(b"x")

    collect.record(collect.KIND_CLASSIFIER_EVENT, {"event": "no_llm", "item_preview": "x"})
    collect.record(collect.KIND_DURABLE_OUTCOME,
                   {"session": "s1", "producer": "wrap", "seen": 2,
                    "created": 0, "created_project": 0, "created_global": 0,
                    "updated": 0, "gated_out": 0, "suggested": 0,
                    "held": 0, "refused": 0, "unplaced": 2})

    findings = mw.watch(session="sess-1")
    kinds = [f.get("kind") for f in findings]
    assert "no_llm-with-candidates" in kinds


# ------------------------------------------------------- routine-spec page


def _frontmatter(text: str) -> dict:
    assert text.startswith("---\n")
    end = text.find("\n---", 3)
    assert end != -1
    return yaml.safe_load(text[3:end])


def test_distiller_weekly_spec_validates():
    ri = importlib.import_module("skills.routine-init.lib")

    page = (
        pathlib.Path(__file__).resolve().parents[3]
        / "wiki-skeleton" / "routines" / "distiller-weekly.md"
    )
    text = page.read_text(encoding="utf-8")
    text = text.replace("{{today}}", "2026-01-01").replace(
        "{{framework_version}}", "0.7.9"
    )
    spec = _frontmatter(text)

    result = ri.validate_routine_spec(spec)
    assert result.valid, result.errors
