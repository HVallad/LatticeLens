"""Graph data API endpoints for the knowledge graph visualization."""

from __future__ import annotations

from fastapi import APIRouter, Request

from lattice_lens.models import FactStatus
from lattice_lens.mcp.tools import (
    tool_graph_contradictions,
    tool_graph_impact,
    tool_graph_orphans,
)


def create_graph_router() -> APIRouter:
    router = APIRouter(prefix="/graph", tags=["graph"])

    @router.get("/data")
    async def graph_data(request: Request, include_inactive: bool = False):
        """Return full graph data (nodes + edges) for D3 rendering."""
        store = request.app.state.store
        index = store.index

        excluded_statuses = set()
        if not include_inactive:
            excluded_statuses = {FactStatus.DEPRECATED, FactStatus.SUPERSEDED}

        nodes = []
        edges = []

        for fact in index.all_facts():
            if fact.status in excluded_statuses:
                continue
            nodes.append(
                {
                    "code": fact.code,
                    "layer": fact.layer.value,
                    "type": fact.type,
                    "status": fact.status.value,
                    "confidence": fact.confidence.value,
                    "tags": fact.tags,
                    "fact": fact.fact,
                    "owner": fact.owner,
                    "version": fact.version,
                }
            )

            # Outgoing edges from this fact
            for target_code, edge_type in index.edges_from(fact.code).items():
                # Only include edge if target is also visible
                target = index.get(target_code)
                if target and target.status not in excluded_statuses:
                    edges.append(
                        {
                            "source": fact.code,
                            "target": target_code,
                            "rel": edge_type.value,
                        }
                    )

        return {"nodes": nodes, "edges": edges}

    @router.get("/impact/{code}")
    async def graph_impact(code: str, request: Request, depth: int = 3):
        """Run impact analysis from a fact."""
        store = request.app.state.store
        roles_dir = request.app.state.roles_dir
        return tool_graph_impact(store, roles_dir, code, depth)

    @router.get("/orphans")
    async def graph_orphans(request: Request):
        """Find facts with no connections."""
        store = request.app.state.store
        return tool_graph_orphans(store)

    @router.get("/contradictions")
    async def graph_contradictions(request: Request, min_shared_tags: int = 2):
        """Find contradiction candidates."""
        store = request.app.state.store
        return tool_graph_contradictions(store, min_shared_tags)

    return router
