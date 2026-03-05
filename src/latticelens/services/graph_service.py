from pathlib import Path

import yaml
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from latticelens.schemas import ContradictionCandidate, ImpactAnalysisResponse, RefsResponse


def _load_agent_roles() -> dict:
    roles_path = Path(__file__).parent.parent / "config" / "agent_roles.yaml"
    if not roles_path.exists():
        return {}
    with open(roles_path) as f:
        data = yaml.safe_load(f)
    return data.get("roles", {})


def _role_matches_fact(role_config: dict, layer: str, fact_type: str, tags: list[str]) -> bool:
    """Check if a fact would be included in a role's query."""
    query = role_config.get("query", {})

    # Check primary layers/types
    primary_layers = query.get("layers", [])
    primary_types = query.get("types", [])
    if layer in primary_layers and (not primary_types or fact_type in primary_types):
        return True

    # Check extra (single dict)
    extra = query.get("extra")
    if extra and layer == extra.get("layer"):
        extra_types = extra.get("types", [])
        if not extra_types or fact_type in extra_types:
            return True

    # Check extra_layers (list of dicts)
    extra_layers = query.get("extra_layers", [])
    for el in extra_layers:
        if layer == el.get("layer"):
            el_types = el.get("types", [])
            if not el_types or fact_type in el_types:
                return True

    # Check tags_any
    tags_any = query.get("tags_any", [])
    if tags_any and any(t in tags for t in tags_any):
        return True

    return False


async def get_impact(db: AsyncSession, code: str) -> ImpactAnalysisResponse:
    # Recursive CTE to find all facts affected by changing this fact
    cte_query = text("""
        WITH RECURSIVE impact AS (
            SELECT from_code AS code, 1 AS depth
            FROM fact_refs
            WHERE to_code = :target_code

            UNION ALL

            SELECT fr.from_code, i.depth + 1
            FROM fact_refs fr
            JOIN impact i ON fr.to_code = i.code
            WHERE i.depth < 3
        )
        SELECT DISTINCT code, MIN(depth) as min_depth
        FROM impact
        GROUP BY code
        ORDER BY min_depth
    """)

    result = await db.execute(cte_query, {"target_code": code})
    rows = result.all()

    directly_affected = [r[0] for r in rows if r[1] == 1]
    transitively_affected = [r[0] for r in rows if r[1] > 1]

    # Determine affected agent roles
    all_affected_codes = [code] + directly_affected + transitively_affected
    affected_roles = set()

    roles = _load_agent_roles()

    # Get fact details for all affected codes
    if all_affected_codes:
        placeholders = ", ".join([f":code_{i}" for i in range(len(all_affected_codes))])
        params = {f"code_{i}": c for i, c in enumerate(all_affected_codes)}
        facts_query = text(f"SELECT code, layer, type, tags FROM facts WHERE code IN ({placeholders})")
        facts_result = await db.execute(facts_query, params)

        for row in facts_result.all():
            fact_code, fact_layer, fact_type, fact_tags = row
            for role_name, role_config in roles.items():
                if _role_matches_fact(role_config, fact_layer, fact_type, fact_tags or []):
                    affected_roles.add(role_name)

    return ImpactAnalysisResponse(
        source_code=code,
        directly_affected=directly_affected,
        transitively_affected=transitively_affected,
        affected_agent_roles=sorted(affected_roles),
    )


async def get_refs(db: AsyncSession, code: str) -> RefsResponse:
    outgoing_result = await db.execute(
        text("SELECT to_code FROM fact_refs WHERE from_code = :code"), {"code": code}
    )
    incoming_result = await db.execute(
        text("SELECT from_code FROM fact_refs WHERE to_code = :code"), {"code": code}
    )

    return RefsResponse(
        code=code,
        outgoing=[r[0] for r in outgoing_result.all()],
        incoming=[r[0] for r in incoming_result.all()],
    )


async def get_orphans(db: AsyncSession) -> list[str]:
    query = text("""
        SELECT f.code
        FROM facts f
        LEFT JOIN fact_refs fr_out ON f.code = fr_out.from_code
        LEFT JOIN fact_refs fr_in ON f.code = fr_in.to_code
        WHERE fr_out.from_code IS NULL AND fr_in.to_code IS NULL
        ORDER BY f.code
    """)
    result = await db.execute(query)
    return [r[0] for r in result.all()]


async def get_contradictions(db: AsyncSession) -> list[ContradictionCandidate]:
    # Find pairs of Active facts sharing 2+ tags but in different layers or with different owners
    query = text("""
        WITH fact_tags AS (
            SELECT code, layer, owner, jsonb_array_elements_text(tags) AS tag
            FROM facts
            WHERE status = 'Active'
        ),
        tag_pairs AS (
            SELECT
                a.code AS code_a, b.code AS code_b,
                a.layer AS layer_a, b.layer AS layer_b,
                a.owner AS owner_a, b.owner AS owner_b,
                array_agg(DISTINCT a.tag) AS shared_tags
            FROM fact_tags a
            JOIN fact_tags b ON a.tag = b.tag AND a.code < b.code
            GROUP BY a.code, b.code, a.layer, b.layer, a.owner, b.owner
            HAVING count(DISTINCT a.tag) >= 2
        )
        SELECT code_a, code_b, shared_tags, layer_a, layer_b, owner_a, owner_b
        FROM tag_pairs
        WHERE layer_a != layer_b OR owner_a != owner_b
        ORDER BY code_a, code_b
    """)

    result = await db.execute(query)
    candidates = []
    for row in result.all():
        code_a, code_b, shared_tags, layer_a, layer_b, owner_a, owner_b = row
        reasons = []
        if layer_a != layer_b:
            reasons.append(f"different layers ({layer_a} vs {layer_b})")
        if owner_a != owner_b:
            reasons.append(f"different owners ({owner_a} vs {owner_b})")
        candidates.append(
            ContradictionCandidate(
                code_a=code_a,
                code_b=code_b,
                shared_tags=shared_tags,
                reason="; ".join(reasons),
            )
        )
    return candidates
