"""Auto-increment code assignment for facts (per DES-13, COMP-15).

Queries the API for existing codes with a given prefix, finds the max
sequence number, and returns the next available code. Retries on 409
CONFLICT up to MAX_RETRIES times (per COMP-15).
"""

from latticelens_mcp.client import LatticeLensClient

MAX_RETRIES = 3

# Valid prefixes by layer (per COMP-10)
LAYER_PREFIXES = {
    "WHY": ["ADR", "PRD", "ETH", "DES"],
    "GUARDRAILS": ["MC", "AUP", "RISK", "DG", "COMP"],
    "HOW": ["SP", "API", "RUN", "ML", "MON"],
}

ALL_PREFIXES = {prefix for prefixes in LAYER_PREFIXES.values() for prefix in prefixes}


def validate_prefix_layer(prefix: str, layer: str) -> bool:
    """Check that prefix is valid for the given layer."""
    return prefix in LAYER_PREFIXES.get(layer, [])


async def get_next_code(client: LatticeLensClient, prefix: str) -> str:
    """Query the API for the next available code with the given prefix.

    Scans ALL statuses to avoid reusing codes from deprecated/superseded facts.
    """
    result = await client.query_facts({
        "status": ["Active", "Draft", "Under Review", "Deprecated", "Superseded"],
        "page_size": 200,
    })

    facts = result.get("facts", [])
    max_seq = 0

    for fact in facts:
        code = fact.get("code", "")
        if code.startswith(f"{prefix}-"):
            try:
                seq = int(code.split("-", 1)[1])
                max_seq = max(max_seq, seq)
            except (IndexError, ValueError):
                continue

    return f"{prefix}-{max_seq + 1:02d}"


async def create_with_auto_code(
    client: LatticeLensClient,
    prefix: str,
    layer: str,
    fact_type: str,
    fact_text: str,
    tags: list[str],
    owner: str = "claude-agent",
    refs: list[str] | None = None,
    status: str = "Draft",
    confidence: str = "Provisional",
) -> dict:
    """Create a fact with auto-assigned code, retrying on 409 CONFLICT.

    Per COMP-15: retries up to 3 times on conflict.
    Per RISK-14: handles concurrent race conditions via retry.
    """
    if not validate_prefix_layer(prefix, layer):
        valid = ", ".join(LAYER_PREFIXES.get(layer, []))
        return {"error": f"Invalid prefix '{prefix}' for layer '{layer}'. Valid: {valid}"}

    payload = {
        "layer": layer,
        "type": fact_type,
        "fact_text": fact_text,
        "tags": tags,
        "owner": owner,
        "status": status,
        "confidence": confidence,
    }
    if refs:
        payload["refs"] = refs

    for attempt in range(MAX_RETRIES):
        code = await get_next_code(client, prefix)
        payload["code"] = code
        result = await client.create_fact(payload)

        if result.get("error") == "conflict":
            continue  # Code was taken, retry with fresh query
        return result

    return {"error": f"Failed to auto-assign code for prefix '{prefix}' after {MAX_RETRIES} retries (concurrent conflict)"}
