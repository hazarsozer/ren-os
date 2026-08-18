"""
Generated guard-test tier (issue #68) — a deterministic, itertools-style
enumerated corpus asserting the real bash guards' verdicts against a
segment-level oracle (design doc 2026-08-18-post-0.7.7-fix-train-design.md §5).

Corpus axes: guarded segment shape x innocuous prefix x innocuous suffix x
shell separator, with quoting variants applied to ARGUMENTS only (paths,
refspecs) — never to hide a verb or flag inside a quoted string, since the
guards are deliberately regex-level, not shell parsers ("best-effort by
design", write_gate docstring).

Oracle: split each generated command on the guards' own separator set; any
segment carrying a guarded verb+flag shape => expected "block" (exit 2, or a
non-None ask dict for the backup-remote check); a command composed only of
innocuous segments => "allow" (0 / None). Cases are built from tagged
segments, so the oracle is computed per case, never hand-copied.

Hard perf rule (design §5): innocuous segments must NEVER contain a plain
`git push` — a non-force push segment sends check_push into git-subprocess
remote resolution and the secrets scan, destroying the sub-second target.
The guarded force shapes are safe: they block before any subprocess work
(pre_push_scan.check_push, force/rewrite check runs first).

Determinism: no hypothesis, no randomness, no network — the corpus
enumerates identically on every run.

Force-push-shaped and secret-shaped strings below are assembled at runtime
(token + token) so the literal shape never appears in this file's text — the
repo's own pre-push guard scans outgoing added lines and would block the
literals (same convention as tests/lib/memory/test_scrub.py's runtime-
assembled fixture shapes; commit e59bbdd is the precedent).

Run with: uv run pytest tests/hooks/test_guards_generated.py -q --durations=5
"""

from __future__ import annotations

from itertools import product

import pytest

from hooks.guards import pre_push_scan, write_gate
from lib.ren_paths import wiki_root

# --- runtime-assembled shape tokens (see module docstring) -------------------

_FORCE = "--" + "force"          # bare force flag
_F = "-" + "f"                   # short force flag
_MIRROR = "--" + "mirror"        # mirror push
_PLUS = "+"                      # force-refspec prefix
_PUSH = "git " + "push"          # push verb (kept unassembled-safe alongside flags)

# --- corpus axes -------------------------------------------------------------

# Innocuous segments: NO `git push` here, ever (perf rule — see docstring).
INNOCUOUS = ("echo ok", "ls -la", "git status", "cat README.md")
PREFIXES = (None,) + INNOCUOUS
SUFFIXES = (None, "echo ok", "ls -la")
# The guards' own separator set (pre_push_scan._SEGMENT_SPLIT_RE and
# write_gate's split include all of these).
SEPARATORS = (" && ", " ; ", " | ", "\n")
_SEP_IDS = {" && ": "and", " ; ": "semi", " | ": "pipe", "\n": "nl"}

# Guarded shapes. `{W}` = wiki root, `{S}` = scratch dir — filled at runtime
# from the module-scoped world fixture (paths aren't known at collection).
PUSH_SHAPES = (
    ("force-flag", f"{_PUSH} {_FORCE} origin main"),
    ("short-f", f"{_PUSH} {_F} origin main"),
    ("plus-refspec", f"{_PUSH} origin {_PLUS}main"),
    ("plus-head-refspec", f"{_PUSH} origin {_PLUS}HEAD:main"),
    ("mirror", f"{_PUSH} {_MIRROR} origin"),
)

RM_SHAPES = (
    ("rm-page", "rm {W}/a.md"),
    ("unlink-page", "unlink {W}/a.md"),
    ("rm-page-dq", 'rm "{W}/a.md"'),
    ("rm-page-sq", "rm '{W}/a.md'"),
    ("rm-three-pages", "rm {W}/a.md {W}/b.md {W}/c.md"),
    ("rm-r-dir", "rm -r {W}/projects/demo"),
    ("rm-rf-dir", "rm -rf {W}/projects/demo"),
    ("rm-long-recursive-dir", "rm --recursive {W}/projects/demo"),
)

WRITE_SHAPES = (
    ("redirect", "echo hi > {W}/projects/demo/x.md"),
    ("append", "echo hi >> {W}/projects/demo/x.md"),
    ("redirect-dq-target", 'echo hi > "{W}/projects/demo/x.md"'),
    ("sed-inplace", "sed -i 's/a/b/' {W}/projects/demo/x.md"),
    ("tee", "echo hi | tee {W}/projects/demo/x.md"),
    ("cp-into-wiki", "cp {S}/src.md {W}/projects/demo/new.md"),
    ("mv-out-of-wiki", "mv {W}/projects/demo/x.md {S}/out.md"),
    ("mv-into-wiki-sq-dest", "mv {S}/src.md '{W}/projects/demo/new.md'"),
)

REMOTE_ASK_SHAPES = (
    ("set-url-backup", "git remote set-url backup git@example.com:x/y.git"),
    ("add-backup", "git remote add backup git@example.com:x/y.git"),
)
REMOTE_ALLOW_SHAPES = (
    ("add-origin", "git remote add origin git@example.com:x/y.git"),
    ("set-url-origin", "git remote set-url origin git@example.com:x/y.git"),
)


def _combos(newline_prefix_ok: bool):
    """Deterministic (prefix, suffix, separator) product. The bare shape (no
    prefix/suffix) is yielded exactly once. When `newline_prefix_ok` is False,
    newline-separated PREFIX combos are excluded from the green corpus — those
    are the confirmed newline-bypass findings, carried separately as xfail
    (see the FINDINGS section at the bottom)."""
    yield (None, None, " && ")  # bare shape; separator unused
    for sep, pre, suf in product(SEPARATORS, PREFIXES, SUFFIXES):
        if pre is None and suf is None:
            continue
        if not newline_prefix_ok and sep == "\n" and pre is not None:
            continue
        yield (pre, suf, sep)


def _assemble(shape_template: str, pre: str | None, suf: str | None, sep: str):
    """Return (command_template, tagged_segments). Segments are tagged
    guarded/innocuous at generation time — the oracle's segment-level input."""
    parts = [(p, guarded) for p, guarded in
             ((pre, False), (shape_template, True), (suf, False)) if p]
    return sep.join(p for p, _ in parts), tuple(parts)


def _oracle_blocks(segments) -> bool:
    """Segment-level oracle (design §5): any guarded segment => block."""
    return any(guarded for _, guarded in segments)


def _case_id(shape_id: str, pre, suf, sep) -> str:
    return (f"{shape_id}"
            f"-p_{(pre or 'none').replace(' ', '_')}"
            f"-s_{(suf or 'none').replace(' ', '_')}"
            f"-{_SEP_IDS[sep]}")


def _build_cases(shapes, newline_prefix_ok: bool):
    cases = []
    for shape_id, template in shapes:
        for pre, suf, sep in _combos(newline_prefix_ok):
            cmd, segments = _assemble(template, pre, suf, sep)
            cases.append(pytest.param(
                cmd, segments, id=_case_id(shape_id, pre, suf, sep)))
    return cases


# Newline-prefixed push/rm shapes are excluded here (confirmed bypass —
# xfail'd below); write_gate's wiki-write split handles newlines, and the
# backup-remote regex is \b-anchored, so those keep the full product.
PUSH_CASES = _build_cases(PUSH_SHAPES, newline_prefix_ok=False)
RM_CASES = _build_cases(RM_SHAPES, newline_prefix_ok=False)
WRITE_CASES = _build_cases(WRITE_SHAPES, newline_prefix_ok=True)
REMOTE_ASK_CASES = _build_cases(REMOTE_ASK_SHAPES, newline_prefix_ok=True)
REMOTE_ALLOW_CASES = [
    pytest.param(cmd, id=case_id)
    for shape_id, template in REMOTE_ALLOW_SHAPES
    for pre, suf, sep in _combos(True)
    for cmd, case_id in [( _assemble(template, pre, suf, sep)[0],
                           _case_id(shape_id, pre, suf, sep) )]
]
INNOCUOUS_CASES = (
    [pytest.param(seg, id=f"solo-{seg.replace(' ', '_')}") for seg in INNOCUOUS]
    + [pytest.param(sep.join((pre, suf)),
                    id=_case_id("pair", pre, suf, sep))
       for sep, pre, suf in product(SEPARATORS, INNOCUOUS, SUFFIXES[1:])]
)


# --- fixtures ----------------------------------------------------------------
# Same env redirect as tests/hooks/test_guards.py's clean_path_env/wiki
# fixtures (REN_FRAMEWORK_ROOT -> tmp; REN_ALLOW_FORCE/REN_QUEUE_APPLY
# cleared), adapted to a module-scoped wiki tree: the guards only INSPECT
# commands (never execute them), so one shared read-only tree keeps ~1300
# cases inside the sub-second target where a per-test tmp wiki would not.


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = tmp_path_factory.mktemp("guards-generated")
    framework = root / "framework"
    mp = pytest.MonkeyPatch()
    try:
        for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT"):
            mp.delenv(var, raising=False)
        mp.setenv("REN_FRAMEWORK_ROOT", str(framework))
        wiki = wiki_root()
        (wiki / "projects" / "demo").mkdir(parents=True, exist_ok=True)
        for name in ("a.md", "b.md", "c.md"):
            (wiki / name).write_text("x\n", encoding="utf-8")
        for name in ("x.md", "y.md", "z.md"):
            (wiki / "projects" / "demo" / name).write_text("x\n", encoding="utf-8")
        scratch = root / "scratch"
        scratch.mkdir()
        (scratch / "src.md").write_text("x\n", encoding="utf-8")
    finally:
        mp.undo()
    return {"framework": str(framework), "wiki": str(wiki), "scratch": str(scratch)}


@pytest.fixture(autouse=True)
def guard_env(monkeypatch, world):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", world["framework"])
    monkeypatch.delenv(pre_push_scan.ALLOW_FORCE_ENV, raising=False)
    monkeypatch.delenv(write_gate.QUEUE_APPLY_ENV, raising=False)


def _fill(template: str, world) -> str:
    return template.replace("{W}", world["wiki"]).replace("{S}", world["scratch"])


# --- generated corpus: guard verdict == oracle verdict -----------------------


@pytest.mark.parametrize("template,segments", PUSH_CASES)
def test_generated_push_verdicts(template, segments, world):
    cmd = _fill(template, world)
    expected = 2 if _oracle_blocks(segments) else 0
    # cwd is a plain tmp dir, NOT a git repo: force shapes block before any
    # git subprocess work, and the corpus contains no non-force push segment.
    assert pre_push_scan.check_push(cmd, world["scratch"]) == expected, cmd


@pytest.mark.parametrize("template,segments", RM_CASES)
def test_generated_mass_delete_verdicts(template, segments, world):
    cmd = _fill(template, world)
    expected = 2 if _oracle_blocks(segments) else 0
    assert write_gate.check_mass_delete(cmd, world["scratch"]) == expected, cmd


@pytest.mark.parametrize("template,segments", WRITE_CASES)
def test_generated_bash_wiki_write_verdicts(template, segments, world):
    cmd = _fill(template, world)
    expected = 2 if _oracle_blocks(segments) else 0
    assert write_gate.check_bash_wiki_write(cmd, world["scratch"]) == expected, cmd


@pytest.mark.parametrize("template,segments", REMOTE_ASK_CASES)
def test_generated_backup_remote_ask_verdicts(template, segments, world):
    cmd = _fill(template, world)
    decision = write_gate.check_backup_remote_change(cmd)
    if _oracle_blocks(segments):
        assert isinstance(decision, dict), cmd
        hso = decision["hookSpecificOutput"]
        assert hso["permissionDecision"] == "ask", cmd
    else:  # pragma: no cover — ask corpus has no innocuous-only commands
        assert decision is None, cmd


@pytest.mark.parametrize("template", REMOTE_ALLOW_CASES)
def test_generated_non_backup_remote_allowed(template, world):
    cmd = _fill(template, world)
    assert write_gate.check_backup_remote_change(cmd) is None, cmd


@pytest.mark.parametrize("cmd", INNOCUOUS_CASES)
def test_generated_innocuous_commands_allowed_by_every_guard(cmd, world):
    # Innocuous-only command => every guard allows (oracle: no guarded
    # segment). No segment contains `git push`, so check_push returns without
    # touching a git subprocess.
    cwd = world["scratch"]
    assert pre_push_scan.check_push(cmd, cwd) == 0, cmd
    assert write_gate.check_mass_delete(cmd, cwd) == 0, cmd
    assert write_gate.check_bash_wiki_write(cmd, cwd) == 0, cmd
    assert write_gate.check_backup_remote_change(cmd) is None, cmd


def test_corpus_is_bounded_and_deterministic():
    total = (len(PUSH_CASES) + len(RM_CASES) + len(WRITE_CASES)
             + len(REMOTE_ASK_CASES) + len(REMOTE_ALLOW_CASES)
             + len(INNOCUOUS_CASES))
    assert 1000 <= total <= 4000  # design §5: bounded, low thousands


# --- FINDINGS: oracle-vs-guard disagreements (issue #68 generated tier) ------
# Real bypasses this tier found — the oracle says block, the guard allows.
# Guard fixes are OUT of this task's file scope; xfail(strict) pins each
# finding so it flips visibly when the guard is fixed.
#
# Finding 1 — newline-prefix bypass: pre_push_scan._GIT_PUSH_RE and
#   write_gate._RM_RE anchor on `(?:^|[;&|]\s*)`, which omits `\n`, so a
#   guarded verb on any line after the first is invisible ("echo ok" +
#   newline + forced push / wiki rm => allowed). Multi-line Bash commands are
#   routine in this harness; write_gate's bash-wiki-write check already
#   treats `\n` as a separator, so this is an inconsistency, not doctrine.
#
# Finding 2 — quoted force-refspec bypass: `_has_force_refspec` tests
#   `token.startswith("+")` on raw tokens, so a quoted refspec argument
#   (which the shell unwraps before git sees it) is invisible and the forced
#   push is allowed. Quoting here is on an ARGUMENT (a refspec), squarely
#   inside the guards' documented contract — a human would call this a bypass.

_XFAIL_NL = pytest.mark.xfail(
    strict=True,
    reason="issue #68 generated-tier finding 1: [;&|] separator class omits "
    "newline — guarded verb after a newline-separated innocuous prefix "
    "is not seen; guard fix out of scope for this test-only task",
)
_XFAIL_QUOTED_REFSPEC = pytest.mark.xfail(
    strict=True,
    reason="issue #68 generated-tier finding 2: quoted +refspec argument "
    "bypasses _has_force_refspec (shell strips the quotes, git still "
    "force-pushes); guard fix out of scope for this test-only task",
)

_NL_PUSH_FINDING_CASES = [
    pytest.param(f"echo ok\n{template}", id=f"nl-prefix-{shape_id}",
                 marks=_XFAIL_NL)
    for shape_id, template in PUSH_SHAPES
]
_QUOTED_REFSPEC_FINDING_CASES = [
    pytest.param(f"{_PUSH} origin '{_PLUS}main'", id="sq-plus-refspec",
                 marks=_XFAIL_QUOTED_REFSPEC),
    pytest.param(f'{_PUSH} origin "{_PLUS}main"', id="dq-plus-refspec",
                 marks=_XFAIL_QUOTED_REFSPEC),
]
_NL_RM_FINDING_CASES = [
    pytest.param("echo ok\nrm {W}/a.md", id="nl-prefix-rm-page",
                 marks=_XFAIL_NL),
    pytest.param("echo ok\nunlink {W}/a.md", id="nl-prefix-unlink-page",
                 marks=_XFAIL_NL),
    pytest.param("echo ok\nrm -rf {W}/projects/demo", id="nl-prefix-rm-rf-dir",
                 marks=_XFAIL_NL),
]


@pytest.mark.parametrize(
    "template", _NL_PUSH_FINDING_CASES + _QUOTED_REFSPEC_FINDING_CASES)
def test_finding_forced_push_shapes_guard_misses(template, world):
    # Oracle: a segment with a force shape => block (2). The guard allows.
    cmd = _fill(template, world)
    assert pre_push_scan.check_push(cmd, world["scratch"]) == 2, cmd


@pytest.mark.parametrize("template", _NL_RM_FINDING_CASES)
def test_finding_newline_prefixed_wiki_rm_guard_misses(template, world):
    # Oracle: a segment rm'ing a wiki page / page-bearing dir => block (2).
    cmd = _fill(template, world)
    assert write_gate.check_mass_delete(cmd, world["scratch"]) == 2, cmd
