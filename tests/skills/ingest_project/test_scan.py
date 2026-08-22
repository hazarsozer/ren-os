"""`scan.py` facts-gathering invariants.

Companion to test_l2_map.py; same importlib pattern (the package dir is
hyphenated, so a plain import statement cannot name it).
"""

from __future__ import annotations

import importlib

scan = importlib.import_module("skills.ingest-project.lib.scan")


def test_framework_version_is_none_when_unresolvable(monkeypatch):
    """A resolver failure must yield None, not a stale literal. A wrong-but-
    plausible version is worse than an absent one: nothing downstream can
    detect it."""

    def boom(*_args, **_kwargs):
        raise OSError("no path")

    monkeypatch.setattr(scan.Path, "resolve", boom)

    assert scan._framework_version() is None


def test_scan_warns_when_framework_version_is_unresolvable(monkeypatch, tmp_path):
    """The fact stays present (the COMPLETE-facts contract) and the failure
    is recorded as a warning rather than silently absent."""
    monkeypatch.setattr(scan, "_framework_version", lambda: None)
    (tmp_path / "README.md").write_text("# demo\n")

    # The module is `scan` and its public entrypoint is also `scan`, taking a
    # str path (skills/ingest-project/lib/scan.py:509) — not a Path.
    facts = scan.scan(str(tmp_path))

    assert "framework_version" in facts
    assert facts["framework_version"] is None
    assert any("framework version" in w.lower() for w in facts["warnings"])


def test_no_hardcoded_version_literal_remains():
    """Pins the defect class, not the instance: no x.y.z literal may sit in
    a return statement of this module again."""
    import re
    from pathlib import Path as _Path

    src = (_Path(__file__).resolve().parents[3] / "skills/ingest-project/lib/scan.py").read_text(
        encoding="utf-8"
    )
    assert not re.search(r'return\s+"\d+\.\d+\.\d+"', src)
