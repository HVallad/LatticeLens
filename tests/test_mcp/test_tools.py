"""Tests for MCP tool registration and behavior."""

import httpx
import pytest
from pytest_httpx import HTTPXMock

from latticelens_mcp.config import MCPConfig
from latticelens_mcp.server import create_server, AGENT_INSTRUCTIONS
from .conftest import TEST_API_URL, SAMPLE_FACT, SAMPLE_QUERY_RESPONSE, SAMPLE_IMPACT, SAMPLE_HEALTH


@pytest.fixture
def config():
    return MCPConfig(api_url=TEST_API_URL)


@pytest.fixture
def mcp_server(config):
    return create_server(config)


# ── Server Setup ────────────────────────────────────────────────────────


def test_server_has_instructions(mcp_server):
    """Server instructions contain the consult-before-act workflow."""
    assert mcp_server.instructions is not None
    assert "Consult Before Act" in mcp_server.instructions
    assert "query_facts" in mcp_server.instructions


def test_server_has_all_tools(mcp_server):
    """All 12 tools are registered."""
    tool_names = set(mcp_server._tool_manager._tools.keys())
    expected = {
        "query_facts", "get_fact", "get_fact_history", "check_health",
        "check_impact", "get_refs", "find_orphans", "find_contradictions",
        "create_fact", "create_facts_bulk", "update_fact", "deprecate_fact",
        "extract_facts",
    }
    # 13 tools (12 planned + get_fact_history which we added)
    assert expected.issubset(tool_names), f"Missing tools: {expected - tool_names}"


# ── Instructions Template ──────────────────────────────────────────────


def test_instructions_contain_all_tool_names():
    """The agent instructions reference all key tools."""
    for tool in ["query_facts", "get_fact", "check_impact", "create_fact",
                 "update_fact", "find_contradictions", "find_orphans"]:
        assert tool in AGENT_INSTRUCTIONS, f"Missing tool '{tool}' in instructions"


def test_instructions_contain_prefixes():
    """Instructions list valid prefixes."""
    for prefix in ["ADR", "PRD", "RISK", "COMP", "API", "RUN"]:
        assert prefix in AGENT_INSTRUCTIONS


def test_instructions_contain_layers():
    """Instructions reference all three layers."""
    for layer in ["WHY", "GUARDRAILS", "HOW"]:
        assert layer in AGENT_INSTRUCTIONS


# ── Tool: query_facts ──────────────────────────────────────────────────


async def test_query_facts_by_tags(mcp_server, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{TEST_API_URL}/facts/query", json=SAMPLE_QUERY_RESPONSE)
    result = await mcp_server.call_tool("query_facts", {"tags": ["architecture"]})
    text = result[0][0].text
    assert "ADR-10" in text
    assert "ADR-11" in text


async def test_query_facts_by_text(mcp_server, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{TEST_API_URL}/facts/query", json=SAMPLE_QUERY_RESPONSE)
    result = await mcp_server.call_tool("query_facts", {"text_search": "FastAPI"})
    text = result[0][0].text
    assert "ADR-10" in text


async def test_query_facts_empty(mcp_server, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{TEST_API_URL}/facts/query",
        json={"facts": [], "total": 0, "page": 1, "page_size": 50, "total_pages": 0},
    )
    result = await mcp_server.call_tool("query_facts", {"text_search": "nonexistent"})
    text = result[0][0].text
    assert "No facts found" in text


async def test_query_facts_connection_error(mcp_server, httpx_mock: HTTPXMock):
    httpx_mock.add_exception(httpx.ConnectError("Connection refused"))
    result = await mcp_server.call_tool("query_facts", {"tags": ["test"]})
    text = result[0][0].text
    assert "ERROR" in text
    assert "Cannot connect" in text


# ── Tool: get_fact ──────────────────────────────────────────────────────


async def test_get_fact_found(mcp_server, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{TEST_API_URL}/facts/ADR-10", json=SAMPLE_FACT)
    result = await mcp_server.call_tool("get_fact", {"code": "ADR-10"})
    text = result[0][0].text
    assert "[ADR-10]" in text
    assert "WHY" in text
    assert "FastAPI" in text


async def test_get_fact_not_found(mcp_server, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{TEST_API_URL}/facts/NOPE-99", status_code=404)
    result = await mcp_server.call_tool("get_fact", {"code": "NOPE-99"})
    text = result[0][0].text
    assert "ERROR" in text
    assert "not found" in text


# ── Tool: check_health ─────────────────────────────────────────────────


async def test_check_health(mcp_server, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{TEST_API_URL}/health", json=SAMPLE_HEALTH)
    result = await mcp_server.call_tool("check_health", {})
    text = result[0][0].text
    assert "healthy" in text
    assert "40" in text  # facts_total


# ── Tool: check_impact ─────────────────────────────────────────────────


async def test_check_impact(mcp_server, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{TEST_API_URL}/graph/ADR-10/impact", json=SAMPLE_IMPACT)
    result = await mcp_server.call_tool("check_impact", {"code": "ADR-10"})
    text = result[0][0].text
    assert "ADR-10" in text
    assert "API-10" in text
    assert "architecture" in text


# ── Tool: create_fact ──────────────────────────────────────────────────


async def test_create_fact_success(mcp_server, httpx_mock: HTTPXMock):
    # Query for next code
    httpx_mock.add_response(
        url=f"{TEST_API_URL}/facts/query",
        json={"facts": [{**SAMPLE_FACT, "code": "ADR-10"}], "total": 1,
              "page": 1, "page_size": 200, "total_pages": 1},
    )
    # Create
    created = {**SAMPLE_FACT, "code": "ADR-11", "status": "Draft", "confidence": "Provisional"}
    httpx_mock.add_response(url=f"{TEST_API_URL}/facts", json=created, status_code=201)

    result = await mcp_server.call_tool("create_fact", {
        "prefix": "ADR",
        "layer": "WHY",
        "type": "Architecture Decision Record",
        "fact_text": "Test fact for MCP tool validation.",
        "tags": ["test", "validation"],
    })
    text = result[0][0].text
    assert "Created fact ADR-11" in text


async def test_create_fact_invalid_prefix(mcp_server, httpx_mock: HTTPXMock):
    result = await mcp_server.call_tool("create_fact", {
        "prefix": "ADR",
        "layer": "GUARDRAILS",
        "type": "Test",
        "fact_text": "This should fail prefix validation.",
        "tags": ["test", "invalid"],
    })
    text = result[0][0].text
    assert "ERROR" in text
    assert "Invalid prefix" in text


# ── Tool: update_fact ──────────────────────────────────────────────────


async def test_update_fact_success(mcp_server, httpx_mock: HTTPXMock):
    updated = {**SAMPLE_FACT, "version": 2, "fact_text": "Updated text for testing."}
    httpx_mock.add_response(url=f"{TEST_API_URL}/facts/ADR-10", json=updated)
    result = await mcp_server.call_tool("update_fact", {
        "code": "ADR-10",
        "change_reason": "Testing update tool",
        "fact_text": "Updated text for testing.",
    })
    text = result[0][0].text
    assert "Updated fact ADR-10" in text
    assert "v2" in text


# ── Tool: deprecate_fact ───────────────────────────────────────────────


async def test_deprecate_fact(mcp_server, httpx_mock: HTTPXMock):
    deprecated = {**SAMPLE_FACT, "status": "Deprecated"}
    httpx_mock.add_response(url=f"{TEST_API_URL}/facts/ADR-10", json=deprecated)
    result = await mcp_server.call_tool("deprecate_fact", {"code": "ADR-10"})
    text = result[0][0].text
    assert "Deprecated fact ADR-10" in text


# ── Tool: find_orphans ─────────────────────────────────────────────────


async def test_find_orphans(mcp_server, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{TEST_API_URL}/graph/orphans", json=["RISK-99", "SP-05"])
    result = await mcp_server.call_tool("find_orphans", {})
    text = result[0][0].text
    assert "RISK-99" in text
    assert "SP-05" in text


async def test_find_orphans_none(mcp_server, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{TEST_API_URL}/graph/orphans", json=[])
    result = await mcp_server.call_tool("find_orphans", {})
    text = result[0][0].text
    assert "No orphaned" in text


# ── Tool: find_contradictions ──────────────────────────────────────────


async def test_find_contradictions(mcp_server, httpx_mock: HTTPXMock):
    contradictions = [{"code_a": "ADR-10", "code_b": "ADR-11",
                       "shared_tags": ["architecture"], "reason": "Different owners"}]
    httpx_mock.add_response(url=f"{TEST_API_URL}/graph/contradictions", json=contradictions)
    result = await mcp_server.call_tool("find_contradictions", {})
    text = result[0][0].text
    assert "ADR-10" in text
    assert "ADR-11" in text
