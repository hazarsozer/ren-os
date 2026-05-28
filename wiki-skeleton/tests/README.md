# wiki-skeleton/tests/

Lint guard against ADR-017's R4 risk (dev-wiki content drift into the user-shipped skeleton).

## Files

- `lint_no_dev_wiki_content.py` — the lint itself. Stdlib only (Python 3.10+).
- `forbidden-substrings.txt` — curated case-insensitive substring blocklist. Extend when PR review catches new drift.

## Run locally

From the repo root:

```bash
python wiki-skeleton/tests/lint_no_dev_wiki_content.py
```

Or from inside `wiki-skeleton/`:

```bash
python tests/lint_no_dev_wiki_content.py
```

Exit codes:

- `0` — clean (no forbidden substrings found, or no template files present)
- `1` — at least one hit; one line per hit printed to stdout, summary to stderr

## Wire into CI

CI doesn't exist for this repo yet. When it lands (likely GitHub Actions on the marketplace repo), add a job step:

```yaml
- name: Lint wiki-skeleton for dev-wiki drift
  run: python wiki-skeleton/tests/lint_no_dev_wiki_content.py
```

Until then: contributors run it before every PR that touches `wiki-skeleton/templates/`.

## Adding a new forbidden substring

1. Caught a PR that leaked dev-wiki content? Add the offending substring to `forbidden-substrings.txt`.
2. Keep entries narrow enough to avoid false positives. Prefer specific phrases over single common words.
3. Add a comment in `forbidden-substrings.txt` documenting which category the entry belongs to (the file's section headers list current categories).

## Whitelisting a substitution

Template files use `{{handle}}` / `{{name}}` / `{{today}}` / `{{framework_version}}` placeholders. The lint runs against the raw `.tmpl` content, not the substituted output, so any forbidden substring would still trip even if it lives inside a placeholder. Don't put forbidden content in placeholder defaults.

## Why this exists (the load-bearing piece)

Per ADR-017: the framework's development wiki (16+ ADRs, 25+ research pages, founder context) is OURS — not what ships to the friend. A friend's wiki starts EMPTY. If a contributor (or future Claude) accidentally drops an example ADR title or a citation into a template "to make it look populated," the friend's wiki inherits that drift forever. This lint makes drift visible at PR time.
