import json
import os
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from latticelens.models import Base

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://latticelens:latticelens_dev@localhost:5433/latticelens_test",
)


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS fact_history CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS fact_refs CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS facts CASCADE"))
        await conn.execute(text("DROP TYPE IF EXISTS fact_layer CASCADE"))
        await conn.execute(text("DROP TYPE IF EXISTS fact_status CASCADE"))
        await conn.execute(text("DROP TYPE IF EXISTS fact_confidence CASCADE"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def client(test_engine):
    from latticelens.db import get_db
    from latticelens.main import app

    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def clean_db(test_engine):
    """Ensure tables are clean before a test."""
    async with test_engine.begin() as conn:
        await conn.execute(text("DELETE FROM fact_history"))
        await conn.execute(text("DELETE FROM fact_refs"))
        await conn.execute(text("DELETE FROM facts"))


@pytest_asyncio.fixture
async def seeded_client(client, clean_db):
    """Client with seed data loaded."""
    seed_path = Path(__file__).parent.parent / "seed" / "example_facts.json"
    with open(seed_path) as f:
        facts = json.load(f)

    all_codes = {f["code"] for f in facts}
    missing_refs = set()
    for fact in facts:
        for ref in fact.get("refs", []):
            if ref not in all_codes:
                missing_refs.add(ref)

    layer_for_prefix = {
        "ADR": "WHY", "PRD": "WHY", "ETH": "WHY", "DES": "WHY",
        "MC": "GUARDRAILS", "AUP": "GUARDRAILS", "RISK": "GUARDRAILS",
        "DG": "GUARDRAILS", "COMP": "GUARDRAILS",
        "SP": "HOW", "API": "HOW", "RUN": "HOW", "ML": "HOW", "MON": "HOW",
    }
    type_for_prefix = {
        "ADR": "Architecture Decision Record", "PRD": "Product Requirement",
        "ETH": "Ethical Review Finding", "DES": "Design Proposal Decision",
        "MC": "Model Card Entry", "AUP": "Acceptable Use Policy Rule",
        "RISK": "Risk Assessment Finding", "DG": "Data Governance Rule",
        "COMP": "Compliance Requirement", "SP": "System Prompt Rule",
        "API": "API Specification", "RUN": "Runbook Procedure",
        "ML": "MLOps Pipeline Rule", "MON": "Monitoring Rule",
    }

    placeholders = []
    for ref_code in sorted(missing_refs):
        prefix = ref_code.split("-")[0]
        placeholders.append({
            "code": ref_code,
            "layer": layer_for_prefix.get(prefix, "HOW"),
            "type": type_for_prefix.get(prefix, "Unknown"),
            "fact_text": f"Placeholder for {ref_code}. Content pending.",
            "tags": ["placeholder", "needs-content"],
            "status": "Draft",
            "confidence": "Assumed",
            "owner": "system",
            "refs": [],
        })

    if placeholders:
        resp = await client.post("/api/v1/facts/bulk", json=placeholders)
        assert resp.status_code == 201

    resp = await client.post("/api/v1/facts/bulk", json=facts)
    assert resp.status_code == 201

    yield client
