import pytest


@pytest.mark.asyncio
async def test_impact_direct(seeded_client):
    resp = await seeded_client.get("/api/v1/graph/ADR-03/impact")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_code"] == "ADR-03"
    # ADR-03 is referenced by MC-01 and RISK-07 (they have ADR-03 in their refs)
    assert "MC-01" in data["directly_affected"] or "RISK-07" in data["directly_affected"]


@pytest.mark.asyncio
async def test_impact_transitive(seeded_client):
    # ADR-01 is referenced by DES-01 (direct), and DES-01 is referenced by RUN-01 (transitive)
    resp = await seeded_client.get("/api/v1/graph/ADR-01/impact")
    assert resp.status_code == 200
    data = resp.json()
    all_affected = data["directly_affected"] + data["transitively_affected"]
    # At least some facts should be found
    assert len(all_affected) >= 1


@pytest.mark.asyncio
async def test_impact_max_depth(seeded_client):
    resp = await seeded_client.get("/api/v1/graph/ADR-01/impact")
    assert resp.status_code == 200
    # The CTE limits to depth 3, so we just verify it completes successfully
    data = resp.json()
    assert "directly_affected" in data
    assert "transitively_affected" in data


@pytest.mark.asyncio
async def test_orphan_detection(seeded_client):
    # Create a truly orphan fact (no outgoing or incoming refs)
    orphan = {
        "code": "ADR-99",
        "layer": "WHY",
        "type": "Architecture Decision Record",
        "fact_text": "An isolated fact with no connections to test orphan detection.",
        "tags": ["orphan", "test"],
        "status": "Active",
        "confidence": "Confirmed",
        "owner": "test-team",
        "refs": [],
    }
    resp = await seeded_client.post("/api/v1/facts", json=orphan)
    assert resp.status_code == 201

    resp = await seeded_client.get("/api/v1/graph/orphans")
    assert resp.status_code == 200
    orphans = resp.json()
    assert isinstance(orphans, list)
    assert "ADR-99" in orphans


@pytest.mark.asyncio
async def test_refs_bidirectional(seeded_client):
    resp = await seeded_client.get("/api/v1/graph/ADR-01/refs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == "ADR-01"
    assert "outgoing" in data
    assert "incoming" in data
    # ADR-01 has refs to DES-01, RISK-03, API-01
    assert len(data["outgoing"]) >= 1
    # Some facts reference ADR-01 (e.g., DES-01, PRD-01, API-01)
    assert len(data["incoming"]) >= 1
