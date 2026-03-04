"""Tests for auto-increment code assignment logic."""

import pytest
from pytest_httpx import HTTPXMock

from latticelens_mcp.auto_code import get_next_code, create_with_auto_code, validate_prefix_layer
from latticelens_mcp.client import LatticeLensClient
from .conftest import TEST_API_URL, SAMPLE_FACT


@pytest.fixture
def client():
    return LatticeLensClient(TEST_API_URL)


# ── Prefix-Layer Validation ─────────────────────────────────────────────


def test_valid_prefix_layer():
    assert validate_prefix_layer("ADR", "WHY") is True
    assert validate_prefix_layer("RISK", "GUARDRAILS") is True
    assert validate_prefix_layer("API", "HOW") is True


def test_invalid_prefix_layer():
    assert validate_prefix_layer("ADR", "GUARDRAILS") is False
    assert validate_prefix_layer("RISK", "WHY") is False
    assert validate_prefix_layer("NOPE", "HOW") is False


# ── get_next_code ───────────────────────────────────────────────────────


async def test_next_code_empty_db(client: LatticeLensClient, httpx_mock: HTTPXMock):
    """Empty database yields PREFIX-01."""
    httpx_mock.add_response(
        url=f"{TEST_API_URL}/facts/query",
        json={"facts": [], "total": 0, "page": 1, "page_size": 200, "total_pages": 0},
    )
    code = await get_next_code(client, "ADR")
    assert code == "ADR-01"


async def test_next_code_existing_facts(client: LatticeLensClient, httpx_mock: HTTPXMock):
    """With ADR-10 and ADR-11, next should be ADR-12."""
    facts = [
        {**SAMPLE_FACT, "code": "ADR-10"},
        {**SAMPLE_FACT, "code": "ADR-11"},
    ]
    httpx_mock.add_response(
        url=f"{TEST_API_URL}/facts/query",
        json={"facts": facts, "total": 2, "page": 1, "page_size": 200, "total_pages": 1},
    )
    code = await get_next_code(client, "ADR")
    assert code == "ADR-12"


async def test_next_code_gaps_not_filled(client: LatticeLensClient, httpx_mock: HTTPXMock):
    """Gaps are NOT filled — ADR-01, ADR-03 yields ADR-04, not ADR-02."""
    facts = [
        {**SAMPLE_FACT, "code": "ADR-01"},
        {**SAMPLE_FACT, "code": "ADR-03"},
    ]
    httpx_mock.add_response(
        url=f"{TEST_API_URL}/facts/query",
        json={"facts": facts, "total": 2, "page": 1, "page_size": 200, "total_pages": 1},
    )
    code = await get_next_code(client, "ADR")
    assert code == "ADR-04"


async def test_next_code_ignores_other_prefixes(client: LatticeLensClient, httpx_mock: HTTPXMock):
    """Only counts facts with matching prefix."""
    facts = [
        {**SAMPLE_FACT, "code": "ADR-05"},
        {**SAMPLE_FACT, "code": "RISK-10"},
        {**SAMPLE_FACT, "code": "COMP-15"},
    ]
    httpx_mock.add_response(
        url=f"{TEST_API_URL}/facts/query",
        json={"facts": facts, "total": 3, "page": 1, "page_size": 200, "total_pages": 1},
    )
    code = await get_next_code(client, "ADR")
    assert code == "ADR-06"


async def test_next_code_zero_padded(client: LatticeLensClient, httpx_mock: HTTPXMock):
    """Codes are zero-padded to 2 digits."""
    facts = [
        {**SAMPLE_FACT, "code": "SP-01"},
        {**SAMPLE_FACT, "code": "SP-02"},
    ]
    httpx_mock.add_response(
        url=f"{TEST_API_URL}/facts/query",
        json={"facts": facts, "total": 2, "page": 1, "page_size": 200, "total_pages": 1},
    )
    code = await get_next_code(client, "SP")
    assert code == "SP-03"


# ── create_with_auto_code ──────────────────────────────────────────────


async def test_create_with_auto_code_success(client: LatticeLensClient, httpx_mock: HTTPXMock):
    """Successful creation with auto-assigned code."""
    # First call: query for next code
    httpx_mock.add_response(
        url=f"{TEST_API_URL}/facts/query",
        json={"facts": [{**SAMPLE_FACT, "code": "ADR-10"}], "total": 1, "page": 1, "page_size": 200, "total_pages": 1},
    )
    # Second call: create fact
    created = {**SAMPLE_FACT, "code": "ADR-11", "status": "Draft"}
    httpx_mock.add_response(url=f"{TEST_API_URL}/facts", json=created, status_code=201)

    result = await create_with_auto_code(
        client=client,
        prefix="ADR",
        layer="WHY",
        fact_type="Architecture Decision Record",
        fact_text="Test auto-increment fact creation works correctly.",
        tags=["test", "auto-increment"],
    )
    assert result["code"] == "ADR-11"


async def test_create_with_auto_code_retry_on_conflict(client: LatticeLensClient, httpx_mock: HTTPXMock):
    """Retries on 409 CONFLICT with fresh code query."""
    # Attempt 1: query
    httpx_mock.add_response(
        url=f"{TEST_API_URL}/facts/query",
        json={"facts": [{**SAMPLE_FACT, "code": "ADR-10"}], "total": 1, "page": 1, "page_size": 200, "total_pages": 1},
    )
    # Attempt 1: create → 409
    httpx_mock.add_response(
        url=f"{TEST_API_URL}/facts", status_code=409,
        json={"detail": "CONFLICT: code ADR-11 already exists"},
    )
    # Attempt 2: query (now ADR-11 exists too)
    httpx_mock.add_response(
        url=f"{TEST_API_URL}/facts/query",
        json={"facts": [{**SAMPLE_FACT, "code": "ADR-10"}, {**SAMPLE_FACT, "code": "ADR-11"}],
              "total": 2, "page": 1, "page_size": 200, "total_pages": 1},
    )
    # Attempt 2: create → success
    created = {**SAMPLE_FACT, "code": "ADR-12", "status": "Draft"}
    httpx_mock.add_response(url=f"{TEST_API_URL}/facts", json=created, status_code=201)

    result = await create_with_auto_code(
        client=client,
        prefix="ADR",
        layer="WHY",
        fact_type="Architecture Decision Record",
        fact_text="Test retry on conflict works correctly.",
        tags=["test", "retry"],
    )
    assert result["code"] == "ADR-12"


async def test_create_with_auto_code_invalid_prefix(client: LatticeLensClient, httpx_mock: HTTPXMock):
    """Invalid prefix for layer returns error without API call."""
    result = await create_with_auto_code(
        client=client,
        prefix="ADR",
        layer="GUARDRAILS",  # ADR is not valid for GUARDRAILS
        fact_type="Architecture Decision Record",
        fact_text="This should fail prefix validation.",
        tags=["test", "invalid"],
    )
    assert "error" in result
    assert "Invalid prefix" in result["error"]


async def test_create_with_auto_code_max_retries(client: LatticeLensClient, httpx_mock: HTTPXMock):
    """After MAX_RETRIES conflicts, returns error."""
    # 3 rounds of query + 409
    for i in range(3):
        httpx_mock.add_response(
            url=f"{TEST_API_URL}/facts/query",
            json={"facts": [{**SAMPLE_FACT, "code": "ADR-10"}], "total": 1,
                  "page": 1, "page_size": 200, "total_pages": 1},
        )
        httpx_mock.add_response(
            url=f"{TEST_API_URL}/facts", status_code=409,
            json={"detail": "CONFLICT"},
        )

    result = await create_with_auto_code(
        client=client,
        prefix="ADR",
        layer="WHY",
        fact_type="Architecture Decision Record",
        fact_text="This should exhaust all retries due to conflicts.",
        tags=["test", "exhausted"],
    )
    assert "error" in result
    assert "retries" in result["error"]
