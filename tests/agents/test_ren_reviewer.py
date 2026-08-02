from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
AGENT = REPO / "agents" / "ren-reviewer.md"


def test_agent_file_exists():
    assert AGENT.is_file()


def test_frontmatter_has_name_description_tools():
    text = AGENT.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    fm = text.split("---", 2)[1]
    assert "name: ren-reviewer" in fm
    assert "description:" in fm
    assert "tools:" in fm
    assert "Write" not in fm.split("tools:", 1)[1].splitlines()[0]  # read-only reviewer


def test_body_carries_the_five_scope_rules():
    body = AGENT.read_text(encoding="utf-8")
    for needle in (
        "runnable repro",
        "PLAUSIBLE",
        "spec",          # scope conformance vs spec/plan item
        "TDD",
        "report format",
    ):
        assert needle in body, f"missing scope rule marker: {needle}"


def test_agents_dir_is_shippable():
    from tests.test_repo_hygiene import SHIPPABLE_DIRS
    assert "agents" in SHIPPABLE_DIRS
