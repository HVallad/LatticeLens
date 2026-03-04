import pytest


@pytest.mark.asyncio
async def test_create_fact(client, clean_db):
    payload = {
        "code": "ADR-99",
        "layer": "WHY",
        "type": "Architecture Decision Record",
        "fact_text": "Test fact for architecture decisions regarding caching strategy.",
        "tags": ["caching", "architecture"],
        "status": "Draft",
        "confidence": "Confirmed",
        "owner": "test-team",
    }
    resp = await client.post("/api/v1/facts", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["code"] == "ADR-99"
    assert data["version"] == 1
    assert data["created_at"] is not None
    assert data["layer"] == "WHY"


@pytest.mark.asyncio
async def test_create_duplicate_code(client, clean_db):
    payload = {
        "code": "ADR-50",
        "layer": "WHY",
        "type": "Architecture Decision Record",
        "fact_text": "First fact about something important for testing.",
        "tags": ["test", "duplicate"],
        "owner": "test-team",
    }
    resp = await client.post("/api/v1/facts", json=payload)
    assert resp.status_code == 201

    resp = await client.post("/api/v1/facts", json=payload)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_invalid_code_format(client, clean_db):
    payload = {
        "code": "invalid",
        "layer": "WHY",
        "type": "Architecture Decision Record",
        "fact_text": "This should fail due to invalid code format.",
        "tags": ["test", "invalid"],
        "owner": "test-team",
    }
    resp = await client.post("/api/v1/facts", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_code_layer_mismatch(client, clean_db):
    payload = {
        "code": "ADR-60",
        "layer": "GUARDRAILS",
        "type": "Risk Assessment Finding",
        "fact_text": "ADR prefix is not valid for GUARDRAILS layer, should fail.",
        "tags": ["test", "mismatch"],
        "owner": "test-team",
    }
    resp = await client.post("/api/v1/facts", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_insufficient_tags(client, clean_db):
    payload = {
        "code": "ADR-61",
        "layer": "WHY",
        "type": "Architecture Decision Record",
        "fact_text": "Should fail because only one tag provided.",
        "tags": ["single"],
        "owner": "test-team",
    }
    resp = await client.post("/api/v1/facts", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_with_refs(client, clean_db):
    # Create target fact first
    target = {
        "code": "ADR-70",
        "layer": "WHY",
        "type": "Architecture Decision Record",
        "fact_text": "Target fact that will be referenced by another fact.",
        "tags": ["target", "reference"],
        "owner": "test-team",
    }
    resp = await client.post("/api/v1/facts", json=target)
    assert resp.status_code == 201

    # Create fact with ref
    payload = {
        "code": "ADR-71",
        "layer": "WHY",
        "type": "Architecture Decision Record",
        "fact_text": "This fact references ADR-70 to test ref creation.",
        "tags": ["source", "reference"],
        "owner": "test-team",
        "refs": ["ADR-70"],
    }
    resp = await client.post("/api/v1/facts", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert "ADR-70" in data["refs"]


@pytest.mark.asyncio
async def test_create_with_invalid_refs(client, clean_db):
    payload = {
        "code": "ADR-72",
        "layer": "WHY",
        "type": "Architecture Decision Record",
        "fact_text": "This fact references a non-existent code which should fail.",
        "tags": ["test", "invalid-ref"],
        "owner": "test-team",
        "refs": ["NONEXISTENT-99"],
    }
    resp = await client.post("/api/v1/facts", json=payload)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_fact(seeded_client):
    resp = await seeded_client.get("/api/v1/facts/ADR-03")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == "ADR-03"
    assert data["layer"] == "WHY"
    assert data["version"] >= 1
    assert "tags" in data
    assert "refs" in data


@pytest.mark.asyncio
async def test_get_nonexistent(client, clean_db):
    resp = await client.get("/api/v1/facts/DOES-NOT-EXIST")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_fact(seeded_client):
    # Get current state
    resp = await seeded_client.get("/api/v1/facts/ADR-03")
    original = resp.json()
    original_version = original["version"]
    original_updated = original["updated_at"]

    # Update
    update_payload = {
        "fact_text": "Updated fact text for testing version increment behavior.",
        "change_reason": "Testing update functionality",
        "changed_by": "test-user",
    }
    resp = await seeded_client.patch("/api/v1/facts/ADR-03", json=update_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == original_version + 1
    assert data["updated_at"] != original_updated
    assert data["fact_text"] == "Updated fact text for testing version increment behavior."

    # Check history was created
    resp = await seeded_client.get("/api/v1/facts/ADR-03/history")
    history = resp.json()
    assert len(history) >= 1
    assert history[0]["version"] == original_version


@pytest.mark.asyncio
async def test_update_preserves_unchanged(seeded_client):
    resp = await seeded_client.get("/api/v1/facts/PRD-01")
    original = resp.json()

    update_payload = {
        "confidence": "Provisional",
        "change_reason": "Testing partial update",
        "changed_by": "test-user",
    }
    resp = await seeded_client.patch("/api/v1/facts/PRD-01", json=update_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["confidence"] == "Provisional"
    assert data["fact_text"] == original["fact_text"]
    assert data["owner"] == original["owner"]
    assert data["layer"] == original["layer"]


@pytest.mark.asyncio
async def test_deprecate_fact(seeded_client):
    resp = await seeded_client.delete("/api/v1/facts/RUN-01")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "Deprecated"

    # Verify it still exists
    resp = await seeded_client.get("/api/v1/facts/RUN-01")
    assert resp.status_code == 200
    assert resp.json()["status"] == "Deprecated"
