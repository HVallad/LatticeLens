import pytest


@pytest.mark.asyncio
async def test_history_created_on_update(client, clean_db):
    # Create a fact
    payload = {
        "code": "ADR-40",
        "layer": "WHY",
        "type": "Architecture Decision Record",
        "fact_text": "Original text for version history testing purposes.",
        "tags": ["test", "versioning"],
        "owner": "test-team",
        "status": "Active",
    }
    resp = await client.post("/api/v1/facts", json=payload)
    assert resp.status_code == 201

    # Update it
    update = {
        "fact_text": "Updated text for version history testing purposes.",
        "change_reason": "Testing history creation",
        "changed_by": "test-user",
    }
    resp = await client.patch("/api/v1/facts/ADR-40", json=update)
    assert resp.status_code == 200

    # Check history
    resp = await client.get("/api/v1/facts/ADR-40/history")
    history = resp.json()
    assert len(history) == 1
    assert history[0]["version"] == 1
    assert history[0]["fact_text"] == "Original text for version history testing purposes."
    assert history[0]["changed_by"] == "test-user"
    assert history[0]["change_reason"] == "Testing history creation"


@pytest.mark.asyncio
async def test_version_increments(client, clean_db):
    payload = {
        "code": "ADR-41",
        "layer": "WHY",
        "type": "Architecture Decision Record",
        "fact_text": "Fact for multi-version increment testing scenario.",
        "tags": ["test", "versioning"],
        "owner": "test-team",
        "status": "Active",
    }
    resp = await client.post("/api/v1/facts", json=payload)
    assert resp.status_code == 201

    for i in range(3):
        update = {
            "fact_text": f"Update number {i + 1} for version testing purposes.",
            "change_reason": f"Update #{i + 1}",
            "changed_by": "test-user",
        }
        resp = await client.patch("/api/v1/facts/ADR-41", json=update)
        assert resp.status_code == 200

    # Should be version 4 after 3 updates
    resp = await client.get("/api/v1/facts/ADR-41")
    assert resp.json()["version"] == 4

    # Should have 3 history rows
    resp = await client.get("/api/v1/facts/ADR-41/history")
    assert len(resp.json()) == 3


@pytest.mark.asyncio
async def test_history_endpoint(client, clean_db):
    payload = {
        "code": "ADR-42",
        "layer": "WHY",
        "type": "Architecture Decision Record",
        "fact_text": "Original text for history endpoint ordering test.",
        "tags": ["test", "history"],
        "owner": "test-team",
        "status": "Active",
    }
    await client.post("/api/v1/facts", json=payload)

    for i in range(2):
        await client.patch("/api/v1/facts/ADR-42", json={
            "fact_text": f"Version {i + 2} text for ordering test purposes.",
            "change_reason": f"Update {i + 1}",
            "changed_by": "test-user",
        })

    resp = await client.get("/api/v1/facts/ADR-42/history")
    history = resp.json()
    # Should be ordered DESC by version
    versions = [h["version"] for h in history]
    assert versions == sorted(versions, reverse=True)


@pytest.mark.asyncio
async def test_superseded_requires_target(client, clean_db):
    payload = {
        "code": "ADR-43",
        "layer": "WHY",
        "type": "Architecture Decision Record",
        "fact_text": "Fact that will be superseded without target for error testing.",
        "tags": ["test", "supersede"],
        "owner": "test-team",
        "status": "Active",
    }
    await client.post("/api/v1/facts", json=payload)

    # Try to set Superseded without superseded_by
    update = {
        "status": "Superseded",
        "change_reason": "Should fail without target",
        "changed_by": "test-user",
    }
    resp = await client.patch("/api/v1/facts/ADR-43", json=update)
    assert resp.status_code == 400
