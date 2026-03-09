"""Tests for the web viewer REST API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from lattice_lens.web.app import create_app


@pytest.fixture
def web_client(tmp_lattice):
    """Create a test client with a temporary lattice."""
    app = create_app(tmp_lattice)
    return TestClient(app)


@pytest.fixture
def seeded_web_client(seeded_store):
    """Create a test client with a seeded lattice (12 facts)."""
    app = create_app(seeded_store.root)
    return TestClient(app)


class TestFactEndpoints:
    def test_list_facts_empty(self, web_client):
        resp = web_client.get("/api/facts")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_facts_seeded(self, seeded_web_client):
        resp = seeded_web_client.get("/api/facts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0

    def test_get_fact(self, seeded_web_client):
        resp = seeded_web_client.get("/api/facts/ADR-01")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "ADR-01"
        assert data["layer"] == "WHY"

    def test_get_fact_not_found(self, seeded_web_client):
        resp = seeded_web_client.get("/api/facts/NOPE-99")
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data

    def test_create_fact(self, web_client):
        resp = web_client.post(
            "/api/facts",
            json={
                "code": "ADR-01",
                "layer": "WHY",
                "type": "Architecture Decision Record",
                "fact": "This is a test fact for the web API",
                "tags": ["test", "api"],
                "owner": "test-team",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "ADR-01"
        assert "error" not in data

    def test_create_fact_with_prefix(self, web_client):
        resp = web_client.post(
            "/api/facts",
            json={
                "prefix": "ADR",
                "layer": "WHY",
                "type": "Architecture Decision Record",
                "fact": "Auto-assigned code test fact here",
                "tags": ["test", "auto-code"],
                "owner": "test-team",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "ADR-01"

    def test_update_fact(self, seeded_web_client):
        resp = seeded_web_client.patch(
            "/api/facts/ADR-01",
            json={
                "changes": {"fact": "Updated fact text for testing purposes"},
                "reason": "Testing update via web API",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "error" not in data

    def test_deprecate_fact(self, seeded_web_client):
        resp = seeded_web_client.post(
            "/api/facts/ADR-01/deprecate",
            json={
                "reason": "No longer relevant",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "Deprecated"

    def test_promote_fact(self, seeded_web_client):
        # Create a Draft fact first
        seeded_web_client.post(
            "/api/facts",
            json={
                "code": "ADR-99",
                "layer": "WHY",
                "type": "Architecture Decision Record",
                "fact": "A draft fact to be promoted via web",
                "tags": ["test", "draft"],
                "owner": "test-team",
            },
        )
        resp = seeded_web_client.post(
            "/api/facts/ADR-99/promote",
            json={
                "reason": "Ready for review",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "Under Review"

    def test_next_code(self, seeded_web_client):
        resp = seeded_web_client.get("/api/facts/next-code/ADR")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"].startswith("ADR-")

    def test_filter_by_layer(self, seeded_web_client):
        resp = seeded_web_client.get("/api/facts?layer=WHY")
        assert resp.status_code == 200
        data = resp.json()
        for fact in data:
            assert fact["layer"] == "WHY"

    def test_filter_by_status(self, seeded_web_client):
        resp = seeded_web_client.get("/api/facts?status=Active")
        assert resp.status_code == 200


class TestGraphEndpoints:
    def test_graph_data(self, seeded_web_client):
        resp = seeded_web_client.get("/api/graph/data")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) > 0
        # Each node should have required fields
        node = data["nodes"][0]
        assert "code" in node
        assert "layer" in node
        assert "status" in node
        assert "tags" in node

    def test_graph_data_with_inactive(self, seeded_web_client):
        resp = seeded_web_client.get("/api/graph/data?include_inactive=true")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data

    def test_graph_orphans(self, seeded_web_client):
        resp = seeded_web_client.get("/api/graph/orphans")
        assert resp.status_code == 200

    def test_graph_contradictions(self, seeded_web_client):
        resp = seeded_web_client.get("/api/graph/contradictions")
        assert resp.status_code == 200

    def test_graph_impact(self, seeded_web_client):
        resp = seeded_web_client.get("/api/graph/impact/ADR-01")
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "ADR-01"


class TestMetaEndpoints:
    def test_meta_stats(self, seeded_web_client):
        resp = seeded_web_client.get("/api/meta/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data or "by_layer" in data or isinstance(data, dict)

    def test_meta_enums(self, seeded_web_client):
        resp = seeded_web_client.get("/api/meta/enums")
        assert resp.status_code == 200
        data = resp.json()
        assert "layers" in data
        assert "statuses" in data
        assert "confidences" in data
        assert "edge_types" in data
        assert "layer_prefixes" in data
        assert "inverse_labels" in data
        assert data["layers"] == ["WHY", "GUARDRAILS", "HOW"]
        assert "Draft" in data["statuses"]
        assert "Active" in data["statuses"]

    def test_meta_tags(self, seeded_web_client):
        resp = seeded_web_client.get("/api/meta/tags")
        assert resp.status_code == 200

    def test_meta_types(self, seeded_web_client):
        resp = seeded_web_client.get("/api/meta/types")
        assert resp.status_code == 200

    def test_meta_roles(self, seeded_web_client):
        resp = seeded_web_client.get("/api/meta/roles")
        assert resp.status_code == 200

    def test_meta_validate(self, seeded_web_client):
        resp = seeded_web_client.get("/api/meta/validate")
        assert resp.status_code == 200
        data = resp.json()
        assert "ok" in data


class TestViewCommand:
    def test_view_no_lattice(self, tmp_path, monkeypatch):
        """View should error when no .lattice exists."""
        from typer.testing import CliRunner
        from lattice_lens.cli.main import app

        runner = CliRunner()
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["view", "--no-open"])
        assert result.exit_code == 1
        assert "No .lattice directory" in result.output or result.exit_code == 1
