"""pytest fixtures for the sf-install integration harness.

Provides:
    repo_root          — absolute Path to the framework repo root
    skeleton_root      — Path to wiki-skeleton/templates/
    tmp_wiki           — a clean temporary wiki root per test
    tmp_checkpoint     — the install-state.json path per test
    distribution_fake  — DistributionFake instance per test
    lifecycle_fake     — LifecycleFake instance per test
    simulator          — InstallSimulator wired up with the fakes

Tests can override the fakes' default behavior by calling inject_* methods.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


# Make this directory importable as a package so relative imports inside
# simulator.py work when pytest discovers the tests via the standard
# rootdir mechanism. We add the PARENT (`tests/`) to sys.path so the
# package name `integration` resolves cleanly.
_INTEGRATION_DIR = Path(__file__).resolve().parent
_TESTS_DIR = _INTEGRATION_DIR.parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))


from integration.fakes.distribution_fake import DistributionFake  # noqa: E402
from integration.fakes.lifecycle_fake import LifecycleFake  # noqa: E402
from integration.simulator import InstallSimulator  # noqa: E402


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Absolute path to the framework repo root."""
    # This conftest.py lives at skills/install/tests/integration/conftest.py
    # so the repo root is four levels up.
    return Path(__file__).resolve().parent.parent.parent.parent.parent


@pytest.fixture(scope="session")
def skeleton_root(repo_root: Path) -> Path:
    """Path to wiki-skeleton/templates/."""
    p = repo_root / "wiki-skeleton" / "templates"
    if not p.is_dir():
        pytest.skip(f"skeleton_root not found at {p}")
    return p


@pytest.fixture
def tmp_wiki(tmp_path: Path) -> Path:
    """Clean temporary wiki root per test."""
    return tmp_path / "wiki"


@pytest.fixture
def tmp_checkpoint(tmp_path: Path) -> Path:
    """install-state.json path per test, never pre-populated."""
    return tmp_path / "state" / "install-state.json"


@pytest.fixture
def distribution_fake() -> DistributionFake:
    return DistributionFake()


@pytest.fixture
def lifecycle_fake() -> LifecycleFake:
    return LifecycleFake()


@pytest.fixture
def simulator(
    tmp_wiki: Path,
    tmp_checkpoint: Path,
    skeleton_root: Path,
    distribution_fake: DistributionFake,
    lifecycle_fake: LifecycleFake,
) -> InstallSimulator:
    return InstallSimulator(
        wiki_root=tmp_wiki,
        checkpoint_path=tmp_checkpoint,
        skeleton_root=skeleton_root,
        distribution=distribution_fake,
        lifecycle=lifecycle_fake,
    )
