"""Tests for skills.update.lib.gc_stale_envs (#40).

GCs framework_root()/.envs/<version> dirs left behind by uv invocations once
that version is no longer in the plugin cache. Cache-root resolution mirrors
`skills.install.lib._repo_root()` / doctor's checks: CLAUDE_PLUGIN_ROOT points
AT the current versioned cache dir (`.../ren-os/ren/<version>/`), so its
parent lists every installed version.
"""

from __future__ import annotations

from skills.update import lib as update_lib


def test_gc_stale_envs_removes_orphans_keeps_live(tmp_path, monkeypatch):
    cache_versions_root = tmp_path / "cache" / "ren-os" / "ren"
    live_version_dir = cache_versions_root / "0.7.5"
    live_version_dir.mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(live_version_dir))

    framework_root = tmp_path / "framework"
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(framework_root))
    envs_root = framework_root / ".envs"
    (envs_root / "0.7.5").mkdir(parents=True)
    (envs_root / "0.7.3").mkdir(parents=True)

    removed = update_lib.gc_stale_envs()

    assert removed == ["0.7.3"]
    assert (envs_root / "0.7.5").is_dir()
    assert not (envs_root / "0.7.3").exists()


def test_gc_stale_envs_no_envs_dir_is_noop(tmp_path, monkeypatch):
    live_version_dir = tmp_path / "cache" / "ren-os" / "ren" / "0.7.5"
    live_version_dir.mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(live_version_dir))
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path / "framework"))

    assert update_lib.gc_stale_envs() == []


def test_gc_stale_envs_unresolvable_cache_root_is_noop(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    framework_root = tmp_path / "framework"
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(framework_root))
    envs_root = framework_root / ".envs"
    (envs_root / "0.7.3").mkdir(parents=True)

    # No cache root to compare against — never delete blind.
    assert update_lib.gc_stale_envs() == []
    assert (envs_root / "0.7.3").is_dir()


def test_gc_stale_envs_never_raises_on_per_dir_oserror(tmp_path, monkeypatch):
    live_version_dir = tmp_path / "cache" / "ren-os" / "ren" / "0.7.5"
    live_version_dir.mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(live_version_dir))

    framework_root = tmp_path / "framework"
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(framework_root))
    envs_root = framework_root / ".envs"
    (envs_root / "0.7.3").mkdir(parents=True)

    import shutil as _shutil

    def _boom(path, *args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(update_lib.shutil, "rmtree", _boom)

    assert update_lib.gc_stale_envs() == []
    assert (envs_root / "0.7.3").is_dir()
