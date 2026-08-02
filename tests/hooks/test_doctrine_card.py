import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "hooks" / "wake-up"))

from wakeup.doctrine_card import (  # noqa: E402
    SECTION_DOCTRINE,
    render_doctrine_card,
    render_doctrine_card_compact,
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

    def test_decompose_gate_spawns_ren_planner(self):
        for sp in (True, False):
            card = render_doctrine_card(sp)
            assert "`ren-planner` agent" in card

    def test_review_gate_requires_open_work_closure(self):
        """Pin the actual phrase: a loose `"closed" in card` would match any
        stray occurrence, and the closure rule must not read as an either/or
        (a model can satisfy "closed OR added" by adding a line and stopping)."""
        for sp in (True, False):
            card = render_doctrine_card(sp)
            assert "open-work ledger is closed" in card
            assert "if it has no line, add one before you claim done" in card

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
    @pytest.mark.parametrize("ratio", [4.0, 12.0])
    def test_card_never_truncates_at_exact_budget(self, ratio):
        """Neither card variant may truncate at or above the safe-default
        calibration ratio. This guards against a footgun: if a future edit
        pushes the card over budget, the slop-tolerant compose test would still
        pass while the card truncates silently."""
        import sys
        sys.path.insert(0, str(REPO / "hooks" / "wake-up"))
        from wakeup import DOCTRINE_BUDGET, truncate_text_to_tokens  # noqa: E402

        for sp in (True, False):
            card = render_doctrine_card(sp)
            truncated = truncate_text_to_tokens(card, DOCTRINE_BUDGET, ratio)
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

            # v2 additions, pinned to their owning gate.
            idx_planner = card.index("`ren-planner` agent")
            idx_ledger = card.index("open-work")
            assert idx_decompose < idx_planner < idx_dispatch, (
                "ren-planner must be named inside the decompose gate"
            )
            assert idx_ledger > idx_review, (
                "the ledger-closure sentence must live in the review gate"
            )

            # The table header for Red flags section (stable structural marker).
            idx_table_header = card.index("| Thought | Reality |")
            assert idx_table_header > idx_review, "Table header appears before review gate"

    def test_compact_card_survives_band_low_budget_intact(self):
        """The head-preserving fallback must fit the band-low budget whole
        (500 tokens x 1.5 chars/token), header and all four gate leads included
        — otherwise it would itself get tail-cut and reintroduce the bug."""
        import sys
        sys.path.insert(0, str(REPO / "hooks" / "wake-up"))
        from wakeup import DOCTRINE_BUDGET, truncate_text_to_tokens  # noqa: E402

        compact = render_doctrine_card_compact()
        assert truncate_text_to_tokens(compact, DOCTRINE_BUDGET, 1.5) == compact
        assert compact.startswith(SECTION_DOCTRINE)
        for lead in (
            "1. **Brainstorm gate.**",
            "2. **Decompose.**",
            "3. **Dispatch.**",
            "4. **Review gate.**",
        ):
            assert lead in compact, lead
        assert "superpowers:" not in compact  # variant-agnostic, so no skill ids

    def test_compact_card_agents_ship(self):
        import re
        for agent_name in re.findall(r"`([a-z-]+)` agent", render_doctrine_card_compact()):
            assert (REPO / "agents" / f"{agent_name}.md").is_file(), agent_name

    def test_card_keeps_margin_under_raised_budget(self):
        """Both variants must stay >=150 chars clear of the 500x4.0 char cap, so
        a small future wording edit cannot silently push the card over."""
        import sys
        sys.path.insert(0, str(REPO / "hooks" / "wake-up"))
        from wakeup import DOCTRINE_BUDGET  # noqa: E402

        assert DOCTRINE_BUDGET == 500
        cap = DOCTRINE_BUDGET * 4.0 - 150
        for sp in (True, False):
            assert len(render_doctrine_card(sp)) <= cap
