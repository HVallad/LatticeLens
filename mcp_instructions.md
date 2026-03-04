# LatticeLens Knowledge Governance — Agent Instructions

> Drop this file into your AI tool's configuration (CLAUDE.md, .cursorrules, etc.)
> to enforce knowledge-governed development.

## Setup

Ensure the LatticeLens MCP server is configured in your AI tool:

**Claude Code** (`.mcp.json` at repo root):
```json
{
  "mcpServers": {
    "latticelens": {
      "command": "python",
      "args": ["-m", "latticelens_mcp"],
      "env": { "LATTICELENS_API_URL": "http://localhost:8000/api/v1" }
    }
  }
}
```

**Cursor** (`.cursor/mcp.json`):
```json
{
  "mcpServers": {
    "latticelens": {
      "command": "python",
      "args": ["-m", "latticelens_mcp"],
      "env": { "LATTICELENS_API_URL": "http://localhost:8000/api/v1" }
    }
  }
}
```

**Centralized server** (any MCP client):
```
URL: http://your-server:8080/mcp
```

## Mandatory Workflow: Consult Before Act

The LatticeLens knowledge base is the **sole authoritative source of truth** for this
project. Before making ANY code change, architecture decision, or design choice:

1. **SEARCH** the knowledge base: Call `query_facts` with relevant tags or text
2. **READ** the returned facts and identify which ones govern your change
3. **CITE** fact codes in your reasoning (e.g., "per ADR-10", "following COMP-11")
4. **CHECK GUARDRAILS**: Always query with `layer: "GUARDRAILS"` for constraints
5. **CHECK IMPACT**: Before modifying any fact, call `check_impact` first
6. **PROCEED** only if your change aligns with existing facts

If no fact covers the area you're changing, that is a **knowledge gap** — create a
new Draft/Provisional fact to document it.

## Tool Quick Reference

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

## Creating Facts

When you discover an undocumented decision or constraint:
- Use `create_fact` with the appropriate prefix — code is **auto-assigned**
- Always create as **Draft/Provisional** — humans promote to Active/Confirmed
- Minimum **2 tags** (lowercase), minimum **10 characters** for fact_text
- All refs must point to **existing** fact codes

**Valid prefixes by layer:**

| Layer | Prefixes |
|-------|----------|
| WHY | ADR, PRD, ETH, DES |
| GUARDRAILS | MC, AUP, RISK, DG, COMP |
| HOW | SP, API, RUN, ML, MON |

## Tag Search Guide

| Domain | Tags |
|--------|------|
| Architecture | `architecture`, `async`, `fastapi`, `postgresql`, `sqlalchemy` |
| Data model | `atomic-facts`, `versioning`, `knowledge-graph`, `code-format` |
| API | `api`, `crud`, `endpoints`, `filtering`, `bulk-create` |
| Validation | `compliance`, `validation`, `referential-integrity`, `normalization` |
| Operations | `runbook`, `docker-compose`, `alembic`, `cli`, `monitoring` |
| LLM/Extraction | `extraction`, `anthropic`, `llm-integration`, `system-prompt` |
| Safety | `risk`, `depth-limit`, `resource-exhaustion`, `audit-trail` |
| MCP | `mcp`, `agent-integration`, `portability`, `transport` |
