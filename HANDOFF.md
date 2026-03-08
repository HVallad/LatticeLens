# LatticeLens — Test Coverage & Quality Orchestration Prompt

> Hand this to a coding agent. It contains everything needed to continue improving LatticeLens test coverage and fix outstanding issues.

---

## Project Context

LatticeLens is a knowledge governance CLI (v1.0.0, Python 3.11+) that stores atomic facts as YAML files in a `.lattice/` directory. It has three storage layers (WHY, GUARDRAILS, HOW), Pydantic validation, two backends (YAML flat-file, SQLite), an MCP server for remote access, and a role-based context assembly system.

**Current state:** 650 tests passing, 87.6% coverage, 0 lint errors. The project dogfoods itself with 93 lattice facts governing its own development.

**Architecture:** CLI (Typer + Rich) → Services (stateless functions) → Store (protocol-based). Each CLI command file is a thin wrapper around a service function. The `LatticeStore` protocol in `store/protocol.py` defines the interface; `yaml_store.py` and `sqlite_store.py` implement it. `lens_store.py` is an MCP client that implements the same protocol for remote lattices.

**Key files:**
- `src/lattice_lens/cli/` — One file per command group
- `src/lattice_lens/services/` — Business logic
- `src/lattice_lens/store/` — Storage backends + in-memory index
- `src/lattice_lens/mcp/` — MCP server (FastMCP)
- `src/lattice_lens/models.py` — Pydantic `Fact` model
- `tests/conftest.py` — Fixtures: `tmp_lattice`, `yaml_store`, `seeded_store`, `make_fact()`

**Governance rules:** The `.lattice/` directory contains rules the project must follow. Key ones: no hard deletes (AUP-01), immutable codes (AUP-02), append-only changelog (DG-01), tag normalization (DG-02). Run `lattice check` to verify integrity. The agent hook injects these rules automatically — follow them.

---

## Tasks (Priority Order)

### Task 1: Fix broken MCP integration tests (CRITICAL)

**Problem:** All 4 tests in `tests/test_lens_integration.py` silently skip because `FastMCP.run()` no longer accepts `host`/`port` kwargs. This means the entire MCP round-trip path has zero actual test coverage.

**Error:** `TypeError: FastMCP.run() got an unexpected keyword argument 'host'`

**Locations (4 identical patterns):**
- Line 107: `server.run(transport="sse", host="127.0.0.1", port=port)`
- Line 152: same
- Line 198: same
- Line 253: same

**Current FastMCP.run() signature:**
```python
FastMCP.run(self, transport: Literal['stdio', 'sse', 'streamable-http'] = 'stdio', mount_path: str | None = None) -> None
```

**What to do:**
1. Read `src/lattice_lens/mcp/server.py` to understand how `create_server()` works
2. Check the installed FastMCP version and its current API for configuring host/port (may be via `Settings`, env vars, or constructor args)
3. Update `test_lens_integration.py` to use the correct API — the tests need to start a real MCP server on a free port in a background thread and connect a `LensStore` client to it
4. If FastMCP no longer supports SSE transport easily, consider using `stdio` transport with subprocess pipes instead
5. Make sure all 4 tests actually RUN (not skip) and PASS

**The tests cover:**
- `test_roundtrip_get` — Seed server, LensStore.get() returns matching Fact
- `test_roundtrip_list` — LensStore.list_facts() returns all expected facts
- `test_roundtrip_write` — Writable LensStore.create() persists to server
- `test_roundtrip_context` — context_service works with LensStore.index

**Keep the `@pytest.mark.integration` marker.** These tests should still be excluded from `pytest -m "not integration"`.

---

### Task 2: Add extract command CLI tests (HIGH)

**Problem:** `src/lattice_lens/cli/extract_command.py` has 14% coverage — the entire CLI layer is untested.

**File to create:** `tests/test_extract_cli.py`

**The extract command signature:**
```python
def extract(
    file: Optional[Path],           # Document to extract from (.md, .txt, .docx)
    prompt: bool,                   # --prompt: print extraction prompt and exit
    dry_run: bool,                  # --dry-run: preview without writing
    model: str,                     # --model: LLM model name
    api_key: Optional[str],         # --api-key: Anthropic API key
):
```

**Code paths to test:**

1. **`--prompt` mode (lines 37-53):** Prints `EXTRACTION_SYSTEM_PROMPT` + existing fact codes to stdout, then exits. Does NOT require an API key or file. Test that output contains the system prompt text and any existing codes.

2. **No file argument (line 55-57):** When no `--prompt` flag and no file, prints error and exits 1.

3. **File not found (lines 59-61):** Nonexistent file path → error, exit 1.

4. **No API key (lines 63-69):** No `--api-key` flag and no `LATTICE_ANTHROPIC_API_KEY` env var → error, exit 1.

5. **Successful extraction + dry-run (lines 71-130):** Mock `extract_facts_from_document()` to return a list of extracted facts. With `--dry-run`, they're displayed but NOT written to the store.

6. **Successful extraction + write (lines 132-144):** Without `--dry-run`, facts are written. Existing codes are skipped (collision detection). User sees "Created" for new facts and "Skipped" for collisions.

**Mocking strategy:** Mock `lattice_lens.services.extract_service.extract_facts_from_document` to return canned `Fact` objects. This avoids needing a real Anthropic API key. Use `monkeypatch.setattr()`.

**Test count target:** 8-10 tests covering all branches.

---

### Task 3: Remove dead code in validate_service.py (MEDIUM)

**Problem:** Lines 95-99 in `src/lattice_lens/services/validate_service.py` check for unsorted or non-lowercase tags, but these checks can NEVER trigger because `validate_lattice` parses facts via `Fact(**data)`, and Pydantic's `normalize_tags` validator (in `models.py` line 117-126) sorts, lowercases, and deduplicates tags during construction.

**The dead code:**
```python
# Line 95-99
for tag in fact.tags:
    if tag != tag.lower():
        result.add_warning(f"{path.name}: Tag '{tag}' is not lowercase")
if fact.tags != sorted(fact.tags):
    result.add_warning(f"{path.name}: Tags are not sorted")
```

**What to do:**
- Remove lines 95-99 from `validate_service.py`
- The existing tests in `test_validate.py` already document this behavior:
  - `test_pydantic_normalizes_tags_so_no_unsorted_warning` — confirms Pydantic normalization prevents the warning
  - `test_raw_unsorted_tags_also_normalized` — confirms even raw YAML gets normalized on `Fact(**data)` load
- After removing the dead code, remove the `test_raw_unsorted_tags_also_normalized` test (it was testing dead code behavior) and update `test_pydantic_normalizes_tags_so_no_unsorted_warning` to not reference the removed checks
- Run `pytest -m "not integration"` to confirm nothing breaks

---

### Task 4: Boost reconcile command coverage to 80%+ (MEDIUM)

**Problem:** `src/lattice_lens/cli/reconcile_command.py` is at 70% — the Rich output rendering branches for different report sections are untested.

**File to expand:** `tests/test_reconcile_cli.py`

**Untested branches (all in `_print_rich()` function):**

1. **Stale facts section (lines 146-152):** When `report.stale` is non-empty, renders a stale facts table. Needs a fact with `review_by` in the past that's referenced in source code.

2. **Violated facts section (lines 155-161):** When `report.violated` is non-empty. Needs a fact referenced in code that violates some constraint.

3. **Untracked patterns section (lines 164-170):** When `report.untracked` is non-empty. Needs source code references that don't match any known fact code.

4. **Confirmed facts in verbose mode (line 180):** Only shown when `--verbose` is passed AND `report.confirmed` is non-empty.

5. **Orphaned facts in verbose mode (lines 183-187):** Facts with no source code references, shown only in verbose mode.

**Testing approach:** Create source files with specific patterns (e.g., `# ADR-01 reference`) and facts with specific states (stale review_by, etc.), then invoke `lattice reconcile` with different flags and assert the output contains the expected sections.

---

### Task 5: Boost validate command coverage to 80%+ (MEDIUM)

**Problem:** `src/lattice_lens/cli/validate_command.py` is at 75% — the entire Lens Mode path (lines 24-57) is untested because `is_lens_mode()` always returns False in tests.

**File to expand:** `tests/test_validate_cli.py`

**Untested path (Lens Mode — lines 24-57):**
```python
if is_lens_mode():
    if fix:  # --fix not allowed remotely
        error + exit(1)

    store = require_lattice()
    result_data = tool_lattice_validate(store)

    if result_data["errors"]:     # show errors
    if result_data["warnings"]:   # show warnings
    if ok and no warnings:        # "All checks passed"
    elif ok with warnings:        # "No errors. N warning(s)."
    else:                         # "N error(s), N warning(s)." + exit(1)
```

**Testing approach:** Use `monkeypatch` to:
1. Mock `lattice_lens.cli.validate_command.is_lens_mode` to return `True`
2. Mock `lattice_lens.cli.validate_command.require_lattice` to return a mock store
3. Mock `lattice_lens.cli.validate_command.tool_lattice_validate` to return various result dicts

**Test cases needed:**
- Lens mode + `--fix` → error, exit 1
- Lens mode + remote returns errors → exit 1, shows error count
- Lens mode + remote returns warnings only → exit 0, shows warning count
- Lens mode + remote returns all clean → "All checks passed"

---

### Task 6: Address unclosed SQLite connections (LOW)

**Problem:** Test suite emits `ResourceWarning: unclosed database` from SQLite backend tests.

**Root cause:** `SqliteStore` opens a `sqlite3.Connection` but doesn't implement `close()` or context manager (`__enter__`/`__exit__`).

**File:** `src/lattice_lens/store/sqlite_store.py`

**What to do:**
1. Add a `close()` method that calls `self._conn.close()`
2. Add `__enter__` and `__exit__` for context manager support
3. Update test fixtures to call `store.close()` in teardown (or use `with` blocks)
4. This is a minor cleanup — don't over-engineer it

---

## Constraints & Rules

1. **Run `pytest -m "not integration"` after each task** — all 650+ tests must pass
2. **Run `ruff check .` and `ruff format --check .`** — zero lint errors allowed
3. **Coverage must stay ≥80%** (configured in `pyproject.toml` as `fail_under = 80`)
4. **Follow governance rules** — no hard deletes (AUP-01), immutable codes (AUP-02), append-only changelog (DG-01). The agent hook will remind you.
5. **Mark integration tests** with `@pytest.mark.integration`
6. **Use existing test patterns** — see `tests/conftest.py` for fixtures (`make_fact()`, `yaml_store`, `seeded_store`, `tmp_lattice`)
7. **Pydantic normalizes on construction** — `Fact(**data)` sorts tags, lowercases them, deduplicates them, validates code-layer prefix, and rejects Superseded without superseded_by. Write raw YAML (bypassing Pydantic) when you need to test validation of malformed data.

## Development Commands

```bash
pip install -e ".[dev,extract,mcp]"    # Install all deps
pytest -m "not integration"            # Run non-integration tests
pytest --cov=lattice_lens              # Run with coverage
ruff check .                           # Lint
ruff format .                          # Auto-format
```

## Success Criteria

- All integration tests actually RUN (not skip) and PASS
- `extract_command.py` coverage ≥ 80%
- `reconcile_command.py` coverage ≥ 80%
- `validate_command.py` coverage ≥ 80%
- Dead code in `validate_service.py` removed
- Overall coverage ≥ 88%
- All existing 650 tests still pass
- Zero ruff errors
