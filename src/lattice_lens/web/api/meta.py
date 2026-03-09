"""Meta/registry API endpoints — tags, types, enums, stats, roles."""

from __future__ import annotations

from fastapi import APIRouter, Request

from fastapi import HTTPException

from lattice_lens.config import LAYER_PREFIXES
from lattice_lens.mcp.tools import tool_lattice_status, tool_lattice_validate
from lattice_lens.models import EdgeType, FactConfidence, FactLayer, FactStatus
from lattice_lens.services import graph_service
from lattice_lens.services.context_service import assemble_context
from lattice_lens.services.tag_service import read_tag_registry
from lattice_lens.services.type_service import read_type_registry
from lattice_lens.store.index import INVERSE_LABELS


def create_meta_router() -> APIRouter:
    router = APIRouter(prefix="/meta", tags=["meta"])

    @router.get("/stats")
    async def meta_stats(request: Request):
        """Lattice summary statistics."""
        store = request.app.state.store
        return tool_lattice_status(store)

    @router.get("/tags")
    async def meta_tags(request: Request):
        """Tag registry with counts and categories."""
        lattice_root = request.app.state.lattice_root
        registry = read_tag_registry(lattice_root)
        return registry or []

    @router.get("/types")
    async def meta_types(request: Request):
        """Type registry (canonical types by layer)."""
        lattice_root = request.app.state.lattice_root
        registry = read_type_registry(lattice_root)
        return registry or {}

    @router.get("/roles")
    async def meta_roles(request: Request):
        """Available role templates."""
        roles_dir = request.app.state.roles_dir
        if not roles_dir.exists():
            return {}
        templates = graph_service.load_role_templates(roles_dir)
        # Return role names and descriptions (don't expose full query specs)
        return {
            name: {
                "name": tmpl.get("name", name),
                "description": tmpl.get("description", ""),
            }
            for name, tmpl in templates.items()
        }

    @router.get("/roles/{role_name}/context")
    async def role_context(request: Request, role_name: str, project: str | None = None):
        """Run context assembly for a role and return matched fact codes."""
        roles_dir = request.app.state.roles_dir
        if not roles_dir.exists():
            raise HTTPException(404, "No roles directory")
        templates = graph_service.load_role_templates(roles_dir)
        if role_name not in templates:
            raise HTTPException(404, f"Role '{role_name}' not found")
        store = request.app.state.store
        index = store.index
        result = assemble_context(index, role_name, templates[role_name], project=project)
        return {
            "role": role_name,
            "facts_loaded": result.to_dict()["facts_loaded"],
            "total_tokens": result.total_tokens,
            "codes": [f.code for f in result.loaded_facts],
            "graph_codes": result.graph_facts,
            "ref_pointers": result.ref_pointers,
        }

    @router.get("/enums")
    async def meta_enums():
        """All enum values for forms and autocomplete."""
        return {
            "layers": [e.value for e in FactLayer],
            "statuses": [e.value for e in FactStatus],
            "confidences": [e.value for e in FactConfidence],
            "edge_types": [e.value for e in EdgeType],
            "layer_prefixes": LAYER_PREFIXES,
            "inverse_labels": {e.value: label for e, label in INVERSE_LABELS.items()},
        }

    @router.get("/validate")
    async def meta_validate(request: Request):
        """Run lattice validation."""
        store = request.app.state.store
        return tool_lattice_validate(store)

    return router
