"""
End-to-end test for the foreign-remint-1 migration (issue #22).

Before #22, `trust_class` minted `ren_trust: "foreign"` for every
`producer="ingest"` write — including knowledge pages drafted by RenOS's own
subagents from the friend's own repo and applied through the queue. The
foreign stamp holds an L2 map out of wake-up unconditionally (spec §4.5),
so those wikis wake up with no map at all for their own ingested projects.

This migration restamps `ren_trust: "foreign"` → `"model"` for pages whose
`ren_writer` is a known non-human class (the mis-minted population — every
existing foreign stamp was self-minted by the ingest door or backfilled by
trust-backfill-1). Pages with `ren_writer: "human"` or no writer at all keep
their stamp (conservative: unknown provenance stays foreign). Quarantine
banners are untouched — a reminted page still stays out of context until
released.

Run with: uv run pytest tests/migrations/test_foreign_remint_1.py -v
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from lib.memory import provenance, quarantine
from lib.ren_paths import wiki_root

_MIGRATE_PATH = (
    Path(__file__).resolve().parents[2] / "migrations" / "foreign-remint-1" / "migrate.py"
)


def _load_migrate():
    spec = importlib.util.spec_from_file_location("_foreign_remint_1_migrate", _MIGRATE_PATH)
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


def _foreign_llm_page_text() -> str:
    body = quarantine.mark("Distilled knowledge from the friend's own repo.\n")
    return (
        '---\n'
        'ren_write_id: "w-01H0000000000000000000011"\n'
        'ren_ts: "2026-07-31T00:00:00Z"\n'
        'ren_writer: "llm-auto"\n'
        'ren_op: "ADD"\n'
        'ren_trust: "foreign"\n'
        '---\n'
    ) + body


def _foreign_no_writer_page_text() -> str:
    return (
        '---\n'
        'ren_trust: "foreign"\n'
        '---\n'
        'Content of genuinely unknown provenance.\n'
    )


def _model_page_text() -> str:
    return (
        '---\n'
        'ren_write_id: "w-01H0000000000000000000012"\n'
        'ren_ts: "2026-07-31T00:00:00Z"\n'
        'ren_writer: "llm-auto"\n'
        'ren_op: "ADD"\n'
        'ren_trust: "model"\n'
        '---\n'
        'Already-model body.\n'
    )


def test_remint_restamps_llm_written_foreign_pages_to_model(wiki):
    page = wiki / "projects" / "flux" / "map.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(_foreign_llm_page_text(), encoding="utf-8")
    before_body = provenance._FRONTMATTER_RE.sub("", page.read_text(encoding="utf-8"), count=1)

    migrate = _load_migrate()
    rc = migrate.main([])
    assert rc == 0

    text = page.read_text(encoding="utf-8")
    prov = provenance.read_frontmatter_provenance(text)
    assert prov["trust"] == "model"
    # Quarantine banner and the rest of the body are byte-for-byte untouched.
    after_body = provenance._FRONTMATTER_RE.sub("", text, count=1)
    assert after_body == before_body
    assert quarantine.is_quarantined(text)


def test_remint_leaves_writerless_foreign_pages_alone(wiki):
    page = wiki / "imported" / "external.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(_foreign_no_writer_page_text(), encoding="utf-8")

    migrate = _load_migrate()
    rc = migrate.main([])
    assert rc == 0

    # read_frontmatter_provenance returns None for a page with no write_id,
    # so assert on the raw text: the stamp must be byte-for-byte untouched.
    assert 'ren_trust: "foreign"' in page.read_text(encoding="utf-8")


def test_remint_is_idempotent_and_skips_non_foreign_pages(wiki):
    foreign = wiki / "projects" / "flux" / "map.md"
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_text(_foreign_llm_page_text(), encoding="utf-8")
    model = wiki / "projects" / "flux" / "notes.md"
    model.write_text(_model_page_text(), encoding="utf-8")

    migrate = _load_migrate()
    migrate.main([])
    first_texts = {p: p.read_text(encoding="utf-8") for p in (foreign, model)}

    rc = migrate.main([])
    assert rc == 0
    for page, text_before in first_texts.items():
        assert page.read_text(encoding="utf-8") == text_before


def test_remint_check_mode_writes_nothing(wiki):
    page = wiki / "projects" / "flux" / "map.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(_foreign_llm_page_text(), encoding="utf-8")

    migrate = _load_migrate()
    rc = migrate.main(["--check"])
    assert rc == 0

    prov = provenance.read_frontmatter_provenance(page.read_text(encoding="utf-8"))
    assert prov["trust"] == "foreign"


def test_remint_skips_dot_prefixed_paths(wiki):
    dotfile = wiki / ".ren" / "state.md"
    dotfile.parent.mkdir(parents=True, exist_ok=True)
    dotfile.write_text(_foreign_llm_page_text(), encoding="utf-8")

    migrate = _load_migrate()
    rc = migrate.main([])
    assert rc == 0

    prov = provenance.read_frontmatter_provenance(dotfile.read_text(encoding="utf-8"))
    assert prov["trust"] == "foreign"


def _foreign_llm_page_text_variant(trust_line: str) -> str:
    return (
        '---\n'
        'ren_write_id: "w-01H0000000000000000000013"\n'
        'ren_ts: "2026-07-31T00:00:00Z"\n'
        'ren_writer: "llm-auto"\n'
        'ren_op: "ADD"\n'
        f'{trust_line}\n'
        '---\n'
        'Body.\n'
    )


@pytest.mark.parametrize(
    "trust_line",
    ["ren_trust: foreign", "ren_trust: 'foreign'", 'ren_trust:  "foreign" '],
    ids=["unquoted", "single-quoted", "extra-spaces"],
)
def test_remint_handles_yaml_trust_line_variants_and_converges(wiki, trust_line):
    # Dogfood-2 M1: _should_remint parses YAML tolerantly, but the rewrite
    # regex only matched `ren_trust: "foreign"` exactly — variant spellings
    # were reported "reminted" every run while the file never changed.
    page = wiki / "projects" / "flux" / "map.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(_foreign_llm_page_text_variant(trust_line), encoding="utf-8")

    migrate = _load_migrate()
    assert migrate.main([]) == 0

    text = page.read_text(encoding="utf-8")
    assert 'ren_trust: "model"' in text
    assert "foreign" not in text
    assert provenance.read_frontmatter_provenance(text)["trust"] == "model"

    # Second run is a no-op (convergent).
    assert migrate.main([]) == 0
    assert page.read_text(encoding="utf-8") == text
