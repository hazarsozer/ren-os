"""
H2 regression (REVIEW-v1.0-preship §H2): force the C locale on every git/gh subprocess
in feed.io_github.

git localizes its messages via gettext. On a non-English host (e.g. Hazar's Turkish
locale) the "[rejected]" / "non-fast-forward" substrings that
`_looks_like_non_fast_forward` matches come back translated, so conflict detection
returns False → the push silently queues instead of rebase-retrying, degrading the
concurrent-write guarantee to eventually-consistent.

These tests are deterministic and locale-independent (no tr_TR locale needed in CI):
1. Every git/gh subprocess is invoked with env LANG=C / LC_ALL=C (and a preserved
   environment so PATH / HOME / git config survive).
2. The English rejection wording matches the detector while a Turkish-localized
   rejection does NOT — which is precisely why we must force C.

Run with: python3 -m pytest feed/tests/test_git_locale.py -v
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from feed import io_github


def test_c_locale_env_merges_environ(monkeypatch):
    """_c_locale_env forces C locale but MERGES (not replaces) the parent environment."""
    monkeypatch.setenv("SF_FEED_LOCALE_PROBE", "kept")
    env = io_github._c_locale_env()
    assert env["LANG"] == "C"
    assert env["LC_ALL"] == "C"
    assert env["SF_FEED_LOCALE_PROBE"] == "kept"  # merged, not wiped
    assert "PATH" in env  # critical: git needs PATH/HOME to function


def _make_spy(captured):
    def spy(cmd, *args, **kwargs):
        captured.append((list(cmd), kwargs.get("env")))
        stdout = ""
        # `git status --porcelain` must look dirty so _stage_and_commit proceeds to commit
        if cmd[:1] == ["git"] and cmd[3:5] == ["status", "--porcelain"]:
            stdout = " M hazar.log.md\n"
        return subprocess.CompletedProcess(cmd, 0, stdout, "")
    return spy


def test_all_git_and_gh_subprocesses_force_C_locale(monkeypatch, tmp_path):
    """Drive every io_github entry point and assert each git/gh call forces C locale."""
    repo = tmp_path / "activity-feed"
    (repo / ".git").mkdir(parents=True)  # make the .git existence guards pass

    captured: list[tuple[list, dict | None]] = []
    monkeypatch.setattr(io_github.subprocess, "run", _make_spy(captured))

    # Exercise: auth check, pull, full push (add/status/commit/push), rebase.
    io_github.check_auth()
    io_github.pull(local_path=repo)
    io_github.push(commit_msg="hazar end 2026-05-28 14:30", local_path=repo)
    io_github._try_rebase(repo, timeout_s=5)

    git_or_gh = [(cmd, env) for cmd, env in captured if cmd and cmd[0] in ("git", "gh")]
    # Sanity: we actually captured the calls we care about (push fans out to several).
    assert any(cmd[0] == "gh" for cmd, _ in git_or_gh), "expected a gh call"
    assert any("push" in cmd for cmd, _ in git_or_gh), "expected a git push call"
    assert len(git_or_gh) >= 6, f"expected ≥6 git/gh calls, got {len(git_or_gh)}"

    for cmd, env in git_or_gh:
        assert env is not None, f"{cmd} ran without an explicit env (host locale leaks in)"
        assert env.get("LANG") == "C", f"{cmd} did not force LANG=C"
        assert env.get("LC_ALL") == "C", f"{cmd} did not force LC_ALL=C"
        assert "PATH" in env, f"{cmd} env was replaced, not merged (PATH missing)"


def test_non_fast_forward_detector_needs_english_wording():
    """Documents the bug class: the detector matches English git output but NOT the
    Turkish-localized form — so forcing C locale (always English) is load-bearing."""
    english = (
        " ! [rejected]        main -> main (non-fast-forward)\n"
        "error: failed to push some refs to 'origin'\n"
        "hint: Updates were rejected because the tip of your current branch is behind"
    )
    assert io_github._looks_like_non_fast_forward(english)

    # A plausible Turkish localization — none of our English substrings appear.
    turkish = (
        " ! [reddedildi]      main -> main (ileri-sarma-değil)\n"
        "hata: bazı referanslar 'origin' adresine gönderilemedi"
    )
    assert not io_github._looks_like_non_fast_forward(turkish)
