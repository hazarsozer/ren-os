# Stage 6 — `/sf:doctor` verification + optional OpenTelemetry

Per ADR-015 Stage 6 (2026-05-28 amendment) + ADR-010. Always runs (per stage-recheck table).

## Procedure

### 6.1 Delegate to `/sf:doctor`

Sf-lifecycle owns `/sf:doctor`. Call its programmatic entry point:

```
result = doctor.report() -> DoctorResult
```

`DoctorResult` (proposed; sf-lifecycle will lock the shape per plan §5.3 ask):

```yaml
DoctorResult:
  passed: bool
  checks: list[Check]
  warnings: list[str]
  remediation_hints: list[str]

Check:
  name: str            # e.g. "plugin: context-mode@x.y.z"
  status: enum {pass|warn|fail}
  detail: str
```

If sf-lifecycle hasn't yet shipped a programmatic entry, fall back to invoking `/sf:doctor` as a slash command and parse its output. Either way, Stage 6 cares about pass/fail at the aggregate level.

### 6.2 Per-check coverage (what sf-doctor checks)

Stage 6 expects sf-doctor to verify at minimum:

- All 6 required plugins present at pinned versions (matches `state.stage_artifacts.2.plugins_installed`)
- Hooks registered in expected order per ADR-010 (Context Mode → claude-mem → wake-up)
- `ANTHROPIC_API_KEY` + Upstash key accessible (re-check Stage 1)
- Wiki at `~/.startup-framework/wiki/` exists with frontmatter-valid `index.md`, `log.md`, `identity.md`
- `identity.md` schema_version matches current framework
- `LICENSES.md` is up-to-date (regenerated this run; see 6.3)

### 6.3 (Re)generate LICENSES.md

After Stage 5's skeleton is in place, write `~/.startup-framework/wiki/LICENSES.md` from sf-distribution's pinned-version registry. Lists each plugin's license + SPDX id + one-line summary + link.

If the friend's existing `LICENSES.md` differs from the regenerated version (e.g. they hand-edited it), Stage 6 surfaces the diff and asks for approval before overwriting. (Per ADR-017's never-silently-overwrite principle.)

### 6.4 Optional OpenTelemetry sub-step

Per ADR-015 Stage 6 (2026-05-28 OTel addition). Ask:

```
Want token usage / session traces / cost observability?

Claude Code has NATIVE OpenTelemetry support. Set:
  OTEL_EXPORTER_OTLP_ENDPOINT     ← your OTLP backend URL
  OTEL_EXPORTER_OTLP_HEADERS      ← auth headers (e.g. "x-honeycomb-team: <key>")

Compatible backends: Honeycomb, Datadog, Grafana, Langfuse, Dash0,
self-hosted OTel Collector.

Skip if you don't want telemetry exported.

  yes → walk me through the env-var setup
  skip → don't ask again this install
```

- **yes** → present the env-var setup hints; persist `state.stage_artifacts.6.otel_enabled: true`.
- **skip** → persist `state.stage_artifacts.6.otel_enabled: false`.

#### Symlink-safe path resolution for OTel writes

If the OTel sub-step writes to a Claude Code config path (e.g. `~/.claude/settings.json` for persistent env-var setup), **resolve the path's symlinks FIRST** before writing. On some dev machines `~/.claude/` is a symlink to a dotfiles repo (e.g. `~/Dev/dotfiles/.claude/`); writing to the literal symlink path without resolving can either follow the link (good) or — depending on the tool/OS — create a regular file where the symlink would have pointed (bad).

Pseudocode:

```
target_path = realpath("~/.claude/settings.json")
# ALL subsequent reads / writes use target_path, not the literal "~/.claude/settings.json"
read(target_path)
edit(target_path)
write(target_path)
```

When the symlink is detected, surface a single info-log line to the friend:

```
Note: ~/.claude/settings.json resolves to <realpath>.
      Edits will be made to the resolved file (your dotfiles repo).
```

This is informational only — the friend already chose to symlink their config to a managed repo; we're just being transparent about where the writes land. No prompt, no opt-out (resolving the symlink is correct behavior; declining would mean writing to a phantom file).

If `~/.claude/` is a real directory (not a symlink), the info-log line is suppressed.

### 6.5 Capture outcomes

```json
{
  "stage_artifacts": {
    "6": {
      "doctor_passed": true,
      "otel_enabled": false,
      "licenses_md_written": true,
      "last_check_at": "<ISO>"
    }
  }
}
```

### 6.6 Friend-facing summary

```
Stage 6 — /sf:doctor verification:
  ✓ 6/6 plugins at pinned versions
  ✓ hooks registered in expected order
  ✓ env vars set
  ✓ wiki path valid
  ✓ identity.md schema current
  ✓ LICENSES.md regenerated (2 plugins under ELv2 — see file for SaaS caveats)

  OpenTelemetry: skipped (re-enable anytime via env vars)
```

If `doctor_passed: false`, surface the failing checks + remediation hints; abort Stage 6 (don't proceed to Stage 7 if doctor is red).

## What this stage deliberately does NOT do

- Doesn't run the same checks Stage 1 ran (auth, gh, node). Sf-doctor handles re-checks at its own discretion; Stage 6 trusts sf-doctor's coverage.
- Doesn't try to fix what sf-doctor flagged. Remediation is the friend's call.

## Edge cases

- **sf-doctor returns a warning** (yellow) → Stage 6 passes if no `fail` checks; warnings are surfaced + counted.
- **OTel env vars already set by the friend before install** → detect via shell env probe; respect; mark `otel_enabled: true` without re-prompting.
- **LICENSES.md regeneration would change a plugin's license summary** (e.g. context-mode bumped from ELv2 to MIT) → flag prominently; the friend may want to know.

## Cross-references

- ADR-010 (hook ordering) — what sf-doctor checks for
- ADR-015 Stage 6 + OTel amendment
- ADR-016 (framework license) — LICENSES.md content
- plan §5.3 — `doctor.report()` schema ask
- `wiki-skeleton/templates/LICENSES.md.tmpl` — the template Stage 6 instantiates
