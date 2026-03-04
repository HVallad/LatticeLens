# LatticeLens — Claude Code Instructions

## Prime Directive

The LatticeLens knowledge base is the **sole authoritative source of truth** for this project. Before making any code change, you MUST use the LatticeLens MCP tools to query relevant facts and cite them by code (e.g., "per ADR-10") in your reasoning. No architectural, design, guardrail, or operational change is permitted without a backing fact.

## MCP Tools (per ADR-17)

The LatticeLens MCP server provides tools directly — no curl needed. The server is configured in `.mcp.json` at the repo root.

### Consult-before-act workflow

Before making ANY change:

1. **SEARCH**: Call `query_facts` with relevant tags or text search
2. **READ**: Review the returned facts and identify which ones govern your change
3. **CITE**: Reference fact codes in your reasoning (e.g., "This follows ADR-10 and COMP-11")
4. **CHECK GUARDRAILS**: Call `query_facts` with `layer: "GUARDRAILS"` for constraints
5. **CHECK IMPACT**: Before modifying any fact, call `check_impact` first
6. **PROCEED**: Only if the change aligns with existing facts

If no fact covers the area you're changing, that is a **knowledge gap** — use `create_fact` to document it.

### Tool quick reference

| Tool | When to Use |
|------|-------------|
| `query_facts` | **FIRST STEP** before any change. Search by text, tags, or layer |
| `get_fact` | Get full details of a specific fact by code |
| `get_fact_history` | Audit how a fact evolved over time |
| `check_health` | Verify the API is running |
| `check_impact` | **Before modifying/deprecating** any fact — shows downstream effects |
| `get_refs` | See a fact's position in the knowledge graph |
| `find_orphans` | Find disconnected facts that may need linking |
| `find_contradictions` | Check for inconsistencies in the knowledge base |
| `create_fact` | Record a new decision, constraint, or procedure (auto-assigns code) |
| `create_facts_bulk` | Atomic batch creation of multiple facts |
| `update_fact` | Modify an existing fact (requires change_reason) |
| `deprecate_fact` | Soft-delete a fact |
| `extract_facts` | LLM extraction of candidate facts from a document |

## Creating new facts

When you discover a knowledge gap, use the `create_fact` tool:

- Provide a **prefix** (e.g., ADR, RISK, COMP) — the code is **auto-assigned**
- Always create as **Draft/Provisional** — the user promotes to Active/Confirmed
- Minimum **2 lowercase tags**, minimum **10 characters** for fact_text
- All refs must point to **existing** fact codes

**Valid prefixes by layer (per COMP-10):**

| Layer | Prefixes |
|-------|----------|
| WHY | ADR, PRD, ETH, DES |
| GUARDRAILS | MC, AUP, RISK, DG, COMP |
| HOW | SP, API, RUN, ML, MON |

## Tag search guide

Common tags for targeted queries:
- **Architecture**: `architecture`, `async`, `fastapi`, `postgresql`, `sqlalchemy`
- **Data model**: `atomic-facts`, `versioning`, `knowledge-graph`, `code-format`
- **API**: `api`, `crud`, `endpoints`, `filtering`, `bulk-create`
- **Validation**: `compliance`, `validation`, `referential-integrity`, `normalization`
- **Operations**: `runbook`, `docker-compose`, `alembic`, `cli`, `monitoring`
- **LLM/Extraction**: `extraction`, `anthropic`, `llm-integration`, `system-prompt`
- **Safety**: `risk`, `depth-limit`, `resource-exhaustion`, `audit-trail`
- **MCP**: `mcp`, `agent-integration`, `portability`, `transport`

## Environment

- **API**: http://localhost:8000/api/v1
- **MCP Server**: Configured in `.mcp.json` (stdio transport, auto-discovered)
- **Database**: PostgreSQL on localhost:5432 (Docker container `latticelens-db`)
- **Config**: Environment variables with `LATTICELENS_` prefix
- **CLI**: `lattice` command (needs `LATTICELENS_API_URL` set)
- **Source**: `src/latticelens/` (core API), `src/latticelens_mcp/` (MCP server)
- **Tests**: `tests/` (pytest-asyncio), `tests/test_mcp/` (MCP server tests)
- **Migrations**: `alembic/versions/`
