"""Installed-plugin-runtime integration test — the C1+C2 acceptance gate (ADR-030).

This is the test that would have caught the V1.0 NO-SHIP blockers C1 (wake-up hook
read the wrong wiki path in production) and C2 (the Activity Feed was dead because
`feed/` was unreachable from the packaged plugin). The 659 prior tests missed both
because they inject SF_WIKI_ROOT, use FeedFake, and run from the dev tree — so the
installed-plugin runtime was never exercised.

Here we materialize a fake $CLAUDE_PLUGIN_ROOT with REAL files in the post-Crucible
layout, run sf-wake-up.py as a SUBPROCESS with a from-scratch (scrubbed) environment,
and assert against the hook's observable output:

    C1 — additionalContext loads the wiki from the home-default path
         ($HOME/.startup-framework/wiki) when no wiki-root env vars are set.
    C2 — the Activity Feed block renders, proving `from feed import …` resolved
         (the ImportError branch produces nothing).

Plus two permanent negative-control "teeth" tests so the guarantee lives in CI, not
in a one-time manual check.

The matching wiki-decisions/030 ADR ratifies the pattern. The one-time FAIL-on-pre-fix
proof (baseline buggy hook → both assertions fail) is recorded there.
"""

from __future__ import annotations

from pathlib import Path

# Contract strings asserted below. Declared explicitly here so the test reads as a
# spec; they mirror hooks/wake-up/lib (master-index header), feed/reader.py
# (_format_header), and sf-wake-up.py (the graceful-degrade log line). Dash-free
# substrings are used where the production string contains an em-dash, to avoid
# any unicode-literal drift in the assertion.
MASTER_INDEX_HEADER = "Master wiki index"
FEED_ACTIVITY_MARKER = "recent friend activity"  # from "Activity Feed — recent friend activity"
FEED_UNAVAILABLE_LOG = "feed module unavailable; skipping feed integration"


# --- The headline acceptance gate: C1 + C2 in ONE invocation ----------------


def test_installed_runtime_wiki_and_feed_both_live(make_plugin_root, make_home, run_wake_up):
    """ADR-030 headline. One realistic CC-style invocation (CLAUDE_PLUGIN_ROOT set,
    no SF_WIKI_ROOT / CLAUDE_PLUGIN_OPTION_WIKIROOT) must bring BOTH features alive."""
    plugin_root = make_plugin_root(include_feed=True)
    home = make_home(with_wiki=True, with_feed_clone=True)

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

    # C2 — feed imported + rendered (the ImportError branch produces nothing).
    assert FEED_ACTIVITY_MARKER in run.context, (
        "C2 REGRESSION: Activity Feed block absent — `from feed import` likely failed.\n"
        f"log={run.log!r}\ncontext={run.context!r}"
    )
    assert "friend-b" in run.context, (
        "C2 REGRESSION: seeded friend handle missing from the rendered feed block.\n"
        f"context={run.context!r}"
    )

    # Diagnostic (not load-bearing): the graceful-degrade path was NOT taken.
    assert FEED_UNAVAILABLE_LOG not in run.log, (
        "feed import silently degraded despite feed/ being present.\n"
        f"log={run.log!r}"
    )


# --- C2 variant: hook self-locates the plugin root via parents[2] -----------


def test_feed_resolves_without_plugin_root_env(make_plugin_root, make_home, run_wake_up):
    """When Claude Code does NOT set $CLAUDE_PLUGIN_ROOT, the hook falls back to
    Path(__file__).resolve().parents[2] and feed still resolves."""
    plugin_root = make_plugin_root(include_feed=True)
    home = make_home(with_wiki=True, with_feed_clone=True)

    run = run_wake_up(plugin_root=plugin_root, home=home, set_plugin_root_env=False)

    assert run.returncode == 0, f"hook exited {run.returncode}; stderr:\n{run.stderr}"
    assert FEED_ACTIVITY_MARKER in run.context, (
        "parents[2] fallback failed to make feed importable.\n"
        f"log={run.log!r}\ncontext={run.context!r}"
    )
    assert "friend-b" in run.context
    assert FEED_UNAVAILABLE_LOG not in run.log


# --- C1 variant: the middle fallback tier (CLAUDE_PLUGIN_OPTION_WIKIROOT) ----


def test_wiki_resolves_via_plugin_option_wikiroot(
    make_plugin_root, make_home, run_wake_up, tmp_path: Path
):
    """Proves the middle wiki-root tier: with no SF_WIKI_ROOT but a set
    CLAUDE_PLUGIN_OPTION_WIKIROOT (the userConfig var the buggy Python layer
    ignored entirely), the hook loads the wiki from that path."""
    tier2_sentinel = "TIER2-OPTION-WIKIROOT-SENTINEL-c9d2"
    opt_wiki = tmp_path / "opt-wiki"
    opt_wiki.mkdir()
    (opt_wiki / "index.md").write_text(
        f"# Option Wiki\n\n{tier2_sentinel}\n", encoding="utf-8"
    )

    plugin_root = make_plugin_root(include_feed=True)
    # Home has NO default wiki, so a loaded wiki can ONLY come from the option path.
    home = make_home(with_wiki=False, with_feed_clone=False)

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


# --- Permanent negative control #1: C2 teeth (feed/ missing) ----------------


def test_no_feed_degrades_gracefully(make_plugin_root, make_home, run_wake_up):
    """If feed/ is missing from the package (the C2 condition), the hook must
    degrade GRACEFULLY — no feed block, the explicit graceful-degrade log line, and
    rc==0 (not a swallowed different error) — while the wiki still loads.

    This is the C2 teeth: it proves the headline test's feed assertion would bite
    if feed/ ever went missing again, AND that the degradation is intentional."""
    plugin_root = make_plugin_root(include_feed=False)  # the bug condition
    home = make_home(with_wiki=True, with_feed_clone=True)

    run = run_wake_up(plugin_root=plugin_root, home=home)

    assert run.returncode == 0, (
        f"hook did NOT exit 0 on missing feed/ — degradation not graceful.\n"
        f"stderr:\n{run.stderr}"
    )
    # Feed block absent...
    assert FEED_ACTIVITY_MARKER not in run.context
    assert "friend-b" not in run.context
    # ...but it degraded via the documented ImportError path (not some other error)...
    assert FEED_UNAVAILABLE_LOG in run.log, (
        "missing feed/ did not log the expected graceful-degrade signal — it may be "
        "failing some OTHER way.\n"
        f"log={run.log!r}"
    )
    # ...and the wiki still loads (feed failure is isolated from wiki injection).
    assert MASTER_INDEX_HEADER in run.context
    assert home.sentinel in run.context


# --- Permanent negative control #2: C1 teeth (no wiki anywhere) -------------


def test_no_wiki_yields_no_context(make_plugin_root, make_home, run_wake_up):
    """If no wiki exists at the home default (and no identity → no feed), the hook
    emits empty context and rc==0. Proves the headline C1 assertion discriminates
    (it is not vacuously always-true)."""
    plugin_root = make_plugin_root(include_feed=True)
    home = make_home(with_wiki=False, with_feed_clone=False)

    run = run_wake_up(plugin_root=plugin_root, home=home)

    assert run.returncode == 0, f"hook exited {run.returncode}; stderr:\n{run.stderr}"
    assert MASTER_INDEX_HEADER not in run.context
    assert FEED_ACTIVITY_MARKER not in run.context
    assert run.context == "", (
        f"expected fully-empty context with no wiki + no identity; got {run.context!r}"
    )
