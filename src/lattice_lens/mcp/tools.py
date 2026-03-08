"""MCP tool logic — pure functions wrapping the store/services layer.

Each function returns a dict (or list). The server layer handles JSON serialization.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from lattice_lens.models import Fact, FactLayer
from lattice_lens.services import context_service, graph_service
from lattice_lens.services.fact_service import (
    create_fact,
    deprecate_fact,
    promote_fact,
    update_fact,
)
from lattice_lens.store.protocol import LatticeStore


# ── Read Tools ──


def tool_fact_get(store: LatticeStore, code: str) -> dict:
    """Get a single fact by its code."""
    fact = store.get(code)
    if fact is None:
        return {"error": f"Fact {code} not found"}
    return fact.model_dump(mode="json")


def tool_fact_query(store: LatticeStore, **filters) -> list[dict]:
    """Query facts with filters. Returns matching facts."""
    # Map 'tags' to 'tags_any' for the store interface
    if "tags" in filters:
        filters["tags_any"] = filters.pop("tags")
    # Remove None values so store defaults apply
    filters = {k: v for k, v in filters.items() if v is not None}
    facts = store.list_facts(**filters)
    return [f.model_dump(mode="json") for f in facts]


def tool_fact_list(store: LatticeStore, layer: str | None = None) -> list[dict]:
    """List all non-deprecated facts, optionally filtered by layer."""
    filters: dict = {"status": ["Active", "Draft", "Under Review"]}
    if layer:
        filters["layer"] = layer
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


def tool_context_assemble(
    store: LatticeStore, roles_dir: Path, role: str, budget: int = 40_000
) -> dict:
    """Assemble token-budgeted context for an agent role."""
    templates = graph_service.load_role_templates(roles_dir)
    if role not in templates:
        available = sorted(templates.keys())
        return {"error": f"Role '{role}' not found. Available: {available}"}

    template = templates[role]
    result = context_service.assemble_context(store.index, role, template, budget=budget)
    return {
        "role": result.role,
        "budget": {
            "total": result.budget,
            "used": result.total_tokens,
            "remaining": (result.budget - result.total_tokens) if result.budget else None,
            "fact_count": len(result.loaded_facts),
        },
        "facts": [
            {
                "code": f.code,
                "layer": f.layer.value,
                "type": f.type,
                "fact": f.fact,
                "tags": f.tags,
                "confidence": f.confidence.value,
                "refs": [{"code": r.code, "rel": r.rel.value} for r in f.refs],
            }
            for f in result.loaded_facts
        ],
        "excluded": result.ref_pointers,
        "budget_exhausted": result.budget_exhausted,
    }


def tool_graph_impact(store: LatticeStore, roles_dir: Path, code: str, depth: int = 3) -> dict:
    """Show what facts and agent roles are affected if a fact changes."""
    if store.get(code) is None:
        return {"error": f"Fact {code} not found"}
    templates = graph_service.load_role_templates(roles_dir)
    result = graph_service.impact_analysis(store.index, code, depth, templates)
    return {
        "source": result.source_code,
        "directly_affected": result.directly_affected,
        "transitively_affected": result.transitively_affected,
        "all_affected": result.all_affected,
        "affected_roles": result.affected_roles,
    }


def tool_graph_orphans(store: LatticeStore) -> list[str]:
    """Find facts with no connections to the knowledge graph."""
    return graph_service.find_orphans(store.index)


def tool_lattice_status(store: LatticeStore) -> dict:
    """Get summary statistics about the lattice."""
    return store.stats()


def tool_reconcile(
    store: LatticeStore,
    codebase_root: Path,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> dict:
    """Run bidirectional reconciliation and return summary."""
    from lattice_lens.services.reconcile_service import reconcile

    report = reconcile(
        store,
        codebase_root,
        include_patterns=include,
        exclude_patterns=exclude,
    )
    return report.summary()


# ── Write Tools ──


def tool_fact_create(store: LatticeStore, data: dict) -> dict:
    """Create a new fact in the lattice."""
    try:
        # Ensure timestamps
        now = datetime.now()
        data.setdefault("created_at", now)
        data.setdefault("updated_at", now)
        # Convert layer string to enum if needed
        if isinstance(data.get("layer"), str):
            data["layer"] = FactLayer(data["layer"])
        fact = Fact(**data)
        created, warnings = create_fact(store, fact)
        result = created.model_dump(mode="json")
        if warnings:
            result["warnings"] = warnings
        return result
    except Exception as e:
        return {"error": str(e)}


def tool_fact_update(store: LatticeStore, code: str, changes: dict, reason: str) -> dict:
    """Update an existing fact. Increments version."""
    try:
        updated, warnings = update_fact(store, code, changes, reason)
        result = updated.model_dump(mode="json")
        if warnings:
            result["warnings"] = warnings
        return result
    except Exception as e:
        return {"error": str(e)}


def tool_fact_deprecate(store: LatticeStore, code: str, reason: str) -> dict:
    """Deprecate a fact. Sets status to Deprecated."""
    try:
        deprecated = deprecate_fact(store, code, reason)
        return deprecated.model_dump(mode="json")
    except Exception as e:
        return {"error": str(e)}


def tool_fact_promote(store: LatticeStore, code: str, reason: str) -> dict:
    """Promote a fact through the lifecycle (Draft -> Under Review -> Active)."""
    try:
        promoted = promote_fact(store, code, reason)
        return promoted.model_dump(mode="json")
    except Exception as e:
        return {"error": str(e)}


def tool_graph_contradictions(store: LatticeStore, min_shared_tags: int = 2) -> list[dict]:
    """Find contradiction candidates among active facts across different layers."""
    candidates = graph_service.find_contradiction_candidates(
        store.index, min_shared_tags=min_shared_tags
    )
    return [{"fact_a": a, "fact_b": b, "shared_tags": tags} for a, b, tags in candidates]


def tool_lattice_validate(store: LatticeStore) -> dict:
    """Run schema and integrity validation on the lattice."""
    from lattice_lens.services.validate_service import validate_lattice

    result = validate_lattice(store.facts_dir)
    return {
        "ok": result.ok,
        "errors": result.errors,
        "warnings": result.warnings,
    }


def tool_fact_exists(store: LatticeStore, code: str) -> dict:
    """Check if a fact code exists in the lattice."""
    return {"code": code, "exists": store.exists(code)}


def tool_all_codes(store: LatticeStore) -> list[str]:
    """Return all fact codes in the lattice."""
    return store.all_codes()
