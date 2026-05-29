"""Installed-plugin-runtime integration tests (ADR-030).

This tier deliberately does NOT use the FeedFake harness or inject SF_WIKI_ROOT —
that harness is exactly what masked C1 (wrong wiki path) and C2 (dead feed import)
behind 659 green tests. Here we materialize a fake $CLAUDE_PLUGIN_ROOT with real
files in the post-Crucible layout, run sf-wake-up.py as a subprocess with a clean
environment, and assert both load-bearing features come alive.
"""
