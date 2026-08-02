from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
AGENT = REPO / "agents" / "ren-wiki-lint.md"


def test_agent_file_exists():
    assert AGENT.is_file()


def test_frontmatter_has_name_description_tools():
    text = AGENT.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    fm = text.split("---", 2)[1]
    assert "name: ren-wiki-lint" in fm
    assert "description:" in fm
    assert "tools:" in fm


def test_body_names_the_engine_one_liner():
    body = AGENT.read_text(encoding="utf-8")
    assert "run_incremental_lint" in body


def test_body_names_the_hard_exclusions():
    body = AGENT.read_text(encoding="utf-8")
    for needle in ("raw/", "log.md", "instruction-plane"):
        assert needle in body, f"missing hard exclusion marker: {needle}"


def test_body_names_the_suggestions_handoff():
    body = AGENT.read_text(encoding="utf-8")
    assert "suggestion" in body.lower()


def test_body_names_full_flag():
    body = AGENT.read_text(encoding="utf-8")
    assert "--full" in body
