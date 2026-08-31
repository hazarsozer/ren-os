"""Unknown is an outcome (spec 2026-08-22).

Companion to `test_fail_open_declared.py`. That audit pins "a broad handler
conceals whether it failed"; this one pins "a reporting surface conceals
whether it looked".

Honest floor: the registry is hand-maintained. A genuinely new reporting
surface that nobody registers is invisible to this audit — see the spec's
§7. What IS enforced is that every registered entry resolves, can signal
blindness, and actually does so when blinded.
"""

from __future__ import annotations

import importlib

from lib.reporting import REPORTING_SURFACES, Unknown


def test_unknown_carries_a_reason():
    u = Unknown(reason="wiki root is not a directory")
    assert u.reason == "wiki root is not a directory"


def test_unknown_is_not_a_falsy_collection():
    """The whole point: a caller that forgets to handle Unknown must break
    loudly, not render it as an empty result."""
    u = Unknown(reason="x")
    assert not isinstance(u, (list, dict, str, tuple))


def test_registry_is_not_empty():
    assert len(REPORTING_SURFACES) >= 4


def test_registry_resolves():
    """Every registered entry names a module and function that exist. This
    is what stops the registry rotting into names that were renamed away."""
    for surface in REPORTING_SURFACES:
        module = importlib.import_module(surface.module)
        assert hasattr(module, surface.function), (
            f"{surface.module}.{surface.function} does not exist"
        )


import ast
import inspect
import textwrap

import pytest


def _constructs_unknown(func) -> bool:
    """True when the function's own source constructs `Unknown(...)`.

    AST rather than a string search: a docstring mentioning Unknown must not
    count as signalling it.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "Unknown":
                return True
    return False


@pytest.mark.parametrize(
    "surface", REPORTING_SURFACES, ids=lambda s: f"{s.module}.{s.function}"
)
def test_surface_can_signal_unknown(surface):
    """Every registered surface has a code path that constructs Unknown.

    Necessary but not sufficient — a dead branch satisfies this. The
    blind-condition test below is the load-bearing one.
    """
    module = importlib.import_module(surface.module)
    func = getattr(module, surface.function)
    assert _constructs_unknown(func), (
        f"{surface.module}.{surface.function} is registered as a reporting "
        f"surface but never constructs Unknown. Blind when: {surface.blind_when}"
    )


def test_sweep_signals_when_blind(tmp_path):
    module = importlib.import_module("skills.wiki-health.lib")
    result = module.sweep(wiki_root=tmp_path / "absent")
    assert isinstance(result, Unknown)


def test_gc_stale_envs_signals_when_blind(tmp_path, monkeypatch):
    module = importlib.import_module("skills.update.lib")
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path / "framework"))
    assert isinstance(module.gc_stale_envs(), Unknown)


def test_changelog_digest_signals_when_blind(tmp_path):
    module = importlib.import_module("skills.update.lib")
    result = module.changelog_digest("0.8.3", "0.8.4", tmp_path / "absent.md")
    assert isinstance(result, Unknown)


def test_rerender_all_project_claude_md_signals_when_blind(tmp_path, monkeypatch):
    module = importlib.import_module("skills.update.lib")
    registry = tmp_path / "projects.json"
    registry.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr("lib.ren_paths.projects_registry_path", lambda: registry)
    monkeypatch.setenv("REN_WIKI_ROOT", str(tmp_path / "wiki"))
    assert isinstance(module.rerender_all_project_claude_md(), Unknown)


def test_render_wrap_screen_signals_when_blind():
    """`render_wrap_screen` always returns a rendered str (it's the wrap
    screen itself, never the missing-check channel), so unlike the other
    three surfaces this asserts on the rendered text rather than
    `isinstance(..., Unknown)`: the literal "concept routing blind" phrase
    plus the reason must appear when `concept_routing.blind` is set."""
    module = importlib.import_module("skills.wrap.lib")
    result = {
        "l1_qid": "q-does-not-exist",
        "applied": [], "held": [], "gated_out": [], "refused": [],
        "fail_closed": False,
        "concept_routing": {"blind": "no taxonomy"},
    }
    screen = module.render_wrap_screen(result, session="sess-audit-blind")
    assert "concept routing blind" in screen
    assert "no taxonomy" in screen


def test_every_surface_has_a_blind_test():
    """The registry and this file must not drift apart: adding a surface
    without a blind-condition test is the gap this audit exists to close.

    `covered` is derived from this module's own `globals()` rather than a
    hardcoded set, so deleting a blind test — not just forgetting to add
    one — makes this fail too."""
    missing = sorted(
        surface.function
        for surface in REPORTING_SURFACES
        if f"test_{surface.function}_signals_when_blind" not in globals()
    )
    assert not missing, (
        f"registered surfaces with no test named "
        f"test_<function>_signals_when_blind: {missing}"
    )
