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


class TestBudgetAndStructure:
    def test_card_never_truncates_at_exact_budget(self):
        """Ensure the card variant measuring ~391 tokens never silently truncates
        when within the 400-token DOCTRINE_BUDGET. This guards against a footgun:
        if a future edit pushes the card over budget, the existing test (with its
        +200 char slop) would still pass while the card truncates silently."""
        import sys
        sys.path.insert(0, str(REPO / "hooks" / "wake-up"))
        from wakeup import DOCTRINE_BUDGET, truncate_text_to_tokens  # noqa: E402

        for sp in (True, False):
            card = render_doctrine_card(sp)
            # Use a calibrated ratio (4.0 chars/token is the safe default).
            # The truncate function preserves the text exactly when it fits.
            truncated = truncate_text_to_tokens(card, DOCTRINE_BUDGET, 4.0)
            assert truncated == card, (
                f"Card variant sp={sp} was truncated despite being within "
                f"DOCTRINE_BUDGET={DOCTRINE_BUDGET}; this suggests an edit "
                f"pushed it over budget silently."
            )

    def test_card_structure_skeleton_pinned(self):
        """Pin the structural skeleton of the doctrine card to catch accidental
        edits. Asserts the presence and order of: section header, four numbered
        gates, and the red-flags table header. Uses successive .index() calls to
        verify in-order appearance (house style: structural stability, not
        verbatim-text pinning)."""
        for sp in (True, False):
            card = render_doctrine_card(sp)

            # The exact section header line
            assert card.index("## How we work (execution doctrine)") >= 0

            # Four numbered gate leads, in order (substring matching the opener).
            # Each .index() call will raise if not found; successive calls
            # verify order (latter index > earlier index).
            idx_brainstorm = card.index("1. **Brainstorm gate.**")
            idx_decompose = card.index("2. **Decompose.**")
            idx_dispatch = card.index("3. **Dispatch.**")
            idx_review = card.index("4. **Review gate.**")

            assert idx_brainstorm < idx_decompose < idx_dispatch < idx_review, (
                "Gate leads are out of order or missing"
            )

            # The table header for Red flags section (stable structural marker).
            idx_table_header = card.index("| Thought | Reality |")
            assert idx_table_header > idx_review, "Table header appears before review gate"
