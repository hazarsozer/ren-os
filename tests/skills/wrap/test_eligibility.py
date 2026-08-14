"""
Tests for skills.wrap.lib._eligible_update_targets — the mechanical eligibility
set from wake-up + recall logs (Task 3).

Run with: uv run pytest tests/skills/wrap/test_eligibility.py -v
"""

from __future__ import annotations

import pytest

from lib.instrument import collect
from lib.ren_paths import wiki_root
from skills.wrap.lib import _eligible_update_targets


@pytest.fixture
def tmp_wiki(monkeypatch, tmp_path):
    """Fixture that points ren_paths.wiki_root() at a tmp dir.

    Reuses the isolation pattern from test_wrap_flow.py's wiki fixture."""
    # Clear all path env vars to ensure wiki_root() picks up from REN_FRAMEWORK_ROOT
    for var in (
        "REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT",
        "CLAUDE_PLUGIN_OPTION_DEVROOT",
    ):
        monkeypatch.delenv(var, raising=False)

    # Set REN_FRAMEWORK_ROOT to tmp_path so state_dir() and wiki_root() land in tmp
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def isolated_metrics(tmp_wiki):
    """Fixture that ensures collect state is isolated to tmp_wiki.

    Since collect.read/record use ren_paths.state_dir() which depends on
    REN_FRAMEWORK_ROOT (already isolated by tmp_wiki), metrics are
    automatically isolated. This fixture is a no-op but named for clarity."""
    return tmp_wiki


def test_eligibility_unions_surface_and_fetch_for_session(tmp_wiki, isolated_metrics):
    """Eligibility set unions pages from wake-up surface and L3 fetch for this session."""
    (tmp_wiki / "projects/p/knowledge").mkdir(parents=True)
    (tmp_wiki / "projects/p/knowledge/a.md").write_text("x", encoding="utf-8")
    (tmp_wiki / "identity.md").write_text("x", encoding="utf-8")

    collect.record(collect.KIND_WAKEUP_SURFACE,
                   {"pages": ["projects/p/knowledge/a.md", "gone.md"], "session": "s1"})
    collect.record(collect.KIND_L3_FETCH,
                   {"page": "identity.md", "query": "q", "session": "s1"})
    collect.record(collect.KIND_L3_FETCH,
                   {"page": "projects/p/knowledge/a.md", "query": "q", "session": "OTHER"})

    got = _eligible_update_targets("s1")
    # gone.md dropped (not on disk); OTHER session's fetch excluded; sorted+deduped
    assert got == ("identity.md", "projects/p/knowledge/a.md")


def test_eligibility_empty_when_nothing_logged(tmp_wiki, isolated_metrics):
    """Empty eligibility set when nothing was logged for this session."""
    assert _eligible_update_targets("s-none") == ()


def test_eligibility_matches_harness_session_id_not_just_wrap_label(
    tmp_wiki, isolated_metrics
):
    """#C1: the wake-up hook logs `wakeup_surface` under the HARNESS
    `session_id`, while wrap's `session` argument is a model-supplied LABEL.
    Matching on the label alone found nothing in production and made the whole
    update path inert. The harness id is recovered from the pairing file the
    same hook stamps."""
    from lib.instrument import calibration

    (tmp_wiki / "projects/p/knowledge").mkdir(parents=True)
    (tmp_wiki / "projects/p/knowledge/a.md").write_text("x", encoding="utf-8")

    # Wake-up: logs surfaces + stamps the pairing file, both under the harness id.
    calibration.persist_last_injection("injected context", "harness-abc-123")
    collect.record(
        collect.KIND_WAKEUP_SURFACE,
        {"pages": ["projects/p/knowledge/a.md"], "session": "harness-abc-123"},
    )

    # Wrap is invoked with a completely different, model-supplied label.
    assert _eligible_update_targets("my-wrap-label") == ("projects/p/knowledge/a.md",)


def test_eligibility_ignores_other_harness_sessions(tmp_wiki, isolated_metrics):
    """Only THIS session's ids count — a surface logged under some other
    harness id stays out of the eligibility set."""
    from lib.instrument import calibration

    (tmp_wiki / "projects/p/knowledge").mkdir(parents=True)
    (tmp_wiki / "projects/p/knowledge/a.md").write_text("x", encoding="utf-8")

    calibration.persist_last_injection("injected context", "harness-abc-123")
    collect.record(
        collect.KIND_WAKEUP_SURFACE,
        {"pages": ["projects/p/knowledge/a.md"], "session": "harness-OTHER"},
    )

    assert _eligible_update_targets("my-wrap-label") == ()
