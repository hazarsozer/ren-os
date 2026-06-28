# lean-ctx CLI Spike Findings

**Date:** 2026-06-17  
**Verdict:** GO — with one important correction to the spec's assumed command surface.

---

## 1. Installed Version

```
lean-ctx 3.8.8 (official, https://github.com/yvgude/lean-ctx)
```

**Install command used:**
```bash
cargo install lean-ctx --version 3.8.8
```
Cargo 1.95.0 was available; compile took ~4 minutes. Binary lands at `~/.cargo/bin/lean-ctx`.

---

## 2. CLI Surface Discovery

**The spec assumed `lean-ctx map <path> --format json`. This subcommand does not exist.**

Running `lean-ctx --help` and `lean-ctx help all` revealed that `lean-ctx` is a context-compression runtime with 10 _read modes_ for files and a _graph_ subsystem for project-level analysis. There is no `map` subcommand.

The two usable CLI surfaces for symbol extraction are:

### Surface A — Per-file signatures (preferred for adapter)

```bash
lean-ctx read <file> -m signatures
```

**Output format (text, stdout):**
```
sf_paths.py [322L]
fn pub framework_version() → str @L49-82
fn pub framework_root() → Path @L98-107
fn _resolve_path_env(name:s) → Path | None @L110-120
fn pub wiki_path() → Path @L123-135
class pub HandleNotConfiguredError @L141-147
class pub InvalidHandleError @L150-160
class pub SchemaVersionMismatchError @L163-183
  fn __init__(self, path:Path, found:int, expected:int) → None @L176-183
fn pub validate_handle(value:s) → str @L192-206
fn pub handle(*, strict_schema:bool = True) → str @L209-248
fn _parse_schema_version_from_frontmatter(text:s) → int | None @L251-259
fn _parse_field_from_frontmatter(text:s, field:s) → str | None @L262-281
fn _parse_handle_from_frontmatter(text:s) → str | None @L284-302
```

**Field mapping from text parsing:**

| Spec field   | Location in text line                              | Example                 |
|--------------|----------------------------------------------------|-------------------------|
| `name`       | token after visibility keyword (or after kind)     | `framework_version`     |
| `kind`       | first token (`fn` or `class`)                      | `fn`                    |
| `file_path`  | from the caller (per-file invocation)              | `lib/sf_paths.py`       |
| `line_start` | number before `-` in `@LN-M`                       | `49`                    |
| `line_end`   | number after `-` in `@LN-M`                        | `82`                    |
| `signature`  | `name(params) → return_type` parsed from line      | `framework_version() → str` |

**Line regex (Python):**
```python
r'^(\s*)(fn|class)\s+(pub\s+)?(\w+)(?:\((.*?)\))?\s*(?:→\s*(.*?))?\s*@L(\d+)-(\d+)\s*$'
```
Groups: `(indent, kind, visibility, name, params, return_type, start, end)`

**Limitation:** per-file only. Adapter must iterate `find <root> -name "*.py"` (or language extension glob) and invoke once per file.

### Surface B — Project-wide graph (SQLite)

```bash
lean-ctx graph build <path>
```

Builds a property graph index stored at:
```
~/.local/share/lean-ctx/graphs/<project-hash>/graph.db
```

`graph.db` schema (nodes table — the only relevant table):
```sql
CREATE TABLE nodes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT NOT NULL,   -- "file" or "symbol"
    name       TEXT NOT NULL,   -- class name (functions NOT indexed)
    file_path  TEXT NOT NULL,
    line_start INTEGER,
    line_end   INTEGER,
    metadata   TEXT             -- NULL in practice for Python
);
```

**Critical limitation:** only **class-level** symbols are indexed; functions are absent from this DB. Surface A (signatures mode) is richer.

---

## 3. Output Format

**No native JSON output.** `--json` flag is accepted but silently ignored for read modes — output format is identical with or without it.

The fixture at `lib/codemap/tests/fixtures/leanctx-sample-output.json` contains the raw text output (in `_raw_signatures_output`) and a parsed JSON representation of all 13 symbols from `lib/sf_paths.py`.

10-line excerpt of the raw signatures output:
```
sf_paths.py [322L]
fn pub framework_version() → str @L49-82
fn pub framework_root() → Path @L98-107
fn _resolve_path_env(name:s) → Path | None @L110-120
fn pub wiki_path() → Path @L123-135
class pub HandleNotConfiguredError @L141-147
class pub InvalidHandleError @L150-160
class pub SchemaVersionMismatchError @L163-183
  fn __init__(self, path:Path, found:int, expected:int) → None @L176-183
fn pub validate_handle(value:s) → str @L192-206
```

---

## 4. Read-Only Verification

```
READ-ONLY: OK
no stray cache dir
```

`lean-ctx graph build lib` writes **only** to `~/.local/share/lean-ctx/graphs/<hash>/` — never into the scanned project tree. Zero files were created or modified under `lib/`.

**Cache location:** `~/.local/share/lean-ctx/` (XDG data dir). No redirect knob needed; the user-level cache dir is the default and acceptable for the code-map use case.

---

## 5. Adapter Design Implications for Task 4

The adapter cannot call `lean-ctx map <path> --format json`. Instead it must:

1. Walk the directory tree (`glob("**/*.py")` for Python projects).
2. For each `.py` file: `lean-ctx read <file> -m signatures 2>/dev/null`
3. Parse each line with the regex above to extract `(kind, name, params, return_type, line_start, line_end)`.
4. Assemble into the `Symbol` model from Task 3.

This is a text-parse adapter, not a JSON-deserialize adapter. The parse regex is deterministic and already validated against `lib/sf_paths.py` (13 symbols, zero missed).

**Alternative:** query the SQLite graph DB directly after `lean-ctx graph build` — faster for large repos but misses all functions; only viable if Task 3's model is class-only.

---

## 6. Go/No-Go Verdict

| Gate                              | Result |
|-----------------------------------|--------|
| `lean-ctx` installs headlessly    | ✅ PASS |
| CLI produces per-symbol output    | ✅ PASS (per-file via `-m signatures`) |
| Output includes name/kind/file/start/end/signature | ✅ PASS |
| Does not write into scanned project | ✅ PASS (READ-ONLY: OK) |
| Native JSON output                | ❌ N/A — text parsing required |
| `lean-ctx map` subcommand         | ❌ Does not exist — use `lean-ctx read -m signatures` |

**Overall: GO.** The adapter approach changes from JSON-deserialize to text-parse, but all required symbol fields are available and the read-only gate passes cleanly.
