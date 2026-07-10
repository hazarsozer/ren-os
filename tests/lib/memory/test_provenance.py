"""
Tests for lib.memory.provenance — the G2 provenance module (Task 1.1).

Frozen interface (spec §3.1 "Provenance", council A-2): every memory write carries
writer class, source session, timestamp, and op. This module is the single place
that stamps and reads that metadata in a wiki page's YAML frontmatter.

Run with: uv run pytest tests/lib/memory/test_provenance.py -v
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from lib.memory.provenance import (
    Provenance,
    TRUST_CLASSES,
    new_provenance,
    read_frontmatter_provenance,
    stamp_frontmatter,
    trust_class,
)


ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


# --- new_provenance ----------------------------------------------------------


def test_new_provenance_write_id_format():
    prov = new_provenance("human", "sess-1", "ADD", "projects/demo/notes.md")
    assert prov.write_id.startswith("w-")
    assert ULID_RE.match(prov.write_id[2:])


def test_new_provenance_write_id_is_unique():
    a = new_provenance("human", "sess-1", "ADD", "page.md")
    b = new_provenance("human", "sess-1", "ADD", "page.md")
    assert a.write_id != b.write_id


def test_new_provenance_ts_is_utc_iso8601():
    prov = new_provenance("llm-auto", "sess-1", "UPDATE", "page.md")
    # Must parse as ISO-8601 and be timezone-aware UTC.
    parsed = datetime.strptime(prov.ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert parsed.tzinfo is timezone.utc
    # Sanity: round-trips close to "now".
    assert abs((datetime.now(timezone.utc) - parsed).total_seconds()) < 10


def test_new_provenance_fields_carried_through():
    prov = new_provenance("routine", "sess-42", "DELETE", "wiki/gaps/x.md", supersedes="w-OLD")
    assert prov.writer == "routine"
    assert prov.session == "sess-42"
    assert prov.op == "DELETE"
    assert prov.page == "wiki/gaps/x.md"
    assert prov.supersedes == "w-OLD"


def test_new_provenance_supersedes_defaults_to_none():
    prov = new_provenance("human", "sess-1", "ADD", "page.md")
    assert prov.supersedes is None


def test_new_provenance_rejects_invalid_writer():
    with pytest.raises(ValueError):
        new_provenance("robot", "sess-1", "ADD", "page.md")


def test_new_provenance_rejects_invalid_op():
    with pytest.raises(ValueError):
        new_provenance("human", "sess-1", "MODIFY", "page.md")


@pytest.mark.parametrize("writer", ["human", "llm-auto", "retrospective", "routine"])
def test_new_provenance_accepts_all_writer_classes(writer):
    assert new_provenance(writer, "sess-1", "NOOP", "page.md").writer == writer


@pytest.mark.parametrize("op", ["ADD", "UPDATE", "DELETE", "NOOP"])
def test_new_provenance_accepts_all_ops(op):
    assert new_provenance("human", "sess-1", op, "page.md").op == op


def test_provenance_is_frozen():
    prov = new_provenance("human", "sess-1", "ADD", "page.md")
    with pytest.raises(Exception):
        prov.op = "DELETE"  # type: ignore[misc]


def test_provenance_direct_construction_rejects_invalid_writer():
    with pytest.raises(ValueError):
        Provenance(
            write_id="w-XXX", ts="2026-01-01T00:00:00Z", writer="bogus",
            session="s", op="ADD", page="p.md", supersedes=None,
        )


def test_provenance_direct_construction_rejects_invalid_op():
    with pytest.raises(ValueError):
        Provenance(
            write_id="w-XXX", ts="2026-01-01T00:00:00Z", writer="human",
            session="s", op="BOGUS", page="p.md", supersedes=None,
        )


# --- stamp_frontmatter / read_frontmatter_provenance round-trip -------------


def test_stamp_creates_frontmatter_when_absent():
    prov = new_provenance("human", "sess-1", "ADD", "page.md")
    body = "# Title\n\nSome body text.\n"
    stamped = stamp_frontmatter(body, prov)
    assert stamped.startswith("---\n")
    assert "ren_write_id:" in stamped
    assert body in stamped


def test_stamp_then_read_round_trips():
    prov = new_provenance("llm-auto", "sess-1", "UPDATE", "page.md", supersedes="w-OLD123")
    stamped = stamp_frontmatter("# Doc\n\nbody\n", prov)
    read = read_frontmatter_provenance(stamped)
    assert read is not None
    assert read["write_id"] == prov.write_id
    assert read["ts"] == prov.ts
    assert read["writer"] == prov.writer
    assert read["op"] == prov.op
    assert read["supersedes"] == prov.supersedes


def test_stamp_omits_supersedes_key_when_none():
    prov = new_provenance("human", "sess-1", "ADD", "page.md")
    stamped = stamp_frontmatter("body\n", prov)
    assert "ren_supersedes" not in stamped
    read = read_frontmatter_provenance(stamped)
    assert read["supersedes"] is None


def test_restamp_replaces_ren_keys_without_duplicating():
    prov1 = new_provenance("human", "sess-1", "ADD", "page.md")
    once = stamp_frontmatter("---\ntitle: Demo\n---\nbody text\n", prov1)

    prov2 = new_provenance("routine", "sess-2", "UPDATE", "page.md", supersedes=prov1.write_id)
    twice = stamp_frontmatter(once, prov2)

    assert twice.count("ren_write_id:") == 1
    assert twice.count("ren_ts:") == 1
    assert twice.count("ren_writer:") == 1
    assert twice.count("ren_op:") == 1
    assert twice.count("ren_supersedes:") == 1

    read = read_frontmatter_provenance(twice)
    assert read["write_id"] == prov2.write_id
    assert read["writer"] == "routine"
    assert read["supersedes"] == prov1.write_id


def test_restamp_preserves_other_frontmatter_keys():
    prov1 = new_provenance("human", "sess-1", "ADD", "page.md")
    original = "---\ntitle: Demo\ntype: project\ncustom_key: hello\n---\nbody text\n"
    once = stamp_frontmatter(original, prov1)

    prov2 = new_provenance("routine", "sess-2", "UPDATE", "page.md")
    twice = stamp_frontmatter(once, prov2)

    assert "title: Demo" in twice
    assert "type: project" in twice
    assert "custom_key: hello" in twice


def test_restamp_preserves_body_byte_for_byte():
    prov1 = new_provenance("human", "sess-1", "ADD", "page.md")
    body = "\n# Heading\n\nParagraph one.\n\n- bullet\n- bullet 2\n\ntrailing text\n"
    original = f"---\ntitle: Demo\n---\n{body}"
    once = stamp_frontmatter(original, prov1)

    prov2 = new_provenance("routine", "sess-2", "UPDATE", "page.md")
    twice = stamp_frontmatter(once, prov2)

    assert twice.endswith(body)


def test_stamp_no_frontmatter_preserves_body_byte_for_byte():
    prov = new_provenance("human", "sess-1", "ADD", "page.md")
    body = "# No frontmatter here\n\njust a body.\n"
    stamped = stamp_frontmatter(body, prov)
    assert stamped.endswith(body)


def test_read_frontmatter_provenance_returns_none_when_unstamped():
    assert read_frontmatter_provenance("---\ntitle: Demo\n---\nbody\n") is None


def test_read_frontmatter_provenance_returns_none_when_no_frontmatter():
    assert read_frontmatter_provenance("just a plain markdown body\n") is None


# --- trust taxonomy (0.5.1, Task 6) -----------------------------------------


def test_trust_class_human_writer_is_user():
    assert trust_class("human", "wrap") == "user"


def test_trust_class_ingest_producer_is_foreign():
    assert trust_class("llm-auto", "ingest") == "foreign"


def test_trust_class_otherwise_is_model():
    assert trust_class("llm-auto", "wrap") == "model"
    assert trust_class("retrospective", "retrospective") == "model"


def test_trust_class_human_writer_wins_over_ingest_producer():
    # writer=="human" always wins, even if producer happens to be "ingest".
    assert trust_class("human", "ingest") == "user"


def test_new_provenance_trust_defaults_to_model():
    prov = new_provenance("llm-auto", "sess-1", "ADD", "page.md")
    assert prov.trust == "model"


def test_new_provenance_carries_trust_kwarg():
    prov = new_provenance("human", "sess-1", "ADD", "page.md", trust="user")
    assert prov.trust == "user"


def test_new_provenance_rejects_invalid_trust():
    with pytest.raises(ValueError):
        new_provenance("human", "sess-1", "ADD", "page.md", trust="bogus")


def test_stamp_frontmatter_writes_ren_trust_user_for_human_write():
    prov = new_provenance("human", "sess-1", "ADD", "page.md", trust="user")
    stamped = stamp_frontmatter("# Title\n\nbody\n", prov)
    assert 'ren_trust: "user"' in stamped
    read = read_frontmatter_provenance(stamped)
    assert read["trust"] == "user"


def test_trust_classes_tuple_contents():
    assert set(TRUST_CLASSES) == {"user", "model", "foreign"}


def test_stamped_ts_stays_a_string_not_yaml_timestamp():
    """Guards against PyYAML's implicit timestamp resolver silently turning an
    unquoted ISO-8601 scalar into a datetime object on read-back."""
    prov = new_provenance("human", "sess-1", "ADD", "page.md")
    stamped = stamp_frontmatter("body\n", prov)
    read = read_frontmatter_provenance(stamped)
    assert isinstance(read["ts"], str)
    assert read["ts"] == prov.ts
