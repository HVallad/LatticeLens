from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


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

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v):
        if v is None:
            return v
        for tag in v:
            if not tag.replace("-", "").replace("_", "").isalnum():
                raise ValueError(f"Tag must be alphanumeric with hyphens: {tag}")
            if tag != tag.lower():
                raise ValueError(f"Tag must be lowercase: {tag}")
        return v


class FactQuery(BaseModel):
    """Query the fact index with filters."""

    layer: list[str] | None = None
    type: list[str] | None = None
    status: list[str] | None = Field(default=["Active"])
    confidence: list[str] | None = None
    tags_any: list[str] | None = None
    tags_all: list[str] | None = None
    owner: str | None = None
    text_search: str | None = None
    include_stale: bool = False
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
    is_stale: bool = False

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
    directly_affected: list[str]
    transitively_affected: list[str]
    affected_agent_roles: list[str]


class RefsResponse(BaseModel):
    code: str
    outgoing: list[str]
    incoming: list[str]


class ContradictionCandidate(BaseModel):
    code_a: str
    code_b: str
    shared_tags: list[str]
    reason: str


class HealthResponse(BaseModel):
    status: str
    version: str
    facts_total: int
    facts_active: int
    facts_stale: int


class ExtractionRequest(BaseModel):
    content: str = Field(..., min_length=10)
    source_name: str = Field(..., min_length=1)
    default_layer: str = Field(default="GUARDRAILS", pattern=r"^(WHY|GUARDRAILS|HOW)$")
    default_owner: str = Field(default="unknown")


class ExtractionCandidate(BaseModel):
    suggested_code: str
    layer: str
    type: str
    fact_text: str
    tags: list[str]
    confidence: str = "Provisional"
    refs: list[str] = Field(default_factory=list)


class ExtractionResponse(BaseModel):
    candidates: list[ExtractionCandidate]
    source_name: str
    model_used: str
