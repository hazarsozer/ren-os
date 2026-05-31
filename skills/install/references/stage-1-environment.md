# Stage 1 — Environment check

Per ADR-015 Stage 1 + team-lead pushback P1 (always-check). Cheap probes; the cost is sub-second and correctness wins.

## What this stage verifies

| Check | Expected | Probe |
|---|---|---|
| Claude Code version | ≥ 1.0.33 (Context Mode requirement) | `claude --version` |
| Claude auth | logged in | `claude auth status` |
| Node.js | ≥ 22.5 (Context Mode requirement) | `node --version` |
| git | installed | `git --version` |
| GitHub CLI | installed AND authenticated (soft requirement; used by `/sf:doctor`'s update check) | `gh --version` + `gh auth status` |
| `ANTHROPIC_API_KEY` | env var set | shell env lookup |
| `UPSTASH_CONTEXT7_API_KEY` (or whatever context7 is using) | env var set | shell env lookup |

## P1 behavior: always run, skip only the prompt-for-fix

The orchestrator's stage-recheck table says `1: true`. Concretely:

1. Run every probe above unconditionally.
2. Build a `checks` map: `{ check_name: pass | fail }`.
3. If the previous checkpoint recorded all green AND today's probes are all green → **no friend prompt**; persist updated `last_check_at` and move on.
4. If any probe failed → **prompt the friend** with the failure list and remediation:

   ```
   Stage 1 — environment check found issues:

     ✗ claude auth status   — not logged in.
       Fix: claude auth login
     ✗ ANTHROPIC_API_KEY    — not set in env.
       Fix: export ANTHROPIC_API_KEY=<your-key>
            (Get one at https://console.anthropic.com)

   Once these are resolved, re-run /sf:install.
   ```

5. If any check failed, the stage does NOT mark itself completed; the orchestrator exits with the "re-run to resume" message.

## Per-check remediation strings

Each failed check produces a one-line `Fix:` hint. The remediation strings live in this doc as the single source of truth so they don't drift across the skill:

- **claude version** (too old): `Fix: claude upgrade` (or `npm i -g @anthropic-ai/claude-code` per Claude Code docs).
- **claude auth**: `Fix: claude auth login`
- **node** (missing or too old): `Fix: install Node.js 22.5+ via your platform's package manager or nvm`.
- **git**: `Fix: install git via your platform's package manager`.
- **gh** (missing): `Fix: install GitHub CLI from https://cli.github.com`.
- **gh auth**: `Fix: gh auth login` — choose GitHub.com, login via web browser.
- **`ANTHROPIC_API_KEY`**: `Fix: export ANTHROPIC_API_KEY=<your-key>; obtain at https://console.anthropic.com`.
- **`UPSTASH_CONTEXT7_API_KEY`**: `Fix: export UPSTASH_CONTEXT7_API_KEY=<your-key>; obtain via context7's OAuth flow at https://context7.com`.

The friend may need to add the env vars to their shell rc (`~/.bashrc`, `~/.zshrc`, etc.) for persistence across sessions; mention this once if neither key was set:

```
Note: env vars set with `export` only persist for the current shell. For
permanent setup, add the export lines to your ~/.bashrc, ~/.zshrc, or
shell-of-choice rc file, then `source` it or open a new terminal.
```

## State recorded

On success, write to `state.stage_artifacts.1`:

```json
{
  "env_ok": true,
  "checks": {
    "claude_auth": true,
    "gh_auth": true,
    "node_version": "22.7.1",
    "node_ok": true,
    "git_ok": true,
    "anthropic_api_key": true,
    "upstash_context7_api_key": true
  },
  "last_check_at": "<ISO-8601>"
}
```

Append `1` to `state.completed_stages` if not already present.

## Subtleties

- **`claude --version` may not exist on every install** — Claude Code CLI is invoked via `claude`. If the executable isn't on PATH, the probe fails and the remediation tells the friend to either reinstall Claude Code or add it to PATH.
- **`claude auth status`** output is parsed liberally — looking for "Logged in" or equivalent. Don't be brittle on exact text matching.
- **Subscription vs API key** are distinct: `claude auth status` covers the subscription; `ANTHROPIC_API_KEY` env var covers the API used by Skill Creator's description optimizer + sf-improve-skill loops. Both are required; failing one shouldn't mask the other.
- **Upstash key name may shift** — the context7 plugin's required env var name is verified at install time from its readme. If the canonical name changes, this doc's check string needs an update; surface the mismatch as a Stage 2 / Stage 6 issue, not a Stage 1 issue.
- **`~/.claude/` may be a symlink** to a dotfiles repo (e.g., on a dev's machine pointing at `~/Dev/dotfiles/.claude/`). Any path operation on the Claude Code config directory MUST resolve symlinks first (`realpath` or `Path.resolve()`). Stage 1's probes don't write to `~/.claude/` so this stage is symlink-transparent, but Stage 6's OpenTelemetry sub-step needs to be aware (see `stage-6-doctor-verification.md`). Stage 1 includes a single info-log line if the symlink is detected so the friend sees we've noticed and acknowledged: `Note: ~/.claude/ resolves to <realpath>`. No prompt, no remediation — informational only.

## What this stage deliberately does NOT do

- Doesn't install missing dependencies. Auto-installing `gh` or `node` is way out of scope and varies wildly by platform.
- Doesn't modify the friend's shell rc files. Even adding an `export` line is too invasive without explicit confirmation; mention it as a hint, don't do it.
- Doesn't time out probes aggressively. `claude auth status` may take a couple seconds; let it run.

## Cross-references

- ADR-015 Stage 1
- team-lead pushback P1
- ADR-031 (solo-first pivot) — Activity Feed removed; gh is now a soft requirement used by `/sf:doctor`'s update check
- ADR-006 (curated stack) — context7 + claude-md-management additions; Skill Creator's ANTHROPIC_API_KEY caveat
