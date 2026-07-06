"""pytest wrapper around scripts/lint_no_dev_wiki_content.py.

The lint itself is a standalone script (importable here, and also runnable
directly in CI per the repo's script-lint convention). This test exercises it
against the real template roots and, separately, proves it actually catches
drift by scanning a synthetic tmp_path fixture seeded with a forbidden
substring.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from lint_no_dev_wiki_content import (  # noqa: E402
    load_forbidden_substrings,
    main,
    scan_file,
)

FORBIDDEN_FILE = REPO_ROOT / "scripts" / "forbidden-substrings.txt"


def test_real_templates_pass_the_lint():
    assert main([str(REPO_ROOT / "scripts" / "lint_no_dev_wiki_content.py")]) == 0


def test_lint_catches_seeded_forbidden_substring(tmp_path):
    templates_root = tmp_path / "templates"
    templates_root.mkdir()
    leaked = templates_root / "leaked.md.tmpl"
    leaked.write_text("See ADR-042 for background on Hazar's decision.\n", encoding="utf-8")

    substrings = load_forbidden_substrings(FORBIDDEN_FILE)
    hits = scan_file(leaked, substrings)

    assert hits, "expected the seeded 'Hazar' substring to be caught"
    assert any(hit.substring.lower() == "hazar" for hit in hits)


def test_clean_synthetic_template_produces_no_hits(tmp_path):
    templates_root = tmp_path / "templates"
    templates_root.mkdir()
    clean = templates_root / "clean.md.tmpl"
    clean.write_text("# Clean Template\n\nNothing forbidden here.\n", encoding="utf-8")

    substrings = load_forbidden_substrings(FORBIDDEN_FILE)
    hits = scan_file(clean, substrings)

    assert hits == []
