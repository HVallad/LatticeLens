# LatticeLens — Phase 1 Implementation Brief

> **Purpose**: This document is the executable spec for an AI coding agent to build LatticeLens Phase 1. It assumes the agent has read the [LatticeLens Design Document](./latticelens-design-doc.docx) as context for _why_ these decisions were made. This document covers _what to build_ and _how to verify it works_.
>
> **Scope**: Phase 1 delivers the Fact Index (Postgres-backed), a FastAPI service with full CRUD + query API, an LLM-powered fact extraction tool, and a basic CLI. At the end of Phase 1, a developer can store facts, query them by role, traverse the knowledge graph, and extract facts from existing documents.

---

## 1. Project Setup

### 1.1 Repository Structure

```
latticelens/
├── README.md
├── LICENSE                          # MIT License (see §1.2)
├── CONTRIBUTING.md                  # Contribution terms (see §1.3)
├── pyproject.toml                   # Python project config
├── docker-compose.yml               # Local dev environment
├── alembic.ini                      # Database migration config
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 001_initial_schema.py    # First migration
├── src/
│   └── latticelens/
│       ├── __init__.py
│       ├── main.py                  # FastAPI app entrypoint
│       ├── config.py                # Settings via pydantic-settings
│       ├── db.py                    # SQLAlchemy engine + session
│       ├── models.py                # SQLAlchemy ORM models
│       ├── schemas.py               # Pydantic request/response schemas
│       ├── routers/
│       │   ├── __init__.py
│       │   ├── facts.py             # /facts endpoints
│       │   ├── graph.py             # /graph endpoints
│       │   └── health.py            # /health endpoint
│       ├── services/
│       │   ├── __init__.py
│       │   ├── fact_service.py      # Business logic for fact CRUD
│       │   ├── graph_service.py     # Reference traversal + impact analysis
│       │   └── extract_service.py   # LLM-powered fact extraction
│       └── cli/
│           ├── __init__.py
│           └── main.py              # Typer CLI entrypoint
├── tests/
│   ├── conftest.py                  # Fixtures: test DB, client, seed data
│   ├── test_facts_crud.py
│   ├── test_facts_query.py
│   ├── test_graph.py
│   ├── test_versioning.py
│   ├── test_extraction.py
│   └── test_cli.py
├── seed/
│   └── example_facts.json           # 12 example facts from design doc
└── docs/
    └── latticelens-design-doc.docx  # Reference design document
```

### 1.2 LICENSE File

```
MIT License

Copyright (c) 2026 LatticeLens Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### 1.3 CONTRIBUTING.md

```markdown
# Contributing to LatticeLens

All contributions to LatticeLens are made under the MIT License.
By submitting a pull request, you agree that your contribution is
licensed under the same MIT License that covers the project.
```

### 1.4 Python Dependencies

```toml
# pyproject.toml
[project]
name = "latticelens"
version = "0.1.0"
description = "Knowledge governance layer for AI agent systems"
license = {text = "MIT"}
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.27.0",
    "sqlalchemy>=2.0.0",
    "asyncpg>=0.29.0",
    "alembic>=1.13.0",
    "pydantic>=2.6.0",
    "pydantic-settings>=2.1.0",
    "typer>=0.9.0",
    "rich>=13.0.0",
    "httpx>=0.27.0",
    "tiktoken>=0.6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-httpx>=0.30.0",
    "ruff>=0.3.0",
]
extract = [
    "anthropic>=0.25.0",
]

[project.scripts]
latticelens = "latticelens.cli.main:app"
```

### 1.5 Docker Compose

```yaml
# docker-compose.yml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: latticelens
      POSTGRES_USER: latticelens
      POSTGRES_PASSWORD: latticelens_dev
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U latticelens"]
      interval: 5s
      timeout: 3s
      retries: 5

  api:
    build: .
    command: uvicorn latticelens.main:app --host 0.0.0.0 --port 8000 --reload
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://latticelens:latticelens_dev@postgres:5432/latticelens
    depends_on:
      postgres:
        condition: service_healthy

volumes:
  pgdata:
```

### 1.6 Application Config

```python
# src/latticelens/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://latticelens:latticelens_dev@localhost:5432/latticelens"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    default_page_size: int = 50
    max_page_size: int = 200

    # For LLM-powered extraction (Phase 1 optional)
    anthropic_api_key: str = ""
    extraction_model: str = "claude-sonnet-4-20250514"

    class Config:
        env_prefix = "LATTICELENS_"

settings = Settings()
```

---

## 2. Database Schema

### 2.1 Enums

```sql
CREATE TYPE fact_layer AS ENUM ('WHY', 'GUARDRAILS', 'HOW');

CREATE TYPE fact_status AS ENUM (
    'Draft',
    'Under Review',
    'Active',
    'Deprecated',
    'Superseded'
);

CREATE TYPE fact_confidence AS ENUM (
    'Confirmed',
    'Provisional',
    'Assumed'
);
```

### 2.2 Facts Table

This is the current state of each fact. One row per fact code.

```sql
CREATE TABLE facts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code            VARCHAR(50) NOT NULL UNIQUE,
    layer           fact_layer NOT NULL,
    type            VARCHAR(100) NOT NULL,
    fact_text       TEXT NOT NULL,
    tags            JSONB NOT NULL DEFAULT '[]',
    status          fact_status NOT NULL DEFAULT 'Draft',
    confidence      fact_confidence NOT NULL DEFAULT 'Confirmed',
    version         INTEGER NOT NULL DEFAULT 1,
    superseded_by   VARCHAR(50) REFERENCES facts(code) ON DELETE SET NULL,
    owner           VARCHAR(100) NOT NULL,
    review_by       DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Fast lookups by layer + status (most common query pattern)
CREATE INDEX idx_facts_layer_status ON facts (layer, status);

-- Fast tag-based queries
CREATE INDEX idx_facts_tags ON facts USING GIN (tags);

-- Fast text search over fact content
CREATE INDEX idx_facts_text_search ON facts USING GIN (to_tsvector('english', fact_text));

-- Status filter (context assembly always filters on Active)
CREATE INDEX idx_facts_status ON facts (status);
```

### 2.3 Fact References Table

Creates the knowledge graph. Bidirectional traversal via two indexes.

```sql
CREATE TABLE fact_refs (
    from_code   VARCHAR(50) NOT NULL REFERENCES facts(code) ON DELETE CASCADE,
    to_code     VARCHAR(50) NOT NULL REFERENCES facts(code) ON DELETE CASCADE,
    PRIMARY KEY (from_code, to_code),
    CHECK (from_code != to_code)
);

CREATE INDEX idx_fact_refs_to ON fact_refs (to_code);
```

### 2.4 Fact History Table

Immutable append-only log. Every mutation to a fact creates a history row BEFORE the update.

```sql
CREATE TABLE fact_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code            VARCHAR(50) NOT NULL,
    version         INTEGER NOT NULL,
    layer           fact_layer NOT NULL,
    type            VARCHAR(100) NOT NULL,
    fact_text       TEXT NOT NULL,
    tags            JSONB NOT NULL,
    status          fact_status NOT NULL,
    confidence      fact_confidence NOT NULL,
    owner           VARCHAR(100) NOT NULL,
    superseded_by   VARCHAR(50),
    review_by       DATE,
    changed_by      VARCHAR(100) NOT NULL,
    changed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    change_reason   TEXT NOT NULL,
    UNIQUE (code, version)
);

CREATE INDEX idx_fact_history_code ON fact_history (code, version DESC);
```

### 2.5 Migration Notes

- Use Alembic for all schema changes. Never apply DDL manually.
- The `001_initial_schema.py` migration must create all three tables, all enums, and all indexes.
- The migration must be idempotent (use `IF NOT EXISTS` where supported).

---

## 3. SQLAlchemy Models

```python
# src/latticelens/models.py
import enum
import uuid
from datetime import date, datetime
from sqlalchemy import (
    Column, String, Text, Integer, Date, DateTime, Enum, ForeignKey,
    CheckConstraint, UniqueConstraint, Index, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class FactLayer(str, enum.Enum):
    WHY = "WHY"
    GUARDRAILS = "GUARDRAILS"
    HOW = "HOW"


class FactStatus(str, enum.Enum):
    DRAFT = "Draft"
    UNDER_REVIEW = "Under Review"
    ACTIVE = "Active"
    DEPRECATED = "Deprecated"
    SUPERSEDED = "Superseded"


class FactConfidence(str, enum.Enum):
    CONFIRMED = "Confirmed"
    PROVISIONAL = "Provisional"
    ASSUMED = "Assumed"


class Fact(Base):
    __tablename__ = "facts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(50), unique=True, nullable=False, index=True)
    layer = Column(Enum(FactLayer), nullable=False)
    type = Column(String(100), nullable=False)
    fact_text = Column(Text, nullable=False)
    tags = Column(JSONB, nullable=False, default=list)
    status = Column(Enum(FactStatus), nullable=False, default=FactStatus.DRAFT)
    confidence = Column(Enum(FactConfidence), nullable=False, default=FactConfidence.CONFIRMED)
    version = Column(Integer, nullable=False, default=1)
    superseded_by = Column(String(50), ForeignKey("facts.code", ondelete="SET NULL"), nullable=True)
    owner = Column(String(100), nullable=False)
    review_by = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    # Relationships
    refs_outgoing = relationship(
        "FactRef", foreign_keys="FactRef.from_code", back_populates="source", cascade="all, delete-orphan"
    )
    refs_incoming = relationship(
        "FactRef", foreign_keys="FactRef.to_code", back_populates="target", cascade="all, delete-orphan"
    )


class FactRef(Base):
    __tablename__ = "fact_refs"

    from_code = Column(String(50), ForeignKey("facts.code", ondelete="CASCADE"), primary_key=True)
    to_code = Column(String(50), ForeignKey("facts.code", ondelete="CASCADE"), primary_key=True)

    source = relationship("Fact", foreign_keys=[from_code], back_populates="refs_outgoing")
    target = relationship("Fact", foreign_keys=[to_code], back_populates="refs_incoming")

    __table_args__ = (
        CheckConstraint("from_code != to_code", name="no_self_ref"),
    )


class FactHistory(Base):
    __tablename__ = "fact_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(50), nullable=False)
    version = Column(Integer, nullable=False)
    layer = Column(Enum(FactLayer), nullable=False)
    type = Column(String(100), nullable=False)
    fact_text = Column(Text, nullable=False)
    tags = Column(JSONB, nullable=False)
    status = Column(Enum(FactStatus), nullable=False)
    confidence = Column(Enum(FactConfidence), nullable=False)
    owner = Column(String(100), nullable=False)
    superseded_by = Column(String(50), nullable=True)
    review_by = Column(Date, nullable=True)
    changed_by = Column(String(100), nullable=False)
    changed_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    change_reason = Column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("code", "version", name="uq_fact_history_code_version"),
    )
```

---

## 4. Pydantic Schemas

```python
# src/latticelens/schemas.py
from datetime import date, datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


# ── Enums (reuse from models or redefine as string literals) ──

# ── Request Schemas ──

class FactCreate(BaseModel):
    """Create a new fact. CODE must be unique and follow {PREFIX}-{SEQ} format."""
    code: str = Field(..., pattern=r"^[A-Z]+-\d+$", examples=["ADR-03", "RISK-07"])
    layer: str = Field(..., pattern=r"^(WHY|GUARDRAILS|HOW)$")
    type: str = Field(..., min_length=1, max_length=100)
    fact_text: str = Field(..., min_length=10)
    tags: list[str] = Field(..., min_length=2)
    status: str = Field(default="Draft")
    confidence: str = Field(default="Confirmed")
    owner: str = Field(..., min_length=1, max_length=100)
    refs: list[str] = Field(default_factory=list, description="Codes of related facts")
    review_by: date | None = None

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v):
        for tag in v:
            if not tag.replace("-", "").replace("_", "").isalnum():
                raise ValueError(f"Tag must be alphanumeric with hyphens: {tag}")
            if tag != tag.lower():
                raise ValueError(f"Tag must be lowercase: {tag}")
        return v


class FactUpdate(BaseModel):
    """Update an existing fact. All fields optional. Triggers version bump."""
    fact_text: str | None = None
    tags: list[str] | None = None
    status: str | None = None
    confidence: str | None = None
    owner: str | None = None
    refs: list[str] | None = None
    review_by: date | None = None
    superseded_by: str | None = None
    change_reason: str = Field(..., min_length=1, description="Why this change was made")
    changed_by: str = Field(..., min_length=1, description="Who made this change")


class FactQuery(BaseModel):
    """Query the fact index with filters."""
    layer: list[str] | None = None
    type: list[str] | None = None
    status: list[str] | None = Field(default=["Active"])
    confidence: list[str] | None = None
    tags_any: list[str] | None = None        # Facts matching ANY of these tags
    tags_all: list[str] | None = None        # Facts matching ALL of these tags
    owner: str | None = None
    text_search: str | None = None           # Full-text search over fact_text
    include_stale: bool = False              # Include facts past review_by date
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


# ── Response Schemas ──

class FactResponse(BaseModel):
    id: UUID
    code: str
    layer: str
    type: str
    fact_text: str
    tags: list[str]
    status: str
    confidence: str
    version: int
    owner: str
    refs: list[str]
    superseded_by: str | None
    review_by: date | None
    created_at: datetime
    updated_at: datetime
    is_stale: bool = False  # True if past review_by date

    model_config = {"from_attributes": True}


class FactListResponse(BaseModel):
    facts: list[FactResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class FactHistoryEntry(BaseModel):
    version: int
    fact_text: str
    tags: list[str]
    status: str
    confidence: str
    changed_by: str
    changed_at: datetime
    change_reason: str

    model_config = {"from_attributes": True}


class ImpactAnalysisResponse(BaseModel):
    """Result of 'if I change this fact, what's affected?'"""
    source_code: str
    directly_affected: list[str]      # Facts that reference this fact
    transitively_affected: list[str]  # 2+ hops away
    affected_agent_roles: list[str]   # Roles whose queries include this fact


class HealthResponse(BaseModel):
    status: str
    version: str
    facts_total: int
    facts_active: int
    facts_stale: int
```

---

## 5. API Endpoints

Base URL: `http://localhost:8000/api/v1`

### 5.1 Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service health + fact counts |

**Response**: `HealthResponse`

### 5.2 Fact CRUD

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/facts` | Create a new fact |
| `GET` | `/facts/{code}` | Get a single fact by code |
| `PATCH` | `/facts/{code}` | Update a fact (triggers version bump + history) |
| `DELETE` | `/facts/{code}` | Deprecate a fact (sets status=Deprecated, never hard-deletes) |
| `GET` | `/facts/{code}/history` | Get full version history for a fact |
| `POST` | `/facts/query` | Query facts with filters (POST because filter body can be complex) |
| `POST` | `/facts/bulk` | Create multiple facts at once (for seeding / extraction) |

#### POST /facts — Create

**Request**: `FactCreate`
**Response**: `FactResponse` (201 Created)
**Errors**:
- `409 Conflict` if code already exists
- `422 Validation Error` if code format invalid, tags < 2, etc.
- `400 Bad Request` if refs contain codes that don't exist

**Behavior**:
1. Validate code format matches `{PREFIX}-{SEQ}` pattern
2. Validate all `refs` codes exist in the facts table
3. Insert fact with version=1, created_at=now, updated_at=now
4. Insert rows into `fact_refs` for each ref
5. Do NOT create a history entry for creation (history starts at first update)
6. Return the created fact

#### PATCH /facts/{code} — Update

**Request**: `FactUpdate` (only provided fields are changed)
**Response**: `FactResponse` (200 OK)
**Errors**:
- `404 Not Found` if code doesn't exist
- `400 Bad Request` if superseded_by references non-existent code

**Behavior**:
1. Load current fact
2. Snapshot current state into `fact_history` with the provided `change_reason` and `changed_by`
3. Apply updates to the fact
4. Increment `version` by 1
5. Set `updated_at` to now
6. If `refs` provided, delete existing `fact_refs` rows and insert new ones
7. If `status` changed to `Superseded`, require `superseded_by` to be set
8. Return the updated fact

#### DELETE /facts/{code} — Deprecate

**Response**: `FactResponse` (200 OK) with status=Deprecated
**Behavior**: Sets `status = 'Deprecated'`. Creates a history entry. Never deletes the row.

#### POST /facts/query — Query

**Request**: `FactQuery`
**Response**: `FactListResponse`

**Query logic** (all filters are AND-combined):
1. Filter by `layer` if provided (IN clause)
2. Filter by `type` if provided (IN clause)
3. Filter by `status` if provided (IN clause, default `['Active']`)
4. Filter by `confidence` if provided (IN clause)
5. Filter by `tags_any` using `tags ?| array[...]` (JSONB any-match)
6. Filter by `tags_all` using `tags ?& array[...]` (JSONB all-match)
7. Filter by `owner` if provided (exact match)
8. Filter by `text_search` using `to_tsvector('english', fact_text) @@ plainto_tsquery(...)` if provided
9. If `include_stale` is false, exclude facts where `review_by < today`; if true, include them but set `is_stale=true` in response
10. Order by: confidence DESC (Confirmed > Provisional > Assumed), then updated_at DESC
11. Apply pagination

### 5.3 Graph Operations

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/graph/{code}/impact` | Impact analysis: what's affected if this fact changes |
| `GET` | `/graph/{code}/refs` | Direct refs (outgoing and incoming) |
| `GET` | `/graph/orphans` | Facts with no incoming or outgoing refs |
| `GET` | `/graph/contradictions` | Facts with overlapping tags but potential conflicts (returns candidates for human review) |

#### GET /graph/{code}/impact — Impact Analysis

**Response**: `ImpactAnalysisResponse`

**Behavior**:
1. Find all facts where `fact_refs.to_code = {code}` (directly affected)
2. Recursively traverse outward up to 3 hops (transitively affected)
3. For each affected fact, determine which agent roles would include it based on default query templates (see §7)
4. Return deduplicated lists

**SQL for recursive traversal**:
```sql
WITH RECURSIVE impact AS (
    -- Direct references to the changed fact
    SELECT from_code AS code, 1 AS depth
    FROM fact_refs
    WHERE to_code = :target_code

    UNION ALL

    -- Transitive references (up to 3 hops)
    SELECT fr.from_code, i.depth + 1
    FROM fact_refs fr
    JOIN impact i ON fr.to_code = i.code
    WHERE i.depth < 3
)
SELECT DISTINCT code, MIN(depth) as min_depth
FROM impact
GROUP BY code
ORDER BY min_depth;
```

### 5.4 Extraction (Optional in Phase 1)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/extract` | Send a document, get back candidate facts |

**Request**:
```json
{
    "content": "Full text of a document to decompose",
    "source_name": "Risk Assessment v2",
    "default_layer": "GUARDRAILS",
    "default_owner": "security-team"
}
```

**Response**:
```json
{
    "candidates": [
        {
            "suggested_code": "RISK-08",
            "layer": "GUARDRAILS",
            "type": "Risk Assessment Finding",
            "fact_text": "...",
            "tags": ["security", "..."],
            "confidence": "Provisional",
            "refs": []
        }
    ],
    "source_name": "Risk Assessment v2",
    "model_used": "claude-sonnet-4-20250514"
}
```

**Behavior**:
1. Send document content to Claude with a system prompt instructing it to decompose into atomic facts following the LatticeLens schema
2. Parse the structured response
3. Auto-assign `suggested_code` based on existing code sequences (e.g., if RISK-07 exists, suggest RISK-08)
4. Return candidates with `confidence = 'Provisional'` — these are NOT auto-inserted
5. The developer reviews and uses `POST /facts/bulk` to insert approved candidates

**LLM System Prompt for Extraction** (store in `src/latticelens/prompts/extract.txt`):

```
You are a knowledge decomposition agent for LatticeLens.

Your job is to decompose a document into atomic facts. Each fact must be:
- Self-contained: readable without external context
- Atomic: one decision, one finding, one rule per fact
- Tagged: minimum 2 semantic tags, lowercase, hyphenated

Respond ONLY with a JSON array of objects. Each object has these fields:
- layer: "WHY", "GUARDRAILS", or "HOW"
- type: The document type (e.g., "Architecture Decision Record", "Risk Assessment Finding")
- fact_text: The atomic fact as a complete sentence or short paragraph
- tags: Array of at least 2 lowercase hyphenated tags
- refs: Array of codes this fact relates to (if you can identify them from context)

Do not include any preamble or explanation. Only valid JSON.
```

---

## 6. Service Layer

### 6.1 Fact Service — Key Business Rules

These rules MUST be enforced in `fact_service.py` regardless of how the endpoint is called:

1. **Code immutability**: A fact's code can never change after creation.
2. **Version monotonicity**: Version always increments by exactly 1 on each update.
3. **History before update**: The current state MUST be written to `fact_history` before any update is applied. This is a single transaction.
4. **Ref integrity**: All codes in `refs` must exist in the `facts` table at the time of create/update.
5. **Superseded requires target**: If `status` is set to `Superseded`, `superseded_by` must be a valid existing code.
6. **No hard deletes**: `DELETE` endpoint sets status to `Deprecated`, never removes the row.
7. **Stale detection**: On read, if `review_by` is non-null and `< today`, set `is_stale = true` in the response. Do NOT change the database status automatically.
8. **Tag normalization**: Tags are always stored lowercase and sorted alphabetically.
9. **Auto-timestamping**: `updated_at` is set to `now()` on every update. `created_at` is never modified.
10. **Layer-code consistency**: The code prefix must match an allowed prefix for its layer (see design doc §5.3). Validate on create:

```python
LAYER_PREFIXES = {
    "WHY": ["ADR", "PRD", "ETH", "DES"],
    "GUARDRAILS": ["MC", "AUP", "RISK", "DG", "COMP"],
    "HOW": ["SP", "API", "RUN", "ML", "MON"],
}

def validate_code_layer(code: str, layer: str) -> bool:
    prefix = code.split("-")[0]
    return prefix in LAYER_PREFIXES.get(layer, [])
```

### 6.2 Graph Service — Traversal Logic

- **Impact analysis**: Use the recursive CTE from §5.3. Cap recursion at depth=3.
- **Orphan detection**: Facts where code appears in neither `fact_refs.from_code` nor `fact_refs.to_code`.
- **Contradiction candidates**: Find pairs of Active facts that share 2+ tags but are in different layers or have different owners. Return as candidates for human review — do NOT auto-flag as contradictions.

---

## 7. Default Agent Role Query Templates

Store these in `src/latticelens/config/agent_roles.yaml`. These are the default query templates used by the `/graph/{code}/impact` endpoint to determine affected roles, and will be used by the Context Assembly Engine in Phase 2.

```yaml
# agent_roles.yaml
roles:
  planning:
    description: "Product Strategist — scopes work, defines acceptance criteria"
    query:
      layers: ["WHY"]
      types: ["Architecture Decision Record", "Product Requirement"]
      status: ["Active"]
      extra:
        layer: "GUARDRAILS"
        types: ["Acceptable Use Policy Rule"]

  architecture:
    description: "Systems Architect — designs components, annotates risks"
    query:
      layers: ["WHY"]
      types: ["Architecture Decision Record", "Design Proposal Decision"]
      status: ["Active"]
      extra_layers:
        - layer: "GUARDRAILS"
          types: ["Model Card Entry", "Risk Assessment Finding", "Data Governance Rule"]
        - layer: "HOW"
          types: ["API Specification"]

  implementation:
    description: "Senior Developer — writes code, configures prompts"
    query:
      layers: ["GUARDRAILS"]
      types: ["Acceptable Use Policy Rule", "Data Governance Rule"]
      status: ["Active"]
      extra:
        layer: "HOW"
        types: ["System Prompt Rule", "API Specification", "MLOps Pipeline Rule"]

  qa:
    description: "Quality & Compliance Reviewer — validates against criteria"
    query:
      layers: ["WHY"]
      types: ["Product Requirement", "Ethical Review Finding"]
      status: ["Active"]
      extra_layers:
        - layer: "GUARDRAILS"
          types: ["Model Card Entry", "Acceptable Use Policy Rule", "Risk Assessment Finding", "Compliance Requirement"]
        - layer: "HOW"
          types: ["Monitoring Rule"]

  deploy:
    description: "DevOps / Release Engineer — deploys and monitors"
    query:
      layers: ["GUARDRAILS"]
      types: ["Risk Assessment Finding"]
      tags_any: ["deploy-time", "high-severity"]
      status: ["Active"]
      extra:
        layer: "HOW"
        types: ["Runbook Procedure", "MLOps Pipeline Rule", "Monitoring Rule"]
```

---

## 8. CLI Specification

The CLI uses Typer and provides a thin wrapper over the API.

```
latticelens health                          # Check service + fact counts
latticelens fact get ADR-03                 # Get a single fact
latticelens fact list                       # List all active facts
latticelens fact list --layer WHY           # Filter by layer
latticelens fact list --tags security       # Filter by tag
latticelens fact create                     # Interactive creation prompt
latticelens fact create --from-json f.json  # Create from JSON file
latticelens fact update ADR-03 --reason "Updated model choice"
latticelens fact deprecate ADR-03 --reason "No longer relevant"
latticelens fact history ADR-03             # Show version history
latticelens graph impact ADR-03             # Impact analysis
latticelens graph orphans                   # List orphaned facts
latticelens seed                            # Load example facts from seed/
latticelens extract doc.md                  # Extract facts from document (requires --api-key or env var)
```

**Output format**: Default is a Rich-formatted table for humans. Add `--json` flag to any command for raw JSON output (for piping to scripts).

**API base URL**: Defaults to `http://localhost:8000/api/v1`. Override with `--api-url` flag or `LATTICELENS_API_URL` env var.

---

## 9. Seed Data

Store in `seed/example_facts.json`. These are the 12 example facts from the design document. Use them for testing and demos.

```json
[
    {
        "code": "ADR-01",
        "layer": "WHY",
        "type": "Architecture Decision Record",
        "fact_text": "Adopted event-driven architecture using message queues over synchronous REST calls for inter-service communication. Decision driven by need for fault tolerance and decoupling — if the inference service goes down, requests queue rather than fail.",
        "tags": ["architecture", "event-driven", "fault-tolerance", "messaging", "decoupling"],
        "status": "Active",
        "confidence": "Confirmed",
        "owner": "architecture-team",
        "refs": ["DES-01", "RISK-03", "API-01"]
    },
    {
        "code": "ADR-03",
        "layer": "WHY",
        "type": "Architecture Decision Record",
        "fact_text": "Selected GPT-4o over Claude 3.5 Sonnet for primary inference due to 40% lower p95 latency on structured output tasks. Claude retained as fallback for complex reasoning tasks exceeding 4k output.",
        "tags": ["model-selection", "latency", "inference", "fallback-strategy", "cost-tradeoff"],
        "status": "Active",
        "confidence": "Confirmed",
        "owner": "architecture-team",
        "refs": ["PRD-01", "RISK-07", "MC-01"]
    },
    {
        "code": "PRD-01",
        "layer": "WHY",
        "type": "Product Requirement",
        "fact_text": "System must support 10,000 concurrent users with p95 response latency under 2 seconds for standard queries. Batch processing queries may take up to 30 seconds.",
        "tags": ["scaling", "latency", "throughput", "user-facing", "performance-requirement"],
        "status": "Active",
        "confidence": "Confirmed",
        "owner": "product-team",
        "refs": ["ADR-01", "MON-01", "RISK-05"]
    },
    {
        "code": "DES-01",
        "layer": "WHY",
        "type": "Design Proposal Decision",
        "fact_text": "Inference, retrieval, and orchestration run as independent services with API contracts between them. Monolith approach rejected due to scaling constraints.",
        "tags": ["architecture", "microservices", "decoupling", "api"],
        "status": "Active",
        "confidence": "Confirmed",
        "owner": "architecture-team",
        "refs": ["ADR-01", "API-01", "RUN-01"]
    },
    {
        "code": "MC-01",
        "layer": "GUARDRAILS",
        "type": "Model Card Entry",
        "fact_text": "GPT-4o achieves 94% accuracy on English structured output tasks but drops to 78% on non-English. Known weakness: ambiguous multi-step instructions.",
        "tags": ["model-selection", "accuracy", "multilingual", "limitations"],
        "status": "Active",
        "confidence": "Confirmed",
        "owner": "ml-team",
        "refs": ["ADR-03", "ETH-01", "RISK-02"]
    },
    {
        "code": "AUP-05",
        "layer": "GUARDRAILS",
        "type": "Acceptable Use Policy Rule",
        "fact_text": "Agent must not generate, store, or transmit personally identifiable information (PII) beyond what is strictly necessary for the current task. All PII must be purged from context within the same session.",
        "tags": ["privacy", "pii", "data-minimization", "user-facing", "compliance", "regulatory"],
        "status": "Active",
        "confidence": "Confirmed",
        "owner": "compliance-team",
        "refs": ["DG-01", "DG-03", "COMP-01", "COMP-04", "ETH-02"]
    },
    {
        "code": "RISK-07",
        "layer": "GUARDRAILS",
        "type": "Risk Assessment Finding",
        "fact_text": "Prompt injection via user-uploaded documents rated HIGH severity (likelihood: 4/5, impact: 5/5). Mitigation: input sanitization + document content sandboxing + output validation against original intent. Residual risk: MEDIUM after mitigation.",
        "tags": ["security", "prompt-injection", "high-severity", "user-input", "mitigation"],
        "status": "Active",
        "confidence": "Confirmed",
        "owner": "security-team",
        "refs": ["ADR-03", "AUP-02", "SP-03", "MON-04"]
    },
    {
        "code": "DG-01",
        "layer": "GUARDRAILS",
        "type": "Data Governance Rule",
        "fact_text": "All PII must be encrypted at rest (AES-256) and in transit (TLS 1.3). No PII in logs, including debug mode. Audit trail required for all PII access events.",
        "tags": ["privacy", "pii", "encryption", "logging", "compliance"],
        "status": "Active",
        "confidence": "Confirmed",
        "owner": "security-team",
        "refs": ["AUP-05", "COMP-04", "SP-03"]
    },
    {
        "code": "SP-01",
        "layer": "HOW",
        "type": "System Prompt Rule",
        "fact_text": "Agent must identify itself as an AI assistant in its first response to any new user session. Format: 'I'm [Agent Name], an AI assistant that [capability description]. How can I help?'",
        "tags": ["transparency", "user-facing", "system-prompt", "identity", "trust"],
        "status": "Active",
        "confidence": "Confirmed",
        "owner": "product-team",
        "refs": ["ETH-01", "AUP-01", "COMP-01"]
    },
    {
        "code": "API-01",
        "layer": "HOW",
        "type": "API Specification",
        "fact_text": "/chat endpoint accepts max 4096 input tokens, returns max 8192 output tokens. Rate limit: 100 requests per minute per API key. Auth: Bearer token via Authorization header.",
        "tags": ["api", "rate-limiting", "authentication", "user-facing", "scaling"],
        "status": "Active",
        "confidence": "Confirmed",
        "owner": "backend-team",
        "refs": ["ADR-01", "DES-01", "MON-01"]
    },
    {
        "code": "MON-01",
        "layer": "HOW",
        "type": "Monitoring Rule",
        "fact_text": "Alert on-call when p95 latency exceeds 2 seconds for 5 consecutive minutes. Escalate to engineering lead if not acknowledged within 15 minutes. Auto-scale inference pods if latency breach persists for 10 minutes.",
        "tags": ["monitoring", "latency", "alerting", "auto-scaling", "incident-response", "ops-team"],
        "status": "Active",
        "confidence": "Confirmed",
        "owner": "ops-team",
        "refs": ["PRD-01", "RUN-01", "RISK-05"]
    },
    {
        "code": "RUN-01",
        "layer": "HOW",
        "type": "Runbook Procedure",
        "fact_text": "Production rollback requires approval from on-call engineering lead. Rollback procedure: revert container image tag, verify health checks, confirm latency recovery within 5 minutes. If not recovered, escalate to incident commander.",
        "tags": ["deploy-time", "rollback", "incident-response", "ops-team", "approval"],
        "status": "Active",
        "confidence": "Confirmed",
        "owner": "ops-team",
        "refs": ["MON-01", "DES-01"]
    }
]
```

**Note on refs**: Some refs in the seed data reference codes that are not in the seed set (e.g., `RISK-03`, `RISK-05`, `ETH-01`, `AUP-01`, `AUP-02`, `SP-03`, `MON-04`, `DG-03`, `COMP-01`, `COMP-04`, `ETH-02`). The seed loader must either:
- (a) Create placeholder facts for missing refs first (preferred — use status=Draft), or
- (b) Skip invalid refs and log a warning

Option (a) is preferred because it demonstrates the knowledge graph's gap detection: after seeding, `GET /graph/orphans` should surface the placeholder facts as needing content.

---

## 10. Test Specifications

All tests use pytest with pytest-asyncio. Use a separate test database (not the dev database).

### 10.1 conftest.py Fixtures

- `db_session`: Creates a fresh test database, runs migrations, yields a session, drops tables after
- `client`: HTTPX async client pointed at the test FastAPI app
- `seeded_db`: Loads the 12 seed facts and returns the session

### 10.2 Required Test Cases

#### test_facts_crud.py
| Test | Asserts |
|------|---------|
| `test_create_fact` | Returns 201, code matches, version=1, created_at is set |
| `test_create_duplicate_code` | Returns 409 Conflict |
| `test_create_invalid_code_format` | Returns 422 (code must match `{PREFIX}-{SEQ}`) |
| `test_create_code_layer_mismatch` | Returns 422 (ADR prefix not allowed for GUARDRAILS layer) |
| `test_create_insufficient_tags` | Returns 422 (minimum 2 tags) |
| `test_create_with_refs` | Refs created in fact_refs table |
| `test_create_with_invalid_refs` | Returns 400 (ref code doesn't exist) |
| `test_get_fact` | Returns 200, all fields present |
| `test_get_nonexistent` | Returns 404 |
| `test_update_fact` | Version increments, updated_at changes, history row created |
| `test_update_preserves_unchanged` | Fields not in update body remain the same |
| `test_deprecate_fact` | Status becomes Deprecated, history row created |

#### test_facts_query.py
| Test | Asserts |
|------|---------|
| `test_query_by_layer` | Only facts from specified layer returned |
| `test_query_by_status` | Default returns only Active facts |
| `test_query_by_tags_any` | Facts matching any of the provided tags |
| `test_query_by_tags_all` | Only facts matching all provided tags |
| `test_query_text_search` | Full-text search returns relevant facts |
| `test_query_pagination` | page/page_size work, total/total_pages correct |
| `test_query_ordering` | Confirmed before Provisional, then by updated_at DESC |
| `test_stale_detection` | Facts past review_by have is_stale=true |

#### test_versioning.py
| Test | Asserts |
|------|---------|
| `test_history_created_on_update` | History row matches pre-update state |
| `test_version_increments` | 3 updates → version=4, 3 history rows |
| `test_history_endpoint` | GET /facts/{code}/history returns all versions ordered DESC |
| `test_superseded_requires_target` | Setting status=Superseded without superseded_by returns 400 |

#### test_graph.py
| Test | Asserts |
|------|---------|
| `test_impact_direct` | Changing ADR-03 surfaces RISK-07, MC-01 |
| `test_impact_transitive` | 2-hop traversal finds indirectly affected facts |
| `test_impact_max_depth` | Traversal stops at depth 3 |
| `test_orphan_detection` | Facts with no refs appear in orphan list |
| `test_refs_bidirectional` | GET /graph/{code}/refs returns both incoming and outgoing |

#### test_cli.py
| Test | Asserts |
|------|---------|
| `test_health_command` | Outputs status and counts |
| `test_fact_get` | Outputs formatted fact |
| `test_fact_list_json` | --json flag returns valid JSON array |
| `test_seed_command` | Loads seed data, subsequent list returns facts |

---

## 11. Acceptance Criteria — Phase 1 Done When:

These are the concrete checks that determine if Phase 1 is complete.

- [ ] `docker-compose up` starts Postgres + API service with no errors
- [ ] Alembic migration creates all tables, enums, indexes
- [ ] All 12 seed facts load via `latticelens seed` or `POST /facts/bulk`
- [ ] `GET /facts/ADR-03` returns the complete fact with all fields
- [ ] `PATCH /facts/ADR-03` increments version and creates history row
- [ ] `POST /facts/query` with `layer=["WHY"]` returns only WHY facts
- [ ] `POST /facts/query` with `tags_any=["security"]` returns RISK-07, DG-01
- [ ] `POST /facts/query` with `text_search="prompt injection"` returns RISK-07
- [ ] `GET /graph/ADR-03/impact` returns affected facts and affected roles
- [ ] `GET /graph/orphans` returns placeholder facts from seeding
- [ ] `GET /facts/ADR-03/history` returns version history in DESC order
- [ ] `DELETE /facts/ADR-03` sets status=Deprecated (row still exists)
- [ ] All tests in §10.2 pass
- [ ] `latticelens health` CLI command returns service status
- [ ] `latticelens fact get ADR-03 --json` returns valid JSON
- [ ] LICENSE file contains MIT License with correct copyright
- [ ] CONTRIBUTING.md states contributions are under MIT

---

## 12. What Phase 1 Does NOT Include

These are explicitly out of scope. Do not build these yet:

- **Context Assembly Engine** (Phase 2) — token budgeting, prompt building, `/context/{role}` endpoint
- **Audit Trail** (Phase 3) — trace events, snapshots, event bus
- **Safety Valves** (Phase 3+) — retry limits, escalation protocol
- **Dashboard** (Phase 4) — React frontend
- **Reconciliation Engine** (Phase 4) — code-to-fact verification
- **Authentication / authorization** — Phase 1 API is unauthenticated (local dev only)
- **Rate limiting** — not needed for local dev
- **WebSocket / real-time updates** — Phase 4

---

*This brief is the HOW document for building LatticeLens Phase 1. The design doc is the WHY and GUARDRAILS. Together they are the first two facts in LatticeLens's own knowledge base.*
