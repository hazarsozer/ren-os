---
description: Approve a pending write-queue entry and apply it to the wiki
argument-hint: <qid>
---

Approve and apply the pending write-queue entry `$ARGUMENTS`.

This is the explicit human-approval path of the `queue` skill — invoke that
skill's approve flow: call
`skills.queue.lib.approve_and_apply(qid, who, session)` with qid `$ARGUMENTS`
(strip surrounding whitespace; it must look like `q-<ULID>`), `who` = the
friend's handle from identity (fallback `"friend"`), and the current session
id. Relay the returned confirmation verbatim — it contains the resulting
`write_id` and the one-line revert hint.

If the qid is missing or malformed, show the pending queue
(`skills.queue.lib` render path, same as /ren:queue) and ask which entry to
approve. Never approve entries the friend did not name.
