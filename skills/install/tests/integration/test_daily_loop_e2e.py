"""End-to-end daily-loop integration test.

Covers the friend's first-day journey end-to-end against REAL peer
implementations (lifecycle's `compose_wake_up_context`, `wrap`, `pin_note`).
Install + Stage 4 interview still go through the InstallSimulator from #38
(no real `/sf:install` orchestrator — that lives in SKILL.md prose, not Python).

Solo-first (ADR-031): the former step 6 (/sf:catch-up against a multi-friend
Activity Feed) was removed with the feed module. The journey is now:

    1. /sf:install         — fresh-machine fixture, 7 stages, checkpoint complete
    2. /sf:interview       — Stage 4; identity.md written
    3. /sf:wake-up         — REAL compose_wake_up_context against the installed wiki
    4. /sf:note            — REAL pin_note captures a mid-session thought
    5. /sf:wrap            — REAL wrap() with an injected classifier

End-assertion: wiki + identity are in steady-state shape.

The signature-drift tests live in `test_contract_drift.py` (peers' real symbols
imported and `inspect.signature`'d). This file exercises BEHAVIOR.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from integration.simulator import InstallSimulator, InterviewAnswers


# Add repo root to path so we can import lifecycle libs that live at
# unconventional paths (skills/wrap/lib/ etc — package name contains a dash).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load_module_from_path(name: str, path: Path):
    """Load a Python module from a file path, registering it in sys.modules.

    Required because lifecycle's skill directories have dashes in their names
    (`wrap`, `note`, etc) which aren't valid Python identifiers, so the
    normal `from X.Y.Z import ...` machinery can't reach them. We bypass with
    `importlib.util.spec_from_file_location`.

    The `sys.modules` registration BEFORE `exec_module` is what makes
    dataclass-defined types work — the dataclass machinery looks up the
    declaring module in sys.modules during type resolution, and without the
    registration, fields with forward-referenced types fail with NoneType.
    """
    import importlib.util
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # MUST happen before exec_module for dataclasses
    spec.loader.exec_module(module)
    return module


# ---- Step 1+2 fixture: a fully-installed friend ----------------------------


@pytest.fixture
def installed_friend(simulator: InstallSimulator) -> InstallSimulator:
    """Run a fresh-machine install end-to-end; return the simulator for
    inspection. Stages 1-7 all complete; identity.md is written; the
    wiki skeleton is stamped."""
    simulator.run()
    assert simulator.aborted_at is None, simulator.abort_reason
    assert simulator.state["completed_stages"] == [1, 2, 3, 4, 5, 6, 7]
    return simulator


@pytest.fixture
def installed_wiki(installed_friend: InstallSimulator) -> Path:
    """Path to the installed wiki root."""
    return installed_friend.wiki_root


@pytest.fixture
def installed_handle(installed_friend: InstallSimulator) -> str:
    return installed_friend.answers.handle


# ---- Step 3: wake-up against the REAL composer ----------------------------


def _import_compose_wake_up_context():
    """Load `compose_wake_up_context` from `hooks/wake-up/wakeup/__init__.py`.

    The `hooks/wake-up/` directory has a dash, so we go through
    `_load_module_from_path` which registers the module in `sys.modules`
    correctly for dataclass type resolution. The package is `wakeup` (renamed
    from `lib` in ADR-031 to avoid colliding with the repo-root `lib` package).
    """
    module = _load_module_from_path(
        "_e2e_sf_wake_up_lib",
        _REPO_ROOT / "hooks" / "wake-up" / "wakeup" / "__init__.py",
    )
    return module.compose_wake_up_context


def test_wake_up_emits_master_index_and_log_sections(installed_wiki: Path) -> None:
    """After install, wake-up's composer reads the master wiki index + log."""
    compose_wake_up_context = _import_compose_wake_up_context()

    context = compose_wake_up_context(
        cwd=installed_wiki,
        wiki_root=installed_wiki,
        source="startup",
    )

    assert context, "compose_wake_up_context returned empty string"
    assert "Master wiki index" in context, (
        "wake-up payload missing 'Master wiki index' section header"
    )
    assert "Recent master log" in context, (
        "wake-up payload missing 'Recent master log' section header"
    )


def test_wake_up_returns_empty_when_wiki_absent(tmp_path: Path) -> None:
    """Graceful degradation per ADR-008 — missing wiki → empty payload, no raise."""
    compose_wake_up_context = _import_compose_wake_up_context()

    context = compose_wake_up_context(
        cwd=tmp_path,
        wiki_root=tmp_path / "nonexistent-wiki",
        source="startup",
    )

    assert context == "", (
        f"expected empty string for missing wiki; got {len(context)} chars"
    )


# ---- Step 4: /sf:note pins a mid-session note ------------------------------


def _import_pin_note():
    module = _load_module_from_path(
        "_e2e_sf_note_lib",
        _REPO_ROOT / "skills" / "note" / "lib" / "__init__.py",
    )
    return module.pin_note, module.resolve_notes_path


def test_note_pin_writes_bullet_to_session_notes_file(
    installed_wiki: Path,
) -> None:
    """A friend's mid-session /sf:note pins a bullet that /sf:wrap can read later."""
    pin_note, resolve_notes_path = _import_pin_note()

    notes_root = installed_wiki / ".session-notes"
    notes_path = resolve_notes_path(session_id="e2e-test-session", notes_root=notes_root)
    result = pin_note(
        "remember to check the rate-limit on the Stripe webhook",
        session_id="e2e-test-session",
        notes_root=notes_root,
    )

    assert result.path == notes_path
    assert result.path.exists()
    body = result.path.read_text(encoding="utf-8")
    assert "remember to check the rate-limit" in body


# ---- Step 5: /sf:wrap end-to-end (real wrap + injected classifier) ---------


def _import_wrap():
    """Load sf-wrap's lib module. Returns the module so callers can pull
    out `wrap`, `WrapInputs`, and `ClassifierResult` from a single load."""
    # Register the lib package + its sub-modules via explicit name so the
    # dataclass machinery + relative imports both work. (The feed-write
    # submodules `validate`/`feed_call` were removed with the feed module.)
    sub_modules = ["types", "classifier", "apply", "diff_plan"]
    parent_name = "_e2e_sf_wrap_lib"
    parent_path = _REPO_ROOT / "skills" / "wrap" / "lib"
    for sub in sub_modules:
        _load_module_from_path(f"{parent_name}.{sub}", parent_path / f"{sub}.py")
    module = _load_module_from_path(parent_name, parent_path / "__init__.py")
    return module


def test_wrap_no_signal_does_not_write_wiki_pages(
    installed_wiki: Path,
) -> None:
    """When the classifier returns 'none', wrap completes without wiki edits
    (beyond CONTEXT.md, which is always rewritten). This is the high-signal-
    threshold discipline per ADR-009."""
    sf_wrap = _import_wrap()
    ClassifierResult = sf_wrap.ClassifierResult

    def stub_classifier(transcript, project_name):
        return ClassifierResult(labels=("none",), reasoning="routine debugging")

    inputs = sf_wrap.WrapInputs(
        session_transcript_path=None,
        session_notes=(),
        cwd=str(installed_wiki),
        active_project=None,
    )

    result = sf_wrap.wrap(
        inputs,
        wiki_root=installed_wiki,
        cwd=installed_wiki,
        classifier_fn=stub_classifier,
    )

    # No signal → no wiki page changes.
    assert result.wiki_pages_changed == ()


def test_wrap_returns_steady_state_result(installed_wiki: Path) -> None:
    """End-to-end: wrap returns a WrapResult with the expected shape regardless
    of signal/no-signal. The shape itself is the contract."""
    sf_wrap = _import_wrap()
    ClassifierResult = sf_wrap.ClassifierResult

    def stub_classifier(transcript, project_name):
        return ClassifierResult(labels=("none",), reasoning="")

    inputs = sf_wrap.WrapInputs(
        session_transcript_path=None,
        session_notes=(),
        cwd=str(installed_wiki),
        active_project=None,
    )

    result = sf_wrap.wrap(
        inputs,
        wiki_root=installed_wiki,
        cwd=installed_wiki,
        classifier_fn=stub_classifier,
    )

    # WrapResult shape contract
    assert hasattr(result, "wiki_pages_changed")
    assert hasattr(result, "next_session_pointer")
    assert hasattr(result, "elapsed_seconds")
    assert result.elapsed_seconds >= 0
    assert isinstance(result.next_session_pointer, str)


# ---- Steady-state assertion ------------------------------------------------


def test_full_daily_loop_lands_in_steady_state(
    installed_friend: InstallSimulator,
    tmp_path: Path,
) -> None:
    """Single end-to-end scenario: install → wake-up → note → wrap,
    end-asserting the friend's wiki + identity are in expected shape.
    """
    wiki = installed_friend.wiki_root
    handle = installed_friend.answers.handle

    # 1+2. Install + interview already done by the fixture.
    assert (wiki / "identity.md").exists()
    assert (wiki / "index.md").exists()
    assert (wiki / "log.md").exists()
    identity_body = (wiki / "identity.md").read_text(encoding="utf-8")
    assert f"handle: {handle}" in identity_body

    # 3. Wake-up against installed wiki.
    compose_wake_up_context = _import_compose_wake_up_context()
    wake_payload = compose_wake_up_context(
        cwd=wiki, wiki_root=wiki, source="startup",
    )
    assert wake_payload  # non-empty
    assert "Master wiki index" in wake_payload

    # 4. Pin a mid-session note.
    pin_note, _resolve_notes_path = _import_pin_note()
    pin_result = pin_note(
        "follow up on the JWT migration",
        session_id="e2e-steady-state",
        notes_root=wiki / ".session-notes",
    )
    assert pin_result.path is not None and pin_result.path.exists()

    # 5. Wrap (no-signal — most sessions).
    sf_wrap = _import_wrap()
    ClassifierResult = sf_wrap.ClassifierResult

    def stub_classifier(transcript, project_name):
        return ClassifierResult(labels=("none",), reasoning="routine")

    inputs = sf_wrap.WrapInputs(
        session_transcript_path=None,
        session_notes=(pin_result.path.read_text(encoding="utf-8"),),
        cwd=str(wiki),
        active_project=None,
    )
    wrap_result = sf_wrap.wrap(
        inputs,
        wiki_root=wiki,
        cwd=wiki,
        classifier_fn=stub_classifier,
    )
    # No-signal → no wiki pages changed.
    assert wrap_result.wiki_pages_changed == ()

    # Steady-state shape: install checkpoint complete + identity written +
    # skeleton intact + wake-up payload non-empty + note pinned + wrap returned
    # a structurally-valid result. If any of those broke, the daily loop is broken.
