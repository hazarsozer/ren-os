"""Regression guard: routine-spec is registered and its template conforms (C4 / ADR-034)."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import conformance  # noqa: E402


def test_routine_spec_registered():
    registry = conformance.load_registry()
    assert "routine-spec" in registry["page_types"]
    meta = registry["page_types"]["routine-spec"]
    assert meta["current"] == 2
    assert meta["supported_from"] == 1


def test_routine_spec_template_conforms():
    registry = conformance.load_registry()
    report = conformance.walk_targets(registry)
    passed = [r.path for r in report.by_status["pass"] if r.type_claimed == "routine-spec"]
    assert passed, "no conformant routine-spec template scanned (is the SCAN_TARGETS glob added?)"
    fails = [(r.path, r.detail) for r in report.by_status["fail"] if r.type_claimed == "routine-spec"]
    assert not fails, f"routine-spec conformance failures: {fails}"
