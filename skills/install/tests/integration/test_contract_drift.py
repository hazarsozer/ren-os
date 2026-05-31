"""Contract-drift pinning.

Each fake's signature is compared against the real peer's signature. If a peer
ships a real impl with a different signature, these tests fail loudly.

The fakes are the documented assumptions. The peer modules are the truth. When
the two drift, the integration tests catch it AT TEST TIME, not at integration
time on a friend's machine.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from integration.fakes.distribution_fake import DistributionFake
from integration.fakes.lifecycle_fake import LifecycleFake


# ---- distribution ---------------------------------------------------------


def test_distribution_fake_documents_assumed_shape() -> None:
    """Distribution hasn't yet shipped a Python contract. The fake's shape
    is documented as the assumed API; this test exists as a placeholder
    that will fail loudly when distribution-2 ships a real one with a
    different signature."""
    fake = DistributionFake()
    assert hasattr(fake, "read_pinned_registry")
    assert hasattr(fake, "regenerate_licenses_md")
    # When distribution-2 ships:
    #   import distribution
    #   assert inspect.signature(distribution.read_pinned_registry).parameters == ...
    # update this test to import + compare.


# ---- lifecycle ------------------------------------------------------------


def test_lifecycle_fake_documents_assumed_shape() -> None:
    """sf-lifecycle hasn't locked doctor.report() yet. The fake's shape is
    documented as the assumed API; this test will need updating when
    lifecycle-2 ships."""
    fake = LifecycleFake()
    result = fake.doctor_report()
    assert hasattr(result, "passed")
    assert hasattr(result, "checks")
    assert hasattr(result, "warnings")
    assert hasattr(result, "remediation_hints")
    # When lifecycle-2 ships:
    #   import lifecycle  # or wherever they expose doctor
    #   assert inspect.signature(lifecycle.doctor_report).return_annotation == DoctorResult
    # update this test.


# ---- lifecycle library signature drift (real symbols, post-#13/#15/#18/#20) ----


def _load_lifecycle_module(rel_path: str, name: str):
    """Load a lifecycle lib module via path (skill directories have dashes,
    so absolute imports don't work). Registered in sys.modules before
    exec_module so dataclass type resolution works."""
    import importlib.util
    import sys
    repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    full_path = repo_root / rel_path
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, full_path)
    if spec is None or spec.loader is None:
        pytest.skip(f"could not spec {full_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_compose_wake_up_context_signature_drift() -> None:
    """Pin per `hooks/wake-up/wakeup/__init__.py`. The wake-up hook's public
    composition entry. Expected: keyword-only cwd / wiki_root / source /
    max_tokens (the feed `fetch_feed_tail` param was removed with the feed
    module, ADR-031)."""
    module = _load_lifecycle_module(
        "hooks/wake-up/wakeup/__init__.py", "_drift_sf_wake_up_lib",
    )
    sig = inspect.signature(module.compose_wake_up_context)
    params = list(sig.parameters.keys())
    for required in ("cwd", "wiki_root", "source", "max_tokens"):
        assert required in params, (
            f"compose_wake_up_context lost param '{required}'; sig now: {params}"
        )
    assert "fetch_feed_tail" not in params, (
        "compose_wake_up_context should no longer expose the removed feed param"
    )


def test_pin_note_signature_drift() -> None:
    """Pin per `skills/sf-note/lib/__init__.py`. Expected:
    (text, *, session_id, notes_root, now=None) -> PinResult."""
    module = _load_lifecycle_module(
        "skills/sf-note/lib/__init__.py", "_drift_sf_note_lib",
    )
    sig = inspect.signature(module.pin_note)
    params = list(sig.parameters.keys())
    assert params[0] == "text", f"pin_note's first param is no longer 'text': {params}"
    for required in ("session_id", "notes_root"):
        assert required in params, (
            f"pin_note lost param '{required}'; sig now: {params}"
        )


def test_wrap_signature_drift() -> None:
    """Pin per `skills/sf-wrap/lib/__init__.py`'s `wrap()` entry. The feed-write
    glue (`feed_write_fn` + the `validate`/`feed_call` submodules) was removed
    with the feed module (ADR-031)."""
    base = "_drift_sf_wrap_lib"
    parent_path = "skills/sf-wrap/lib"
    for sub in ("types", "classifier", "apply", "diff_plan"):
        _load_lifecycle_module(f"{parent_path}/{sub}.py", f"{base}.{sub}")
    module = _load_lifecycle_module(f"{parent_path}/__init__.py", base)
    sig = inspect.signature(module.wrap)
    params = list(sig.parameters.keys())
    assert params[0] == "inputs"
    for required in ("wiki_root", "cwd", "classifier_fn", "approve_fn"):
        assert required in params, (
            f"wrap lost param '{required}'; sig now: {params}"
        )
    assert "feed_write_fn" not in params, (
        "wrap should no longer expose the removed feed_write_fn param"
    )
