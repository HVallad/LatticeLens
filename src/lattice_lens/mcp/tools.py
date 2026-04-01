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
from lattice_lens.services.tag_service import build_tag_registry, read_tag_registry
from lattice_lens.services.type_service import (
    CANONICAL_TYPES,
    audit_types,
    read_type_registry,
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


def tool_lattice_check(
    store: LatticeStore,
    *,
    strict: bool = False,
    stale_is_error: bool = False,
    reconcile_path: Path | None = None,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    min_coverage: int = 0,
) -> dict:
    """Run CI-gate integrity checks (validation + optional reconciliation)."""
    from lattice_lens.services.check_service import run_check

    result = run_check(
        store,
        stale_is_error=stale_is_error,
        reconcile_path=reconcile_path,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        min_coverage=min_coverage,
    )
    passed = not result.failed(strict=strict)
    return {
        "passed": passed,
        "errors": [{"message": i.message, "file": i.file, "line": i.line} for i in result.errors],
        "warnings": [
            {"message": i.message, "file": i.file, "line": i.line} for i in result.warnings
        ],
        "coverage_pct": result.coverage_pct,
    }


def tool_tags(store: LatticeStore) -> list[dict]:
    """Return the tag registry: all tags with usage counts and categories."""
    registry = read_tag_registry(store.root)
    if registry is None:
        registry = build_tag_registry(store)
    return registry


def tool_types(store: LatticeStore, audit_mode: bool = False) -> dict:
    """Return the type registry or audit mismatches.

    Args:
        audit_mode: If True, returns facts with non-canonical types instead.
    """
    if audit_mode:
        return {"mismatches": audit_types(store)}
    registry = read_type_registry(store.root) or CANONICAL_TYPES
    return {"registry": registry}


def tool_evaluate(store: LatticeStore) -> dict:
    """Evaluate governance rules — returns guardrails and knowledge summary."""
    from lattice_lens.services.evaluate_service import evaluate_governance

    result = evaluate_governance(start_path=store.root.parent)
    return result.to_dict()


def tool_export(store: LatticeStore, format: str = "json") -> dict:
    """Export all facts as a serialized string.

    Args:
        format: Output format — 'json' or 'yaml'.
    """
    from lattice_lens.services.exchange_service import export_facts

    try:
        data = export_facts(store, format=format)
        return {"format": format, "data": data}
    except ValueError as e:
        return {"error": str(e)}


def tool_import(
    store: LatticeStore,
    data: str,
    format: str = "json",
    strategy: str = "skip",
) -> dict:
    """Import facts from a JSON or YAML string.

    Args:
        data: Serialized facts (JSON array or YAML list).
        format: Data format — 'json' or 'yaml'.
        strategy: Merge strategy — 'skip', 'overwrite', or 'fail'.
    """
    from lattice_lens.services.exchange_service import import_facts

    try:
        return import_facts(store, data, format=format, strategy=strategy)
    except (FileExistsError, ValueError) as e:
        return {"error": str(e)}


def tool_reindex(store: LatticeStore) -> dict:
    """Rebuild the in-memory index from fact files and return summary."""
    store.invalidate_index()
    index = store.index
    facts = index.all_facts()

    by_status: dict[str, int] = {}
    by_layer: dict[str, int] = {}
    for f in facts:
        by_status[f.status.value] = by_status.get(f.status.value, 0) + 1
        by_layer[f.layer.value] = by_layer.get(f.layer.value, 0) + 1

    return {
        "total_facts": len(facts),
        "by_layer": by_layer,
        "by_status": by_status,
    }


def tool_fact_exists(store: LatticeStore, code: str) -> dict:
    """Check if a fact code exists in the lattice."""
    return {"code": code, "exists": store.exists(code)}


def tool_semantic_search(
    store: LatticeStore,
    query: str,
    top_k: int = 10,
    threshold: float = 0.3,
    tag: str | None = None,
    layer: str | None = None,
    status: str | None = None,
    project: str | None = None,
) -> dict:
    """Semantic search — find facts by meaning."""
    try:
        from lattice_lens.services.embedding_service import semantic_search
    except ImportError:
        return {
            "error": (
                "sentence-transformers not installed. "
                "Install with: pip install lattice-lens[semantic]"
            )
        }

    facts = store.list_facts()
    results = semantic_search(
        query=query,
        facts=facts,
        lattice_root=store.root,
        top_k=top_k,
        threshold=threshold,
        tag=tag,
        layer=layer,
        status=status,
        project=project,
    )
    return {"query": query, "results": results}


def tool_all_codes(store: LatticeStore) -> list[str]:
    """Return all fact codes in the lattice."""
    return store.all_codes()
