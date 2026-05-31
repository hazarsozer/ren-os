# eval deferred — see ADR-012

This directory is **intentionally empty of `eval.json`** for V1.

`sf-improve-skill` improves *other* skills via the Karpathy loop (ADR-012). Every
framework-shipped skill it operates on has a real, ADR-011-conformant `eval.json`
(pinned in `../lib/tests/test_preflight.py::CANONICAL_EVAL_FIXTURES`), so the
capability works — only **self-application** (improve-skill improving itself) is
deferred.

**Why deferred, not faked:** a meta-skill's eval must assert whether improve-skill
*itself* got better. A trivial/hand-wavy `eval.json` is worse than none for the one
skill whose job is rigor — it manufactures false confidence in the rigor tool. The
binary, deterministic properties of improve-skill (preflight refusals, autonomous-flag
gating, dirty-tree refusal, revert-on-no-improvement, iteration bound) are already
covered by unit tests in `../lib/tests/`. An `eval.json` re-asserting them is redundant;
asserting end-to-end loop *quality* is non-deterministic and not cleanly binary.

**To un-defer:** when a loop behavior emerges that is binary, deterministic, AND not
already unit-tested, author `eval.json` here and add it to `CANONICAL_EVAL_FIXTURES`.

Full rationale + the candidate assertions considered: `../learnings.md`
(entry 2026-05-29). Loop design: `wiki/decisions/012-two-layer-self-improvement.md`.
