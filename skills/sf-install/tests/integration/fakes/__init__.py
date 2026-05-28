"""Fakes for sf-install's peer-skill contract surfaces.

Each module implements one peer's contract:
    feed_fake          ← sf-feed's locked Stage 3 + Stage 4 surface
    distribution_fake  ← sf-distribution's pinned-registry + licenses regen
    lifecycle_fake     ← sf-lifecycle's doctor.report()

All fakes follow the same shape:
    - Construct with sensible defaults
    - inject_* methods configure simulated responses per scenario
    - calls list records every method invocation for assertions

Real peer impls live under feed/, skills/sf-doctor/, etc. Tests in this
directory import the peer's REAL symbols only for signature-drift checks
(test_contract_drift.py); behavior tests use these fakes for determinism.
"""
