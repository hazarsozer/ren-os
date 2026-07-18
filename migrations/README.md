## Portability doctrine (issue #9)

Existing shell migrations were rewritten to POSIX-portable sed (BSD + GNU).
**New migrations must be written in Python** (≥3.11 is already a hard dep and
inherently portable) — shell migration scripts are legacy. CI's
`scripts/lint-shell-portability.py` guards the remaining shell against
bash-4isms and GNU-only sed.
