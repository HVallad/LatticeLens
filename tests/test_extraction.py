import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_extraction_no_api_key(client, clean_db):
    """Extraction should fail gracefully without API key."""
    payload = {
        "content": "This is a test document about system architecture decisions.",
        "source_name": "Test Doc",
        "default_layer": "WHY",
        "default_owner": "test-team",
    }
    resp = await client.post("/api/v1/extract", json=payload)
    assert resp.status_code == 400
    assert "API" in resp.json()["detail"] or "not configured" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_extraction_with_mock(client, clean_db):
    """Test extraction with a mocked Anthropic client."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = json.dumps([
        {
            "layer": "WHY",
            "type": "Architecture Decision Record",
            "fact_text": "Selected PostgreSQL as the primary database for structured data storage due to JSONB support and mature ecosystem.",
            "tags": ["database", "architecture"],
            "refs": [],
        },
        {
            "layer": "GUARDRAILS",
            "type": "Risk Assessment Finding",
            "fact_text": "Database connection pooling must be configured to prevent connection exhaustion under load.",
            "tags": ["database", "scaling", "risk"],
            "refs": [],
        },
    ])

    with patch("latticelens.services.extract_service.settings") as mock_settings:
        mock_settings.anthropic_api_key = "test-key"
        mock_settings.extraction_model = "claude-sonnet-4-20250514"

        with patch("latticelens.services.extract_service.anthropic.Anthropic") as MockClient:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            MockClient.return_value = mock_client

            payload = {
                "content": "We decided to use PostgreSQL for structured data. Connection pooling is critical.",
                "source_name": "Architecture Notes",
                "default_layer": "WHY",
                "default_owner": "arch-team",
            }
            resp = await client.post("/api/v1/extract", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["candidates"]) == 2
            assert data["source_name"] == "Architecture Notes"
            assert data["model_used"] == "claude-sonnet-4-20250514"
            assert data["candidates"][0]["confidence"] == "Provisional"
