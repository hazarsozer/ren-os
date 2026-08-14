# Quarantine-Exit Fix-Train + Project Standing Instructions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the quarantine-exit trio (#52 decline-hold, #51 audit metric, #46 8k cap) plus the archive-lint rider, and build project-scoped standing instructions (#63).

**Architecture:** Tasks 1–4 are independent bounded fixes to existing flows (judge cap, lint walker, quarantine release paths). Tasks 5–9 build #63 in dependency order: instruction-plane predicate → promotion entry path → CLAUDE.md render → apply-hook + wake-up exclusion → doctor check + end-to-end. Every wiki write goes through the existing single write door; no new write paths.

**Tech Stack:** Python ≥3.11, uv, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-14-project-standing-instructions-design.md` (covers Tasks 5–9; Tasks 1–4 were designed in chat — their contracts are fully restated here).

## Global Constraints

- Run all tests with `uv run pytest <path> -v` from the repo root (`/Users/hazarsozer/Dev/ren-os`).
- Never write to `~/.renos/wiki` in tests — every test uses tmp_path fixtures (see `tests/conftest.py` for the existing `wiki` fixture pattern; `REN_WIKI_ROOT` env var overrides the wiki root).
- All wiki writes go through `lib.memory.queue` (`propose` / `approve_and_apply` / `propose_and_apply`) — never a direct file write to a wiki page.
- Fail closed everywhere: any doubt in a quarantine-exit path leaves the page quarantined; any render doubt renders nothing.
- Doctor checks are warn-not-block: statuses are `"ok" | "warn" | "info" | "skip" | "error"`, never an exception.
- Commit after every task with a conventional-commit message ending in the Co-Authored-By trailer.
- Match surrounding code style: module-level docstrings explain WHY, `Final` type annotations on constants, lazy imports inside functions where the existing code does that.

---

### Task 1: #46 — raise the judge text cap to 8,000 chars

**Files:**
- Modify: `lib/memory/judge.py:49` (`_MAX_TEXT_CHARS`)
- Test: `tests/skills/wiki_health/test_quarantine_screen.py` (existing tests already use the `JUDGE_MAX_TEXT_CHARS` export, so they track the new value automatically), plus one new pin test in `tests/lib/memory/test_judge_cap.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `lib.memory.judge.JUDGE_MAX_TEXT_CHARS == 8_000` (read by the quarantine screen and Task 4's tests).

- [ ] **Step 1: Write the failing test**

Create `tests/lib/memory/test_judge_cap.py`:

```python
"""#46: the 4,000-char cap routed 14/20 screened candidates to the human as
`too-long` (all only marginally over: 4,016-5,816 chars) — the suggestions
store became the de-facto quarantine exit. 8,000 covers every observed page
with headroom while keeping the judge on WHOLE pages (no excerpt judging)."""

from lib.memory.judge import JUDGE_MAX_TEXT_CHARS, build_judge_prompt


def test_cap_is_8000():
    assert JUDGE_MAX_TEXT_CHARS == 8_000


def test_truncate_keeps_tail_at_new_cap():
    text = "x" * 100 + "T" * 8_000
    prompt = build_judge_prompt(text, "b")
    assert "T" * 8_000 in prompt        # full 8k tail survives
    assert "x" not in prompt            # 100 head chars truncated away
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/lib/memory/test_judge_cap.py -v`
Expected: FAIL — `assert 4000 == 8000`

- [ ] **Step 3: Change the constant**

In `lib/memory/judge.py` line 49:

```python
_MAX_TEXT_CHARS: Final[int] = 8_000
```

Update the comment above `JUDGE_MAX_TEXT_CHARS` only if it hardcodes "4,000" in prose (it doesn't today — it says "Same value as `_MAX_TEXT_CHARS`").

- [ ] **Step 4: Run the full affected suites**

Run: `uv run pytest tests/lib/memory/test_judge_cap.py tests/skills/wiki_health/ -v`
Expected: ALL PASS (screen tests use the export, not the literal).

- [ ] **Step 5: Commit**

```bash
git add lib/memory/judge.py tests/lib/memory/test_judge_cap.py
git commit -m "fix(judge): raise text cap to 8k so the screen judges long-but-normal pages (#46)"
```

---

### Task 2: archive-lint rider — exclude `archive/` from the incremental lint

**Files:**
- Modify: `skills/wiki-health/lib/lint.py` (`walk_wiki_pages`, ~line 75; the `run_incremental_lint` call site that invokes it, ~line 405+)
- Modify: `skills/wiki-health/lib/__init__.py` (`_in_archive`, line 422 — move it to `lint.py`, re-import in `__init__.py` from `.lint`)
- Test: `tests/skills/wiki_health/test_lint_archive_scope.py` (new)

**Interfaces:**
- Consumes: `lib.ren_paths.in_project_raw(parts)` (existing predicate, same shape).
- Produces: `walk_wiki_pages(wiki_root, skip_raw=False, skip_archive=False)` — new keyword param; `in_archive(parts)` public in `skills/wiki-health/lib/lint.py` (renamed from `_in_archive`, imported by `__init__.py` as `_in_archive = in_archive` to keep existing internal callers at lines 506/570 working unchanged).

- [ ] **Step 1: Write the failing test**

Create `tests/skills/wiki_health/test_lint_archive_scope.py`:

```python
"""#52 side observation: the wrap close-out lint sweep flags archive/l1/*
copies for missing-frontmatter-type. archive/ is a graveyard of point-in-time
copies, not live claims — excluded from lint scope like raw/ (same noise
class as #31)."""

import importlib

lint = importlib.import_module("skills.wiki-health.lib.lint")


def _mk(root, rel, text="body, no frontmatter\n"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_walk_skips_archive_when_asked(tmp_path):
    _mk(tmp_path, "archive/l1/old-session.md")
    _mk(tmp_path, "projects/flux/archive/notes.md")
    _mk(tmp_path, "projects/flux/knowledge/live.md")
    pages = lint.walk_wiki_pages(tmp_path, skip_archive=True)
    assert pages == ["projects/flux/knowledge/live.md"]


def test_walk_keeps_archive_by_default(tmp_path):
    _mk(tmp_path, "archive/l1/old-session.md")
    pages = lint.walk_wiki_pages(tmp_path)
    assert "archive/l1/old-session.md" in pages


def test_knowledge_archive_is_not_exempt(tmp_path):
    # only root archive/ and projects/<slug>/archive/ — never arbitrary depth
    _mk(tmp_path, "projects/flux/knowledge/archive/deep.md")
    pages = lint.walk_wiki_pages(tmp_path, skip_archive=True)
    assert "projects/flux/knowledge/archive/deep.md" in pages
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/skills/wiki_health/test_lint_archive_scope.py -v`
Expected: FAIL — `walk_wiki_pages() got an unexpected keyword argument 'skip_archive'`

- [ ] **Step 3: Implement**

In `skills/wiki-health/lib/lint.py`, move the predicate from `__init__.py` (delete it there) and extend the walker:

```python
def in_archive(parts: tuple[str, ...]) -> bool:
    """Spec-exact archive exemption: `archive/` at the wiki root, or
    `projects/<slug>/archive/` — NOT an `archive` dir at arbitrary depth
    (that would silently exempt e.g. `projects/x/knowledge/archive/n.md`).
    Mirrors `ren_paths.in_project_raw`'s shape for the project-scoped case.
    Moved here from `__init__.py` (#52 rider) so the walker can use it
    without a circular import."""
    if parts and parts[0] == "archive":
        return True
    return len(parts) >= 3 and parts[0] == "projects" and parts[2] == "archive"


def walk_wiki_pages(
    wiki_root: Path, skip_raw: bool = False, skip_archive: bool = False
) -> list[str]:
    pages: list[str] = []
    for md_path in sorted(wiki_root.rglob("*.md")):
        parts = md_path.relative_to(wiki_root).parts
        if ".ren" in parts:
            continue
        if skip_raw and ren_paths.in_project_raw(parts):
            continue
        if skip_archive and in_archive(parts):
            continue
        pages.append(md_path.relative_to(wiki_root).as_posix())
    return pages
```

In `run_incremental_lint` (same file), find the `walk_wiki_pages(...)` call and add `skip_archive=True` (keep its existing `skip_raw` argument exactly as it is).

In `skills/wiki-health/lib/__init__.py`: delete the `_in_archive` definition at line 422 and add to the existing `from .lint import ...` line (line 94): `from .lint import in_archive as _in_archive` — internal callers at lines 506/570 keep working unchanged.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/skills/wiki_health/ -v`
Expected: ALL PASS (new file + no regressions in sweep/screen tests).

- [ ] **Step 5: Commit**

```bash
git add skills/wiki-health/lib/lint.py skills/wiki-health/lib/__init__.py tests/skills/wiki_health/test_lint_archive_scope.py
git commit -m "fix(wiki-health): exclude archive/ from incremental lint scope (#52 rider)"
```

---

### Task 3: #51 — audit trail on every quarantine release path

**Files:**
- Modify: `skills/wiki-health/lib/__init__.py` (`release_page` line 1124; `release_page_auto`'s `collect.record` call ~line 1256)
- Modify: `skills/suggestions/lib/__init__.py` (the `action == "quarantine_release"` branch, ~line 160)
- Test: `tests/skills/wiki_health/test_release_audit.py` (new)

**Interfaces:**
- Consumes: `lib.instrument.collect.KIND_QUARANTINE_RELEASE` (= `"quarantine_release"`), `collect.record(kind, data)`.
- Produces: `release_page(page, session, *, via="human-direct", evidence=None)` — new keyword-only params, existing positional callers unaffected. Metric data dict gains `"via"`: `"machine"` (auto), `"suggestion-accepted"`, or `"human-direct"`.

- [ ] **Step 1: Write the failing test**

Create `tests/skills/wiki_health/test_release_audit.py`. Look at `tests/skills/wiki_health/test_quarantine_screen.py` first and reuse its fixture pattern for building a quarantined page in a tmp wiki and reading recorded metrics (it asserts on `collect` records already — copy the same monkeypatch/fixture approach rather than inventing a new one). The three tests:

```python
def test_release_page_records_metric_with_via(wiki_with_quarantined_page, recorded_metrics):
    # wiki fixture provides a quarantined model-trust page at rel
    wiki_health.release_page(rel, "sess-t3", via="suggestion-accepted",
                             evidence={"judge": {"confidence": 0.9}})
    events = [e for e in recorded_metrics if e["kind"] == collect.KIND_QUARANTINE_RELEASE]
    assert len(events) == 1
    assert events[0]["data"]["via"] == "suggestion-accepted"
    assert events[0]["data"]["evidence"] == {"judge": {"confidence": 0.9}}


def test_release_page_default_via_is_human_direct(wiki_with_quarantined_page, recorded_metrics):
    wiki_health.release_page(rel, "sess-t3")
    events = [e for e in recorded_metrics if e["kind"] == collect.KIND_QUARANTINE_RELEASE]
    assert events[0]["data"]["via"] == "human-direct"
    assert events[0]["data"]["evidence"] == {}


def test_release_page_auto_metric_carries_via_machine(wiki_with_quarantined_page, recorded_metrics):
    wiki_health.release_page_auto(rel, "sess-t3", {"judge": {"confidence": 0.9, "reason": "r"}})
    events = [e for e in recorded_metrics if e["kind"] == collect.KIND_QUARANTINE_RELEASE]
    assert events[0]["data"]["via"] == "machine"
```

(Adapt fixture names to what `test_quarantine_screen.py` actually provides — the assertions are the contract.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/skills/wiki_health/test_release_audit.py -v`
Expected: FAIL — `release_page() got an unexpected keyword argument 'via'`

- [ ] **Step 3: Implement**

In `release_page`, change the signature and add the metric record after the successful `approve_and_apply` (mirror `release_page_auto`'s lazy import style):

```python
def release_page(
    page: str, session: str, *, via: str = "human-direct", evidence: dict | None = None
) -> tuple:
```

and immediately after `prov = approve_and_apply(entry.qid, who="human:quarantine-release")`:

```python
    from lib.instrument import collect

    collect.record(
        collect.KIND_QUARANTINE_RELEASE,
        {"page": page, "session": session, "via": via, "evidence": evidence or {}},
    )
```

Extend the docstring: the metric is recorded only on a completed release (held/no-op paths return before it), `via` distinguishes the three exit flavors, and `evidence` is the suggestion payload's judge/ineligibility dict when the release came through `/ren:suggestions` (#51).

In `release_page_auto`'s existing `collect.record` call, add `"via": "machine"` to the data dict.

In `skills/suggestions/lib/__init__.py`, the `quarantine_release` branch:

```python
    if action == "quarantine_release":
        wiki_health = importlib.import_module("skills.wiki-health.lib")
        entry, prov = wiki_health.release_page(
            payload["page"], session,
            via="suggestion-accepted", evidence=payload.get("evidence") or {},
        )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/skills/wiki_health/ tests/skills/suggestions/ -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/wiki-health/lib/__init__.py skills/suggestions/lib/__init__.py tests/skills/wiki_health/test_release_audit.py
git commit -m "fix(wiki-health): record KIND_QUARANTINE_RELEASE with via on every release path (#51)"
```

---

### Task 4: #52 — a human decline holds the machine exit until content changes

**Files:**
- Modify: `lib/suggestions/__init__.py` (`decide` ledger line, ~line 195; new `ledger_entries()` accessor)
- Modify: `skills/wiki-health/lib/__init__.py` (`_record_release_suggestion` ~line 1263; `run_quarantine_screen` ~line 1281; `apply_quarantine_verdicts` ~line 1354; new `declined_release_holds`)
- Test: `tests/skills/wiki_health/test_declined_hold.py` (new), `tests/lib/suggestions/test_ledger_hash.py` (new)

**Interfaces:**
- Consumes: `lib.suggestions.ledger_fingerprints()` (triggers ledger backfill), suggestion payload dicts.
- Produces:
  - `lib.suggestions.ledger_entries() -> list[dict]` — parsed ledger lines (`fingerprint`, `decision`, `sid`, `ts`, optional `content_sha256`).
  - `decide()` ledger lines carry `"content_sha256"` copied from the entry's `payload["content_sha256"]` when present (absent key otherwise — no `None` noise).
  - `skills.wiki-health.lib.declined_release_holds(rel: str, text: str) -> bool`.
  - Screen result dicts gain a `"held_declined": [rel, ...]` key (both phases).

- [ ] **Step 1: Write the failing tests**

Create `tests/lib/suggestions/test_ledger_hash.py`:

```python
"""#52: the durable-decline ledger must carry the declined page's content
hash so the machine exit can distinguish 'same page the human declined'
from 'page changed since the decline'. Passthrough is generic: decide()
copies payload['content_sha256'] to the ledger line when present."""

from lib.suggestions import SuggestionSpec, decide, ledger_entries, record


def _spec(fp, payload):
    return SuggestionSpec(
        producer="wiki-health", title="t", rationale="r", evidence={},
        kind="structured_action", payload=payload, fingerprint=fp,
    )


def test_decline_ledgers_content_hash(suggestions_store):  # reuse existing store fixture
    entry = record(_spec("quarantine:release:p.md",
                         {"action": "quarantine_release", "page": "p.md",
                          "content_sha256": "abc123"}))
    decide(entry["sid"], "declined")
    lines = [e for e in ledger_entries() if e["fingerprint"] == "quarantine:release:p.md"]
    assert lines[0]["content_sha256"] == "abc123"


def test_decline_without_hash_omits_key(suggestions_store):
    entry = record(_spec("other:fp", {"action": "x"}))
    decide(entry["sid"], "declined")
    lines = [e for e in ledger_entries() if e["fingerprint"] == "other:fp"]
    assert "content_sha256" not in lines[0]
```

(Check `tests/lib/suggestions/` for the existing store-isolation fixture name and reuse it.)

Create `tests/skills/wiki_health/test_declined_hold.py` — reuse `test_quarantine_screen.py`'s wiki/store fixtures:

```python
import hashlib


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_declined_page_never_machine_releases_while_unchanged(...):
    # 1. build quarantined, eligible, model-trust page `rel` with text T
    # 2. record + decline a release suggestion whose payload carries _sha(T)
    # 3. run_quarantine_screen: rel must appear in result["held_declined"],
    #    NOT in result["candidates"]
    # 4. apply_quarantine_verdicts(session, {rel: <passing verdict json>}):
    #    rel in result["held_declined"], page still quarantined on disk


def test_content_change_lifts_the_hold(...):
    # decline recorded against _sha(T); page content then edited to T2
    # run_quarantine_screen: rel IS in result["candidates"]


def test_legacy_decline_without_hash_holds_unconditionally(...):
    # ledgered decline with no content_sha256 (the pre-train incident shape)
    # -> held_declined, never a candidate, even after content edits
```

Write these three fully against the real fixtures (the sketches above are the required behavior; the incident in #52 is test 1 exactly: judge nondeterminism re-sampling a declined, unchanged page).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/lib/suggestions/test_ledger_hash.py tests/skills/wiki_health/test_declined_hold.py -v`
Expected: FAIL — `ImportError: cannot import name 'ledger_entries'`

- [ ] **Step 3: Implement `lib/suggestions` side**

In `decide()`, extend the `_append_ledger_line` call:

```python
    line = {
        "fingerprint": entry["fingerprint"],
        "decision": decision,
        "sid": entry["sid"],
        "ts": entry["decided_at"],
    }
    payload = entry.get("payload")
    if isinstance(payload, dict) and isinstance(payload.get("content_sha256"), str):
        line["content_sha256"] = payload["content_sha256"]
    _append_ledger_line(line)
```

Add the accessor (below `ledger_fingerprints`):

```python
def ledger_entries() -> list[dict]:
    """Every decision-ledger line, parsed. Calls `ledger_fingerprints()`
    first so the pre-0.5.0 backfill path runs; unparsable lines are skipped
    with a stderr warning (same torn-file tolerance as everywhere else).
    Consumers: the #52 declined-release hold, which needs `decision` and the
    optional `content_sha256` alongside the fingerprint."""
    ledger_fingerprints()
    path = _ledger_path()
    if not path.exists():
        return []
    entries: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            print(f"ren suggestions: skipping unparsable ledger line: {exc}", file=sys.stderr)
    return entries
```

Export `ledger_entries` in the module's `__all__` if one exists.

- [ ] **Step 4: Implement `wiki-health` side**

Add near the screen section (after `screen_ineligibility`):

```python
def declined_release_holds(rel: str, text: str) -> bool:
    """#52: True when a recorded HUMAN decline of releasing `rel` must hold
    it out of the machine exit. Judge nondeterminism re-sampled a declined,
    unchanged page and released it around the decline (2026-08-04 incident);
    a decline now sticks until the page content actually changes.

    Fail-closed ordering: any declined ledger line for this page that
    carries no content hash (pre-train declines) holds unconditionally —
    change can't be proven, so it isn't assumed. With hashes present, the
    hold applies exactly while the current text's sha256 matches a declined
    one. The human path (`release_page`) is never gated by this."""
    import hashlib

    from lib.suggestions import ledger_entries

    fingerprint = f"quarantine:release:{rel}"
    declined = [
        e for e in ledger_entries()
        if e.get("fingerprint") == fingerprint and e.get("decision") == "declined"
    ]
    if not declined:
        return False
    hashes = {e.get("content_sha256") for e in declined}
    if None in hashes:
        return True
    return hashlib.sha256(text.encode("utf-8")).hexdigest() in hashes
```

In `_record_release_suggestion`, add the hash to the payload — change the signature to take the page text:

```python
def _record_release_suggestion(rel: str, why: str, evidence: dict, text: str = "") -> None:
```

and in the `payload=` dict add:

```python
            payload={
                "action": "quarantine_release",
                "page": rel,
                "evidence": evidence,
                "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            },
```

(`import hashlib` at module top; update ALL existing `_record_release_suggestion(...)` call sites in both screen phases to pass `text=text` — there are six.)

In `run_quarantine_screen`: initialize `"held_declined": []` in `result`, and after the `why is not None` block (page is eligible), before the too-long check:

```python
        if declined_release_holds(rel, text):
            result["held_declined"].append(rel)
            continue
```

In `apply_quarantine_verdicts`: same — initialize `"held_declined": []`, and insert the identical check after its `why is not None` block, before its too-long re-check. Add `declined_release_holds` to `__all__`.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/lib/suggestions/ tests/skills/wiki_health/ -v`
Expected: ALL PASS (existing screen tests unaffected — no declines recorded in their fixtures).

- [ ] **Step 6: Commit**

```bash
git add lib/suggestions/__init__.py skills/wiki-health/lib/__init__.py tests/lib/suggestions/test_ledger_hash.py tests/skills/wiki_health/test_declined_hold.py
git commit -m "fix(wiki-health): human decline holds machine release until content changes (#52)"
```

---

### Task 5: #63 — `projects/<slug>/instructions.md` joins the instruction plane

**Files:**
- Modify: `lib/governance/tiers.py` (`is_instruction_plane_page`, line 105; the `INSTRUCTION_PLANE_PREFIXES` docstring)
- Test: `tests/lib/governance/test_tiers.py` (extend)

**Interfaces:**
- Consumes: nothing new.
- Produces: `is_instruction_plane_page("projects/<slug>/instructions.md") is True` — automatically gates the queue (`propose_and_apply` holds pending), `apply_auto` (refuses), the quarantine screen (`screen_ineligibility` → `"instruction-plane"`), and lint fixability (`is_fixable_page` → False). Every consumer delegates to this predicate already; no other module changes.

- [ ] **Step 1: Write the failing tests** (append to `tests/lib/governance/test_tiers.py`)

```python
def test_project_instructions_page_is_instruction_plane():
    assert tiers.is_instruction_plane_page("projects/ren-os/instructions.md")


def test_project_instructions_normalized_form_is_gated():
    assert tiers.is_instruction_plane_page("./projects/ren-os/instructions.md")


def test_project_non_instructions_pages_stay_data_plane():
    assert not tiers.is_instruction_plane_page("projects/ren-os/map.md")
    assert not tiers.is_instruction_plane_page("projects/ren-os/knowledge/instructions.md")
    assert not tiers.is_instruction_plane_page("projects/ren-os/instructions/notes.md")


def test_project_instructions_write_holds_pending(wiki):
    # reuse this file's existing queue fixtures: a propose_and_apply targeting
    # projects/x/instructions.md with writer="llm-auto" must land status=="pending"
```

(Write the fourth test against the file's existing queue-fixture pattern — see `test_apply_auto_rejects_global_page_even_for_routine` for the shape.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/lib/governance/test_tiers.py -v`
Expected: the three new predicate tests FAIL (`assert False`).

- [ ] **Step 3: Implement**

In `is_instruction_plane_page`, after the prefix check and before the bare-dir-name return:

```python
    # #63: a project's standing-instructions page is instruction-plane —
    # it renders into that repo's CLAUDE.md managed block, so its writes
    # are always human diff-approved, same as global/. Exactly
    # projects/<slug>/instructions.md — never a nested path.
    if len(parts) == 3 and parts[0] == "projects" and parts[2] == "instructions.md":
        return True
```

Extend the `INSTRUCTION_PLANE_PREFIXES` docstring's final paragraph with one sentence noting the #63 pattern is part of the plane but is a path PATTERN, not a prefix — encoded in `is_instruction_plane_page`, covered by the same drift discipline.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/lib/governance/ tests/skills/wiki_health/ -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/governance/tiers.py tests/lib/governance/test_tiers.py
git commit -m "feat(governance): projects/<slug>/instructions.md is instruction-plane (#63)"
```

---

### Task 6: #63 — `promote_to_project` entry path + page-type registration

**Files:**
- Modify: `lib/memory/promotion.py` (new function + template below `promote_to_global`)
- Modify: `skills/wiki-migration/schemas.json` (register `project-instructions`)
- Modify: `skills/pin/SKILL.md` (one paragraph: standing rules route through `promote_to_project`)
- Modify: `skills/suggestions/lib/__init__.py` (new `promote_to_project` structured-action branch, alongside the existing `quarantine_release` branch)
- Test: `tests/lib/memory/test_promote_to_project.py` (new), `tests/skills/suggestions/test_promote_to_project_action.py` (new)

**Interfaces:**
- Consumes: `lib.memory.queue.propose`, `Proposal`, `lib.ren_paths.HANDLE_RE`, `lib.memory.quarantine.is_quarantined`, this module's existing `_read_page`/`_page_exists`/`PromotionError`.
- Produces: `promote_to_project(text: str, slug: str, session: str) -> QueueEntry` (PENDING — instruction-plane hold from Task 5 does the gating; the caller completes it via `queue.approve_and_apply(qid, who="human:<...>")` exactly like pin's `_complete_if_held`).

- [ ] **Step 1: Write the failing tests**

Create `tests/lib/memory/test_promote_to_project.py` (reuse the wiki/queue tmp fixtures from `tests/lib/memory/`'s existing promotion tests):

```python
def test_first_rule_creates_page_pending(wiki):
    entry = promotion.promote_to_project("Never touch the vendored parser.", "flux", "s-1")
    assert entry.status == "pending"                    # instruction-plane hold
    assert entry.proposal.op == "ADD"
    assert entry.proposal.page == "projects/flux/instructions.md"
    assert "type: project-instructions" in entry.proposal.content
    assert "- Never touch the vendored parser." in entry.proposal.content


def test_second_rule_appends_to_existing_page(wiki):
    # apply the first via approve_and_apply, then promote a second rule:
    # op == "UPDATE", content ends with both bullets in order


def test_empty_rule_raises(wiki):
    with pytest.raises(promotion.PromotionError):
        promotion.promote_to_project("   ", "flux", "s-1")


def test_bad_slug_raises(wiki):
    with pytest.raises(promotion.PromotionError):
        promotion.promote_to_project("rule", "../evil", "s-1")


def test_quarantined_page_refuses(wiki):
    # write a bannered instructions.md via the queue, then:
    with pytest.raises(promotion.PromotionError):
        promotion.promote_to_project("rule", "flux", "s-1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/lib/memory/test_promote_to_project.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'promote_to_project'`

- [ ] **Step 3: Implement**

In `lib/memory/promotion.py`:

```python
_PROJECT_INSTRUCTIONS_TEMPLATE = """\
---
type: project-instructions
schema_version: 1
project: {slug}
title: "Standing Instructions"
---

# Standing instructions — {slug}

Rules on this page render into the project repo's CLAUDE.md managed block
(#63) and bind every session there, subagents included. Writes are
instruction-plane: always human diff-approved, never auto-applied.

## Rules
"""


def promote_to_project(text: str, slug: str, session: str) -> QueueEntry:
    """Propose a standing rule for `projects/<slug>/instructions.md` (#63).

    Manual-first entry path: reached from /ren:pin ("make this a standing
    rule for this repo") or an accepted /ren:suggestions promotion. Returns
    a PENDING entry — the Task-5 instruction-plane hold is the gate; the
    caller releases it with `queue.approve_and_apply` once the human has
    approved in chat (same completion contract as pin's `_complete_if_held`).

    Raises PromotionError on an empty rule, an invalid slug, or a
    quarantined target page (quarantined content must never become standing
    instructions)."""
    from lib.ren_paths import HANDLE_RE

    rule = " ".join(text.split())
    if not rule:
        raise PromotionError("standing rule text is empty")
    if not HANDLE_RE.match(slug):
        raise PromotionError(f"invalid project slug: {slug!r}")

    page = f"projects/{slug}/instructions.md"
    if _page_exists(page):
        existing = _read_page(page)
        if quarantine.is_quarantined(existing):
            raise PromotionError(
                f"{page!r} is quarantined — release it before promoting new rules"
            )
        op = "UPDATE"
        content = existing.rstrip("\n") + f"\n- {rule}\n"
    else:
        op = "ADD"
        content = _PROJECT_INSTRUCTIONS_TEMPLATE.format(slug=slug) + f"\n- {rule}\n"

    return propose(
        Proposal(
            op=op,
            page=page,
            content=content,
            reason="promote-to-project",
            producer="promotion",
            writer="human",
            session=session,
        )
    )
```

(Match the module's actual import surface — it already imports `propose`, `Proposal`, `quarantine`; add whatever is missing at the top in the module's style.)

In `skills/wiki-migration/schemas.json`, add to `page_types`:

```json
    "project-instructions": {
      "current": 1,
      "migrations": []
    }
```

In `skills/pin/SKILL.md`, add one short section: when the friend asks for a standing rule scoped to the current project, the session calls `lib.memory.promotion.promote_to_project(text, slug, session)` and completes the hold with `queue.approve_and_apply(qid, who="human:pin")` after verbal approval — pin's own `pin()` stays for ordinary page pins.

In `skills/suggestions/lib/__init__.py`, add a structured-action branch (spec §2: `promote_to_project` is reachable from an accepted suggestion; acceptance IS the human approval, so the hold completes immediately, same reasoning as pin's `_complete_if_held`):

```python
    if action == "promote_to_project":
        from lib.memory import promotion, queue

        entry = promotion.promote_to_project(
            payload["text"], payload["slug"], session
        )
        if entry.status == "pending" and not any(
            c.get("kind") == "contradicts" for c in entry.conflicts
        ):
            prov = queue.approve_and_apply(entry.qid, who="human:suggestion-promote")
            return {
                "sid": sid,
                "applied": True,
                "detail": {"qid": entry.qid, "write_id": prov.write_id, "page": prov.page},
            }
        return {
            "sid": sid,
            "applied": False,
            "detail": {"qid": entry.qid, "status": entry.status,
                       "held_on": [c for c in entry.conflicts if c.get("kind") == "contradicts"]},
        }
```

(Match the surrounding branches' exact return-dict shapes and import style.) Add `tests/skills/suggestions/test_promote_to_project_action.py` with two tests, reusing that suite's store/wiki fixtures: an accepted `promote_to_project` suggestion writes the rule to `projects/<slug>/instructions.md` and reports `applied: True`; a `contradicts`-held entry reports `applied: False` with the hold visible.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/lib/memory/ tests/skills/wiki_migration/ tests/skills/doctor/ -v`
Expected: ALL PASS (doctor's `check_schema_versions` reads schemas.json — must still parse).

- [ ] **Step 5: Commit**

```bash
git add lib/memory/promotion.py skills/wiki-migration/schemas.json skills/pin/SKILL.md tests/lib/memory/test_promote_to_project.py
git commit -m "feat(promotion): promote_to_project standing-rule entry path (#63)"
```

---

### Task 7: #63 — render standing instructions into the project CLAUDE.md block

**Files:**
- Modify: `lib/adapter/claude_md.py` (`render_project_block`, line 213; new helper + constants)
- Test: `tests/lib/adapter/test_claude_md.py` (extend)

**Interfaces:**
- Consumes: `lib.memory.quarantine.is_quarantined`.
- Produces: `render_project_block(slug, *, wiki_root=None)` output gains a `## Standing instructions` section when (and only when) a clean, non-empty `projects/<slug>/instructions.md` exists. `STANDING_INSTRUCTIONS_CAP: Final[int] = 3_000` exported. `write_project_claude_md` is unchanged (it already calls `render_project_block`).

- [ ] **Step 1: Write the failing tests** (append to `tests/lib/adapter/test_claude_md.py`, reusing its tmp-wiki fixture pattern)

```python
def test_project_block_without_instructions_page_is_unchanged(tmp_wiki):
    block = claude_md.render_project_block("flux", wiki_root=tmp_wiki)
    assert "Standing instructions" not in block


def test_project_block_renders_instructions_body(tmp_wiki):
    _write_instructions(tmp_wiki, "flux", "---\ntype: project-instructions\n---\n\n## Rules\n- Never touch vendored code.\n")
    block = claude_md.render_project_block("flux", wiki_root=tmp_wiki)
    assert "## Standing instructions" in block
    assert "- Never touch vendored code." in block
    assert "type: project-instructions" not in block          # frontmatter stripped


def test_instructions_section_caps_at_3000_chars_with_marker(tmp_wiki):
    _write_instructions(tmp_wiki, "flux", "---\nt: x\n---\n" + "- rule\n" * 1000)
    block = claude_md.render_project_block("flux", wiki_root=tmp_wiki)
    section = block.split("## Standing instructions", 1)[1]
    assert "truncated" in section
    assert len(section) < 3_400   # cap + heading + marker slack


def test_quarantined_instructions_render_nothing(tmp_wiki):
    # write an instructions.md carrying the ren-quarantine banner token
    # (copy the banner literal from lib/memory/quarantine.py) — block must
    # not contain "Standing instructions"


def test_empty_body_renders_nothing(tmp_wiki):
    _write_instructions(tmp_wiki, "flux", "---\ntype: project-instructions\n---\n\n")
    block = claude_md.render_project_block("flux", wiki_root=tmp_wiki)
    assert "Standing instructions" not in block
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/lib/adapter/test_claude_md.py -v`
Expected: new tests FAIL (`"Standing instructions" not in block` inverse cases).

- [ ] **Step 3: Implement**

In `lib/adapter/claude_md.py`:

```python
STANDING_INSTRUCTIONS_CAP: Final[int] = 3_000
_STANDING_TRUNCATION_MARKER: Final[str] = (
    "\n\n*(truncated at 3,000 characters — the full page lives in the wiki)*"
)
_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n?", re.DOTALL)


def _standing_instructions_section(project_slug: str, wiki: Path) -> str:
    """The `## Standing instructions` section for the project block (#63),
    or "" — fail-closed: a missing, unreadable, quarantine-bannered, or
    empty-bodied page renders NOTHING (quarantined content must never
    become standing instructions). Body only (frontmatter stripped),
    capped at STANDING_INSTRUCTIONS_CAP with a truncation marker; the wiki
    page itself is never capped."""
    from lib.memory import quarantine

    page = wiki / "projects" / project_slug / "instructions.md"
    try:
        text = page.read_text(encoding="utf-8")
    except OSError:
        return ""
    if quarantine.is_quarantined(text):
        return ""
    body = _FRONTMATTER_RE.sub("", text).strip()
    if not body:
        return ""
    if len(body) > STANDING_INSTRUCTIONS_CAP:
        body = body[:STANDING_INSTRUCTIONS_CAP] + _STANDING_TRUNCATION_MARKER
    return (
        "\n\n## Standing instructions\n\n"
        "Sourced from the governed wiki page — change it via /ren:pin, never by editing here.\n\n"
        f"{body}"
    )
```

In `render_project_block`, change the return to append the section:

```python
    base = f"""\
# RenOS — project memory pointer

- This project's knowledge map: `{map_path}` — recall its contents via `/ren:recall` (agent-initiated); never raw-Read wiki pages to answer memory questions.
- Global RenOS doctrine (behavioral core, recall rules, wiki navigation) lives in the user-level CLAUDE.md — it is not repeated here.
- Durable changes to the wiki save themselves (revertible), never a direct file edit."""
    return base + _standing_instructions_section(project_slug, wiki)
```

Add `STANDING_INSTRUCTIONS_CAP` to `__all__`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/lib/adapter/ -v`
Expected: ALL PASS — including the pre-existing project-block tests (byte-identical output when no instructions page exists).

- [ ] **Step 5: Commit**

```bash
git add lib/adapter/claude_md.py tests/lib/adapter/test_claude_md.py
git commit -m "feat(adapter): render project standing instructions into CLAUDE.md block (#63)"
```

---

### Task 8: #63 — apply-path re-render + wake-up exclusion

**Files:**
- Modify: `lib/memory/queue.py` (`apply`, line 470 — post-apply hook)
- Modify: `hooks/wake-up/wakeup/__init__.py` (`_discover_extra_candidates`)
- Test: `tests/lib/memory/test_instructions_rerender.py` (new), `tests/hooks/test_wakeup.py` (extend)

**Interfaces:**
- Consumes: Task 7's `write_project_claude_md`, `lib.ren_paths.load_project_registry()`.
- Produces: applying a queue entry for `projects/<slug>/instructions.md` best-effort re-renders the mapped repo's CLAUDE.md (unmapped slug or render failure: silent no-op — doctor's Task 9 check is the backstop). Wake-up extras never include any `projects/<slug>/instructions.md`.

- [ ] **Step 1: Write the failing tests**

Create `tests/lib/memory/test_instructions_rerender.py` (reuse queue test fixtures; point the project registry at a tmp repo dir via the `state_dir` isolation fixture the queue tests already use):

```python
def test_applying_instructions_write_rerenders_repo_claude_md(wiki, tmp_repo):
    # register slug -> tmp_repo via ren_paths.record_project_repo
    # propose + approve_and_apply an instructions.md write through the queue
    # assert (tmp_repo / "CLAUDE.md").read_text() contains the rule and the
    # ren:begin/ren:end markers


def test_unmapped_project_applies_without_error(wiki):
    # no registry entry for the slug: approve_and_apply succeeds, no crash


def test_render_failure_never_fails_the_write(wiki, monkeypatch):
    # monkeypatch claude_md.write_project_claude_md to raise; approve_and_apply
    # still returns a Provenance and the page is written
```

In `tests/hooks/test_wakeup.py` add:

```python
def test_instructions_page_never_an_extras_candidate(...):
    # build a wiki with a released (non-quarantined) projects/flux/instructions.md
    # plus one ordinary knowledge page; _discover_extra_candidates must return
    # the knowledge page and NOT the instructions page; held_count unchanged
```

(Reuse that file's existing extras-candidate test fixtures.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/lib/memory/test_instructions_rerender.py tests/hooks/test_wakeup.py -v`
Expected: rerender test FAILS (no CLAUDE.md produced); wakeup test FAILS (instructions page in candidates).

- [ ] **Step 3: Implement the queue hook**

In `lib/memory/queue.py`, add a module-level helper and call it at the end of `apply()` (after `_persist(entry)`, before `return prov`):

```python
def _rerender_project_claude_md(page: str) -> None:
    """#63 post-apply hook: an applied write to projects/<slug>/instructions.md
    re-renders the mapped repo's CLAUDE.md managed block. Best-effort BY
    CONTRACT — the wiki write has already succeeded and is journaled; a
    render failure (unmapped slug, missing repo, adapter error) must never
    fail or roll back the apply. Doctor's standing_instructions_drift check
    is the visibility backstop for skipped renders."""
    parts = page.split("/")
    if len(parts) != 3 or parts[0] != "projects" or parts[2] != "instructions.md":
        return
    try:
        from pathlib import Path

        from lib import ren_paths
        from lib.adapter import claude_md

        entry = ren_paths.load_project_registry().get(parts[1])
        if entry:
            claude_md.write_project_claude_md(Path(entry["repo_path"]), parts[1])
    except Exception:  # noqa: BLE001 - see docstring: never fail the applied write
        pass
```

and in `apply()`:

```python
    entry.status = _APPLIED
    entry.write_id = prov.write_id
    _persist(entry)
    _rerender_project_claude_md(proposal.page)
    return prov
```

(`apply_auto` needs no hook: instruction-plane targets can never reach it — Task 5's predicate makes `auto_apply_allowed` false for this page.)

- [ ] **Step 4: Implement the wake-up exclusion**

In `_discover_extra_candidates`'s loop, after the `_is_project_raw(rel)` check:

```python
        rel_parts = rel.split("/")
        if len(rel_parts) == 3 and rel_parts[0] == "projects" and rel_parts[2] == "instructions.md":
            # #63: standing instructions are already in every session via the
            # repo's CLAUDE.md managed block — surfacing them here would spend
            # extras budget on a duplicate. Not counted in held_count: nothing
            # is being withheld, the content is injected by another channel.
            continue
```

Update the function docstring's exclusion list with one clause naming this.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/lib/memory/ tests/hooks/ -v`
Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add lib/memory/queue.py hooks/wake-up/wakeup/__init__.py tests/lib/memory/test_instructions_rerender.py tests/hooks/test_wakeup.py
git commit -m "feat(queue,wakeup): instructions apply re-renders CLAUDE.md; extras exclude it (#63)"
```

---

### Task 9: #63 — doctor drift check + end-to-end test

**Files:**
- Modify: `skills/doctor/lib/__init__.py` (new check + `_ALL_CHECK_NAMES` + `__all__`)
- Modify: `skills/doctor/SKILL.md` (one row in the new-checks table)
- Test: `tests/skills/doctor/test_standing_instructions_drift.py` (new), `tests/integration/test_standing_instructions_e2e.py` (new)

**Interfaces:**
- Consumes: Task 7's `render_project_block` + the existing pure `spliced_text(existing_text, content)`; `ren_paths.load_project_registry()`.
- Produces: `check_standing_instructions_drift() -> CheckResult`, registered in `_ALL_CHECK_NAMES` (renders as `standing_instructions_drift` in the report).

- [ ] **Step 1: Write the failing tests**

Create `tests/skills/doctor/test_standing_instructions_drift.py` (reuse `test_doctor.py`'s isolation fixtures for wiki + registry):

```python
def test_skip_when_no_project_has_instructions(...):
    res = doctor.check_standing_instructions_drift()
    assert res.status == "skip"


def test_ok_when_block_matches(...):
    # instructions page exists; repo CLAUDE.md written via
    # claude_md.write_project_claude_md -> status "ok"


def test_warn_on_stale_splice(...):
    # render CLAUDE.md, then change the wiki page body WITHOUT re-rendering
    # -> "warn", message names the slug


def test_warn_when_repo_claude_md_missing(...):
    # instructions page exists, mapped repo has no CLAUDE.md -> "warn"
```

Create `tests/integration/test_standing_instructions_e2e.py`:

```python
"""#63 end-to-end: promote -> human approve -> repo CLAUDE.md carries the rule."""


def test_pin_to_claude_md_round_trip(wiki, tmp_repo):
    # 1. ren_paths.record_project_repo("flux", tmp_repo)
    # 2. entry = promotion.promote_to_project("Never force-push to main.", "flux", "s-e2e")
    # 3. assert entry.status == "pending"          (instruction-plane hold)
    # 4. queue.approve_and_apply(entry.qid, who="human:pin")
    # 5. text = (tmp_repo / "CLAUDE.md").read_text(encoding="utf-8")
    #    assert "- Never force-push to main." in text
    #    assert text.count(claude_md.MARKER_BEGIN) == 1
    # 6. doctor.check_standing_instructions_drift().status == "ok"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/skills/doctor/test_standing_instructions_drift.py tests/integration/test_standing_instructions_e2e.py -v`
Expected: FAIL — `AttributeError: ... no attribute 'check_standing_instructions_drift'` (e2e should already pass through step 5 if Tasks 6–8 are correct; step 6 fails).

- [ ] **Step 3: Implement**

In `skills/doctor/lib/__init__.py`:

```python
def check_standing_instructions_drift() -> CheckResult:
    """#63: for every registered project with an instructions.md, the repo's
    CLAUDE.md managed block must match a fresh render — a mismatch means a
    stale splice (re-render never fired), a hand-edit inside the markers, or
    a missing CLAUDE.md. Warn-not-block; remediation is a re-render
    (`lib.adapter.claude_md.write_project_claude_md`), never automatic."""
    from lib import ren_paths
    from lib.adapter import claude_md

    wiki = ren_paths.wiki_root()
    stale: list[str] = []
    seen = 0
    for slug, entry in sorted(ren_paths.load_project_registry().items()):
        if not (wiki / "projects" / slug / "instructions.md").is_file():
            continue
        seen += 1
        repo_md = Path(entry["repo_path"]) / "CLAUDE.md"
        try:
            current = repo_md.read_text(encoding="utf-8") if repo_md.is_file() else ""
        except OSError:
            stale.append(slug)
            continue
        expected = claude_md.render_project_block(slug, wiki_root=wiki)
        if claude_md.spliced_text(current, expected) != current:
            stale.append(slug)
    if not seen:
        return CheckResult("standing_instructions_drift", "skip", "no project has an instructions.md")
    if stale:
        return CheckResult(
            "standing_instructions_drift", "warn",
            f"stale CLAUDE.md block for: {', '.join(stale)} — re-render via write_project_claude_md",
        )
    return CheckResult("standing_instructions_drift", "ok", f"{seen} project block(s) in sync")
```

Add `"check_standing_instructions_drift"` to `_ALL_CHECK_NAMES` (after `check_execution_doctrine`) and to `__all__`. Add a row to `skills/doctor/SKILL.md`'s new-checks table: `check_standing_instructions_drift` | #63: repo CLAUDE.md standing-instructions block matches a fresh render of the wiki page.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/skills/doctor/ tests/integration/test_standing_instructions_e2e.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -q`
Expected: ALL PASS — zero regressions across the train.

- [ ] **Step 6: Commit**

```bash
git add skills/doctor/lib/__init__.py skills/doctor/SKILL.md tests/skills/doctor/test_standing_instructions_drift.py tests/integration/test_standing_instructions_e2e.py
git commit -m "feat(doctor): standing_instructions_drift check + #63 end-to-end test"
```
