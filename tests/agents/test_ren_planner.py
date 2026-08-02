from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
AGENT = REPO / "agents" / "ren-planner.md"


def test_agent_file_exists():
    assert AGENT.is_file()


def test_frontmatter_has_name_description_tools():
    text = AGENT.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    fm = text.split("---", 2)[1]
    assert "name: ren-planner" in fm
    assert "description:" in fm
    tools_line = next(line for line in fm.splitlines() if line.strip().startswith("tools:"))
    assert "Write" in tools_line  # ren-planner writes brief files, unlike ren-reviewer


def test_body_carries_the_decompose_markers():
    body = AGENT.read_text(encoding="utf-8")
    for needle in (
        "atomic",
        "one clean subagent context",
        "Interfaces",
        "wiki pointers",
        "verification",
        "briefs",
    ):
        assert needle in body, f"missing body marker: {needle}"


def test_body_constrains_writes_to_briefs_dir_and_forbids_wiki_repo_writes():
    body = AGENT.read_text(encoding="utf-8")
    assert "briefs directory" in body
    assert "Never write" in body or "never write" in body.lower()
    assert "wiki" in body.lower()


def test_agents_dir_is_shippable():
    from tests.test_repo_hygiene import SHIPPABLE_DIRS
    assert "agents" in SHIPPABLE_DIRS
