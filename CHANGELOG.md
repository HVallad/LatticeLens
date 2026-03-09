# Changelog

All notable changes to LatticeLens are documented in this file.

## [1.0.0] - 2025-12-20

### Added
- **Interactive web viewer** — FastAPI-based UI with graph visualization and role context preview (`lattice view`)
- **Typed edges & graph expansion** (Layer 4) — inferred relationships between facts with edge types
- **Lens mode** — remote lattice access via MCP client for cross-project queries (`lattice lens`)
- **Evaluation command** — fact quality scoring and assessment (`lattice evaluate`)
- **Project scoping** — multi-project lattice support with per-project filtering
- **LLM-powered reconciliation** — bidirectional code-to-facts sync with prompt and API modes
- **SQLite backend** (Tier 2) — alternative to YAML flat-file storage
- **CI/CD pipeline** — GitHub Actions with lint, test matrix (3.11–3.13), coverage gate (80%), and lattice integrity check
- **MCP server** — expose lattice as MCP tools for AI agent integration (`lattice serve`)
- **LLM-powered fact extraction** — extract facts from documents using Anthropic API (`lattice extract`)
- **Import/export** — JSON and YAML exchange formats with conflict resolution strategies
- **Coverage reporting** — pytest-cov integration with 91% coverage across 700+ tests
- **Tag and type registries** — generated indexes for tags and code-prefix mappings
- **Lattice check command** — CI-gate integrity validation with GitHub Actions annotations
- **Role-scoped context assembly** — token-budgeted context for different agent roles

### Core
- YAML flat-file storage backend with Pydantic validation
- Three-layer fact organization (WHY, GUARDRAILS, HOW)
- Fact lifecycle management (Draft → Under Review → Active → Deprecated/Superseded)
- Git-scoped diff and log commands
- Rich CLI output with `--json` support for machine-readable output
- Append-only changelog in `history/changelog.jsonl`
- 93 self-governing facts in the project's own `.lattice/` directory
