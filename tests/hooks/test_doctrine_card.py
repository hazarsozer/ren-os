import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "hooks" / "wake-up"))

from wakeup.doctrine_card import (  # noqa: E402
    SECTION_DOCTRINE,
    render_doctrine_card,
    superpowers_installed,
)


class TestCardContent:
    def test_header_constant(self):
        assert SECTION_DOCTRINE == "## How we work (execution doctrine)"

    def test_both_variants_carry_all_four_gates(self):
        for sp in (True, False):
            card = render_doctrine_card(sp)
            assert card.startswith(SECTION_DOCTRINE)
            assert "Brainstorm gate" in card
            assert "Decompose" in card
            assert "Review gate" in card
            assert "ren-reviewer" in card
            assert "Red flags" in card
            assert "MANDATORY" in card  # hard-gate tone, not advisory

    def test_superpowers_variant_delegates_by_skill_name(self):
        card = render_doctrine_card(True)
        assert "superpowers:brainstorming" in card
        assert "superpowers:subagent-driven-development" in card
        assert "superpowers:test-driven-development" in card

    def test_fallback_variant_is_self_contained(self):
        card = render_doctrine_card(False)
        assert "superpowers:" not in card
        assert "recommended companion" in card  # points at /ren:doctor advice

    def test_line_cap_50(self):
        for sp in (True, False):
            assert len(render_doctrine_card(sp).splitlines()) <= 50


class TestDetection:
    def test_absent_cache_means_not_installed(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REN_CLAUDE_DIR", str(tmp_path / ".claude"))
        assert superpowers_installed() is False

    def test_present_cache_dir_detected(self, tmp_path, monkeypatch):
        claude = tmp_path / ".claude"
        (claude / "plugins" / "cache" / "claude-plugins-official" / "superpowers").mkdir(parents=True)
        monkeypatch.setenv("REN_CLAUDE_DIR", str(claude))
        assert superpowers_installed() is True

    def test_cache_path_is_a_file_treated_as_absent(self, tmp_path, monkeypatch):
        claude = tmp_path / ".claude"
        (claude / "plugins" / "cache" / "weird").mkdir(parents=True)
        (claude / "plugins" / "cache" / "weird" / "superpowers").write_text("not a dir")
        monkeypatch.setenv("REN_CLAUDE_DIR", str(claude))
        assert superpowers_installed() is False


class TestReferencesResolve:
    def test_every_agent_named_by_the_card_ships(self):
        import re
        for sp in (True, False):
            card = render_doctrine_card(sp)
            for agent_name in re.findall(r"`([a-z-]+)` agent", card):
                assert (REPO / "agents" / f"{agent_name}.md").is_file(), agent_name

    def test_superpowers_skills_named_by_card_use_known_ids(self):
        card = render_doctrine_card(True)
        known = {
            "superpowers:brainstorming",
            "superpowers:subagent-driven-development",
            "superpowers:test-driven-development",
        }
        import re
        assert set(re.findall(r"superpowers:[a-z-]+", card)) <= known
