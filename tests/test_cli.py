import json
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from latticelens.cli.main import app

runner = CliRunner()


def mock_api_get(path):
    if path == "/health":
        return {
            "status": "healthy",
            "version": "0.1.0",
            "facts_total": 12,
            "facts_active": 10,
            "facts_stale": 1,
        }
    elif path.startswith("/facts/") and "/history" in path:
        return [
            {
                "version": 1,
                "fact_text": "Original text",
                "tags": ["test", "cli"],
                "status": "Active",
                "confidence": "Confirmed",
                "changed_by": "test-user",
                "changed_at": "2026-03-01T00:00:00Z",
                "change_reason": "Initial",
            }
        ]
    elif path.startswith("/facts/"):
        return {
            "id": "00000000-0000-0000-0000-000000000001",
            "code": "ADR-03",
            "layer": "WHY",
            "type": "Architecture Decision Record",
            "fact_text": "Test fact text for CLI testing purposes.",
            "tags": ["test", "cli"],
            "status": "Active",
            "confidence": "Confirmed",
            "version": 1,
            "owner": "test-team",
            "refs": [],
            "superseded_by": None,
            "review_by": None,
            "created_at": "2026-03-01T00:00:00Z",
            "updated_at": "2026-03-01T00:00:00Z",
            "is_stale": False,
        }
    return {}


@patch("latticelens.cli.main.api_get", side_effect=mock_api_get)
def test_health_command(mock_get):
    result = runner.invoke(app, ["health"])
    assert result.exit_code == 0
    assert "healthy" in result.output


@patch("latticelens.cli.main.api_get", side_effect=mock_api_get)
def test_fact_get(mock_get):
    result = runner.invoke(app, ["fact", "get", "ADR-03"])
    assert result.exit_code == 0
    assert "ADR-03" in result.output


@patch("latticelens.cli.main.api_get", side_effect=mock_api_get)
def test_fact_get_json(mock_get):
    result = runner.invoke(app, ["fact", "get", "ADR-03", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["code"] == "ADR-03"


@patch("latticelens.cli.main.api_post")
def test_fact_list_json(mock_post):
    mock_post.return_value = {
        "facts": [
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "code": "ADR-03",
                "layer": "WHY",
                "type": "Architecture Decision Record",
                "fact_text": "Test",
                "tags": ["test", "cli"],
                "status": "Active",
                "confidence": "Confirmed",
                "version": 1,
                "owner": "test-team",
                "refs": [],
                "superseded_by": None,
                "review_by": None,
                "created_at": "2026-03-01T00:00:00Z",
                "updated_at": "2026-03-01T00:00:00Z",
                "is_stale": False,
            }
        ],
        "total": 1,
        "page": 1,
        "page_size": 50,
        "total_pages": 1,
    }
    result = runner.invoke(app, ["fact", "list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "facts" in data


@patch("latticelens.cli.main.api_post")
def test_seed_command(mock_post):
    mock_post.return_value = [{"code": f"FACT-{i}"} for i in range(12)]
    result = runner.invoke(app, ["seed"])
    assert result.exit_code == 0
    assert "loaded" in result.output.lower() or "facts" in result.output.lower()
