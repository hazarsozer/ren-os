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


def _seed_eligibility(root, page, source_session, *, trust=None):
    (root / page).parent.mkdir(parents=True, exist_ok=True)
    fm = "---\ntype: knowledge\n"
    if trust:
        fm += f"ren_trust: {trust}\n"
    fm += "---\n"
    (root / page).write_text(fm + "# existing\nold body\n", encoding="utf-8")
    collect.record(collect.KIND_WAKEUP_SURFACE,
                   {"pages": [page], "session": source_session})


def _update_candidate(item, content, target_page, source_session, project=None):
    return {"item": item, "source_session": source_session, "project": project,
            "content": content, "page": None,
            "verdict": {"verdict": "durable", "reason": "r", "scope": "global",
                        "action": "update", "target_page": target_page}}


def test_apply_candidates_update_path_applies_via_write_door(wiki):
    page = "knowledge/target.md"
    _seed_eligibility(wiki, page, "dsess-1")
    cand = _update_candidate("updated fact", "# existing\nnew body\n", page, "dsess-1")
    result = apply_candidates([cand], run_session="distill-run-4")
    assert len(result["applied"]) == 1
    assert result["applied"][0]["page"] == page
    assert result["applied"][0]["op"] == "UPDATE"
    assert result["held"] == [] and result["suggested"] == []


def test_apply_candidates_update_user_trust_routes_to_suggested(wiki):
    page = "knowledge/human-owned.md"
    _seed_eligibility(wiki, page, "dsess-2", trust="user")
    cand = _update_candidate("updated fact", "# existing\nnew body\n", page, "dsess-2")
    result = apply_candidates([cand], run_session="distill-run-5")
    assert result["applied"] == []
    assert len(result["suggested"]) == 1


def test_apply_candidates_watermark_after_stops_before_unprocessed_session(wiki):
    batch = [
        {"session": "s1", "ren_ts": "2026-08-01T00:00:00Z"},
        {"session": "s2", "ren_ts": "2026-08-02T00:00:00Z"},
        {"session": "s3", "ren_ts": "2026-08-03T00:00:00Z"},
    ]
    cands = [_durable_create(f"item {i}", f"# L{i}\nbody") for i in range(WRITE_CAP)]
    for c in cands:
        c["source_session"] = "s1"
    overflow = _durable_create("overflow item", "# over\nbody")
    overflow["source_session"] = "s2"
    cands.append(overflow)

    result = apply_candidates(cands, run_session="distill-run-6", batch=batch,
                              watermark_before=None)
    assert result["capped_remainder"] == 1
    assert result["watermark_after"] == "2026-08-01T00:00:00Z"


def test_apply_candidates_watermark_after_full_batch_no_remainder(wiki):
    batch = [
        {"session": "s1", "ren_ts": "2026-08-01T00:00:00Z"},
        {"session": "s2", "ren_ts": "2026-08-02T00:00:00Z"},
    ]
    cands = [_durable_create("only item", "# x\nbody")]
    cands[0]["source_session"] = "s1"
    result = apply_candidates(cands, run_session="distill-run-7", batch=batch)
    assert result["capped_remainder"] == 0
    assert result["watermark_after"] == "2026-08-02T00:00:00Z"


def test_apply_candidates_no_batch_watermark_after_none(wiki):
    cands = [_durable_create("only item", "# x\nbody")]
    result = apply_candidates(cands, run_session="distill-run-8")
    assert result["watermark_after"] is None


def test_apply_candidates_duplicate_bucket_excluded_from_cap(wiki):
    page = "lessons/dup-item.md"
    content = "# L\nbody"
    cand = _durable_create("dup item", content)
    cand["page"] = page
    # Land it once so a re-run of the exact same content is a noop-duplicate.
    first = apply_candidates([cand], run_session="distill-run-9a")
    assert len(first["applied"]) == 1

    rerun_cands = [_durable_create("dup item", content) for _ in range(3)]
    for c in rerun_cands:
        c["page"] = page
    result = apply_candidates(rerun_cands, run_session="distill-run-9b")
    assert len(result["duplicates"]) == 3
    assert result["applied"] == [] and result["held"] == []
    assert result["capped_remainder"] == 0
    run_event = collect.read(kind="distiller_run")[-1]
    assert run_event["duplicates"] == 3


def test_watermark_holds_when_the_earliest_entry_is_blocked():
    """Spec §3.4: sessions with unprocessed candidates must stay BEHIND the
    watermark so their L1s are re-mined. If even the batch's earliest entry
    belongs to one, nothing can safely advance."""
    from skills.distill.lib import _watermark_after

    batch = [
        {"ren_ts": "2026-08-01T00:00:00Z", "session": "s1"},
        {"ren_ts": "2026-08-02T00:00:00Z", "session": "s2"},
    ]
    unprocessed = [{"source_session": "s1"}]

    assert _watermark_after(batch, unprocessed) is None


def test_watermark_same_timestamp_boundary_is_strict():
    """`safe` is entries STRICTLY below the blocked floor. An entry sharing
    the blocked session's exact ren_ts must not be treated as safe."""
    from skills.distill.lib import _watermark_after

    batch = [
        {"ren_ts": "2026-08-01T00:00:00Z", "session": "s0"},
        {"ren_ts": "2026-08-02T00:00:00Z", "session": "s1"},
        {"ren_ts": "2026-08-02T00:00:00Z", "session": "s2"},
    ]
    unprocessed = [{"source_session": "s2"}]

    assert _watermark_after(batch, unprocessed) == "2026-08-01T00:00:00Z"


def test_watermark_no_remainder_takes_the_batch_max():
    from skills.distill.lib import _watermark_after

    batch = [
        {"ren_ts": "2026-08-01T00:00:00Z", "session": "s1"},
        {"ren_ts": "2026-08-03T00:00:00Z", "session": "s2"},
    ]

    assert _watermark_after(batch, []) == "2026-08-03T00:00:00Z"


def test_watermark_none_batch_never_guesses():
    from skills.distill.lib import _watermark_after

    assert _watermark_after(None, []) is None
    assert _watermark_after(None, [{"source_session": "s1"}]) is None
