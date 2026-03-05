# LatticeLens — Phase 5 Implementation Brief
# MCP Server

> **Purpose**: Expose the lattice over the network via the Model Context Protocol, enabling AI tools (Claude Desktop, Claude Code, Cursor, custom agents) to query governed facts natively.
>
> **Timeline**: Week 5 (~5 days).
>
> **Prerequisites**: Phase 4 complete. Full CLI working with YAML backend.

---

## 1. What This Phase Delivers

After Phase 5, a developer can:
- Run `lattice serve` and have Claude Desktop, Claude Code, or Cursor query their lattice via MCP
- Let any MCP-compatible agent ask "what are the active risk findings?" and get governed, role-scoped facts
- Optionally allow write operations (fact creation, updates) through MCP in writable mode

This is the phase that validates LatticeLens's core value proposition end-to-end: an AI agent queries a governed knowledge base and receives precisely the facts it needs, token-budgeted and role-scoped.

---

## 2. New Files

```
src/lattice_lens/
├── mcp/
│   ├── __init__.py
│   ├── server.py               # NEW: MCP server entrypoint
│   ├── tools.py                # NEW: MCP tool definitions
│   └── transport.py            # NEW: stdio + HTTP transport
├── cli/
│   └── serve_command.py        # NEW: lattice serve
tests/
├── test_mcp_tools.py           # NEW: tool logic tests
├── test_mcp_server.py          # NEW: integration tests
└── test_serve_cli.py           # NEW
```

Add `mcp>=1.0.0` to `pyproject.toml` dependencies.

---

## 3. Architecture

The MCP server is a thin wrapper around the same `LatticeStore` and services that the CLI uses. No new storage logic, no new query logic — just a network interface.

```
┌─────────────────────────────┐
│  Claude Desktop / Cursor /  │
│  Claude Code / Custom Agent │
└──────────┬──────────────────┘
           │ MCP Protocol (stdio or HTTP)
           ▼
┌─────────────────────────────┐
│  lattice serve              │
│  (MCP Server)               │
│                             │
│  Tools:                     │
│    fact_get                 │
│    fact_query               │
│    fact_list                │
│    context_assemble         │
│    graph_impact             │
│    graph_orphans            │
│    lattice_status           │
│    [writable mode:]         │
│    fact_create              │
│    fact_update              │
│    fact_deprecate           │
└──────────┬──────────────────┘
           │ LatticeStore protocol
           ▼
┌─────────────────────────────┐
│  YamlFileStore              │
│  .lattice/facts/*.yaml      │
└─────────────────────────────┘
```

---

## 4. MCP Tool Definitions

### 4.1 Read-Only Tools (always available)

```python
# src/lattice_lens/mcp/tools.py
from __future__ import annotations
from lattice_lens.store.protocol import LatticeStore
from lattice_lens.services import graph_service, context_service


# ── fact_get ──
# Description: "Get a single fact by its code (e.g., ADR-03, RISK-07)"
# Input: { "code": string }
# Output: Full fact as JSON, or error if not found
def tool_fact_get(store: LatticeStore, code: str) -> dict:
    fact = store.get(code)
    if fact is None:
        return {"error": f"Fact {code} not found"}
    return fact.model_dump(mode="json")


# ── fact_query ──
# Description: "Query facts with filters. Returns matching facts."
# Input: {
#   "layer": string | null,     e.g., "WHY", "GUARDRAILS", "HOW"
#   "tags": [string] | null,    match any of these tags
#   "status": string | null,    default "Active"
#   "type": string | null,
#   "text_search": string | null
# }
# Output: Array of facts
def tool_fact_query(store: LatticeStore, **filters) -> list[dict]:
    # Map 'tags' to 'tags_any' for the store interface
    if "tags" in filters:
        filters["tags_any"] = filters.pop("tags")
    facts = store.list_facts(**filters)
    return [f.model_dump(mode="json") for f in facts]


# ── fact_list ──
# Description: "List all facts, optionally filtered by layer"
# Input: { "layer": string | null }
# Output: Array of {code, layer, type, status, tags}
def tool_fact_list(store: LatticeStore, layer: str | None = None) -> list[dict]:
    filters = {}
    if layer:
        filters["layer"] = layer
    filters["status"] = ["Active", "Draft", "Under Review"]  # Exclude deprecated
    facts = store.list_facts(**filters)
    return [
        {
            "code": f.code,
            "layer": f.layer.value,
            "type": f.type,
            "status": f.status.value,
            "tags": f.tags,
            "version": f.version,
        }
        for f in facts
    ]


# ── context_assemble ──
# Description: "Assemble token-budgeted context for an agent role.
#   Returns the exact facts that should be injected into the agent's prompt."
# Input: { "role": string, "budget": int | null }
# Output: { role, budget, facts, excluded, refs_outside }
def tool_context_assemble(
    index, roles_dir, role: str, budget: int = 40_000
) -> dict:
    result = context_service.assemble_context(index, roles_dir, role, budget)
    return {
        "role": result.role,
        "budget": {
            "total": result.budget.total_tokens,
            "used": result.budget.used_tokens,
            "remaining": result.budget.remaining,
            "fact_count": result.budget.fact_count,
        },
        "facts": [
            {
                "code": f.code,
                "layer": f.layer.value,
                "type": f.type,
                "fact": f.fact,
                "tags": f.tags,
                "confidence": f.confidence.value,
                "refs": f.refs,
            }
            for f in result.facts_included
        ],
        "excluded": result.facts_excluded,
        "refs_outside": result.refs_outside,
    }


# ── graph_impact ──
# Description: "Show what facts and agent roles are affected if a fact changes"
# Input: { "code": string, "depth": int | null }
# Output: { source, directly_affected, transitively_affected, affected_roles }
def tool_graph_impact(index, code: str, depth: int = 3, role_templates=None) -> dict:
    result = graph_service.impact_analysis(index, code, depth, role_templates)
    return {
        "source": result.source_code,
        "directly_affected": result.directly_affected,
        "transitively_affected": result.transitively_affected,
        "all_affected": result.all_affected,
        "affected_roles": result.affected_roles,
    }


# ── graph_orphans ──
# Description: "Find facts with no connections to the knowledge graph"
# Input: {}
# Output: [codes]
def tool_graph_orphans(index) -> list[str]:
    return graph_service.find_orphans(index)


# ── lattice_status ──
# Description: "Get summary statistics about the lattice"
# Input: {}
# Output: { total, by_layer, by_status, stale, backend }
def tool_lattice_status(store: LatticeStore) -> dict:
    return store.stats()
```

### 4.2 Write Tools (writable mode only)

```python
# ── fact_create ──
# Description: "Create a new fact in the lattice"
# Input: { code, layer, type, fact, tags, owner, ... }
# Output: Created fact or error

# ── fact_update ──
# Description: "Update an existing fact. Increments version."
# Input: { code, changes: {field: value, ...}, reason: string }
# Output: Updated fact or error

# ── fact_deprecate ──
# Description: "Deprecate a fact. Sets status to Deprecated."
# Input: { code, reason: string }
# Output: Deprecated fact or error
```

Write tools follow the same business rules as the CLI (§5 of Phase 1 brief). They call the same `store.create()`, `store.update()`, `store.deprecate()` methods.

---

## 5. MCP Server Implementation

```python
# src/lattice_lens/mcp/server.py
from __future__ import annotations
from pathlib import Path
from mcp.server import Server
from mcp.types import Tool, TextContent
from lattice_lens.store.yaml_store import YamlFileStore
from lattice_lens.config import find_lattice_root, ROLES_DIR
from lattice_lens.mcp.tools import (
    tool_fact_get, tool_fact_query, tool_fact_list,
    tool_context_assemble, tool_graph_impact,
    tool_graph_orphans, tool_lattice_status,
)
import json


def create_server(lattice_root: Path, writable: bool = False) -> Server:
    server = Server("lattice-lens")
    store = YamlFileStore(lattice_root)
    roles_dir = lattice_root / ROLES_DIR

    # Register tools
    read_tools = [
        Tool(
            name="fact_get",
            description="Get a single fact by code (e.g., ADR-03, RISK-07)",
            inputSchema={
                "type": "object",
                "properties": {"code": {"type": "string", "description": "Fact code"}},
                "required": ["code"],
            },
        ),
        Tool(
            name="fact_query",
            description="Query facts with filters. Returns matching active facts.",
            inputSchema={
                "type": "object",
                "properties": {
                    "layer": {"type": "string", "enum": ["WHY", "GUARDRAILS", "HOW"]},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Match any of these tags"},
                    "status": {"type": "string"},
                    "type": {"type": "string"},
                    "text_search": {"type": "string"},
                },
            },
        ),
        Tool(
            name="fact_list",
            description="List all non-deprecated facts, optionally filtered by layer",
            inputSchema={
                "type": "object",
                "properties": {
                    "layer": {"type": "string", "enum": ["WHY", "GUARDRAILS", "HOW"]},
                },
            },
        ),
        Tool(
            name="context_assemble",
            description=(
                "Assemble token-budgeted context for an agent role. "
                "Returns the exact facts that should be injected into an agent's prompt. "
                "Available roles: planning, architecture, implementation, qa, deploy"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "role": {"type": "string", "description": "Role name (e.g., planning, architecture)"},
                    "budget": {"type": "integer", "description": "Token budget (default: 40000)"},
                },
                "required": ["role"],
            },
        ),
        Tool(
            name="graph_impact",
            description="Show what facts and agent roles would be affected if a fact changes",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "depth": {"type": "integer", "description": "Max traversal depth (default: 3)"},
                },
                "required": ["code"],
            },
        ),
        Tool(
            name="graph_orphans",
            description="Find facts disconnected from the knowledge graph (no references in or out)",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="lattice_status",
            description="Get summary statistics: fact counts by layer/status, staleness, backend type",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]

    @server.list_tools()
    async def list_tools():
        tools = read_tools[:]
        if writable:
            tools.extend(_write_tools())
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        # Refresh index on each call to pick up file changes
        store.invalidate_index()

        if name == "fact_get":
            result = tool_fact_get(store, arguments["code"])
        elif name == "fact_query":
            result = tool_fact_query(store, **arguments)
        elif name == "fact_list":
            result = tool_fact_list(store, arguments.get("layer"))
        elif name == "context_assemble":
            result = tool_context_assemble(
                store.index, roles_dir,
                arguments["role"],
                arguments.get("budget", 40_000),
            )
        elif name == "graph_impact":
            result = tool_graph_impact(
                store.index,
                arguments["code"],
                arguments.get("depth", 3),
            )
        elif name == "graph_orphans":
            result = tool_graph_orphans(store.index)
        elif name == "lattice_status":
            result = tool_lattice_status(store)
        elif writable and name in ("fact_create", "fact_update", "fact_deprecate"):
            result = _handle_write(store, name, arguments)
        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, default=str))]

    return server
```

---

## 6. CLI Command

### 6.1 lattice serve

```
lattice serve [--stdio] [--host HOST] [--port PORT] [--writable]
```

**--stdio** (default): Run as stdio transport. This is what Claude Desktop and Claude Code expect when configured via `mcpServers` in their config.

**--host/--port**: Run as HTTP transport on the specified address. For team server deployments.

**--writable**: Enable write tools (fact_create, fact_update, fact_deprecate). Disabled by default for safety.

```python
# src/lattice_lens/cli/serve_command.py
import typer
from pathlib import Path
from lattice_lens.config import find_lattice_root

serve_app = typer.Typer()

@serve_app.callback(invoke_without_command=True)
def serve(
    stdio: bool = typer.Option(True, help="Use stdio transport (for Claude Desktop/Code)"),
    host: str = typer.Option("127.0.0.1", help="HTTP host (disables stdio)"),
    port: int = typer.Option(3100, help="HTTP port"),
    writable: bool = typer.Option(False, help="Enable write operations"),
):
    """Start the LatticeLens MCP server."""
    root = find_lattice_root()
    if root is None:
        typer.echo("Error: No .lattice directory found. Run 'lattice init' first.", err=True)
        raise typer.Exit(1)

    from lattice_lens.mcp.server import create_server
    server = create_server(root, writable=writable)

    if stdio:
        from mcp.server.stdio import stdio_server
        import asyncio
        asyncio.run(stdio_server(server))
    else:
        # HTTP transport
        from mcp.server.sse import sse_server
        import asyncio
        asyncio.run(sse_server(server, host=host, port=port))
```

---

## 7. MCP Client Configuration Templates

### 7.1 Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "lattice": {
      "command": "lattice",
      "args": ["serve", "--stdio"],
      "cwd": "/path/to/your/project"
    }
  }
}
```

### 7.2 Claude Desktop with Writable Mode

```json
{
  "mcpServers": {
    "lattice": {
      "command": "lattice",
      "args": ["serve", "--stdio", "--writable"],
      "cwd": "/path/to/your/project"
    }
  }
}
```

### 7.3 Team Server (HTTP)

```bash
# On the server (in the project directory with .lattice/):
lattice serve --host 0.0.0.0 --port 3100 --writable
```

---

## 8. Test Specifications

### test_mcp_tools.py
| Test | Asserts |
|------|---------|
| `test_fact_get_existing` | Returns full fact JSON for valid code |
| `test_fact_get_missing` | Returns error object for invalid code |
| `test_fact_query_by_layer` | layer="WHY" returns only WHY facts |
| `test_fact_query_by_tags` | tags=["security"] returns matching facts |
| `test_fact_list_default` | Returns non-deprecated facts with summary fields |
| `test_context_assemble_planning` | Returns facts scoped to planning role with budget |
| `test_context_assemble_with_budget` | Small budget limits included facts |
| `test_graph_impact` | Returns affected facts and roles |
| `test_graph_orphans` | Returns disconnected fact codes |
| `test_lattice_status` | Returns counts by layer and status |

### test_mcp_server.py
| Test | Asserts |
|------|---------|
| `test_list_tools_readonly` | Read-only mode lists 7 tools |
| `test_list_tools_writable` | Writable mode lists 10 tools |
| `test_call_tool_fact_get` | MCP call returns TextContent with fact JSON |
| `test_call_unknown_tool` | Returns error for unknown tool name |
| `test_index_refreshed_on_call` | Adding a fact file between calls makes it visible |

### test_serve_cli.py
| Test | Asserts |
|------|---------|
| `test_serve_no_lattice_errors` | Without .lattice/, exits with error |
| `test_serve_writable_flag` | --writable flag passed to server creation |

---

## 9. Acceptance Criteria — Phase 5 Done When

- [ ] `lattice serve --stdio` starts and responds to MCP tool list request
- [ ] Claude Desktop can connect via MCP config and call `fact_get`
- [ ] `fact_query` with layer filter returns correct results
- [ ] `context_assemble` returns token-budgeted facts for a role
- [ ] `graph_impact` returns affected facts and roles
- [ ] `lattice_status` returns accurate counts
- [ ] Writable mode enables fact_create, fact_update, fact_deprecate
- [ ] Read-only mode (default) rejects write operations
- [ ] Changes to .lattice/facts/ files are visible on next MCP call (index refresh)
- [ ] All tests in §8 pass

---

## 10. What Phase 5 Does NOT Include

- **Authentication** — Phase 5 MCP server is unauthenticated. Auth comes with Phase 7 (Enterprise).
- **WebSocket push notifications** — polling via repeated tool calls. Push comes with Enterprise.
- **Rate limiting** — not needed for local/small-team use.
- **SQLite backend support** — the MCP server uses whatever backend is active. When Phase 6 adds SQLite, the MCP server automatically uses it with WAL mode for concurrent reads.
- **Multi-project scoping** — single project per server instance. Multi-project comes with Phase 7.

---

*Phase 5 completes the feedback loop: developers govern facts in the lattice, agents consume them via MCP, and every query is role-scoped and token-budgeted. The core value proposition is now testable end-to-end.*
