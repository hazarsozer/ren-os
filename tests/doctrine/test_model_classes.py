from pathlib import Path
import re

DOC = Path("doctrine/model-classes.md")


def _rows():
    rows = [l for l in DOC.read_text().splitlines() if l.startswith("|") and "---" not in l]
    return [tuple(c.strip() for c in r.strip("|").split("|")) for r in rows[1:]]


def test_three_classes_present():
    assert {r[0] for r in _rows()} == {"orchestrator", "worker", "classifier"}


def test_every_class_names_at_least_one_model():
    assert all(r[1] for r in _rows())


def test_updated_stamp_present():
    assert re.search(r"renos:model-map-updated: \d{4}-\d{2}-\d{2}", DOC.read_text())


def test_no_model_names_outside_mapping_file():
    """Doctrine speaks in classes; model names live only in model-classes.md."""
    for p in Path("doctrine").glob("*.md"):
        if p.name == "model-classes.md":
            continue
        text = p.read_text().lower()
        for name in ("haiku", "sonnet", "opus", "fable"):
            assert name not in text, f"{p}: model name '{name}' outside mapping file"
