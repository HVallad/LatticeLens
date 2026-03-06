"""MCP server for LatticeLens — exposes lattice operations via FastMCP."""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from lattice_lens.config import ROLES_DIR, load_config
from lattice_lens.mcp.tools import (
    tool_context_assemble,
    tool_fact_create,
    tool_fact_deprecate,
    tool_fact_get,
    tool_fact_list,
    tool_fact_query,
    tool_fact_update,
    tool_graph_impact,
    tool_graph_orphans,
    tool_lattice_status,
    tool_reconcile,
)
from lattice_lens.store.yaml_store import YamlFileStore


def create_server(lattice_root: Path, writable: bool = False) -> FastMCP:
    """Create and configure a LatticeLens MCP server.

    Args:
        lattice_root: Path to the .lattice/ directory.
        writable: Enable write tools (fact_create, fact_update, fact_deprecate).

    Returns:
        Configured FastMCP server instance.
    """
    mcp = FastMCP("lattice-lens")

    # Select backend based on config
    config = load_config(lattice_root)
    backend = config.get("backend", "yaml")
    if backend == "sqlite":
        from lattice_lens.store.sqlite_store import SqliteStore

        store = SqliteStore(lattice_root)
    else:
        store = YamlFileStore(lattice_root)

    roles_dir = lattice_root / ROLES_DIR

    def _refresh():
        """Invalidate index to pick up file changes between calls."""
        store.invalidate_index()

    def _json(data) -> str:
        """Serialize result to JSON string."""
        return json.dumps(data, default=str)

    # ── Read-Only Tools ──

    @mcp.tool()
    async def fact_get(code: str) -> str:
        """Get a single fact by its code (e.g., ADR-03, RISK-07).

        Args:
            code: The fact code to look up.
        """
        _refresh()
        return _json(tool_fact_get(store, code))

    @mcp.tool()
    async def fact_query(
        layer: str | None = None,
        tags: list[str] | None = None,
        status: str | None = None,
        type: str | None = None,
        text_search: str | None = None,
    ) -> str:
        """Query facts with filters. Returns matching active facts.

        Args:
            layer: Filter by layer (WHY, GUARDRAILS, HOW).
            tags: Match facts with any of these tags.
            status: Filter by status (default: Active).
            type: Filter by fact type.
            text_search: Substring search in fact text.
        """
        _refresh()
        filters: dict = {}
        if layer is not None:
            filters["layer"] = layer
        if tags is not None:
            filters["tags"] = tags
        if status is not None:
            filters["status"] = status
        if type is not None:
            filters["type"] = type
        if text_search is not None:
            filters["text_search"] = text_search
        return _json(tool_fact_query(store, **filters))

    @mcp.tool()
    async def fact_list(layer: str | None = None) -> str:
        """List all non-deprecated facts, optionally filtered by layer.

        Args:
            layer: Filter by layer (WHY, GUARDRAILS, HOW).
        """
        _refresh()
        return _json(tool_fact_list(store, layer))

    @mcp.tool()
    async def context_assemble(role: str, budget: int = 40_000) -> str:
        """Assemble token-budgeted context for an agent role.

        Returns the exact facts that should be injected into an agent's prompt.
        Available roles: planning, architecture, implementation, qa, deploy.

        Args:
            role: Role name (e.g., planning, architecture).
            budget: Token budget (default: 40000).
        """
        _refresh()
        return _json(tool_context_assemble(store, roles_dir, role, budget))

    @mcp.tool()
    async def graph_impact(code: str, depth: int = 3) -> str:
        """Show what facts and agent roles would be affected if a fact changes.

        Args:
            code: The fact code to analyze.
            depth: Max traversal depth (default: 3).
        """
        _refresh()
        return _json(tool_graph_impact(store, roles_dir, code, depth))

    @mcp.tool()
    async def graph_orphans() -> str:
        """Find facts disconnected from the knowledge graph (no references in or out)."""
        _refresh()
        return _json(tool_graph_orphans(store))

    @mcp.tool()
    async def lattice_status() -> str:
        """Get summary statistics: fact counts by layer/status, staleness, backend type."""
        _refresh()
        return _json(tool_lattice_status(store))

    @mcp.tool()
    async def reconcile(
        path: str | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
    ) -> str:
        """Run bidirectional reconciliation of governance facts against the codebase.

        Returns a summary with counts of confirmed, stale, violated, untracked,
        and orphaned findings plus coverage percentage.

        Args:
            path: Directory to scan (default: project root).
            include: Glob patterns to include (default: **/*.py).
            exclude: Glob patterns to exclude.
        """
        _refresh()
        codebase_root = Path(path) if path else lattice_root.parent
        return _json(tool_reconcile(store, codebase_root, include, exclude))

    # ── Write Tools (writable mode only) ──

    if writable:

        @mcp.tool()
        async def fact_create(
            code: str,
            layer: str,
            type: str,
            fact: str,
            tags: list[str],
            owner: str,
            refs: list[str] | None = None,
            review_by: str | None = None,
        ) -> str:
            """Create a new fact in the lattice.

            Args:
                code: Fact code (e.g., ADR-05, RISK-03).
                layer: Layer (WHY, GUARDRAILS, HOW).
                type: Fact type (e.g., Architecture Decision Record).
                fact: The fact text (minimum 10 characters).
                tags: List of tags (minimum 2).
                owner: Team or person responsible.
                refs: References to other fact codes.
                review_by: Review expiry date (YYYY-MM-DD).
            """
            _refresh()
            data: dict = {
                "code": code,
                "layer": layer,
                "type": type,
                "fact": fact,
                "tags": tags,
                "owner": owner,
            }
            if refs is not None:
                data["refs"] = refs
            if review_by is not None:
                data["review_by"] = review_by
            return _json(tool_fact_create(store, data))

        @mcp.tool()
        async def fact_update(code: str, reason: str, **changes) -> str:
            """Update an existing fact. Increments version automatically.

            Args:
                code: The fact code to update.
                reason: Reason for the update.
                **changes: Fields to update (e.g., fact="new text", tags=["a","b"]).
            """
            _refresh()
            return _json(tool_fact_update(store, code, changes, reason))

        @mcp.tool()
        async def fact_deprecate(code: str, reason: str) -> str:
            """Deprecate a fact. Sets status to Deprecated.

            Args:
                code: The fact code to deprecate.
                reason: Reason for deprecation.
            """
            _refresh()
            return _json(tool_fact_deprecate(store, code, reason))

    return mcp
