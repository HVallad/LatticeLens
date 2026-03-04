# LatticeLens

A knowledge governance layer for AI agent systems. LatticeLens gives your agents a structured, versioned, queryable **constitution** — the facts, rules, and guardrails that define how they should behave.

---

## The Problem

AI agents accumulate institutional knowledge fast — architecture decisions, safety policies, prompt rules, API contracts, runbook procedures. In practice, this knowledge ends up scattered across design docs, PDFs, Slack threads, and config files. Nobody has a clear picture of what the agent is *supposed* to do, and when a policy changes, there's no reliable way to know what else breaks.

This causes real problems:

- **Fragmentation** — Facts live in a dozen places. No single source of truth.
- **Invisible dependencies** — Changing a guardrail might invalidate a system prompt, but you won't find out until something goes wrong.
- **No audit trail** — Who changed the acceptable use policy? When? Why?
- **Onboarding friction** — New team members have to reverse-engineer constraints from scattered documents.
- **Contradictions** — Conflicting rules accumulate silently as the system grows.

## What LatticeLens Does

LatticeLens replaces that mess with a single, structured fact index backed by PostgreSQL. Every piece of agent knowledge becomes an **atomic, versioned fact** that can be queried, linked, tracked, and analyzed.

### Three-Layer Knowledge Model

Facts are organized into three semantic layers:

| Layer | Purpose | Example Prefixes |
|-------|---------|-----------------|
| **WHY** | Decisions and rationale | `ADR-` `PRD-` `ETH-` `DES-` |
| **GUARDRAILS** | Governance and control | `MC-` `AUP-` `RISK-` `DG-` `COMP-` |
| **HOW** | Operational implementation | `SP-` `API-` `RUN-` `ML-` `MON-` |

Each fact is self-contained: a unique code, natural-language text, semantic tags, a confidence level, a lifecycle status, an owner, and an immutable version history.

### Knowledge Graph

Facts reference each other through directed edges. `RISK-07` depends on `ADR-03`. `SP-01` implements `AUP-05`. These relationships enable **impact analysis** — ask the system *"if I change this fact, what else is affected?"* and get an answer in milliseconds, not hours of document archaeology.

### LLM-Powered Extraction

Feed a document (risk assessment, design doc, policy) to the extraction endpoint. LatticeLens uses Claude to decompose it into candidate facts, auto-assigns codes, and returns them for human review before insertion.

---

## Who This Is For

- **Teams building AI agent systems** that need structured governance over agent behavior
- **Platform engineers** managing the rules, prompts, and policies that guide LLM-based agents
- **Compliance and safety teams** that need audit trails and impact analysis for policy changes
- **Anyone** tired of grepping through docs to figure out what constraints apply to their agent

---

## Quick Start

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- (Optional) Python 3.13+ if running the CLI locally

### 1. Start the stack

```bash
git clone https://github.com/HVallad/LatticeLens.git
cd LatticeLens
docker compose up -d
```

This starts:
- **PostgreSQL 16** on port `5432`
- **FastAPI service** on port `8000`

### 2. Run the database migration

```bash
docker compose exec api alembic upgrade head
```

### 3. Verify it's running

```bash
curl http://localhost:8000/api/v1/health
```

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "facts_total": 0,
  "facts_active": 0,
  "facts_stale": 0
}
```

### 4. Seed example data

The repo includes 12 example facts covering all three layers. Load them via the CLI or API:

```bash
# Via CLI (install locally first: pip install -e .)
lattice seed

# Or via API
curl -X POST http://localhost:8000/api/v1/facts/bulk \
  -H "Content-Type: application/json" \
  -d @seed/example_facts.json
```

---

## API Reference

Base URL: `http://localhost:8000/api/v1`

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Service status, version, and fact counts |

### Facts CRUD

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/facts` | Create a new fact |
| `GET` | `/facts/{code}` | Get a fact by code (e.g., `ADR-03`) |
| `PATCH` | `/facts/{code}` | Update a fact (creates history entry, increments version) |
| `DELETE` | `/facts/{code}` | Deprecate a fact (soft delete, never removes data) |
| `GET` | `/facts/{code}/history` | Get full version history |
| `POST` | `/facts/query` | Query with filters (layer, status, tags, text search, pagination) |
| `POST` | `/facts/bulk` | Bulk create multiple facts |

### Knowledge Graph

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/graph/{code}/impact` | Impact analysis — what's affected if this fact changes (up to 3 hops) |
| `GET` | `/graph/{code}/refs` | Get incoming and outgoing references for a fact |
| `GET` | `/graph/orphans` | Find facts with no connections |
| `GET` | `/graph/contradictions` | Find candidate contradictions (overlapping tags, different layers) |

### Extraction

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/extract` | LLM-powered fact extraction from documents (requires Anthropic API key) |

### Example: Create a Fact

```bash
curl -X POST http://localhost:8000/api/v1/facts \
  -H "Content-Type: application/json" \
  -d '{
    "code": "AUP-05",
    "layer": "GUARDRAILS",
    "type": "Acceptable Use Policy Rule",
    "fact_text": "The agent must never generate medical diagnoses or treatment plans.",
    "tags": ["safety", "healthcare", "content-policy"],
    "status": "Active",
    "confidence": "Confirmed",
    "owner": "safety-team",
    "refs": []
  }'
```

### Example: Impact Analysis

```bash
curl http://localhost:8000/api/v1/graph/ADR-03/impact
```

```json
{
  "source_code": "ADR-03",
  "directly_affected": ["RISK-07", "MC-01"],
  "transitively_affected": ["DG-01", "SP-03"],
  "affected_agent_roles": ["architecture", "implementation"]
}
```

### Example: Query Facts

```bash
curl -X POST http://localhost:8000/api/v1/facts/query \
  -H "Content-Type: application/json" \
  -d '{
    "layer": ["GUARDRAILS"],
    "status": ["Active"],
    "tags_any": ["security", "privacy"]
  }'
```

---

## CLI

Install locally for CLI access:

```bash
pip install -e .
```

The CLI command is `lattice`. It talks to the API service.

```bash
# Check service health
lattice health

# Get a specific fact
lattice fact get ADR-03

# List facts with filters
lattice fact list --layer WHY
lattice fact list --tags security,privacy
lattice fact list --status Active --owner platform-team

# Create a fact (interactive prompts)
lattice fact create

# Create from a JSON file
lattice fact create --from-json my-facts.json

# Update a fact
lattice fact update ADR-03 --text "Updated text" --reason "Revised after review"

# Deprecate a fact
lattice fact deprecate ADR-03

# View version history
lattice fact history ADR-03

# Impact analysis
lattice graph impact ADR-03

# Find orphaned facts
lattice graph orphans

# Seed the database
lattice seed

# Extract facts from a document
lattice extract document.md --source "Risk Assessment v2" --owner security-team

# Any command supports --json for raw output
lattice fact list --json
```

---

## Configuration

All settings use the `LATTICELENS_` prefix and can be set via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LATTICELENS_DATABASE_URL` | `postgresql+asyncpg://latticelens:latticelens_dev@localhost:5432/latticelens` | Database connection string |
| `LATTICELENS_API_HOST` | `0.0.0.0` | API bind address |
| `LATTICELENS_API_PORT` | `8000` | API port |
| `LATTICELENS_DEFAULT_PAGE_SIZE` | `50` | Default query page size |
| `LATTICELENS_MAX_PAGE_SIZE` | `200` | Maximum query page size |
| `LATTICELENS_ANTHROPIC_API_KEY` | *(empty)* | Required for `/extract` endpoint |
| `LATTICELENS_EXTRACTION_MODEL` | `claude-sonnet-4-20250514` | Model used for fact extraction |

The CLI uses `LATTICELENS_API_URL` (default: `http://localhost:8000/api/v1`) or the `--api-url` flag.

---

## Project Structure

```
LatticeLens/
  src/latticelens/
    main.py              # FastAPI app
    settings.py          # Configuration (Pydantic BaseSettings)
    db.py                # Async SQLAlchemy engine + session
    models.py            # ORM models (Fact, FactRef, FactHistory)
    schemas.py           # Request/response schemas
    routers/             # API endpoint handlers
    services/            # Business logic (CRUD, graph traversal, extraction)
    cli/                 # Typer CLI
    config/              # agent_roles.yaml
    prompts/             # LLM extraction prompt
  alembic/               # Database migrations
  seed/                  # Example seed data (12 facts)
  tests/                 # 36 tests (pytest + pytest-asyncio)
  docker-compose.yml     # Postgres + API
  Dockerfile
  pyproject.toml
```

---

## Running Tests

Tests require a Postgres instance on port `5433`:

```bash
docker run -d --name latticelens-test-db \
  -e POSTGRES_USER=latticelens \
  -e POSTGRES_PASSWORD=latticelens_dev \
  -e POSTGRES_DB=latticelens_test \
  -p 5433:5432 \
  postgres:16-alpine

python -m pytest tests/ -x -q
```

---

## Tech Stack

- **FastAPI** + **Uvicorn** — async API server
- **SQLAlchemy 2.0** + **asyncpg** — async ORM with PostgreSQL
- **Alembic** — database migrations
- **Pydantic v2** — data validation
- **Typer** + **Rich** — CLI with interactive prompts and formatted output
- **Anthropic Claude API** — LLM-powered fact extraction
- **PostgreSQL 16** — JSONB tags, GIN indexes, full-text search, recursive CTEs

---

## License

[MIT](LICENSE)
