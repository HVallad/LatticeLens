import pytest


@pytest.mark.asyncio
async def test_query_by_layer(seeded_client):
    resp = await seeded_client.post("/api/v1/facts/query", json={
        "layer": ["WHY"],
        "status": ["Active"],
    })
    assert resp.status_code == 200
    data = resp.json()
    for fact in data["facts"]:
        assert fact["layer"] == "WHY"


@pytest.mark.asyncio
async def test_query_by_status(seeded_client):
    # Default query should return only Active facts
    resp = await seeded_client.post("/api/v1/facts/query", json={})
    assert resp.status_code == 200
    data = resp.json()
    for fact in data["facts"]:
        assert fact["status"] == "Active"


@pytest.mark.asyncio
async def test_query_by_tags_any(seeded_client):
    resp = await seeded_client.post("/api/v1/facts/query", json={
        "tags_any": ["security"],
        "status": ["Active"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["facts"]) >= 1
    for fact in data["facts"]:
        assert any("security" in tag for tag in fact["tags"])


@pytest.mark.asyncio
async def test_query_by_tags_all(seeded_client):
    resp = await seeded_client.post("/api/v1/facts/query", json={
        "tags_all": ["privacy", "pii"],
        "status": ["Active"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["facts"]) >= 1
    for fact in data["facts"]:
        assert "privacy" in fact["tags"]
        assert "pii" in fact["tags"]


@pytest.mark.asyncio
async def test_query_text_search(seeded_client):
    resp = await seeded_client.post("/api/v1/facts/query", json={
        "text_search": "prompt injection",
        "status": ["Active"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["facts"]) >= 1
    codes = [f["code"] for f in data["facts"]]
    assert "RISK-07" in codes


@pytest.mark.asyncio
async def test_query_pagination(seeded_client):
    resp = await seeded_client.post("/api/v1/facts/query", json={
        "status": ["Active"],
        "page": 1,
        "page_size": 3,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["facts"]) <= 3
    assert data["page"] == 1
    assert data["page_size"] == 3
    assert data["total"] > 0
    assert data["total_pages"] > 0


@pytest.mark.asyncio
async def test_query_ordering(seeded_client):
    # Update one fact to Provisional confidence
    await seeded_client.patch("/api/v1/facts/SP-01", json={
        "confidence": "Provisional",
        "change_reason": "Testing ordering",
        "changed_by": "test",
    })

    resp = await seeded_client.post("/api/v1/facts/query", json={
        "status": ["Active"],
        "layer": ["HOW"],
    })
    assert resp.status_code == 200
    data = resp.json()
    facts = data["facts"]
    if len(facts) >= 2:
        # Confirmed facts should come before Provisional
        confirmed_indices = [i for i, f in enumerate(facts) if f["confidence"] == "Confirmed"]
        provisional_indices = [i for i, f in enumerate(facts) if f["confidence"] == "Provisional"]
        if confirmed_indices and provisional_indices:
            assert max(confirmed_indices) < min(provisional_indices)


@pytest.mark.asyncio
async def test_stale_detection(client, clean_db):
    payload = {
        "code": "ADR-80",
        "layer": "WHY",
        "type": "Architecture Decision Record",
        "fact_text": "This fact has an expired review date for stale detection testing.",
        "tags": ["test", "stale"],
        "status": "Active",
        "confidence": "Confirmed",
        "owner": "test-team",
        "review_by": "2020-01-01",
    }
    resp = await client.post("/api/v1/facts", json=payload)
    assert resp.status_code == 201

    # Default query should exclude stale facts
    resp = await client.post("/api/v1/facts/query", json={"status": ["Active"]})
    data = resp.json()
    codes = [f["code"] for f in data["facts"]]
    assert "ADR-80" not in codes

    # With include_stale, should include it with is_stale=true
    resp = await client.post("/api/v1/facts/query", json={
        "status": ["Active"],
        "include_stale": True,
    })
    data = resp.json()
    stale_facts = [f for f in data["facts"] if f["code"] == "ADR-80"]
    assert len(stale_facts) == 1
    assert stale_facts[0]["is_stale"] is True
