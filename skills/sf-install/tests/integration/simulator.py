"""InstallSimulator — walks the documented 7-stage /sf:install procedure.

Each stage method maps 1:1 to a step in skills/sf-install/references/stage-N-*.md.
Keep this thin: any time you're tempted to add "business logic" here, add it to
the stage ref doc first and then mirror in code.

The simulator captures the state the real install would write to
$XDG_STATE_HOME/sf/install-state.json. Tests assert against this `state` dict.

Pushback-pinning behavior is encoded in the per-stage methods:
    P1 (always-check) → Stage 1 always invokes the env probes (no cache skip).
    P2 (additive-only) → Stage 5 calls the loader's additive-diff path on existing
                         wikis; never overwrites.
    P3 (manual handoff) → Stage 7 prints the tour but does NOT invoke any other
                          slash command.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .fakes.feed_fake import FeedFake, FeedWriteResult, RepoState
from .fakes.distribution_fake import DistributionFake
from .fakes.lifecycle_fake import LifecycleFake


# ---- Stage 1 environment probe ----------------------------------------------


@dataclass(frozen=True)
class EnvSnapshot:
    """A snapshot of what Stage 1 probes return for this scenario."""
    claude_auth: bool = True
    gh_auth: bool = True
    node_version: str = "22.7.1"
    node_ok: bool = True
    git_ok: bool = True
    anthropic_api_key: bool = True
    upstash_context7_api_key: bool = True

    def all_green(self) -> bool:
        return all([
            self.claude_auth,
            self.gh_auth,
            self.node_ok,
            self.git_ok,
            self.anthropic_api_key,
            self.upstash_context7_api_key,
        ])

    def to_checks_dict(self) -> dict:
        return {
            "claude_auth": self.claude_auth,
            "gh_auth": self.gh_auth,
            "node_version": self.node_version,
            "node_ok": self.node_ok,
            "git_ok": self.git_ok,
            "anthropic_api_key": self.anthropic_api_key,
            "upstash_context7_api_key": self.upstash_context7_api_key,
        }


# ---- Stage 4 friend response stub (interview answers) -----------------------


@dataclass(frozen=True)
class InterviewAnswers:
    handle: str = "eval-friend"
    name: str = "Eval Friend"
    phase: str = "ideation"
    strong_skills: tuple[str, ...] = ("backend",)
    clouds: tuple[str, ...] = ("vercel",)
    contact_timezone: str = ""
    contact_working_hours: str = ""
    intro_paragraph: str = "Builder."
    contribution_paragraph: str = "Skeptical reviewer."
    communication_style: str = "balanced-with-emoji"


# ---- The simulator ----------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class InstallSimulator:
    """Walks the 7-stage /sf:install procedure against fakes.

    Construction args:
        wiki_root        — friend's wiki root (typically ~/.startup-framework/wiki/)
        checkpoint_path  — $XDG_STATE_HOME/sf/install-state.json
        skeleton_root    — repo's wiki-skeleton/templates/
        feed             — FeedFake
        distribution    — DistributionFake
        lifecycle        — LifecycleFake
        env              — EnvSnapshot for Stage 1
        repo_url         — Activity Feed repo URL the friend would type
        answers          — interview answers for Stage 4

    Public state after run:
        self.state                — the would-be install-state.json dict
        self.stage_log            — list of (stage_n, status, detail) tuples
        self.auto_invoked_commands — list of slash-commands the simulator
                                     would have auto-invoked (should stay [])
        self.stage1_probe_count   — how many times Stage 1 probes ran
                                    (P1 verification helper)
        self.stage5_overwrites    — paths where Stage 5 would have overwritten
                                    (must stay [] — P2)
    """

    FRAMEWORK_VERSION = "1.0.0"
    REQUIRED_PLUGIN_NAMES = (
        "context-mode",
        "claude-mem",
        "superpowers",
        "skill-creator",
        "context7",
        "claude-md-management",
    )

    def __init__(
        self,
        *,
        wiki_root: Path,
        checkpoint_path: Path,
        skeleton_root: Path,
        feed: FeedFake,
        distribution: DistributionFake,
        lifecycle: LifecycleFake,
        env: EnvSnapshot | None = None,
        repo_url: str = "eval-friends/activity-feed",
        answers: InterviewAnswers | None = None,
    ) -> None:
        self.wiki_root = wiki_root
        self.checkpoint_path = checkpoint_path
        self.skeleton_root = skeleton_root
        self.feed = feed
        self.distribution = distribution
        self.lifecycle = lifecycle
        self.env = env or EnvSnapshot()
        self.repo_url = repo_url
        self.answers = answers or InterviewAnswers()

        self.state: dict[str, Any] = self._load_or_init_state()
        self.stage_log: list[tuple[int, str, str]] = []
        self.auto_invoked_commands: list[str] = []
        self.stage1_probe_count: int = 0
        self.stage5_overwrites: list[Path] = []
        self.aborted_at: int | None = None
        self.abort_reason: str = ""

    # ------------------------------------------------------------------ run

    def run(self) -> None:
        """Drive the orchestrator from the resume protocol entry point.

        Stages 1 and 6 are always_recheck=True per resume-protocol.md.
        Other stages skip if marked complete (idempotent).
        """
        for n in range(1, 8):
            try:
                handler = getattr(self, f"_run_stage_{n}")
                handler()
            except StageAbort as exc:
                self.aborted_at = n
                self.abort_reason = str(exc)
                self._append_abort(n, str(exc))
                self._persist()
                return
        self._persist()

    # ----------------------------------------------------------- stages

    def _run_stage_1(self) -> None:
        """Always run probes (P1). Skip only the prompt-for-fix when green."""
        self.stage1_probe_count += 1
        env = self.env
        checks = env.to_checks_dict()
        self.state["stage_artifacts"]["1"] = {
            "env_ok": env.all_green(),
            "checks": checks,
            "last_check_at": _now_iso(),
        }
        if not env.all_green():
            self.stage_log.append((1, "fail", "env not green; prompt user to fix"))
            raise StageAbort("stage 1 env probes failed")
        self._mark_complete(1)
        self.stage_log.append((1, "ok", "all checks green"))

    def _run_stage_2(self) -> None:
        """Install 6 plugins in ADR-010 order, idempotent per-plugin."""
        if 2 in self.state["completed_stages"]:
            already = {p["name"] for p in self.state["stage_artifacts"]["2"]["plugins_installed"]}
            if set(self.REQUIRED_PLUGIN_NAMES) <= already:
                self.stage_log.append((2, "skip", "plugins already installed"))
                return

        registry = self.distribution.read_pinned_registry()
        installed = list(self.state["stage_artifacts"].setdefault(
            "2", {"plugins_installed": []}
        )["plugins_installed"])
        installed_names = {p["name"] for p in installed}

        for plugin in registry.plugins:
            if plugin.name in installed_names:
                continue
            installed.append({"name": plugin.name, "version": plugin.version})
            self._persist_intermediate()

        self.state["stage_artifacts"]["2"] = {"plugins_installed": installed}
        self._mark_complete(2)
        self.stage_log.append((2, "ok", f"{len(installed)} plugins"))

    def _run_stage_3(self) -> None:
        """Activity Feed setup + mini-handle prompt + conditional plugins."""
        if 3 in self.state["completed_stages"]:
            self.stage_log.append((3, "skip", "feed already set up"))
            return

        state = self.feed.feed_detect_repo_state(self.repo_url, None)

        if state.auth_error:
            auth = self.feed.check_auth()
            if not auth.authed:
                raise StageAbort(f"feed auth failed: {auth.reason}")
            state = self.feed.feed_detect_repo_state(self.repo_url, None)

        # 3.3 mini-handle prompt — friend picks; validate against existing handles.
        proposed_handle = self.answers.handle
        if proposed_handle in state.existing_handles:
            # Re-prompt would happen in real install; for the simulator we surface
            # this as an abort so tests can assert on collision detection.
            raise StageAbort(
                f"handle collision: '{proposed_handle}' in existing_handles "
                f"{list(state.existing_handles)}"
            )

        if state.mode == "first-friend-bootstrap":
            self.feed.feed_bootstrap_first_friend(state.local_path, proposed_handle, self.repo_url)
        elif state.mode == "joiner-clone":
            self.feed.feed_clone_existing(self.repo_url, state.local_path, proposed_handle)
        # "already-cloned" → no-op

        self.state["stage_artifacts"]["3"] = {
            "activity_feed_url": self.repo_url,
            "feed_state": state.mode,
            "local_clone_path": str(state.local_path),
            "proposed_handle": proposed_handle,
        }
        self._mark_complete(3)
        self.stage_log.append((3, "ok", f"feed mode={state.mode}"))

    def _run_stage_4(self) -> None:
        """Identity bootstrap via sf-interview."""
        identity_path = self.wiki_root / "identity.md"
        if 4 in self.state["completed_stages"] and identity_path.exists():
            self.stage_log.append((4, "skip", "identity.md already present"))
            return

        proposed = self.state["stage_artifacts"].get("3", {}).get("proposed_handle")
        final_handle = self.answers.handle

        if proposed and proposed != final_handle:
            renamed = self.feed.rename_handle(proposed, final_handle)
            if not renamed and proposed != final_handle:
                self.stage_log.append((4, "warn", "rename_handle returned False"))

        # Render local identity.md (mocking sf-interview's output).
        identity_path.parent.mkdir(parents=True, exist_ok=True)
        identity_path.write_text(self._render_identity_md(), encoding="utf-8")

        # Render public summary + delegate push.
        public_md = self._render_public_summary_md()
        result: FeedWriteResult = self.feed.feed_upsert_identity(final_handle, public_md)

        self.state["stage_artifacts"]["4"] = {
            "identity_path": str(identity_path),
            "handle_written": final_handle,
            "public_summary_pushed": result.pushed,
            "feed_push_warning": result.error if not result.success else None,
        }
        self._mark_complete(4)
        self.stage_log.append((4, "ok", f"handle={final_handle}, pushed={result.pushed}"))

    def _run_stage_5(self) -> None:
        """Master wiki skeleton bootstrap. Additive-only (P2).

        Per stage-5-wiki-bootstrap.md + template-loader.md § Additive-diff mode.
        """
        # We track which files would be written and explicitly never overwrite.
        applied: list[str] = []
        declined: list[str] = []

        wiki_files_planned = [
            "index.md",
            "log.md",
            "LICENSES.md",  # written by Stage 6, but planned at Stage 5
        ]
        # identity.md already written by Stage 4; manifest's copy_if_missing rule
        # means Stage 5 sees it present and skips.

        for relative in wiki_files_planned:
            target = self.wiki_root / relative
            if target.exists():
                # NEVER overwrite. Per P2 + template-loader.md § "Never overwrite".
                self.stage5_overwrites_check(target)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self._render_template_for(relative), encoding="utf-8")
            applied.append(relative)

        for subdir in ("research", "decisions", "alternatives", "patterns", "projects"):
            path = self.wiki_root / subdir
            path.mkdir(parents=True, exist_ok=True)
            gitkeep = path / ".gitkeep"
            if not gitkeep.exists():
                gitkeep.write_text("", encoding="utf-8")
                applied.append(f"{subdir}/.gitkeep")

        self.state["stage_artifacts"]["5"] = {
            "wiki_root": str(self.wiki_root),
            "skeleton_schema_version": 1,
            "additive_changes_applied": applied,
            "additive_changes_declined": declined,
        }
        self._mark_complete(5)
        self.stage_log.append((5, "ok", f"{len(applied)} writes; 0 overwrites"))

    def stage5_overwrites_check(self, path: Path) -> None:
        """Sentinel: if this is ever reached after a write, it's a P2 violation."""
        # Path exists; we SKIP, not overwrite. Record nothing.
        # If a test wants to force-fail a P2 violation, they can patch this.
        return

    def _run_stage_6(self) -> None:
        """Doctor verification + LICENSES.md regen + optional OTel."""
        report = self.lifecycle.doctor_report()

        licenses_content = self.distribution.regenerate_licenses_md(self.wiki_root)
        licenses_path = self.wiki_root / "LICENSES.md"
        if licenses_path.exists():
            existing = licenses_path.read_text(encoding="utf-8")
            if existing != licenses_content:
                # Diff exists; in real install we'd prompt. Simulator just notes it.
                self.stage_log.append((6, "warn", "LICENSES.md differs from registry; would prompt"))
        else:
            licenses_path.write_text(licenses_content, encoding="utf-8")

        self.state["stage_artifacts"]["6"] = {
            "doctor_passed": report.passed,
            "otel_enabled": False,
            "licenses_md_written": True,
            "last_check_at": _now_iso(),
        }
        if not report.passed:
            failing = [c.name for c in report.checks if c.status == "fail"]
            raise StageAbort(f"doctor reported failures: {failing}")
        self._mark_complete(6)
        self.stage_log.append((6, "ok", f"{len(report.checks)} checks green"))

    def _run_stage_7(self) -> None:
        """First-session walkthrough. P3: print tour; do NOT auto-invoke anything."""
        if 7 in self.state["completed_stages"]:
            self.stage_log.append((7, "skip", "already acknowledged"))
            return
        # Stage 7 is informational; the friend types `y` to ack.
        # IMPORTANT P3: we do NOT auto-invoke /sf:wake-up, /sf:doctor, etc.
        # The auto_invoked_commands list MUST stay empty.
        self.state["stage_artifacts"]["7"] = {
            "walkthrough_acknowledged": True,
            "acknowledged_at": _now_iso(),
        }
        self._mark_complete(7)
        self.stage_log.append((7, "ok", "walkthrough acknowledged"))

    # ------------------------------------------------------------ helpers

    def _load_or_init_state(self) -> dict[str, Any]:
        if self.checkpoint_path.exists():
            return json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        return {
            "schema_version": 1,
            "framework_version": self.FRAMEWORK_VERSION,
            "started_at": _now_iso(),
            "last_updated_at": _now_iso(),
            "completed_stages": [],
            "stage_artifacts": {},
            "abort_log": [],
        }

    def _persist(self) -> None:
        self.state["last_updated_at"] = _now_iso()
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.checkpoint_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.state, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.checkpoint_path)

    def _persist_intermediate(self) -> None:
        # Same as _persist; named differently for self-documentation in stage 2's
        # per-plugin loop.
        self._persist()

    def _mark_complete(self, n: int) -> None:
        completed = self.state["completed_stages"]
        if n not in completed:
            completed.append(n)
            completed.sort()
        self._persist()

    def _append_abort(self, stage_n: int, error_summary: str) -> None:
        self.state["abort_log"].append({
            "stage": stage_n,
            "error_summary": error_summary,
            "ts": _now_iso(),
        })

    def _render_template_for(self, relative: str) -> str:
        path = self.skeleton_root / f"{relative}.tmpl"
        if not path.exists():
            return f"<placeholder {relative}>\n"
        text = path.read_text(encoding="utf-8")
        bindings = {
            "{{handle}}": self.answers.handle,
            "{{name}}": self.answers.name,
            "{{today}}": _today(),
            "{{framework_version}}": self.FRAMEWORK_VERSION,
        }
        for placeholder, value in bindings.items():
            text = text.replace(placeholder, value)
        return text

    def _render_identity_md(self) -> str:
        # Tiny render — full version lives in sf-interview; this is a stub
        # for integration purposes.
        a = self.answers
        return (
            "---\n"
            f"title: \"{a.name}'s Identity\"\n"
            "type: identity\n"
            "schema_version: 1\n"
            f"framework_version: \"{self.FRAMEWORK_VERSION}\"\n"
            f"handle: {a.handle}\n"
            f"name: \"{a.name}\"\n"
            f"created: {_today()}\n"
            f"updated: {_today()}\n"
            f"phase: {a.phase}\n"
            f"strong_skills: {list(a.strong_skills)!r}\n"
            f"clouds: {list(a.clouds)!r}\n"
            f"communication_style: {a.communication_style}\n"
            "---\n\n"
            f"# About {a.name}\n\n{a.intro_paragraph}\n"
            f"\n## What I contribute\n\n{a.contribution_paragraph}\n"
        )

    def _render_public_summary_md(self) -> str:
        a = self.answers
        lines = ["---"]
        lines.append(f"handle: {a.handle}")
        lines.append(f'name: "{a.name}"')
        lines.append(f"phase: {a.phase}")
        if a.strong_skills:
            lines.append(f"strong_skills: {list(a.strong_skills)!r}")
        if a.clouds:
            lines.append(f"clouds: {list(a.clouds)!r}")
        if a.contact_timezone or a.contact_working_hours:
            lines.append("contact:")
            if a.contact_timezone:
                lines.append(f'  timezone: "{a.contact_timezone}"')
            if a.contact_working_hours:
                lines.append(f'  working_hours: "{a.contact_working_hours}"')
        lines.append("---")
        lines.append("")
        lines.append(f"# {a.handle}")
        lines.append("")
        if a.phase != "other":
            lines.append(f"**Phase:** {a.phase}")
            lines.append("")
        lines.append(a.intro_paragraph)
        lines.append("")
        lines.append("## What I contribute")
        lines.append("")
        lines.append(a.contribution_paragraph)
        lines.append("")
        return "\n".join(lines)

    # ------------------------------------------- P3 enforcement helpers

    def would_auto_invoke(self, slash_command: str) -> None:
        """Test sentinel: simulator should NEVER call this. Stage 7 only
        suggests; it doesn't execute. Tests can patch this to assert."""
        self.auto_invoked_commands.append(slash_command)


# ---- Aborts ---------------------------------------------------------------


class StageAbort(RuntimeError):
    """Raised inside a stage handler when the simulator must halt mid-run."""
