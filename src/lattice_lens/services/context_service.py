"""Context assembly — role-based, token-budgeted fact selection for agent prompts."""

from __future__ import annotations

from dataclasses import dataclass, field

from lattice_lens.models import Fact, FactConfidence, FactStatus
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
        parts.append(f"Refs: {', '.join(fact.refs)}")
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


@dataclass
class ContextResult:
    """Result of a context assembly for an agent role."""

    role: str
    loaded_facts: list[Fact] = field(default_factory=list)
    ref_pointers: list[str] = field(default_factory=list)
    total_tokens: int = 0
    budget: int | None = None
    budget_exhausted: bool = False

    def render_text(self) -> str:
        """Render assembled context as text for agent prompts."""
        lines: list[str] = []
        lines.append(f"# Context for role: {self.role}")
        lines.append(f"# Facts loaded: {len(self.loaded_facts)}")
        lines.append(f"# Estimated tokens: {self.total_tokens}")
        if self.budget is not None:
            lines.append(f"# Token budget: {self.budget}")
        lines.append("")

        for fact in self.loaded_facts:
            lines.append(f"## [{fact.code} v{fact.version}] {fact.type}")
            lines.append(
                f"Layer: {fact.layer.value} | "
                f"Status: {fact.status.value} | "
                f"Confidence: {fact.confidence.value}"
            )
            lines.append(f"Tags: {', '.join(fact.tags)}")
            if fact.refs:
                lines.append(f"Refs: {', '.join(fact.refs)}")
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
                    "refs": f.refs,
                    "fact": f.fact,
                    "tokens": estimate_fact_tokens(f),
                }
                for f in self.loaded_facts
            ],
            "ref_pointers": self.ref_pointers,
        }


def assemble_context(
    index: FactIndex,
    role_name: str,
    role_template: dict,
    budget: int | None = None,
    project: str | None = None,
) -> ContextResult:
    """Assemble facts for a role, respecting lifecycle and token budget.

    Priority loading per AUP-07:
    1. Confirmed facts first (Active with Confirmed confidence)
    2. Provisional facts if budget remains (Under Review, or Active with Provisional)
    3. Never Draft, Deprecated, or Superseded

    Within each confidence tier, sort by tag match score (descending).
    """
    query = _get_query(role_template)
    role_tags = query.get("tags", [])
    max_facts = query.get("max_facts")

    # Collect all facts that match the role query
    matched: list[Fact] = []
    for fact in index.all_facts():
        if fact.status in _EXCLUDED_STATUSES:
            continue
        if project and not fact_matches_project(fact.projects, project):
            continue
        if _role_matches_fact(role_template, fact.layer.value, fact.type):
            matched.append(fact)

    # Split into priority tiers.
    # DG-06: stale facts (past review_by) are downgraded to Provisional tier
    # regardless of their stored confidence. This is a runtime-only downgrade —
    # the YAML file is not modified.
    confirmed: list[Fact] = []
    provisional: list[Fact] = []

    for fact in matched:
        if is_stale(fact):
            # Review Expired — downgrade to Provisional tier per DG-06
            provisional.append(fact)
        elif fact.confidence == FactConfidence.CONFIRMED:
            confirmed.append(fact)
        elif fact.confidence == FactConfidence.PROVISIONAL:
            provisional.append(fact)
        else:
            # Assumed confidence — treat like Provisional
            provisional.append(fact)

    # Sort each tier by tag match score (descending), then code for stability
    def sort_key(f: Fact) -> tuple:
        return (-_tag_match_score(f, role_tags), f.code)

    confirmed.sort(key=sort_key)
    provisional.sort(key=sort_key)

    # Priority loading: Confirmed first, then Provisional
    ordered = confirmed + provisional

    # Apply max_facts limit from role template
    if max_facts is not None:
        ordered = ordered[:max_facts]

    # Load facts within budget
    result = ContextResult(role=role_name, budget=budget)
    loaded_codes: set[str] = set()

    for fact in ordered:
        tokens = estimate_fact_tokens(fact)
        if budget is not None and result.total_tokens + tokens > budget:
            result.budget_exhausted = True
            break
        result.loaded_facts.append(fact)
        result.total_tokens += tokens
        loaded_codes.add(fact.code)

    # Build REFS pointers for facts that exist but weren't loaded.
    # Include: facts matching the role that were cut by budget/max_facts,
    # plus any refs from loaded facts that point to unloaded facts.
    all_matched_codes = {f.code for f in matched}
    not_loaded_from_match = all_matched_codes - loaded_codes

    # Also include refs from loaded facts that point outside the loaded set
    refs_outside: set[str] = set()
    for fact in result.loaded_facts:
        for ref in fact.refs:
            if ref not in loaded_codes:
                ref_fact = index.get(ref)
                if ref_fact and ref_fact.status not in _EXCLUDED_STATUSES:
                    refs_outside.add(ref)

    all_pointers = sorted(not_loaded_from_match | refs_outside)
    for code in all_pointers:
        ptr_fact = index.get(code)
        if ptr_fact:
            result.ref_pointers.append(f"{code} ({ptr_fact.layer.value}/{ptr_fact.type})")
        else:
            result.ref_pointers.append(code)

    return result
