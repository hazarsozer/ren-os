"""Installed-plugin-runtime integration test — the C1 acceptance gate (ADR-030, ADR-031).

This is the test that would have caught the V1.0 NO-SHIP blocker C1 (wake-up hook
read the wrong wiki path in production). The prior tests missed it because they
inject SF_WIKI_ROOT and run from the dev tree — so the installed-plugin runtime was
never exercised.

Here we materialize a fake $CLAUDE_PLUGIN_ROOT with REAL files in the post-Crucible
layout, run sf-wake-up.py as a SUBPROCESS with a from-scratch (scrubbed) environment,
and assert against the hook's observable output:

    C1 — additionalContext loads the wiki from the home-default path
         ($HOME/.startup-framework/wiki) when no wiki-root env vars are set.
    F1 — with no SF_WIKI_ROOT but a set CLAUDE_PLUGIN_OPTION_WIKIROOT (the userConfig
         var the buggy Python layer ignored entirely), the wiki loads from that path.

Solo-first (ADR-031): the Activity Feed was removed, so the former C2 assertions
(feed block renders) are gone. The wiki injection is now the whole payload.

Plus a permanent negative-control "teeth" test so the C1 guarantee lives in CI.

The matching wiki-decisions/030 ADR ratifies the pattern.
"""

from __future__ import annotations

from pathlib import Path

# Contract string asserted below. Declared explicitly here so the test reads as a
# spec; it mirrors hooks/wake-up/wakeup (master-index header). A dash-free substring
# avoids any unicode-literal drift in the assertion.
MASTER_INDEX_HEADER = "Master wiki index"


# --- The headline acceptance gate: C1 (home-default wiki resolves) ----------


def test_installed_runtime_wiki_loads_from_home_default(make_plugin_root, make_home, run_wake_up):
    """ADR-030 headline. One realistic CC-style invocation (CLAUDE_PLUGIN_ROOT set,
    no SF_WIKI_ROOT / CLAUDE_PLUGIN_OPTION_WIKIROOT) must load the home-default wiki."""
    plugin_root = make_plugin_root()
    home = make_home(with_wiki=True)

    run = run_wake_up(plugin_root=plugin_root, home=home)

    # Never abort the session (ADR-008 invariant).
    assert run.returncode == 0, f"hook exited {run.returncode}; stderr:\n{run.stderr}"

    # C1 — wiki resolved from the home default (not CWD, not skipped).
    assert MASTER_INDEX_HEADER in run.context, (
        "C1 REGRESSION: wiki context absent — home-default wiki not loaded.\n"
        f"context={run.context!r}"
    )
    assert home.sentinel in run.context, (
        "C1 REGRESSION: home wiki sentinel missing from additionalContext.\n"
        f"context={run.context!r}"
    )


# --- Headline F1: the middle fallback tier (CLAUDE_PLUGIN_OPTION_WIKIROOT) ---


def test_wiki_resolves_via_plugin_option_wikiroot(
    make_plugin_root, make_home, run_wake_up, tmp_path: Path
):
    """Headline F1 (Codex): with no SF_WIKI_ROOT but a set CLAUDE_PLUGIN_OPTION_WIKIROOT
    (the userConfig var the buggy Python layer ignored entirely), the hook loads the
    wiki from that path — proving the advertised `wikiRoot` option is honored."""
    tier2_sentinel = "TIER2-OPTION-WIKIROOT-SENTINEL-c9d2"
    opt_wiki = tmp_path / "opt-wiki"
    opt_wiki.mkdir()
    (opt_wiki / "index.md").write_text(
        f"# Option Wiki\n\n{tier2_sentinel}\n", encoding="utf-8"
    )

    plugin_root = make_plugin_root()
    # Home has NO default wiki, so a loaded wiki can ONLY come from the option path.
    home = make_home(with_wiki=False)

    run = run_wake_up(
        plugin_root=plugin_root,
        home=home,
        extra_env={"CLAUDE_PLUGIN_OPTION_WIKIROOT": str(opt_wiki)},
    )

    assert run.returncode == 0, f"hook exited {run.returncode}; stderr:\n{run.stderr}"
    assert MASTER_INDEX_HEADER in run.context
    assert tier2_sentinel in run.context, (
        "CLAUDE_PLUGIN_OPTION_WIKIROOT (middle fallback tier) not honored.\n"
        f"context={run.context!r}"
    )


# --- C1 variant: hook self-runs without $CLAUDE_PLUGIN_ROOT set --------------


def test_wiki_loads_without_plugin_root_env(make_plugin_root, make_home, run_wake_up):
    """When Claude Code does NOT set $CLAUDE_PLUGIN_ROOT, the hook self-locates via
    Path(__file__).resolve().parents[2] and still composes the wiki payload."""
    plugin_root = make_plugin_root()
    home = make_home(with_wiki=True)

    run = run_wake_up(plugin_root=plugin_root, home=home, set_plugin_root_env=False)

    assert run.returncode == 0, f"hook exited {run.returncode}; stderr:\n{run.stderr}"
    assert MASTER_INDEX_HEADER in run.context, (
        "wiki context absent when CLAUDE_PLUGIN_ROOT unset.\n"
        f"log={run.log!r}\ncontext={run.context!r}"
    )
    assert home.sentinel in run.context


# --- Permanent negative control: C1 teeth (no wiki anywhere) ----------------


def test_no_wiki_yields_no_context(make_plugin_root, make_home, run_wake_up):
    """If no wiki exists at the home default, the hook emits empty context and
    rc==0. Proves the headline C1 assertion discriminates (not vacuously true)."""
    plugin_root = make_plugin_root()
    home = make_home(with_wiki=False)

    run = run_wake_up(plugin_root=plugin_root, home=home)

    assert run.returncode == 0, f"hook exited {run.returncode}; stderr:\n{run.stderr}"
    assert MASTER_INDEX_HEADER not in run.context
    assert run.context == "", (
        f"expected fully-empty context with no wiki; got {run.context!r}"
    )
