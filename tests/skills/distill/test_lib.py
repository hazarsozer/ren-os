import json

import pytest

from lib.instrument import collect
from skills.distill.lib import (
    WRITE_CAP,
    apply_candidates,
    l1_batch,
    read_watermark,
    watermark_path,
    write_watermark,
)

L1_TEMPLATE = """---
title: "s"
type: l1
ren_ts: "{ts}"
---
# Narrative for {name}
A learning happened.
"""


@pytest.fixture
def wiki(tmp_path, monkeypatch):
    root = tmp_path / "wiki"
    (root / "projects" / "alpha" / "l1").mkdir(parents=True)
    (root / "l1").mkdir(parents=True)
    monkeypatch.setenv("REN_WIKI_ROOT", str(root))
    return root


def _l1(root, rel, ts):
    p = root / rel
    p.write_text(L1_TEMPLATE.format(ts=ts, name=p.stem), encoding="utf-8")


def test_watermark_roundtrip(wiki):
    assert read_watermark() is None
    write_watermark("2026-08-03T00:00:00Z")
    assert read_watermark() == "2026-08-03T00:00:00Z"
    assert watermark_path().name == "distiller-watermark.json"


def test_l1_batch_filters_and_sorts(wiki):
    _l1(wiki, "projects/alpha/l1/session-old.md", "2026-08-01T00:00:00Z")
    _l1(wiki, "projects/alpha/l1/session-mid.md", "2026-08-10T00:00:00Z")
    _l1(wiki, "l1/session-new.md", "2026-08-15T00:00:00Z")
    batch = l1_batch("2026-08-03T00:00:00Z")
    assert [b["session"] for b in batch] == ["mid", "new"]
    assert batch[0]["project"] == "alpha" and batch[1]["project"] is None
    assert "Narrative" in batch[0]["escaped_body"]


def test_l1_batch_none_returns_all(wiki):
    _l1(wiki, "l1/session-a.md", "2026-08-01T00:00:00Z")
    assert len(l1_batch(None)) == 1


def _durable_create(item, content, project=None):
    return {"item": item, "source_session": "s-x", "project": project,
            "content": content, "page": None,
            "verdict": {"verdict": "durable", "reason": "r", "scope": "global",
                        "action": "create", "target_page": None}}


def test_apply_candidates_caps_at_write_cap(wiki):
    cands = [_durable_create(f"item {i}", f"# L{i}\nbody") for i in range(WRITE_CAP + 3)]
    result = apply_candidates(cands, run_session="distill-run-1")
    assert len(result["applied"]) + len(result["held"]) == WRITE_CAP
    assert result["capped_remainder"] == 3
    run_event = collect.read(kind="distiller_run")[-1]
    assert run_event["capped_remainder"] == 3
    outcome = collect.read(kind=collect.KIND_DURABLE_OUTCOME)[-1]
    assert outcome["producer"] == "distiller"


def test_apply_candidates_placement_error_to_suggestions(wiki):
    bad = _durable_create("orphan", "# x\nbody")
    bad["verdict"]["scope"] = None
    result = apply_candidates([bad], run_session="distill-run-2")
    assert result["applied"] == [] and len(result["suggested"]) == 1


def test_apply_candidates_non_durable_gates_out(wiki):
    c = _durable_create("noise", "# x\nbody")
    c["verdict"]["verdict"] = "discard"
    result = apply_candidates([c], run_session="distill-run-3")
    assert len(result["gated_out"]) == 1 and result["applied"] == []
