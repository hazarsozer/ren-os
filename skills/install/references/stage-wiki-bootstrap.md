# Stage: wiki bootstrap

Carried in spirit from donor `skills/install/references/stage-5-wiki-bootstrap.md`
— the loader procedure that reference doc only DESCRIBED is now real, shippable
code (`lib.skeleton.stamp_skeleton`), so this page just points at it rather
than re-describing the same steps twice.

1. Call `skills.install.lib.stamp_wiki(profile="master")`.
2. Report `result.written` (newly created pages/dirs) vs `result.skipped`
   (already present — untouched). A friend re-running install after a partial
   prior run should see mostly `skipped`, a few `written`.
3. Surface any `result.warnings` (an unresolved `{{placeholder}}` left in a
   written file) — this should not normally happen with the default
   `{"name": "Friend", "handle": "friend"}` placeholders `stamp_wiki` supplies,
   but if it does, tell the friend which file and field.

Never overwrites. Never diffs for auto-merge. A file that already exists is
reported as `skipped`, full stop — per `lib.skeleton`'s module docstring.
