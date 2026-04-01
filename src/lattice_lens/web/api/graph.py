"""Graph data API endpoints for the knowledge graph visualization."""

from __future__ import annotations

from enum import Enum

from fastapi import APIRouter, Query, Request

from lattice_lens.models import FactStatus
from lattice_lens.mcp.tools import (
    tool_graph_contradictions,
    tool_graph_impact,
    tool_graph_orphans,
)


class HighlightCriterion(str, Enum):
    """What property to match against when highlighting nodes."""

    search = "search"
    tag = "tag"
    layer = "layer"
    status = "status"


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

    @router.get("/highlight")
    async def graph_highlight(
        request: Request,
        criterion: HighlightCriterion = HighlightCriterion.search,
        q: str = Query("", description="Search text, tag name, layer, or status value"),
    ):
        """Return the set of fact codes that match a highlight criterion.

        This is the server-side counterpart to the frontend highlight logic,
        useful for deep-linking or external tools that want to compute
        which nodes match a given query.
        """
        store = request.app.state.store
        index = store.index

        if not q.strip():
            return {"criterion": criterion.value, "query": q, "codes": []}

        matched: list[str] = []
        q_lower = q.lower()

        for fact in index.all_facts():
            if criterion == HighlightCriterion.search:
                if (
                    q_lower in fact.code.lower()
                    or q_lower in fact.fact.lower()
                    or any(q_lower in t for t in fact.tags)
                    or q_lower in fact.type.lower()
                    or q_lower in fact.layer.value.lower()
                    or q_lower in fact.owner.lower()
                ):
                    matched.append(fact.code)
            elif criterion == HighlightCriterion.tag:
                if q in fact.tags:
                    matched.append(fact.code)
            elif criterion == HighlightCriterion.layer:
                if fact.layer.value == q:
                    matched.append(fact.code)
            elif criterion == HighlightCriterion.status:
                if fact.status.value == q:
                    matched.append(fact.code)

        return {"criterion": criterion.value, "query": q, "codes": matched}

    return router
