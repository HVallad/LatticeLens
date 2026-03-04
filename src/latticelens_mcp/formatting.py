"""Format API responses as readable text for AI agents (per API-20)."""

from datetime import datetime


def format_fact(fact: dict) -> str:
    """Format a single fact as readable text."""
    lines = [
        f"[{fact['code']}] {fact['layer']} / {fact['status']} (v{fact.get('version', 1)})",
        f"Type: {fact['type']}",
        f"Text: {fact['fact_text']}",
        f"Tags: {', '.join(fact.get('tags', []))}",
        f"Confidence: {fact.get('confidence', 'Unknown')}",
        f"Owner: {fact.get('owner', 'Unknown')}",
    ]
    if fact.get("refs"):
        lines.append(f"Refs: {', '.join(fact['refs'])}")
    if fact.get("superseded_by"):
        lines.append(f"Superseded by: {fact['superseded_by']}")
    if fact.get("review_by"):
        lines.append(f"Review by: {fact['review_by']}")
    if fact.get("is_stale"):
        lines.append("WARNING: This fact is STALE (past review date)")
    return "\n".join(lines)


def format_fact_list(result: dict) -> str:
    """Format a paginated fact list response."""
    facts = result.get("facts", [])
    total = result.get("total", 0)
    page = result.get("page", 1)
    total_pages = result.get("total_pages", 1)

    if not facts:
        return "No facts found matching your query."

    lines = []
    for fact in facts:
        stale_marker = " [STALE]" if fact.get("is_stale") else ""
        lines.append(
            f"[{fact['code']}] ({fact['layer']}/{fact['status']}{stale_marker}) "
            f"{fact['fact_text'][:120]}{'...' if len(fact.get('fact_text', '')) > 120 else ''}"
        )
        lines.append(f"  Tags: {', '.join(fact.get('tags', []))}")

    lines.append(f"\n--- Page {page}/{total_pages} ({total} total facts) ---")
    return "\n".join(lines)


def format_impact(result: dict) -> str:
    """Format impact analysis response."""
    source = result.get("source_code", "?")
    direct = result.get("directly_affected", [])
    transitive = result.get("transitively_affected", [])
    roles = result.get("affected_agent_roles", [])

    lines = [f"Impact analysis for {source}:"]

    if direct:
        lines.append(f"\nDirectly affected ({len(direct)}):")
        for code in direct:
            lines.append(f"  - {code}")
    else:
        lines.append("\nNo directly affected facts.")

    if transitive:
        lines.append(f"\nTransitively affected ({len(transitive)}):")
        for code in transitive:
            lines.append(f"  - {code}")

    if roles:
        lines.append(f"\nAffected agent roles: {', '.join(roles)}")

    return "\n".join(lines)


def format_refs(result: dict) -> str:
    """Format refs response."""
    code = result.get("code", "?")
    outgoing = result.get("outgoing", [])
    incoming = result.get("incoming", [])

    lines = [f"References for {code}:"]
    lines.append(f"\nOutgoing (this fact references): {', '.join(outgoing) if outgoing else 'none'}")
    lines.append(f"Incoming (referenced by): {', '.join(incoming) if incoming else 'none'}")
    return "\n".join(lines)


def format_orphans(orphans: list) -> str:
    """Format orphan list."""
    if not orphans:
        return "No orphaned facts found. All facts are connected in the knowledge graph."
    return f"Orphaned facts ({len(orphans)}):\n" + "\n".join(f"  - {code}" for code in orphans)


def format_contradictions(contradictions: list) -> str:
    """Format contradiction candidates."""
    if not contradictions:
        return "No potential contradictions found."

    lines = [f"Potential contradictions ({len(contradictions)}):"]
    for c in contradictions:
        lines.append(f"\n  {c.get('code_a', '?')} vs {c.get('code_b', '?')}")
        lines.append(f"  Shared tags: {', '.join(c.get('shared_tags', []))}")
        lines.append(f"  Reason: {c.get('reason', 'Unknown')}")
    return "\n".join(lines)


def format_history(history: list) -> str:
    """Format fact version history."""
    if not history:
        return "No history found for this fact."

    lines = ["Version history:"]
    for entry in history:
        lines.append(
            f"\n  v{entry.get('version', '?')} by {entry.get('changed_by', '?')} "
            f"at {entry.get('changed_at', '?')}"
        )
        lines.append(f"  Reason: {entry.get('change_reason', 'N/A')}")
        lines.append(f"  Status: {entry.get('status', '?')} | Confidence: {entry.get('confidence', '?')}")
        text = entry.get("fact_text", "")
        if text:
            lines.append(f"  Text: {text[:120]}{'...' if len(text) > 120 else ''}")
    return "\n".join(lines)


def format_health(result: dict) -> str:
    """Format health check response."""
    return (
        f"LatticeLens API: {result.get('status', 'unknown')}\n"
        f"Version: {result.get('version', '?')}\n"
        f"Facts total: {result.get('facts_total', '?')}\n"
        f"Facts active: {result.get('facts_active', '?')}\n"
        f"Facts stale: {result.get('facts_stale', '?')}"
    )


def format_extraction(result: dict) -> str:
    """Format extraction response."""
    candidates = result.get("candidates", [])
    source = result.get("source_name", "unknown")
    model = result.get("model_used", "unknown")

    if not candidates:
        return f"No facts extracted from '{source}' (model: {model})."

    lines = [f"Extracted {len(candidates)} candidate facts from '{source}' (model: {model}):"]
    for c in candidates:
        lines.append(f"\n  [{c.get('suggested_code', '?')}] {c.get('layer', '?')} / {c.get('type', '?')}")
        lines.append(f"  Text: {c.get('fact_text', '')[:120]}")
        lines.append(f"  Tags: {', '.join(c.get('tags', []))}")
        lines.append(f"  Confidence: {c.get('confidence', '?')}")

    lines.append("\nThese are CANDIDATES only — use create_fact or create_facts_bulk to save them.")
    return "\n".join(lines)
