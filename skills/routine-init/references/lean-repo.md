# Lean-repo discipline (ADR-034 · research tension #5)

A Cloud Routine clones its linked repo, loads `CLAUDE.md`, runs, and destroys the env. A large `CLAUDE.md` + unrelated project code burns the run's context budget and quota on irrelevant tokens. So each routine gets its **own minimal repo** — the *muscle*, nothing more.

## What goes in a routine repo

- A small `CLAUDE.md` — what the routine does, where its secrets are (env vars, never `.env`), the cross-run memory files.
- `ROUTINE_PROMPT.md` — the skill-as-prompt: one named `/ren:` skill, explicit order of operations, the required failure footer, single-pass exit.
- `state.md` / `run-log.md` — the cross-run memory trail (read at start via `/ren:recall --routine .`, written back via git push).
- Only the scripts/skills this one routine needs.

## What stays OUT

- Unrelated project source, other projects' CLAUDE.md, the whole dev-wiki.
- Secrets of any kind (those live in the cloud environment).

## The export-from-rich-session step

The lean-repo principle conflicts with wanting the rich context that makes a system prompt specific. The resolution (Nate Herk): design/iterate the routine **inside** your rich interactive session, then export only the necessary context into the lean routine repo. `/ren:routine-init` is that export step — it captures the skill + conventions into a minimal repo so the cloud run starts clean.

## Green-before-schedule

Use **Run-Now** to iterate on the routine interactively before committing it to a schedule — run, observe, fix the prompt/env, repeat until it one-shots cleanly. Same discipline as TDD: green before schedule.
