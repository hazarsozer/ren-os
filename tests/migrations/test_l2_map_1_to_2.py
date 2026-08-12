"""l2-map 1→2 — the repo's first BODY-rewriting migration (#53): arrow-form
wiki pointers under ## Decision map become markdown links; repo: refs and
prose arrows are untouched; schema_version lands at 2 (inserted when absent —
the dogfood maps were never stamped, issue #20)."""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MIGRATE = REPO_ROOT / "migrations" / "l2-map-1-to-2" / "migrate.sh"

V1_MAP = """---
type: l2-map
project: demo
ren_write_id: "w-01MAP"
---
# demo — knowledge map
## Knowledge
- a fact mentioning A → B in prose (untouched)
## Decision map
_All pointer paths are relative to the wiki root, not this file._
- [Stack] → projects/demo/knowledge/stack.md (w-01A)
- [Schema] → projects/demo/schema.md#naming (unstamped)
- [Specs] → repo:idea-generator:analyses (w-01B)
## Log
- 2026-08-12: test
"""


def run_migration(page: Path, tmp_path: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["REN_WIKI_ROOT"] = str(tmp_path)
    env["REN_SNAPSHOT_DIR"] = str(tmp_path / "snap")
    (tmp_path / "snap").mkdir(exist_ok=True)
    return subprocess.run(
        ["bash", str(MIGRATE), str(page)],
        capture_output=True, text=True, env=env, cwd=REPO_ROOT,
    )


@pytest.fixture
def page(tmp_path):
    p = tmp_path / "map.md"
    p.write_text(V1_MAP, encoding="utf-8")
    return p


def test_converts_wiki_pointers_and_stamps_schema(page, tmp_path):
    result = run_migration(page, tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"
    text = page.read_text(encoding="utf-8")
    assert "- [Stack](projects/demo/knowledge/stack.md) (w-01A)" in text
    assert "- [Schema](projects/demo/schema.md#naming) (unstamped)" in text
    assert "- [Specs] → repo:idea-generator:analyses (w-01B)" in text   # repo ref untouched
    assert "a fact mentioning A → B in prose (untouched)" in text        # prose arrow untouched
    assert "schema_version: 2" in text
    assert text.index("schema_version: 2") > text.index("type: l2-map")
    assert "] → projects/" not in text


def test_idempotent_second_run_skips(page, tmp_path):
    run_migration(page, tmp_path)
    second = run_migration(page, tmp_path)
    assert second.returncode == 0
    assert second.stdout.strip().startswith("SKIP")


def test_existing_schema_version_line_is_bumped(page, tmp_path):
    page.write_text(V1_MAP.replace('project: demo', 'project: demo\nschema_version: 1'), encoding="utf-8")
    result = run_migration(page, tmp_path)
    assert result.returncode == 0
    text = page.read_text(encoding="utf-8")
    assert "schema_version: 2" in text
    assert "schema_version: 1" not in text


def test_missing_args_exit_2(tmp_path):
    result = subprocess.run(["bash", str(MIGRATE)], capture_output=True, text=True, cwd=REPO_ROOT)
    assert result.returncode == 2


def test_transform_failure_leaves_page_byte_identical(page, tmp_path):
    # A page whose Decision map contains a line the parser can't round-trip:
    # topic containing "](" makes render+reparse disagree → self-verify fails.
    broken = V1_MAP.replace("- [Stack] →", "- [Bad](topic] →")
    page.write_text(broken, encoding="utf-8")
    before = page.read_bytes()
    result = run_migration(page, tmp_path)
    # Either the line is left alone (not pointer-shaped → OK) or the
    # transform refused — in BOTH cases the invariant holds:
    text_after = page.read_bytes()
    if result.returncode == 1:
        assert text_after == before
    else:
        assert b"](topic]" in text_after   # untouched garbage, no corruption
