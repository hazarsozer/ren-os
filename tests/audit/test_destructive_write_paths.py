"""Destructive-write audit pins (issue #11 §2).

Two of the last four releases fixed data-destroying bugs; the worst
(`/ren:bootstrap-project` silently overwriting a grown L2 map, latent since
0.2, fixed in 0.5.6) had the shape "a template or generated write meets an
existing file". These tests pin the CLASS, not the single instance:

  1. Re-stamping the skeleton / re-running bootstrap on a populated wiki never
     truncates grown content.
  2. Every write primitive under `lib/` + `skills/` is accounted for in
     `docs/audits/2026-07-destructive-writes.md` — a new write site is a
     failing test until someone classifies it.
  3. `write_agents_md` (the audit's one VIOLATION) preserves a pre-existing
     hand-authored AGENTS.md instead of clobbering it.

All fixtures redirect ren_paths at tmp_path — never the real ~/.renos.
"""

from __future__ import annotations

import importlib
import re
import subprocess
from pathlib import Path

import pytest

from lib.portability.agents_surface import write_agents_md
from lib.skeleton import stamp_skeleton

REPO_ROOT = Path(__file__).resolve().parents[2]
SKELETON_ROOT = REPO_ROOT / "wiki-skeleton"
AUDIT_DOC = REPO_ROOT / "docs" / "audits" / "2026-07-destructive-writes.md"

bootstrap = importlib.import_module("skills.bootstrap-project.lib").bootstrap


@pytest.fixture
def wiki(tmp_path, monkeypatch):
    """`wiki_root()` == tmp_path/"wiki" (write_apply always resolves against
    wiki_root(), per lib/skeleton.py's module docstring)."""
    for var in ("CLAUDE_PLUGIN_OPTION_WIKIROOT", "CLAUDE_SESSION_ID"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("REN_WIKI_ROOT", str(tmp_path / "wiki"))
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path / ".renos"))
    return tmp_path / "wiki"


def _placeholders() -> dict[str, str]:
    return {"handle": "friend", "name": "Friend", "framework_version": "0.6.0"}


def _stamp(target: Path) -> None:
    stamp_skeleton(
        skeleton_root=SKELETON_ROOT,
        target_root=target,
        profile="master",
        placeholders=_placeholders(),
    )


def test_stamp_skeleton_rerun_preserves_grown_pages(wiki):
    """copy_if_missing: a page that grew after the first stamp survives a re-stamp."""
    _stamp(wiki)
    grown = wiki / "index.md"
    grown.write_text(
        grown.read_text(encoding="utf-8") + "\n## grown section\nreal knowledge\n",
        encoding="utf-8",
    )
    before = grown.read_text(encoding="utf-8")

    _stamp(wiki)

    assert grown.read_text(encoding="utf-8") == before


def _configure_real_backup_remote(wiki: Path, tmp_path: Path) -> None:
    """Satisfy the 0.6.0 backup gate through its REAL public surface — a
    `backup` git remote on the wiki repo, pointing at a bare repo in the
    sandbox — rather than faking `backup_gate.backup_configured`. (Fix round
    1, finding 2: the private fake here masked a false positive in the gate's
    own populated-wiki detection.)"""
    bare = tmp_path / "backup.git"
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
    wiki.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=wiki, check=True)
    subprocess.run(["git", "remote", "add", "backup", str(bare)], cwd=wiki, check=True)


def test_bootstrap_rerun_preserves_grown_l2_map(wiki, tmp_path):
    """The exact 0.5.6 bug shape, pinned at the real L2 map path."""
    # The second bootstrap call below lands on an already-populated wiki, so
    # the 0.6.0 backup gate applies — configure a real backup remote so this
    # pin keeps testing the ORIGINAL bug shape, not the (separately tested)
    # gate.
    _configure_real_backup_remote(wiki, tmp_path)
    bootstrap("falcon", session="sess-1")
    grown = wiki / "projects" / "falcon" / "map.md"
    assert grown.is_file()
    grown.write_text(
        grown.read_text(encoding="utf-8") + "\n## Knowledge\n- hard-won fact\n",
        encoding="utf-8",
    )
    before = grown.read_text(encoding="utf-8")

    bootstrap("falcon", session="sess-2")

    assert grown.read_text(encoding="utf-8") == before


def test_write_agents_md_preserves_pre_existing_hand_authored_file(tmp_path):
    """VIOLATION fix: bootstrap must not destroy a repo's own AGENTS.md.

    AGENTS.md is a widely-used convention — many repos already have one,
    hand-written, before RenOS ever sees them. A regenerable pointer file is
    allowed to refresh ITS OWN block; it is not allowed to truncate the
    user's content.
    """
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    mine = "# AGENTS.md\n\nRun `make test` before every commit. Do not touch vendor/.\n"
    (repo_root / "AGENTS.md").write_text(mine, encoding="utf-8")

    write_agents_md(repo_root, wiki_root, project_slug="demo-project")

    text = (repo_root / "AGENTS.md").read_text(encoding="utf-8")
    assert mine.rstrip("\n") in text  # the human's content survives
    assert "demo-project" in text  # ours got added alongside


def test_audit_doc_covers_all_write_sites():
    """Every write primitive under lib/ + skills/ appears in the audit table."""
    audit = AUDIT_DOC.read_text(encoding="utf-8")
    hits = subprocess.run(
        [
            "grep",
            "-rlE",
            # Python write/move/delete primitives, plus the shell equivalents
            # (`rm -rf`, `cp -a`, `mv`) used by skills/update/scripts/*.sh —
            # without those the shell tree destroyers were invisible here.
            r"write_text\(|write_bytes\(|open\(.+[\"']w[\"']"
            r"|shutil\.copy|shutil\.move|shutil\.rmtree"
            r"|os\.replace|os\.rename|\.rename\(|\.unlink\("
            r"|rm -rf|cp -a|mv ",
            "lib",
            "skills",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    ).stdout.split()
    assert hits, "sweep found no write sites at all — the grep is broken"
    missing = [h for h in hits if "__pycache__" not in h and h not in audit]
    assert not missing, f"write sites absent from audit doc: {missing}"


def test_audit_doc_records_no_unfixed_violations():
    """A VIOLATION row must always be marked fixed — the doc is a live ledger."""
    audit = AUDIT_DOC.read_text(encoding="utf-8")
    open_rows = [
        line
        for line in audit.splitlines()
        # only numbered rows of the audit table itself, not the vocabulary key
        if re.match(r"\|\s*\d+\s*\|", line)
        and "VIOLATION" in line
        and "FIXED" not in line
    ]
    assert not open_rows, f"unfixed VIOLATION rows in audit doc: {open_rows}"
