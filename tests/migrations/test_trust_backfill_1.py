"""
End-to-end test for the trust-backfill-1 migration (0.5.1 Task 7).

Like `migrations/queue-governance-2-to-3/`, this migration walks state
directly (the wiki tree) rather than following `skills/wiki-migration`'s
per-page-type `migrate.sh` chain shape — see this migration's README for the
shape-decision rationale. It backfills `ren_trust` onto pre-0.5.1 pages that
predate the trust taxonomy (0.5.1 Task 6):

  - ren_writer == "human"  -> "user"
  - quarantined            -> "foreign"
  - else                   -> "model"

Run with: uv run pytest tests/migrations/test_trust_backfill_1.py -v
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from lib.memory import provenance, quarantine
from lib.ren_paths import wiki_root

_MIGRATE_PATH = (
    Path(__file__).resolve().parents[2] / "migrations" / "trust-backfill-1" / "migrate.py"
)


def _load_migrate():
    spec = importlib.util.spec_from_file_location("_trust_backfill_1_migrate", _MIGRATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def wiki(clean_path_env, tmp_path):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _human_page_text() -> str:
    return (
        '---\n'
        'title: "human lesson"\n'
        'ren_write_id: "w-01H0000000000000000000001"\n'
        'ren_ts: "2026-01-01T00:00:00Z"\n'
        'ren_writer: "human"\n'
        'ren_op: "ADD"\n'
        '---\n'
        'A human-authored body.\n'
    )


def _quarantined_page_text() -> str:
    body = quarantine.mark("An LLM-drafted body, unreviewed.\n")
    return (
        '---\n'
        'title: "quarantined draft"\n'
        'ren_write_id: "w-01H0000000000000000000002"\n'
        'ren_ts: "2026-01-01T00:00:00Z"\n'
        'ren_writer: "llm-auto"\n'
        'ren_op: "ADD"\n'
        '---\n'
    ) + body


def _plain_llm_page_text() -> str:
    return (
        '---\n'
        'title: "plain llm lesson"\n'
        'ren_write_id: "w-01H0000000000000000000003"\n'
        'ren_ts: "2026-01-01T00:00:00Z"\n'
        'ren_writer: "llm-auto"\n'
        'ren_op: "ADD"\n'
        '---\n'
        'A model-authored body, not quarantined.\n'
    )


def _seed_three_pages(root: Path) -> tuple[Path, Path, Path]:
    human = root / "lessons" / "human.md"
    quarantined = root / "lessons" / "quarantined.md"
    plain = root / "lessons" / "plain.md"
    human.parent.mkdir(parents=True, exist_ok=True)

    human.write_text(_human_page_text(), encoding="utf-8")
    quarantined.write_text(_quarantined_page_text(), encoding="utf-8")
    plain.write_text(_plain_llm_page_text(), encoding="utf-8")
    return human, quarantined, plain


def test_migration_classifies_each_page_correctly(wiki):
    human, quarantined, plain = _seed_three_pages(wiki)
    before_bodies = {
        p: provenance._FRONTMATTER_RE.sub("", p.read_text(encoding="utf-8"), count=1)
        for p in (human, quarantined, plain)
    }

    migrate = _load_migrate()
    rc = migrate.main([])
    assert rc == 0

    human_prov = provenance.read_frontmatter_provenance(human.read_text(encoding="utf-8"))
    quarantined_prov = provenance.read_frontmatter_provenance(quarantined.read_text(encoding="utf-8"))
    plain_prov = provenance.read_frontmatter_provenance(plain.read_text(encoding="utf-8"))

    assert human_prov["trust"] == "user"
    assert quarantined_prov["trust"] == "foreign"
    assert plain_prov["trust"] == "model"

    # Bodies (below frontmatter) are byte-identical to before migration.
    for page, before_body in before_bodies.items():
        after_body = provenance._FRONTMATTER_RE.sub("", page.read_text(encoding="utf-8"), count=1)
        assert after_body == before_body


def test_migration_is_idempotent_second_run_is_noop(wiki):
    human, quarantined, plain = _seed_three_pages(wiki)

    migrate = _load_migrate()
    migrate.main([])
    first_texts = {p: p.read_text(encoding="utf-8") for p in (human, quarantined, plain)}

    rc = migrate.main([])
    assert rc == 0

    for page, text_before in first_texts.items():
        assert page.read_text(encoding="utf-8") == text_before


def test_migration_no_pages_is_a_clean_noop(wiki):
    migrate = _load_migrate()
    rc = migrate.main([])
    assert rc == 0


def test_migration_skips_dot_prefixed_paths(wiki):
    ren_dir = wiki / ".ren"
    ren_dir.mkdir(parents=True, exist_ok=True)
    dotfile = ren_dir / "state.md"
    dotfile.write_text("---\ntitle: state\n---\nnot a wiki page\n", encoding="utf-8")

    migrate = _load_migrate()
    rc = migrate.main([])
    assert rc == 0

    text = dotfile.read_text(encoding="utf-8")
    assert "ren_trust" not in text
