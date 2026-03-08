"""Context assembly — role-based, token-budgeted fact selection for agent prompts."""

from __future__ import annotations

from dataclasses import dataclass, field

from lattice_lens.models import EdgeType, Fact, FactConfidence, FactStatus
from lattice_lens.services.fact_service import is_stale
from lattice_lens.services.graph_service import _get_query, _role_matches_fact
from lattice_lens.services.project_service import fact_matches_project
from lattice_lens.store.index import FactIndex


def estimate_tokens(text: str) -> int:
    """Estimate token count using character-based heuristic.

    Average English token is ~4 characters. This avoids a tiktoken dependency
    while being accurate enough for budget enforcement.
    """
    return max(1, len(text) // 4)


def estimate_fact_tokens(fact: Fact) -> int:
    """Estimate the total token cost of a fact in assembled context.

    Includes: code, layer, type, status, confidence, tags, refs, fact text.
    """
    parts = [
        f"[{fact.code}]",
        f"Layer: {fact.layer.value}",
        f"Type: {fact.type}",
        f"Status: {fact.status.value}",
        f"Confidence: {fact.confidence.value}",
        f"Tags: {', '.join(fact.tags)}",
    ]
    if fact.refs:
        ref_strs = [f"{r.code}({r.rel.value})" for r in fact.refs]
        parts.append(f"Edges: {', '.join(ref_strs)}")
    parts.append(fact.fact)
    return estimate_tokens("\n".join(parts))


# Statuses that are NEVER included in context assembly
_EXCLUDED_STATUSES = {
    FactStatus.DRAFT,
    FactStatus.DEPRECATED,
    FactStatus.SUPERSEDED,
}


def _tag_match_score(fact: Fact, role_tags: list[str]) -> int:
    """Score a fact by how many of the role's tags it matches."""
    if not role_tags:
        return 0
    return len(set(fact.tags) & set(role_tags))


def _confidence_tier(fact: Fact) -> int:
    """Return 0 for Confirmed (highest priority), 1 for Provisional/Assumed."""
    if is_stale(fact):
        return 1  # Stale facts downgraded to Provisional tier per DG-06
    if fact.confidence == FactConfidence.CONFIRMED:
        return 0
    return 1  # Provisional, Assumed, etc.


@dataclass
class ContextResult:
    """Result of a context assembly for an agent role."""

    role: str
    loaded_facts: list[Fact] = field(default_factory=list)
    ref_pointers: list[str] = field(default_factory=list)
    total_tokens: int = 0
    budget: int | None = None
    budget_exhausted: bool = False
    graph_facts: list[str] = field(default_factory=list)

    def render_text(self) -> str:
        """Render assembled context as text for agent prompts."""
        lines: list[str] = []
        lines.append(f"# Context for role: {self.role}")
        lines.append(f"# Facts loaded: {len(self.loaded_facts)}")
        lines.append(f"# Estimated tokens: {self.total_tokens}")
        if self.budget is not None:
            lines.append(f"# Token budget: {self.budget}")
        lines.append("")

        graph_set = set(self.graph_facts)
        for fact in self.loaded_facts:
            source = "graph" if fact.code in graph_set else "direct"
            lines.append(f"## [{fact.code} v{fact.version}] {fact.type} ({source})")
            lines.append(
                f"Layer: {fact.layer.value} | "
                f"Status: {fact.status.value} | "
                f"Confidence: {fact.confidence.value}"
            )
            lines.append(f"Tags: {', '.join(fact.tags)}")
            if fact.refs:
                edge_strs = [f"{r.rel.value}\u2192{r.code}" for r in fact.refs]
                lines.append(f"Edges: {', '.join(edge_strs)}")
            lines.append("")
            lines.append(fact.fact)
            lines.append("")

        if self.ref_pointers:
            lines.append("---")
            lines.append("# Additional facts exist but were not loaded:")
            for ptr in self.ref_pointers:
                lines.append(f"#   - {ptr}")
            lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize to dict for JSON output."""
        graph_set = set(self.graph_facts)
        return {
            "role": self.role,
            "facts_loaded": len(self.loaded_facts),
            "total_tokens": self.total_tokens,
            "budget": self.budget,
            "budget_exhausted": self.budget_exhausted,
            "facts": [
                {
                    "code": f.code,
                    "version": f.version,
                    "layer": f.layer.value,
                    "type": f.type,
                    "status": f.status.value,
                    "confidence": f.confidence.value,
                    "tags": f.tags,
                    "refs": [{"code": r.code, "rel": r.rel.value} for r in f.refs],
                    "fact": f.fact,
                    "tokens": estimate_fact_tokens(f),
                    "source": "graph" if f.code in graph_set else "direct",
                }
                for f in self.loaded_facts
            ],
            "ref_pointers": self.ref_pointers,
            "graph_facts": self.graph_facts,
        }


def assemble_context(
    index: FactIndex,
    role_name: str,
    role_template: dict,
    budget: int | None = None,
    project: str | None = None,
    graph_depth: int | None = None,
) -> ContextResult:
    """Assemble facts for a role, respecting lifecycle and token budget.

    6-step pipeline:
    1. Project filter (narrow)
    2. Role filter — layer/type match (narrow)
    3. Tag filter/score (narrow — used for sorting, not exclusion)
    4. Graph expansion (widen — only if candidates < max_facts and depth != 0)
    5. Confidence sort with source_type tiebreaker
    6. Take top N (max_facts then token budget)

    Priority loading per AUP-07:
    - Confirmed facts first (Active with Confirmed confidence)
    - Provisional facts if budget remains
    - Never Draft, Deprecated, or Superseded
    - Direct matches rank above graph-pulled within same confidence tier
    """
    query = _get_query(role_template)
    role_tags = query.get("tags", [])
    max_facts = query.get("max_facts")

    # Resolve graph_depth: CLI param overrides template value
    effective_depth = graph_depth
    if effective_depth is None:
        effective_depth = query.get("graph_depth", 0)

    # Parse edge priority from template
    edge_priority_raw = query.get("edge_priority")
    edge_priority: list[EdgeType] | None = None
    if edge_priority_raw:
        edge_priority = []
        for ep in edge_priority_raw:
            try:
                edge_priority.append(EdgeType(ep))
            except ValueError:
                pass  # Skip unknown edge types

    # Steps 1-2: Project filter + Role filter
    direct_matched: list[Fact] = []
    for fact in index.all_facts():
        if fact.status in _EXCLUDED_STATUSES:
            continue
        if project and not fact_matches_project(fact.projects, project):
            continue
        if _role_matches_fact(role_template, fact.layer.value, fact.type):
            direct_matched.append(fact)

    direct_codes = {f.code for f in direct_matched}

    # Step 4: Graph expansion — only if we have room and depth is enabled
    graph_codes: set[str] = set()
    graph_facts_list: list[Fact] = []
    need_expansion = (
        effective_depth != 0
        and (max_facts is None or len(direct_matched) < max_facts)
        and direct_codes  # need seeds for BFS
    )

    if need_expansion:
        neighborhood = index.neighborhood(
            seeds=direct_codes,
            max_depth=abs(effective_depth) if effective_depth != -1 else -1,
            edge_types=edge_priority,
            excluded_statuses=_EXCLUDED_STATUSES,
        )
        for code, _distance in neighborhood.items():
            if code in direct_codes:
                continue  # Already a direct match
            fact = index.get(code)
            if fact is None:
                continue
            if fact.status in _EXCLUDED_STATUSES:
                continue
            if project and not fact_matches_project(fact.projects, project):
                continue
            graph_codes.add(code)
            graph_facts_list.append(fact)

    # Step 5: Unified sort — (confidence_tier, source_type, -tag_score, code)
    # source_type: 0=direct, 1=graph-pulled
    all_candidates = direct_matched + graph_facts_list

    def sort_key(f: Fact) -> tuple:
        tier = _confidence_tier(f)
        source = 0 if f.code in direct_codes else 1
        tag_score = _tag_match_score(f, role_tags)
        return (tier, source, -tag_score, f.code)

    all_candidates.sort(key=sort_key)

    # Track all candidates before truncation for ref pointers
    all_pool_codes = {f.code for f in all_candidates}

    # Step 6: Apply max_facts limit
    if max_facts is not None:
        all_candidates = all_candidates[:max_facts]

    # Load facts within token budget
    result = ContextResult(role=role_name, budget=budget)
    loaded_codes: set[str] = set()

    for fact in all_candidates:
        tokens = estimate_fact_tokens(fact)
        if budget is not None and result.total_tokens + tokens > budget:
            result.budget_exhausted = True
            break
        result.loaded_facts.append(fact)
        result.total_tokens += tokens
        loaded_codes.add(fact.code)
        if fact.code in graph_codes:
            result.graph_facts.append(fact.code)

    # Build REFS pointers for facts that exist but weren't loaded.
    # Includes facts cut by max_facts or budget from the full candidate pool.
    not_loaded = all_pool_codes - loaded_codes

    # Also include refs from loaded facts that point outside the loaded set
    refs_outside: set[str] = set()
    for fact in result.loaded_facts:
        for ref in fact.refs:
            if ref.code not in loaded_codes:
                ref_fact = index.get(ref.code)
                if ref_fact and ref_fact.status not in _EXCLUDED_STATUSES:
                    refs_outside.add(ref.code)

    all_pointers = sorted(not_loaded | refs_outside)
    for code in all_pointers:
        ptr_fact = index.get(code)
        if ptr_fact:
            result.ref_pointers.append(f"{code} ({ptr_fact.layer.value}/{ptr_fact.type})")
        else:
            result.ref_pointers.append(code)

    return result
