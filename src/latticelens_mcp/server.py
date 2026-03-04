"""LatticeLens MCP Server — 12 tools for knowledge governance (per ADR-17, API-20).

All tools are thin wrappers around the LatticeLens HTTP API (per ADR-19).
"""

import json

import httpx
from mcp.server.fastmcp import FastMCP

from latticelens_mcp.auto_code import LAYER_PREFIXES, create_with_auto_code
from latticelens_mcp.client import LatticeLensClient
from latticelens_mcp.config import MCPConfig
from latticelens_mcp.formatting import (
    format_contradictions,
    format_extraction,
    format_fact,
    format_fact_list,
    format_health,
    format_history,
    format_impact,
    format_orphans,
    format_refs,
)

AGENT_INSTRUCTIONS = """\
# LatticeLens Knowledge Governance

You have access to the LatticeLens knowledge base via MCP tools. This knowledge base
is the SOLE AUTHORITATIVE SOURCE OF TRUTH for this project.

## Mandatory Workflow: Consult Before Act

Before making ANY code change, architecture decision, or design choice:

1. SEARCH the knowledge base: Call `query_facts` with relevant tags or text
2. READ the returned facts and identify which ones govern your change
3. CITE fact codes in your reasoning (e.g., "per ADR-10", "following COMP-11")
4. CHECK GUARDRAILS: Always search the GUARDRAILS layer for constraints
5. CHECK IMPACT: Before modifying any fact, call `check_impact` first

## Tool Quick Reference

| Tool | When to Use |
|------|-------------|
| `query_facts` | FIRST STEP before any change. Search by text, tags, or layer |
| `get_fact` | Get full details of a specific fact by code |
| `check_impact` | Before modifying or deprecating any fact |
| `create_fact` | Record a new decision, constraint, or procedure |
| `update_fact` | Modify an existing fact (requires change_reason) |
| `find_contradictions` | Check for inconsistencies in the knowledge base |
| `find_orphans` | Find disconnected facts that may need linking |

## Creating Facts

When you discover an undocumented decision or constraint:
- Use `create_fact` with appropriate prefix (ADR, RISK, COMP, etc.)
- Code is auto-assigned -- just provide the prefix
- Always create as Draft/Provisional -- humans promote to Active/Confirmed
- Minimum 2 tags, minimum 10 characters for fact_text
- Valid prefixes: WHY(ADR,PRD,ETH,DES) GUARDRAILS(MC,AUP,RISK,DG,COMP) HOW(SP,API,RUN,ML,MON)

## Tag Search Guide

- Architecture: architecture, async, fastapi, postgresql, sqlalchemy
- Validation: compliance, validation, referential-integrity
- API: api, crud, endpoints, filtering
- Safety: risk, depth-limit, audit-trail
- Operations: runbook, docker-compose, alembic, cli, monitoring
- LLM: extraction, anthropic, llm-integration
"""


def _error_message(e: Exception, api_url: str) -> str:
    """Format exception into a helpful error message for the agent."""
    if isinstance(e, httpx.ConnectError):
        return f"ERROR: Cannot connect to LatticeLens API at {api_url}. Is the server running?"
    if isinstance(e, httpx.HTTPStatusError):
        return f"ERROR: API returned {e.response.status_code}: {e.response.text}"
    return f"ERROR: {type(e).__name__}: {e}"


def create_server(config: MCPConfig) -> FastMCP:
    """Create and configure the FastMCP server with all tools."""
    mcp = FastMCP(
        "LatticeLens",
        instructions=AGENT_INSTRUCTIONS,
    )

    api = LatticeLensClient(config.api_url, timeout=config.request_timeout)
    default_owner = config.default_owner

    # ── Consultation Tools ──────────────────────────────────────────────

    @mcp.tool()
    async def query_facts(
        text_search: str | None = None,
        tags: list[str] | None = None,
        layer: str | None = None,
        status: str | None = None,
        owner: str | None = None,
        page_size: int = 50,
    ) -> str:
        """Search the LatticeLens knowledge base for facts relevant to your current task.

        IMPORTANT: Call this tool BEFORE making any code change, architecture decision,
        or design choice. Query by text (full-text search), tags, layer (WHY/GUARDRAILS/HOW),
        or owner. Returns matching facts with their codes, which you should cite in your
        reasoning (e.g., "per ADR-10").

        Common tag searches:
        - Architecture: architecture, async, fastapi, postgresql, sqlalchemy
        - Validation: compliance, validation, referential-integrity
        - API: api, crud, endpoints, filtering
        - Safety: risk, depth-limit, audit-trail
        - Operations: runbook, docker-compose, alembic, cli, monitoring
        - LLM: extraction, anthropic, llm-integration
        """
        try:
            query = {"page_size": min(page_size, 200)}
            if text_search:
                query["text_search"] = text_search
            if tags:
                query["tags_any"] = tags
            if layer:
                query["layer"] = [layer]
            if status:
                query["status"] = [status]
            else:
                query["status"] = ["Active"]
            if owner:
                query["owner"] = owner
            result = await api.query_facts(query)
            return format_fact_list(result)
        except Exception as e:
            return _error_message(e, config.api_url)

    @mcp.tool()
    async def get_fact(code: str) -> str:
        """Retrieve a single fact by its code (e.g., ADR-10, RISK-11, COMP-12).

        Use this when you know the exact code and need the full details including
        version, refs, review date, and staleness status.
        """
        try:
            result = await api.get_fact(code)
            if "error" in result:
                return f"ERROR: {result['error']}"
            return format_fact(result)
        except Exception as e:
            return _error_message(e, config.api_url)

    @mcp.tool()
    async def get_fact_history(code: str) -> str:
        """Get the version history of a fact. Shows who changed it, when, and why.

        Use this to understand how a fact evolved over time, or to audit changes.
        """
        try:
            result = await api.get_fact_history(code)
            if isinstance(result, dict) and "error" in result:
                return f"ERROR: {result['error']}"
            return format_history(result)
        except Exception as e:
            return _error_message(e, config.api_url)

    @mcp.tool()
    async def check_health() -> str:
        """Check if the LatticeLens API is healthy and get summary statistics.

        Returns API status, version, total facts count, active facts count,
        and stale facts count.
        """
        try:
            result = await api.health()
            return format_health(result)
        except Exception as e:
            return _error_message(e, config.api_url)

    # ── Knowledge Graph Tools ───────────────────────────────────────────

    @mcp.tool()
    async def check_impact(code: str) -> str:
        """Check what would be affected if a fact changes (3-hop impact analysis).

        IMPORTANT: Call this BEFORE modifying or deprecating any fact. Shows directly
        affected facts, transitively affected facts, and which agent roles would be
        impacted. Helps prevent unintended side effects.
        """
        try:
            result = await api.get_impact(code)
            if "error" in result:
                return f"ERROR: {result['error']}"
            return format_impact(result)
        except Exception as e:
            return _error_message(e, config.api_url)

    @mcp.tool()
    async def get_refs(code: str) -> str:
        """Get incoming and outgoing references for a fact.

        Shows which facts this one depends on (outgoing) and which facts depend on
        this one (incoming). Useful for understanding a fact's position in the
        knowledge graph.
        """
        try:
            result = await api.get_refs(code)
            if "error" in result:
                return f"ERROR: {result['error']}"
            return format_refs(result)
        except Exception as e:
            return _error_message(e, config.api_url)

    @mcp.tool()
    async def find_orphans() -> str:
        """Find facts with no references to or from other facts.

        Orphaned facts may indicate knowledge gaps or facts that need to be
        connected to the broader knowledge graph.
        """
        try:
            result = await api.get_orphans()
            return format_orphans(result)
        except Exception as e:
            return _error_message(e, config.api_url)

    @mcp.tool()
    async def find_contradictions() -> str:
        """Find pairs of active facts that may contradict each other.

        Detects facts sharing 2+ tags but in different layers or with different
        owners. Review these pairs to ensure consistency.
        """
        try:
            result = await api.get_contradictions()
            return format_contradictions(result)
        except Exception as e:
            return _error_message(e, config.api_url)

    # ── Fact Management Tools ───────────────────────────────────────────

    @mcp.tool()
    async def create_fact(
        prefix: str,
        layer: str,
        type: str,
        fact_text: str,
        tags: list[str],
        owner: str | None = None,
        refs: list[str] | None = None,
        status: str = "Draft",
        confidence: str = "Provisional",
    ) -> str:
        """Create a new fact in the knowledge base with auto-assigned code.

        Provide a prefix (e.g., ADR, RISK, COMP, API) and the server automatically
        assigns the next available number. The fact is created as Draft/Provisional
        by default -- a human must promote it to Active/Confirmed.

        Valid prefixes by layer:
        - WHY: ADR, PRD, ETH, DES
        - GUARDRAILS: MC, AUP, RISK, DG, COMP
        - HOW: SP, API, RUN, ML, MON

        Requires minimum 2 lowercase tags and at least 10 characters for fact_text.
        All refs must point to existing fact codes.
        """
        try:
            result = await create_with_auto_code(
                client=api,
                prefix=prefix.upper(),
                layer=layer,
                fact_type=type,
                fact_text=fact_text,
                tags=tags,
                owner=owner or default_owner,
                refs=refs,
                status=status,
                confidence=confidence,
            )
            if "error" in result:
                return f"ERROR: {result.get('detail', result['error'])}"
            return f"Created fact {result['code']}:\n\n{format_fact(result)}"
        except Exception as e:
            return _error_message(e, config.api_url)

    @mcp.tool()
    async def create_facts_bulk(facts_json: str) -> str:
        """Create multiple facts atomically in a single transaction.

        Input is a JSON string containing an array of fact objects. Each object needs:
        prefix, layer, type, fact_text, tags. Optional: owner, refs, status, confidence.
        Codes are auto-assigned for each fact based on its prefix.

        Use this when extracting or recording multiple related facts at once.

        Example input:
        [
          {"prefix": "ADR", "layer": "WHY", "type": "Architecture Decision Record",
           "fact_text": "Chose Redis for caching.", "tags": ["caching", "redis"]},
          {"prefix": "RISK", "layer": "GUARDRAILS", "type": "Risk Assessment Finding",
           "fact_text": "Cache invalidation may cause stale reads.",
           "tags": ["caching", "risk"]}
        ]
        """
        try:
            items = json.loads(facts_json)
        except json.JSONDecodeError as e:
            return f"ERROR: Invalid JSON: {e}"

        if not isinstance(items, list):
            return "ERROR: Input must be a JSON array of fact objects."

        try:
            # Auto-assign codes for each item
            payloads = []
            for item in items:
                prefix = item.get("prefix", "").upper()
                layer = item.get("layer", "")

                code = await _get_next_code_for_bulk(api, prefix, payloads)
                payloads.append({
                    "code": code,
                    "layer": layer,
                    "type": item.get("type", ""),
                    "fact_text": item.get("fact_text", ""),
                    "tags": item.get("tags", []),
                    "owner": item.get("owner", default_owner),
                    "status": item.get("status", "Draft"),
                    "confidence": item.get("confidence", "Provisional"),
                    "refs": item.get("refs", []),
                })

            result = await api.bulk_create(payloads)
            if isinstance(result, dict) and "error" in result:
                return f"ERROR: {result.get('detail', result['error'])}"

            codes = [f["code"] for f in result]
            return f"Created {len(result)} facts: {', '.join(codes)}"
        except Exception as e:
            return _error_message(e, config.api_url)

    @mcp.tool()
    async def update_fact(
        code: str,
        change_reason: str,
        changed_by: str | None = None,
        fact_text: str | None = None,
        tags: list[str] | None = None,
        status: str | None = None,
        confidence: str | None = None,
        owner: str | None = None,
        refs: list[str] | None = None,
    ) -> str:
        """Update an existing fact. Triggers a version bump and creates audit history.

        You MUST provide a change_reason explaining why. Always call check_impact first
        to understand downstream effects. Only modified fields need to be provided.
        """
        try:
            payload = {
                "change_reason": change_reason,
                "changed_by": changed_by or default_owner,
            }
            if fact_text is not None:
                payload["fact_text"] = fact_text
            if tags is not None:
                payload["tags"] = tags
            if status is not None:
                payload["status"] = status
            if confidence is not None:
                payload["confidence"] = confidence
            if owner is not None:
                payload["owner"] = owner
            if refs is not None:
                payload["refs"] = refs

            result = await api.update_fact(code, payload)
            if "error" in result:
                return f"ERROR: {result.get('detail', result['error'])}"
            return f"Updated fact {code} (now v{result.get('version', '?')}):\n\n{format_fact(result)}"
        except Exception as e:
            return _error_message(e, config.api_url)

    @mcp.tool()
    async def deprecate_fact(code: str) -> str:
        """Soft-delete a fact by setting its status to Deprecated.

        The fact remains in the database for audit purposes but is excluded from
        default queries. Always call check_impact first to understand what depends
        on this fact.
        """
        try:
            result = await api.deprecate_fact(code)
            if "error" in result:
                return f"ERROR: {result['error']}"
            return f"Deprecated fact {code}. It is now excluded from default queries."
        except Exception as e:
            return _error_message(e, config.api_url)

    # ── Analysis Tools ──────────────────────────────────────────────────

    @mcp.tool()
    async def extract_facts(
        content: str,
        source_name: str,
        default_layer: str = "GUARDRAILS",
        default_owner: str = "unknown",
    ) -> str:
        """Extract candidate facts from a document using LLM analysis.

        Sends the content to the LatticeLens extraction endpoint which uses Claude
        to decompose the document into atomic facts. Returns candidates with
        suggested codes -- these are NOT yet saved to the database.

        Review the candidates and use create_fact or create_facts_bulk to save
        the ones you approve.
        """
        try:
            result = await api.extract({
                "content": content,
                "source_name": source_name,
                "default_layer": default_layer,
                "default_owner": default_owner,
            })
            return format_extraction(result)
        except Exception as e:
            return _error_message(e, config.api_url)

    return mcp


async def _get_next_code_for_bulk(
    client: LatticeLensClient, prefix: str, already_assigned: list[dict]
) -> str:
    """Get next code considering both API and already-assigned codes in this batch."""
    from latticelens_mcp.auto_code import get_next_code

    api_next = await get_next_code(client, prefix)

    # Also check codes already assigned in this batch
    batch_max = 0
    for p in already_assigned:
        code = p.get("code", "")
        if code.startswith(f"{prefix}-"):
            try:
                seq = int(code.split("-", 1)[1])
                batch_max = max(batch_max, seq)
            except (IndexError, ValueError):
                continue

    api_seq = int(api_next.split("-", 1)[1])
    final_seq = max(api_seq, batch_max + 1)
    return f"{prefix}-{final_seq:02d}"
