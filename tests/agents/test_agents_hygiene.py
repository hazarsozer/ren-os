"""
Generalized agents hygiene lint (Task 4, RenOS 0.6.5): every shipped agent
in agents/*.md must pass this, not just ren-wiki-lint. Parametrized over
every agent file on disk so a new agent automatically inherits the check.
"""
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO / "agents"
AGENT_FILES = sorted(AGENTS_DIR.glob("*.md"))


def _frontmatter(text: str) -> str:
    assert text.startswith("---\n"), "agent file must start with YAML frontmatter"
    return text.split("---", 2)[1]


@pytest.mark.parametrize("path", AGENT_FILES, ids=lambda p: p.stem)
def test_frontmatter_has_name_description_tools(path):
    fm = _frontmatter(path.read_text(encoding="utf-8"))
    assert "name:" in fm
    assert "description:" in fm
    assert "tools:" in fm


@pytest.mark.parametrize("path", AGENT_FILES, ids=lambda p: p.stem)
def test_name_equals_filename_stem(path):
    fm = _frontmatter(path.read_text(encoding="utf-8"))
    name_line = next(line for line in fm.splitlines() if line.strip().startswith("name:"))
    name = name_line.split(":", 1)[1].strip()
    assert name == path.stem, f"frontmatter name {name!r} != filename stem {path.stem!r}"


@pytest.mark.parametrize("path", AGENT_FILES, ids=lambda p: p.stem)
def test_name_starts_with_ren_prefix(path):
    assert path.stem.startswith("ren-"), f"agent name {path.stem!r} must start with 'ren-'"


@pytest.mark.parametrize("path", AGENT_FILES, ids=lambda p: p.stem)
def test_no_version_fields(path):
    fm = _frontmatter(path.read_text(encoding="utf-8"))
    keys = [line.split(":", 1)[0].strip() for line in fm.splitlines() if ":" in line]
    assert "version" not in keys, "agent frontmatter must not carry a version field"
    assert "framework_version" not in keys, "agent frontmatter must not carry a framework_version field"


@pytest.mark.parametrize("path", AGENT_FILES, ids=lambda p: p.stem)
def test_read_only_claim_matches_tools(path):
    """If the body claims to be read-only, the tools line must not grant
    write-capable tools — an agent that says 'read-only' but ships Write
    would be a defect a friend could trust incorrectly."""
    text = path.read_text(encoding="utf-8")
    fm = _frontmatter(text)
    body = text.split("---", 2)[2] if text.count("---") >= 2 else ""
    if "read-only" not in body.lower() and "read-only" not in fm.lower():
        pytest.skip("agent does not claim to be read-only")
    tools_line = next(line for line in fm.splitlines() if line.strip().startswith("tools:"))
    for forbidden in ("Write", "Edit", "NotebookEdit"):
        assert forbidden not in tools_line, f"{path.name} claims read-only but tools include {forbidden}"


def test_at_least_one_agent_shipped():
    assert AGENT_FILES, "expected at least one agent file under agents/"
