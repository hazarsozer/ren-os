import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "hooks" / "wake-up"))

from wakeup import DOCTRINE_POINTER  # noqa: E402
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
        stray occurrence."""
        for sp in (True, False):
            card = render_doctrine_card(sp)
            assert "open-work ledger line is closed" in card

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
            "superpowers:using-git-worktrees",
            "superpowers:writing-plans",
            "superpowers:subagent-driven-development",
            "superpowers:test-driven-development",
            "superpowers:finishing-a-development-branch",
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
        edits. Asserts the presence and order of: section header, seven
        numbered gates, and the red-flags table header. Uses successive
        .index() calls to verify in-order appearance (house style: structural
        stability, not verbatim-text pinning)."""
        for sp in (True, False):
            card = render_doctrine_card(sp)

            # The exact section header line
            assert card.index("## How we work (execution doctrine)") >= 0

            # Seven numbered gate leads, in order (substring matching the
            # opener). Each .index() call will raise if not found; successive
            # calls verify order (latter index > earlier index).
            idx_brainstorm = card.index("1. **Brainstorm gate.**")
            idx_isolate = card.index("2. **Isolate & plan.**")
            idx_decompose = card.index("3. **Decompose.**")
            idx_dispatch = card.index("4. **Dispatch.**")
            idx_per_task = card.index("5. **Per-task review.**")
            idx_review = card.index("6. **Review gate.**")
            idx_finish = card.index("7. **Finish.**")

            assert (
                idx_brainstorm
                < idx_isolate
                < idx_decompose
                < idx_dispatch
                < idx_per_task
                < idx_review
                < idx_finish
            ), "Gate leads are out of order or missing"

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
            assert idx_table_header > idx_finish, "Table header appears before finish gate"

    def test_compact_card_survives_band_low_budget_intact(self):
        """The head-preserving fallback must fit the band-low budget whole
        (650 tokens x 1.5 chars/token = 975 chars), header and all five gate
        leads included — otherwise it would itself get tail-cut and
        reintroduce the bug."""
        import sys
        sys.path.insert(0, str(REPO / "hooks" / "wake-up"))
        from wakeup import DOCTRINE_BUDGET, truncate_text_to_tokens  # noqa: E402

        compact = render_doctrine_card_compact()
        assert truncate_text_to_tokens(compact, DOCTRINE_BUDGET, 1.5) == compact
        assert compact.startswith(SECTION_DOCTRINE)
        for lead in (
            "1. **Brainstorm gate.**",
            "2. **Isolate & plan.**",
            "3. **Decompose.**",
            "4. **Dispatch.**",
            "5. **Per-task review**",
        ):
            assert lead in compact, lead
        assert "superpowers:writing-plans" in compact
        assert "superpowers:subagent-driven-development" in compact

    def test_compact_card_agents_ship(self):
        import re
        for agent_name in re.findall(r"`([a-z-]+)` agent", render_doctrine_card_compact()):
            assert (REPO / "agents" / f"{agent_name}.md").is_file(), agent_name

    def test_card_keeps_margin_under_raised_budget(self):
        """Both variants must stay >=150 chars clear of the 650x4.0 char cap, so
        a small future wording edit cannot silently push the card over."""
        import sys
        sys.path.insert(0, str(REPO / "hooks" / "wake-up"))
        from wakeup import DOCTRINE_BUDGET  # noqa: E402

        assert DOCTRINE_BUDGET == 650
        cap = DOCTRINE_BUDGET * 4.0 - 150
        for sp in (True, False):
            assert len(render_doctrine_card(sp)) <= cap


_PIPELINE_PHASES = [
    "brainstorm", "worktree", "plan", "decompose", "per-task review", "review gate", "finish",
]
_SKILL_NAMES_FULL = [
    "superpowers:brainstorming",
    "superpowers:using-git-worktrees",
    "superpowers:writing-plans",
    "superpowers:subagent-driven-development",
    "superpowers:test-driven-development",
    "superpowers:finishing-a-development-branch",
]
_MODEL_NAMES = ["sonnet", "haiku", "opus", "fable", "claude-"]


def test_full_card_names_every_phase_and_skill():
    card = render_doctrine_card(superpowers=True)
    low = card.lower()
    for phase in _PIPELINE_PHASES:
        assert phase in low, phase
    for skill in _SKILL_NAMES_FULL:
        assert skill in card, skill
    assert "model-classes.md" in card          # routing pointer
    assert "per-task" in low                    # review before chaining


def test_fallback_card_names_phases_without_superpowers_refs_breaking():
    card = render_doctrine_card(superpowers=False)
    low = card.lower()
    for phase in _PIPELINE_PHASES:
        assert phase in low, phase
    assert "model-classes.md" in card
    assert "recommended companion" in low       # footer still points at superpowers


def test_compact_card_keeps_skill_names_and_routing():
    card = render_doctrine_card_compact()
    assert "superpowers:writing-plans" in card
    assert "superpowers:subagent-driven-development" in card
    assert "model-classes.md" in card
    assert len(card) <= 1200  # head-preserving fallback must stay small


def test_no_model_names_anywhere():
    for card in (
        render_doctrine_card(True),
        render_doctrine_card(False),
        render_doctrine_card_compact(),
    ):
        low = card.lower()
        for name in _MODEL_NAMES:
            assert name not in low, name


def test_full_card_fits_doctrine_budget_at_default_ratio():
    from wakeup import DOCTRINE_BUDGET, CHARS_PER_TOKEN
    card = render_doctrine_card(superpowers=True)
    assert len(card) <= DOCTRINE_BUDGET * CHARS_PER_TOKEN


def test_doctrine_pointer_is_a_path():
    assert "doctrine_card.py" in DOCTRINE_POINTER
