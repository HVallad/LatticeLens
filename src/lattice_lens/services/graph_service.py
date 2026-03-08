"""Knowledge graph traversal — impact analysis, orphan detection, contradiction candidates."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml import YAML

from lattice_lens.store.index import FactIndex

yaml = YAML()


@dataclass
class ImpactResult:
    source_code: str
    directly_affected: list[str] = field(default_factory=list)
    transitively_affected: list[str] = field(default_factory=list)
    all_affected: list[str] = field(default_factory=list)
    affected_roles: list[str] = field(default_factory=list)
    depth_reached: int = 0


def load_role_templates(roles_dir: Path) -> dict:
    """Load role templates from .lattice/roles/*.yaml.

    Returns dict of {role_name: template_dict}.
    Emits a warning to stderr if any role uses the old Phase 1 flat format.
    """
    templates: dict = {}
    if not roles_dir.exists():
        return templates

    old_format_found = False
    for path in sorted(roles_dir.glob("*.yaml")):
        try:
            with open(path) as f:
                data = yaml.load(f)
            if data is None:
                continue
            role_name = path.stem
            # Detect old flat format (has top-level "layers" but no "query")
            if "layers" in data and "query" not in data:
                old_format_found = True
            templates[role_name] = data
        except Exception as e:
            print(f"Warning: skipping role {path.name}: {e}", file=sys.stderr)

    if old_format_found:
        print(
            "Warning: Role templates use v0.1.0 format. "
            "Run `lattice upgrade` to migrate to v0.2.0.",
            file=sys.stderr,
        )

    return templates


def _get_query(template: dict) -> dict:
    """Extract the query dict from a role template, handling both formats."""
    return template.get("query", template)


def _role_matches_fact(template: dict, fact_layer: str, fact_type: str) -> bool:
    """Check if a fact matches a role template's query criteria."""
    query = _get_query(template)
    layers = query.get("layers", [])
    types = query.get("types", [])
    extra = query.get("extra", [])

    # Check main query
    if fact_layer in layers:
        if not types or fact_type in types:
            return True

    # Check extra rules
    for rule in extra:
        if fact_layer == rule.get("layer"):
            rule_types = rule.get("types", [])
            if not rule_types or fact_type in rule_types:
                return True

    return False


def impact_analysis(
    index: FactIndex,
    code: str,
    max_depth: int = 3,
    role_templates: dict | None = None,
) -> ImpactResult:
    """Traverse the reverse reference graph from `code`.

    1. Find all facts whose `refs` field contains `code` (direct)
    2. For each of those, recurse up to max_depth
    3. Deduplicate, separate direct from transitive
    4. Cross-reference with role query templates to find affected roles
    """
    visited: set[str] = set()
    direct: set[str] = set()
    transitive: set[str] = set()

    def traverse(current: str, depth: int):
        if depth > max_depth or current in visited:
            return
        visited.add(current)
        referencing = index.refs_to(current)
        for ref_code in referencing:
            if ref_code == code:
                continue
            if depth == 1:
                direct.add(ref_code)
            else:
                transitive.add(ref_code)
            traverse(ref_code, depth + 1)

    traverse(code, 1)
    transitive -= direct  # Don't double-count

    # Determine affected roles
    affected_roles: list[str] = []
    if role_templates:
        all_affected_codes = direct | transitive | {code}
        for role_name, template in role_templates.items():
            for affected_code in all_affected_codes:
                fact = index.get(affected_code)
                if fact and _role_matches_fact(template, fact.layer.value, fact.type):
                    affected_roles.append(role_name)
                    break

    return ImpactResult(
        source_code=code,
        directly_affected=sorted(direct),
        transitively_affected=sorted(transitive),
        all_affected=sorted(direct | transitive),
        affected_roles=sorted(set(affected_roles)),
        depth_reached=max_depth,
    )


def find_orphans(index: FactIndex) -> list[str]:
    """Find facts that have no inbound refs AND no outbound refs.

    These are disconnected from the knowledge graph.
    """
    orphans = []
    for fact in index.all_facts():
        has_outbound = len(index.refs_from(fact.code)) > 0
        has_inbound = len(index.refs_to(fact.code)) > 0
        if not has_outbound and not has_inbound:
            orphans.append(fact.code)
    return sorted(orphans)


def find_contradiction_candidates(
    index: FactIndex,
    min_shared_tags: int = 2,
) -> list[tuple[str, str, list[str]]]:
    """Find pairs of Active facts that share tags but differ in layer or owner,
    plus any pairs explicitly linked with a CONTRADICTS edge.

    These are CANDIDATES for human review, not confirmed contradictions.
    Returns list of (code_a, code_b, shared_tags) tuples.
    """
    from lattice_lens.models import EdgeType

    active_facts = [f for f in index.all_facts() if f.status.value == "Active"]
    seen_pairs: set[tuple[str, str]] = set()
    candidates = []

    # Tag-based contradiction candidates
    for i, a in enumerate(active_facts):
        for b in active_facts[i + 1 :]:
            shared = sorted(set(a.tags) & set(b.tags))
            if len(shared) >= min_shared_tags:
                if a.layer != b.layer or a.owner != b.owner:
                    pair = (min(a.code, b.code), max(a.code, b.code))
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        candidates.append((a.code, b.code, shared))

    # Explicit CONTRADICTS edges
    for fact in active_facts:
        edges = index.edges_from(fact.code, edge_types=[EdgeType.CONTRADICTS])
        for target_code in edges:
            target = index.get(target_code)
            if target and target.status.value == "Active":
                pair = (min(fact.code, target_code), max(fact.code, target_code))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    shared = sorted(set(fact.tags) & set(target.tags))
                    candidates.append((fact.code, target_code, shared))

    return candidates
