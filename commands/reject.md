---
description: Reject a pending write-queue entry with a reason
argument-hint: <qid> [why]
---

Reject the pending write-queue entry named in `$ARGUMENTS`.

This is the rejection path of the `queue` skill — parse `$ARGUMENTS` as
`<qid> [why...]` (qid looks like `q-<ULID>`; everything after it is the
reason). Call `skills.queue.lib.reject_with_reason(qid, why)`. If no reason
was given, ask the friend for a short one first — rejections are recorded
with provenance and "no reason" hides signal from future consolidation.
Relay the returned confirmation verbatim.

If the qid is missing or malformed, show the pending queue (same render as
/ren:queue) and ask which entry to reject.
