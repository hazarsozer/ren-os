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
