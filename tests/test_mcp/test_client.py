"""Tests for the LatticeLens HTTP client wrapper."""

import pytest
import httpx
from pytest_httpx import HTTPXMock

from latticelens_mcp.client import LatticeLensClient
from .conftest import TEST_API_URL, SAMPLE_FACT, SAMPLE_QUERY_RESPONSE, SAMPLE_HEALTH


@pytest.fixture
def client():
    return LatticeLensClient(TEST_API_URL)


# ── Health ──────────────────────────────────────────────────────────────


async def test_health(client: LatticeLensClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{TEST_API_URL}/health", json=SAMPLE_HEALTH)
    result = await client.health()
    assert result["status"] == "healthy"
    assert result["facts_total"] == 40


# ── Get Fact ────────────────────────────────────────────────────────────


async def test_get_fact_found(client: LatticeLensClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{TEST_API_URL}/facts/ADR-10", json=SAMPLE_FACT)
    result = await client.get_fact("ADR-10")
    assert result["code"] == "ADR-10"
    assert result["layer"] == "WHY"


async def test_get_fact_not_found(client: LatticeLensClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{TEST_API_URL}/facts/NOPE-99", status_code=404)
    result = await client.get_fact("NOPE-99")
    assert "error" in result
    assert "not found" in result["error"]


# ── Query Facts ─────────────────────────────────────────────────────────


async def test_query_facts(client: LatticeLensClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{TEST_API_URL}/facts/query", json=SAMPLE_QUERY_RESPONSE)
    result = await client.query_facts({"tags_any": ["architecture"], "page_size": 50})
    assert result["total"] == 2
    assert len(result["facts"]) == 2


# ── Create Fact ─────────────────────────────────────────────────────────


async def test_create_fact_success(client: LatticeLensClient, httpx_mock: HTTPXMock):
    created = {**SAMPLE_FACT, "code": "ADR-20", "status": "Draft"}
    httpx_mock.add_response(url=f"{TEST_API_URL}/facts", json=created, status_code=201)
    result = await client.create_fact({"code": "ADR-20", "layer": "WHY", "type": "Architecture Decision Record",
                                       "fact_text": "Test fact.", "tags": ["test", "fact"], "owner": "test"})
    assert result["code"] == "ADR-20"


async def test_create_fact_conflict(client: LatticeLensClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{TEST_API_URL}/facts", status_code=409,
                            json={"detail": "CONFLICT: code ADR-10 already exists"})
    result = await client.create_fact({"code": "ADR-10", "layer": "WHY", "type": "ADR",
                                       "fact_text": "Duplicate.", "tags": ["test", "dup"], "owner": "test"})
    assert result["error"] == "conflict"


async def test_create_fact_validation_error(client: LatticeLensClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{TEST_API_URL}/facts", status_code=422,
                            json={"detail": "fact_text too short"})
    result = await client.create_fact({"code": "ADR-99", "layer": "WHY", "type": "ADR",
                                       "fact_text": "Short", "tags": ["a"], "owner": "test"})
    assert result["error"] == "validation"


# ── Update Fact ─────────────────────────────────────────────────────────


async def test_update_fact_success(client: LatticeLensClient, httpx_mock: HTTPXMock):
    updated = {**SAMPLE_FACT, "version": 2, "fact_text": "Updated text for the fact."}
    httpx_mock.add_response(url=f"{TEST_API_URL}/facts/ADR-10", json=updated)
    result = await client.update_fact("ADR-10", {"fact_text": "Updated text for the fact.",
                                                  "change_reason": "test", "changed_by": "test"})
    assert result["version"] == 2


async def test_update_fact_not_found(client: LatticeLensClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{TEST_API_URL}/facts/NOPE-99", status_code=404)
    result = await client.update_fact("NOPE-99", {"fact_text": "x", "change_reason": "test", "changed_by": "test"})
    assert "error" in result


# ── Deprecate Fact ──────────────────────────────────────────────────────


async def test_deprecate_fact_success(client: LatticeLensClient, httpx_mock: HTTPXMock):
    deprecated = {**SAMPLE_FACT, "status": "Deprecated"}
    httpx_mock.add_response(url=f"{TEST_API_URL}/facts/ADR-10", json=deprecated)
    result = await client.deprecate_fact("ADR-10")
    assert result["status"] == "Deprecated"


async def test_deprecate_fact_not_found(client: LatticeLensClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{TEST_API_URL}/facts/NOPE-99", status_code=404)
    result = await client.deprecate_fact("NOPE-99")
    assert "error" in result


# ── History ─────────────────────────────────────────────────────────────


async def test_get_fact_history(client: LatticeLensClient, httpx_mock: HTTPXMock):
    history = [{"version": 1, "changed_by": "test", "changed_at": "2025-01-01T00:00:00Z",
                "change_reason": "initial", "fact_text": "Original.", "status": "Draft", "confidence": "Provisional"}]
    httpx_mock.add_response(url=f"{TEST_API_URL}/facts/ADR-10/history", json=history)
    result = await client.get_fact_history("ADR-10")
    assert isinstance(result, list)
    assert result[0]["version"] == 1


# ── Graph ───────────────────────────────────────────────────────────────


async def test_get_impact(client: LatticeLensClient, httpx_mock: HTTPXMock):
    impact = {"source_code": "ADR-10", "directly_affected": ["API-10"],
              "transitively_affected": [], "affected_agent_roles": ["architecture"]}
    httpx_mock.add_response(url=f"{TEST_API_URL}/graph/ADR-10/impact", json=impact)
    result = await client.get_impact("ADR-10")
    assert result["source_code"] == "ADR-10"
    assert "API-10" in result["directly_affected"]


async def test_get_refs(client: LatticeLensClient, httpx_mock: HTTPXMock):
    refs = {"code": "ADR-10", "outgoing": ["PRD-10"], "incoming": ["API-10"]}
    httpx_mock.add_response(url=f"{TEST_API_URL}/graph/ADR-10/refs", json=refs)
    result = await client.get_refs("ADR-10")
    assert result["outgoing"] == ["PRD-10"]


async def test_get_orphans(client: LatticeLensClient, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=f"{TEST_API_URL}/graph/orphans", json=["RISK-99"])
    result = await client.get_orphans()
    assert "RISK-99" in result


async def test_get_contradictions(client: LatticeLensClient, httpx_mock: HTTPXMock):
    contradictions = [{"code_a": "ADR-10", "code_b": "ADR-11", "shared_tags": ["architecture"],
                       "reason": "Different layers"}]
    httpx_mock.add_response(url=f"{TEST_API_URL}/graph/contradictions", json=contradictions)
    result = await client.get_contradictions()
    assert len(result) == 1


# ── Bulk Create ─────────────────────────────────────────────────────────


async def test_bulk_create(client: LatticeLensClient, httpx_mock: HTTPXMock):
    created = [{**SAMPLE_FACT, "code": "ADR-20"}, {**SAMPLE_FACT, "code": "ADR-21"}]
    httpx_mock.add_response(url=f"{TEST_API_URL}/facts/bulk", json=created, status_code=201)
    result = await client.bulk_create([{"code": "ADR-20"}, {"code": "ADR-21"}])
    assert len(result) == 2


# ── Extract ─────────────────────────────────────────────────────────────


async def test_extract(client: LatticeLensClient, httpx_mock: HTTPXMock):
    extraction = {"candidates": [{"suggested_code": "ADR-20", "layer": "WHY",
                                   "type": "ADR", "fact_text": "Extracted fact.",
                                   "tags": ["test", "extraction"], "confidence": "Provisional"}],
                  "source_name": "test.md", "model_used": "claude-sonnet-4-20250514"}
    httpx_mock.add_response(url=f"{TEST_API_URL}/extract", json=extraction)
    result = await client.extract({"content": "Test doc", "source_name": "test.md"})
    assert len(result["candidates"]) == 1
