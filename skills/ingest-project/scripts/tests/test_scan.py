"""Hermetic tests for skills/ingest-project/scripts/scan.py.

Every test builds a throwaway project tree under tmp_path, runs the read-only
scanner against it, and asserts on the parsed facts JSON. The load-bearing
invariant (Task 7): the scanner mutates NOTHING in the project.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import scan  # noqa: E402


def run_scan(path: Path) -> dict:
    """Call scan.scan() and return the parsed facts dict."""
    return scan.scan(str(path))


def test_empty_dir_is_not_a_project(tmp_path):
    facts = run_scan(tmp_path)
    assert facts["schema_version"] == 1
    assert facts["scanned_path"] == str(tmp_path)
    assert facts["looks_like_project"] is False
    assert "framework_version" in facts
