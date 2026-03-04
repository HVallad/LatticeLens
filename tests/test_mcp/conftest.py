"""Shared fixtures for MCP server tests."""

import pytest

from latticelens_mcp.client import LatticeLensClient
from latticelens_mcp.config import MCPConfig

TEST_API_URL = "http://test-api:8000/api/v1"


@pytest.fixture
def config():
    return MCPConfig(api_url=TEST_API_URL)


@pytest.fixture
def api_client():
    return LatticeLensClient(TEST_API_URL)


SAMPLE_FACT = {
    "id": "00000000-0000-0000-0000-000000000001",
    "code": "ADR-10",
    "layer": "WHY",
    "type": "Architecture Decision Record",
    "fact_text": "Selected FastAPI as the HTTP framework for async support.",
    "tags": ["architecture", "fastapi"],
    "status": "Active",
    "confidence": "Confirmed",
    "version": 1,
    "owner": "architecture-team",
    "refs": ["PRD-10"],
    "superseded_by": None,
    "review_by": None,
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-01-01T00:00:00Z",
    "is_stale": False,
}

SAMPLE_FACT_2 = {
    "id": "00000000-0000-0000-0000-000000000002",
    "code": "ADR-11",
    "layer": "WHY",
    "type": "Architecture Decision Record",
    "fact_text": "Selected PostgreSQL 16 for JSONB and full-text search.",
    "tags": ["architecture", "postgresql"],
    "status": "Active",
    "confidence": "Confirmed",
    "version": 1,
    "owner": "architecture-team",
    "refs": [],
    "superseded_by": None,
    "review_by": None,
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-01-01T00:00:00Z",
    "is_stale": False,
}

SAMPLE_QUERY_RESPONSE = {
    "facts": [SAMPLE_FACT, SAMPLE_FACT_2],
    "total": 2,
    "page": 1,
    "page_size": 50,
    "total_pages": 1,
}

SAMPLE_IMPACT = {
    "source_code": "ADR-10",
    "directly_affected": ["API-10", "DES-10"],
    "transitively_affected": ["RUN-11"],
    "affected_agent_roles": ["architecture", "implementation"],
}

SAMPLE_HEALTH = {
    "status": "healthy",
    "version": "0.1.0",
    "facts_total": 40,
    "facts_active": 30,
    "facts_stale": 2,
}
