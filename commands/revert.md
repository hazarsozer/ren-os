---
description: Revert an applied wiki write by its write_id (one-step undo)
argument-hint: <write_id>
---

Revert the applied wiki write `$ARGUMENTS`.

This is the undo path of the `queue` skill — parse `$ARGUMENTS` as a
`write_id` (looks like `w-<ULID>`). Call
`skills.queue.lib.revert_write(write_id)` and relay the returned
confirmation verbatim — it names the restored page and any pages that cite
the reverted write (those citations may now dangle; surface them, do not
auto-edit them).

If the write_id is missing or malformed, ask for it — the friend gets it
from the /ren:approve confirmation or from `wiki/.ren/journal.jsonl`. Never
guess a write_id.
