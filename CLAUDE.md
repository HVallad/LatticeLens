# CLAUDE.md

## Project Overview

LatticeLens is a knowledge governance CLI for AI agent systems. It stores atomic facts as individual YAML files in a `.lattice/` directory, organized into three layers (WHY, GUARDRAILS, HOW). Facts have a lifecycle (Draft -> Under Review -> Active), are validated by Pydantic, tracked by git, and queryable by tag, layer, status, and text search.

The project dogfoods itself: its own `.lattice/` directory contains 90 facts governing its development.

## Development Setup

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Install with all optional features
pip install -e ".[dev,extract,mcp]"

# Run tests (excludes integration tests that need API keys)
pytest -m "not integration"

# Run all tests
pytest

# Lint and format
ruff check .
ruff format --check .
ruff format .          # auto-fix
```

Python 3.11+ required. Ruff config: line-length=100, target py311.

## Project Structure

```
src/lattice_lens/
  cli/                  # Typer CLI commands (one file per command group)
    main.py             # App entrypoint, registers all commands
    helpers.py           # require_lattice() — finds .lattice/ root, returns store
    fact_commands.py     # fact add/get/ls/edit/promote/deprecate
    graph_commands.py    # graph impact/orphans/contradictions
    check_command.py     # CI gate (--format github for Actions annotations)
    reconcile_command.py # Bidirectional code-to-facts reconciliation
    context_commands.py  # Role-scoped, token-budgeted context assembly
    extract_command.py   # LLM-powered fact extraction from docs
    exchange_commands.py # import/export (JSON/YAML)
    backend_command.py   # backend status/switch (yaml <-> sqlite)
    git_commands.py      # diff, log (git-scoped to .lattice/)
    serve_command.py     # MCP server
    tags_command.py      # Tag registry
    types_command.py     # Type registry
    ...
  services/             # Business logic (stateless functions, take store as arg)
    fact_service.py      # promote_fact(), create_fact(), update_fact()
    graph_service.py     # impact_analysis(), find_orphans(), find_contradictions()
    check_service.py     # CI-gate integrity checks
    reconcile_service.py # Code scanning + fact matching
    context_service.py   # Token-budgeted context assembly
    extract_service.py   # LLM extraction pipeline
    exchange_service.py  # Import/export with conflict strategies
    validate_service.py  # Lattice-wide validation
    tag_service.py       # Tag registry rebuild
    type_service.py      # Type registry + audit
    code_scanner.py      # Codebase scanning for reconciliation
    ...
  store/                # Storage abstraction
    protocol.py          # LatticeStore Protocol (interface)
    yaml_store.py        # YAML flat-file backend (Tier 1)
    sqlite_store.py      # SQLite backend (Tier 2)
    index.py             # In-memory FactIndex
  mcp/                  # MCP server (FastMCP)
    server.py            # Server setup
    tools.py             # Tool definitions
  models.py             # Pydantic Fact model + enums (FactStatus, FactLayer, etc.)
  config.py             # Settings, lattice root discovery, layer/prefix mappings
```

## Key Patterns

- **CLI**: Typer with Rich console output. Each command file exports functions registered in `main.py`. Support `--json` for machine-readable output.
- **Storage Protocol**: `LatticeStore` in `store/protocol.py` defines the interface (`get`, `create`, `update`, `list_facts`, etc.). All services accept any store implementation. `helpers.py:require_lattice()` returns the correct store based on `config.yaml`.
- **Service Layer**: Pure functions in `services/` taking a store as first argument. CLI commands are thin wrappers.
- **Pydantic Models**: `Fact` model in `models.py` with validators for code format (`^[A-Z]+-\d+$`), tag normalization, layer-prefix consistency, and superseded rules.
- **Changelog**: Every mutation appends to `history/changelog.jsonl` (rule DG-01). Append-only, never truncated.

## Testing

Tests use `pytest` with `typer.testing.CliRunner` for CLI integration tests.

Key fixtures in `conftest.py`:
- `tmp_lattice` — temp `.lattice/` directory with proper structure
- `yaml_store` — `YamlFileStore` pointed at `tmp_lattice`
- `seeded_store` — store pre-loaded with 12 seed facts
- `make_fact(**overrides)` — helper to create facts with sensible defaults

Mark tests requiring external APIs with `@pytest.mark.integration`.

## Governance

The `.lattice/` directory contains the project's own knowledge lattice. Key rules:

- **DG-01**: Every mutation appends to changelog.jsonl
- **AUP-01**: No hard deletes — deprecation only
- **AUP-02**: Fact codes are immutable after creation
- **DG-06**: Lifecycle: Draft -> Under Review -> Active -> Deprecated/Superseded

Run `lattice check` to verify lattice integrity. Run `lattice status` for a summary.

## Configuration

- `pyproject.toml` — Python 3.11+, dependencies, ruff/pytest config
- `.lattice/config.yaml` — Backend (yaml/sqlite), schema version
- `.lattice/tags.yaml` — Generated tag registry
- `.lattice/types.yaml` — Code prefix to canonical type mapping
