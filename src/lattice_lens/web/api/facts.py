"""Fact CRUD API endpoints — wraps mcp/tools.py functions."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from lattice_lens.mcp.tools import (
    tool_fact_create,
    tool_fact_deprecate,
    tool_fact_get,
    tool_fact_promote,
    tool_fact_query,
    tool_fact_update,
)
from lattice_lens.services.fact_service import next_code


class FactCreateRequest(BaseModel):
    code: str | None = None
    prefix: str | None = None
    layer: str
    type: str
    fact: str
    tags: list[str]
    owner: str
    refs: list[dict] | None = None
    review_by: str | None = None
    projects: list[str] | None = None


class FactUpdateRequest(BaseModel):
    changes: dict
    reason: str


class ReasonRequest(BaseModel):
    reason: str


def create_facts_router() -> APIRouter:
    router = APIRouter(tags=["facts"])

    @router.get("/facts/next-code/{prefix}")
    async def get_next_code(prefix: str, request: Request):
        """Get the next available code for a prefix (e.g., ADR -> ADR-04)."""
        store = request.app.state.store
        code = next_code(store, prefix)
        return {"code": code}

    @router.get("/facts")
    async def list_facts(
        request: Request,
        layer: str | None = None,
        status: str | None = None,
        tags: str | None = None,
        type: str | None = None,
        text_search: str | None = None,
        project: str | None = None,
    ):
        """Query facts with optional filters."""
        store = request.app.state.store
        filters: dict = {}
        if layer is not None:
            filters["layer"] = layer
        if status is not None:
            # Support comma-separated status values
            filters["status"] = [s.strip() for s in status.split(",")]
        if tags is not None:
            filters["tags"] = [t.strip() for t in tags.split(",")]
        if type is not None:
            filters["type"] = type
        if text_search is not None:
            filters["text_search"] = text_search
        if project is not None:
            filters["project"] = project
        return tool_fact_query(store, **filters)

    @router.get("/facts/{code}")
    async def get_fact(code: str, request: Request):
        """Get a single fact by code."""
        store = request.app.state.store
        return tool_fact_get(store, code)

    @router.post("/facts")
    async def create_fact(body: FactCreateRequest, request: Request):
        """Create a new fact."""
        store = request.app.state.store

        # Auto-assign code if prefix provided instead of code
        code = body.code
        if code is None and body.prefix:
            code = next_code(store, body.prefix)
        elif code is None:
            return {"error": "Either code or prefix is required"}

        data: dict = {
            "code": code,
            "layer": body.layer,
            "type": body.type,
            "fact": body.fact,
            "tags": body.tags,
            "owner": body.owner,
        }
        if body.refs is not None:
            data["refs"] = body.refs
        if body.review_by is not None:
            data["review_by"] = body.review_by
        if body.projects is not None:
            data["projects"] = body.projects

        return tool_fact_create(store, data)

    @router.patch("/facts/{code}")
    async def update_fact(code: str, body: FactUpdateRequest, request: Request):
        """Update an existing fact."""
        store = request.app.state.store
        return tool_fact_update(store, code, body.changes, body.reason)

    @router.post("/facts/{code}/deprecate")
    async def deprecate_fact(code: str, body: ReasonRequest, request: Request):
        """Deprecate a fact (no hard deletes)."""
        store = request.app.state.store
        return tool_fact_deprecate(store, code, body.reason)

    @router.post("/facts/{code}/promote")
    async def promote_fact(code: str, body: ReasonRequest, request: Request):
        """Promote a fact through the lifecycle."""
        store = request.app.state.store
        return tool_fact_promote(store, code, body.reason)

    return router
