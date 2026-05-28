"""
Pytest configuration for feed integration tests.

Registers the `@pytest.mark.integration` marker so callers can filter:

    python3 -m pytest feed/tests/ -m "not integration"   # fast unit suite (~1s)
    python3 -m pytest feed/tests/integration/            # full multi-friend dogfood (~20s)
    python3 -m pytest feed/tests/                        # everything

Marker added separately from the project-wide pytest.ini (which doesn't exist yet —
sf-distribution may add one as part of CI work; this conftest provides the marker
locally for now).
"""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: real-disk integration test (slow; involves git subprocess + multiprocessing)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-mark tests under feed/tests/integration/ as `integration`.

    Note: pytest_collection_modifyitems receives ALL collected items (not just those
    matching this conftest's directory), so we filter by path explicitly to avoid
    marking unit tests in sibling directories.
    """
    integration_path = "feed/tests/integration"
    for item in items:
        if integration_path in str(item.path):
            item.add_marker(pytest.mark.integration)
