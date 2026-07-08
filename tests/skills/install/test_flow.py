"""
Tests for skills.install.lib — idempotent guided install (Task 8.1).

Idempotency by REAL state inspection (donor's InstallSimulator core idea,
without the simulator): `install_state()` reads the actual wiki, not a fake
one. Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/skills/install/test_flow.py -v
"""

from __future__ import annotations

import json

import pytest

from lib.ren_paths import state_dir, wiki_root
from skills.install.lib import install_state, record_install, stamp_wiki
from skills.interview.lib import save_identity


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    return monkeypatch


@pytest.fixture
def wiki(clean_path_env, tmp_path):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


# --- install_state: virgin env ----------------------------------------------


def test_install_state_on_virgin_env_is_all_false_or_zero(wiki):
    state = install_state(wiki)
    assert state["wiki_stamped"] is False
    assert state["identity_present"] is False
    assert state["backup_configured"] is False
    assert state["l2_maps"] == 0
    assert state["installed_version"] is None


# --- stamp_wiki ---------------------------------------------------------


def test_stamp_wiki_flips_wiki_stamped_and_identity_present(wiki):
    result = stamp_wiki()
    assert "index.md" in result.written
    assert "identity.md" in result.written

    state = install_state(wiki)
    assert state["wiki_stamped"] is True
    assert state["identity_present"] is True
    assert state["l2_maps"] == 0  # master index.md is not a PROJECT map (F3, 2026-07-07)


def test_stamp_wiki_is_idempotent_second_call_changes_nothing_new(wiki):
    first = stamp_wiki()
    assert first.written  # something was written the first time

    before_files = sorted(p.relative_to(wiki) for p in wiki.rglob("*") if p.is_file())

    second = stamp_wiki()
    assert second.written == []  # nothing NEW written the second time
    assert set(second.skipped) >= set(first.written)  # what was written is now reported skipped

    after_files = sorted(p.relative_to(wiki) for p in wiki.rglob("*") if p.is_file())
    assert before_files == after_files  # byte-for-byte no new files


# --- save_identity flips identity_present's meaning is already covered by --
# --- stamp_wiki (stub identity.md); confirm a real interview UPDATE lands --


def test_full_flow_flips_expected_fields(wiki):
    stamp_wiki()

    # v2.2: identity.md is a non-global (data-plane) page — save_identity
    # auto-applies through propose_and_apply. (The stub wiki content used to
    # trip a false `contradicts` conflict here — index.md.tmpl's "whenever"
    # was misread as a negated "never" line; fixed in lib.memory.semantics
    # via word-boundary negation matching, so this is now deterministic.)
    entry = save_identity({"name": "Hazar", "handle": "hazar"}, session="sess-1")
    assert entry.status == "applied"

    record_install("0.2.0")

    state = install_state(wiki)
    assert state["wiki_stamped"] is True
    assert state["identity_present"] is True
    assert state["installed_version"] == "0.2.0"


# --- record_install -----------------------------------------------------


def test_record_install_round_trips(wiki):
    record_install("0.2.0")
    path = state_dir() / "install.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == "0.2.0"
    assert "ts" in data

    state = install_state(wiki)
    assert state["installed_version"] == "0.2.0"


def test_install_state_never_raises_on_corrupt_install_json(wiki):
    path = state_dir() / "install.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json", encoding="utf-8")

    state = install_state(wiki)  # must not raise
    assert state["installed_version"] is None


def test_install_state_never_raises_on_missing_wiki_root(tmp_path):
    missing = tmp_path / "does-not-exist"
    state = install_state(missing)
    assert state["wiki_stamped"] is False
    assert state["l2_maps"] == 0

# --- global CLAUDE.md layer (finalize-v0.2 agenda item 1) ---------------------


def test_install_state_reports_global_claude_md(wiki, monkeypatch, tmp_path):
    claude_dir = tmp_path / "claude-home"
    monkeypatch.setenv("REN_CLAUDE_DIR", str(claude_dir))

    assert install_state(wiki)["global_claude_md"] is False

    from lib.adapter.claude_md import write_global_claude_md

    write_global_claude_md(wiki_root=wiki)
    assert install_state(wiki)["global_claude_md"] is True


def test_install_state_global_claude_md_ignores_unmanaged_file(wiki, monkeypatch, tmp_path):
    """A pre-existing user CLAUDE.md without our markers is NOT 'done'."""
    claude_dir = tmp_path / "claude-home"
    claude_dir.mkdir()
    (claude_dir / "CLAUDE.md").write_text("my own rules\n", encoding="utf-8")
    monkeypatch.setenv("REN_CLAUDE_DIR", str(claude_dir))

    assert install_state(wiki)["global_claude_md"] is False


# --- dogfood 2026-07-07 findings -----------------------------------------


def test_stamp_wiki_binds_framework_version(wiki):
    """F1: fresh install must not leave literal {{framework_version}} in pages."""
    from lib.ren_paths import framework_version

    result = stamp_wiki()
    assert not [w for w in result.warnings if "framework_version" in w]
    for name in ("index.md", "log.md", "identity.md", "LICENSES.md"):
        text = (wiki / name).read_text(encoding="utf-8")
        assert "{{framework_version}}" not in text, name
    assert framework_version() in (wiki / "index.md").read_text(encoding="utf-8")


def test_l2_maps_counts_only_project_maps(wiki):
    """F3: the master index.md (type: l2-map) must not count as a project map."""
    stamp_wiki()
    assert install_state(wiki)["l2_maps"] == 0

    proj = wiki / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / "map.md").write_text(
        "---\ntype: l2-map\nproject: demo\n---\n# demo\n", encoding="utf-8"
    )
    assert install_state(wiki)["l2_maps"] == 1
