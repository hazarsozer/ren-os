"""
Repro tests for the adversarial review findings on the 0.6.2 train
(C1, H1, H2, H3, M1, M2, L1, L2). Written failing-first; each test names
the finding it closes.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from lib import ren_paths
from lib.governance.tiers import is_instruction_plane_page
from lib.memory import quarantine, queue, semantics
from lib.memory.queue import Proposal
from lib.ren_paths import load_project_registry, state_dir, wiki_root


@pytest.fixture
def wiki(monkeypatch, tmp_path):
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _proposal(**overrides):
    defaults = dict(
        op="ADD",
        page="projects/x/notes.md",
        content="hello world",
        reason="testing",
        producer="ingest",
        writer="llm-auto",
        session="sess-1",
    )
    defaults.update(overrides)
    return Proposal(**defaults)


# ---------------------------------------------------------------- C1: traversal


class TestC1PageNormalization:
    def test_dotdot_page_rejected_at_proposal_construction(self):
        with pytest.raises(ValueError):
            _proposal(page="projects/x/../../global/doctrine2.md")

    def test_absolute_page_rejected(self):
        with pytest.raises(ValueError):
            _proposal(page="/global/doctrine.md")

    def test_backslash_page_rejected(self):
        with pytest.raises(ValueError):
            _proposal(page="projects\\x\\notes.md")

    def test_dot_segments_collapsed_so_instruction_plane_gate_holds(self, wiki):
        for raw in ("./global/x.md", "./decisions/x.md", "global/./x.md"):
            p = _proposal(page=raw)
            assert is_instruction_plane_page(p.page), raw
            entry, prov = queue.propose_and_apply(p)
            assert prov is None, f"{raw} auto-applied into the instruction plane"
            assert entry.status == "pending"

    def test_is_instruction_plane_page_normalizes_defense_in_depth(self):
        assert is_instruction_plane_page("./global/x.md")
        assert is_instruction_plane_page("./decisions/x.md")
        assert is_instruction_plane_page("projects/x/../../global/x.md")

    def test_normal_pages_for_all_producers_still_pass(self, wiki):
        for producer, writer in (
            ("pin", "human"),
            ("wrap", "llm-auto"),
            ("ingest", "llm-auto"),
            ("promotion", "human"),
        ):
            p = _proposal(
                page=f"projects/x/{producer}.md",
                producer=producer,
                writer=writer,
                content=f"content for {producer}",
            )
            assert p.page == f"projects/x/{producer}.md"


# ------------------------------------------------------- H1: l2-map self-exempt


class TestH1L2MapSelfExemption:
    def test_proposed_frontmatter_cannot_self_exempt_from_contradiction(self, wiki):
        proj = wiki / "projects" / "p"
        proj.mkdir(parents=True)
        (proj / "facts.md").write_text(
            "Migrations run automatically on deploy pipeline.\n", encoding="utf-8"
        )
        content = (
            "---\ntype: l2-map\n---\n"
            "Do not run migrations automatically on deploy pipeline.\n"
        )
        conflicts = semantics.detect(
            op="ADD",
            page="projects/p/notes.md",
            content=content,
            wiki_root=wiki,
        )
        assert any(c.kind == "contradicts" for c in conflicts), (
            "a proposal self-exempted from contradiction checks by declaring "
            "type: l2-map in its own frontmatter"
        )

    def test_real_map_page_by_path_still_exempt(self, wiki):
        proj = wiki / "projects" / "p"
        proj.mkdir(parents=True)
        (proj / "facts.md").write_text(
            "Migrations run automatically on deploy pipeline.\n", encoding="utf-8"
        )
        conflicts = semantics.detect(
            op="ADD",
            page="projects/p/map.md",
            content="Do not run migrations automatically on deploy pipeline.\n",
            wiki_root=wiki,
        )
        assert not any(c.kind == "contradicts" for c in conflicts)

    def test_existing_candidate_frontmatter_detection_kept(self, wiki):
        proj = wiki / "projects" / "p"
        proj.mkdir(parents=True)
        (proj / "legacy-map.md").write_text(
            "---\ntype: l2-map\n---\n"
            "Migrations run automatically on deploy pipeline.\n",
            encoding="utf-8",
        )
        conflicts = semantics.detect(
            op="ADD",
            page="projects/p/notes.md",
            content="Do not run migrations automatically on deploy pipeline.\n",
            wiki_root=wiki,
        )
        assert not any(c.kind == "contradicts" for c in conflicts)


# -------------------------------------------------- H2: negated-claim overlap


class TestH2ContainmentOverlap:
    def test_negation_with_explanation_still_detected(self):
        existing = "Migrations run automatically on deploy."
        proposed = "Migrations do not run automatically on deploy; run them manually first."
        assert semantics.contradiction_evidence(proposed, existing) is not None

    def test_topic_only_restatement_not_flagged(self):
        # Short negated claim vs a paragraph merely mentioning the topic.
        a = "Do not enable the cache layer here."
        b = "The deployment guide describes services, containers and monitoring dashboards in detail."
        assert semantics.contradiction_evidence(a, b) is None


# ------------------------------------------------------ H3: release_page works


class TestH3ReleaseInstructionPlane:
    def test_release_quarantined_decisions_page_lands_on_disk(self, wiki):
        import importlib

        wh = importlib.import_module("skills.wiki-health.lib")
        page_dir = wiki / "decisions"
        page_dir.mkdir(parents=True)
        body = "Merge policy: squash always.\n"
        (page_dir / "merge-policy.md").write_text(
            quarantine.mark(body), encoding="utf-8"
        )
        entry, prov = wh.release_page("decisions/merge-policy.md", session="s1")
        assert prov is not None, "release of an instruction-plane page silently pended"
        on_disk = (page_dir / "merge-policy.md").read_text(encoding="utf-8")
        assert not quarantine.is_quarantined(on_disk)


# ---------------------------------------------- M1: same-batch exemption scope


class TestM1SameBatchScoping:
    def test_different_producer_same_session_not_exempt(self, wiki):
        (wiki / "projects" / "p").mkdir(parents=True)
        queue.propose_and_apply(
            _proposal(page="projects/p/a.md", producer="wrap", writer="llm-auto")
        )
        pages = queue._same_batch_pages(
            _proposal(page="projects/p/b.md", producer="ingest")
        )
        assert "projects/p/a.md" not in pages

    def test_same_producer_recent_applied_is_exempt(self, wiki):
        (wiki / "projects" / "p").mkdir(parents=True)
        queue.propose_and_apply(
            _proposal(page="projects/p/a.md", producer="ingest", writer="llm-auto")
        )
        pages = queue._same_batch_pages(
            _proposal(page="projects/p/b.md", producer="ingest")
        )
        assert "projects/p/a.md" in pages

    def test_stale_entry_outside_window_not_exempt(self, wiki):
        (wiki / "projects" / "p").mkdir(parents=True)
        entry, _ = queue.propose_and_apply(
            _proposal(page="projects/p/a.md", producer="ingest", writer="llm-auto")
        )
        # Age the entry past the batch window.
        path = state_dir() / "queue" / f"{entry.qid}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        old = datetime.now(timezone.utc) - timedelta(hours=2)
        data["ts"] = old.strftime("%Y-%m-%dT%H:%M:%SZ")
        path.write_text(json.dumps(data), encoding="utf-8")
        pages = queue._same_batch_pages(
            _proposal(page="projects/p/b.md", producer="ingest")
        )
        assert "projects/p/a.md" not in pages


# ------------------------------------------------- M2: incremental journaling


class TestM2IncrementalJournal:
    def test_journal_survives_mid_run_unlink_failure(self, wiki, monkeypatch):
        import importlib.util
        from pathlib import Path

        spec = importlib.util.spec_from_file_location(
            "pk1_migrate",
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "project-knowledge-1"
            / "migrate.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        proj = wiki / "projects" / "p"
        proj.mkdir(parents=True)
        (proj / "aaa.md").write_text("first page body\n", encoding="utf-8")
        (proj / "bbb.md").write_text("second page body\n", encoding="utf-8")

        real_unlink = Path.unlink

        def failing_unlink(self, *args, **kwargs):
            if self.name == "bbb.md":
                raise OSError("simulated mid-run failure")
            return real_unlink(self, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", failing_unlink)
        with pytest.raises(OSError):
            mod.main(["--apply"])

        journal_path = state_dir() / "migrations" / "project-knowledge-1.jsonl"
        assert journal_path.exists(), (
            "mid-run failure lost the record of the already-moved file"
        )
        records = [json.loads(l) for l in journal_path.read_text().splitlines()]
        assert any(r["from"] == "projects/p/aaa.md" for r in records)


# --------------------------------------------------------- L1: registry slugs


class TestL1RegistrySlugValidation:
    def test_traversal_slug_dropped(self, wiki):
        path = ren_paths.projects_registry_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "projects": {
                        "../..": {"repo_path": "/tmp/evil"},
                        "good-slug": {"repo_path": "/tmp/good"},
                    },
                }
            ),
            encoding="utf-8",
        )
        registry = load_project_registry()
        assert "../.." not in registry
        assert "good-slug" in registry


# ------------------------------------------- L2: indented frontmatter keys


class TestL2IndentedFrontmatterKeys:
    def test_indented_key_not_treated_as_top_level(self):
        import importlib.util
        from pathlib import Path

        spec = importlib.util.spec_from_file_location(
            "pk1_migrate_l2",
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "project-knowledge-1"
            / "migrate.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        text = "---\nmeta:\n  type: nested-value\n---\nbody\n"
        out = mod.normalize_frontmatter(text, "p")
        assert "  type: nested-value" in out, "indented YAML key was rewritten"
        assert "\ntype: project-knowledge" in out
