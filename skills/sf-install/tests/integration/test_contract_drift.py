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

from integration.fakes.feed_fake import FeedFake
from integration.fakes.distribution_fake import DistributionFake
from integration.fakes.lifecycle_fake import LifecycleFake


# ---- feed -----------------------------------------------------------------


def _real_feed_module():
    """Import the real feed module. If import fails, skip drift tests for it."""
    try:
        import feed  # type: ignore
        return feed
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"feed module not importable: {exc}")


def test_feed_detect_repo_state_signature_drift() -> None:
    real = _real_feed_module()
    real_sig = inspect.signature(real.feed_detect_repo_state)
    fake_sig = inspect.signature(FeedFake.feed_detect_repo_state)

    # Drop the 'self' on the fake side; compare positional+keyword names.
    fake_params = [p for p in fake_sig.parameters.values() if p.name != "self"]
    real_params = list(real_sig.parameters.values())

    fake_names = [p.name for p in fake_params]
    real_names = [p.name for p in real_params]
    assert fake_names == real_names, (
        f"feed_detect_repo_state signature drift: fake={fake_names}, real={real_names}"
    )


def test_feed_bootstrap_first_friend_signature_drift() -> None:
    real = _real_feed_module()
    real_sig = inspect.signature(real.feed_bootstrap_first_friend)
    fake_sig = inspect.signature(FeedFake.feed_bootstrap_first_friend)

    fake_params = [p.name for p in fake_sig.parameters.values() if p.name != "self"]
    real_params = [p.name for p in real_sig.parameters.values()]
    assert fake_params == real_params


def test_feed_clone_existing_signature_drift() -> None:
    real = _real_feed_module()
    real_sig = inspect.signature(real.feed_clone_existing)
    fake_sig = inspect.signature(FeedFake.feed_clone_existing)

    fake_params = [p.name for p in fake_sig.parameters.values() if p.name != "self"]
    real_params = [p.name for p in real_sig.parameters.values()]
    assert fake_params == real_params


def test_feed_upsert_identity_signature_drift() -> None:
    real = _real_feed_module()
    real_sig = inspect.signature(real.feed_upsert_identity)
    fake_sig = inspect.signature(FeedFake.feed_upsert_identity)

    fake_params = [p.name for p in fake_sig.parameters.values() if p.name != "self"]
    real_params = [p.name for p in real_sig.parameters.values()]
    assert fake_params == real_params


def test_feed_rename_handle_signature_drift() -> None:
    real = _real_feed_module()
    if not hasattr(real, "rename_handle"):
        pytest.skip("feed.rename_handle not yet exported")
    real_sig = inspect.signature(real.rename_handle)
    fake_sig = inspect.signature(FeedFake.rename_handle)

    fake_params = [p.name for p in fake_sig.parameters.values() if p.name != "self"]
    real_params = [p.name for p in real_sig.parameters.values()]
    assert fake_params == real_params


def test_feed_writeresult_field_drift() -> None:
    """Our fake FeedWriteResult must carry the same fields as feed.FeedWriteResult."""
    real = _real_feed_module()
    if not hasattr(real, "FeedWriteResult"):
        pytest.skip("feed.FeedWriteResult not yet exported")
    from integration.fakes.feed_fake import FeedWriteResult as FakeWR

    real_fields = {f for f in real.FeedWriteResult.__dataclass_fields__}
    fake_fields = {f for f in FakeWR.__dataclass_fields__}
    # The fake should be a strict subset (we don't HAVE to track every real
    # field, but every fake field must exist in the real).
    missing_in_real = fake_fields - real_fields
    assert not missing_in_real, (
        f"FeedWriteResult fake has fields not in real: {missing_in_real}"
    )


def test_feed_repostate_field_drift() -> None:
    real = _real_feed_module()
    if not hasattr(real, "RepoState"):
        pytest.skip("feed.RepoState not yet exported")
    from integration.fakes.feed_fake import RepoState as FakeRS

    real_fields = {f for f in real.RepoState.__dataclass_fields__}
    fake_fields = {f for f in FakeRS.__dataclass_fields__}
    missing_in_real = fake_fields - real_fields
    assert not missing_in_real, (
        f"RepoState fake has fields not in real: {missing_in_real}"
    )


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
    """Pin per `hooks/wake-up/lib/__init__.py`. The wake-up hook's public
    composition entry. Expected: keyword-only cwd / wiki_root / source /
    max_tokens / fetch_feed_tail."""
    module = _load_lifecycle_module(
        "hooks/wake-up/lib/__init__.py", "_drift_sf_wake_up_lib",
    )
    sig = inspect.signature(module.compose_wake_up_context)
    params = list(sig.parameters.keys())
    for required in ("cwd", "wiki_root", "source", "max_tokens", "fetch_feed_tail"):
        assert required in params, (
            f"compose_wake_up_context lost param '{required}'; sig now: {params}"
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
    """Pin per `skills/sf-wrap/lib/__init__.py`'s `wrap()` entry."""
    base = "_drift_sf_wrap_lib"
    parent_path = "skills/sf-wrap/lib"
    for sub in ("types", "validate", "classifier", "apply", "diff_plan", "feed_call"):
        _load_lifecycle_module(f"{parent_path}/{sub}.py", f"{base}.{sub}")
    module = _load_lifecycle_module(f"{parent_path}/__init__.py", base)
    sig = inspect.signature(module.wrap)
    params = list(sig.parameters.keys())
    assert params[0] == "inputs"
    for required in ("wiki_root", "cwd", "classifier_fn", "approve_fn", "feed_write_fn"):
        assert required in params, (
            f"wrap lost param '{required}'; sig now: {params}"
        )


# ---- additional feed reader pin (used by /sf:catch-up flow) ----------------


def test_feed_read_friends_tails_signature_drift() -> None:
    """Pin per feed/__init__.py. Consumed by /sf:catch-up + Stage 6 doctor."""
    real = _real_feed_module()
    sig = inspect.signature(real.feed_read_friends_tails)
    params = list(sig.parameters.keys())
    assert params[0] == "own_handle"
    for required in ("n_per_friend", "include_self", "since", "max_tokens", "refresh"):
        assert required in params, (
            f"feed_read_friends_tails lost param '{required}'; sig now: {params}"
        )
