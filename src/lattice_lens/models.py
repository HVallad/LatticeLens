"""Pydantic fact models and enums."""

from __future__ import annotations

import enum
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from lattice_lens.config import LAYER_PREFIXES


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


class Fact(BaseModel):
    """Core fact model. One YAML file per fact."""

    code: str = Field(..., pattern=r"^[A-Z]+-\d+$")
    layer: FactLayer
    type: str = Field(..., min_length=1, max_length=100)
    fact: str = Field(..., min_length=10, description="The atomic fact text")
    tags: list[str] = Field(..., min_length=2)
    status: FactStatus = FactStatus.DRAFT
    confidence: FactConfidence = FactConfidence.CONFIRMED
    version: int = Field(default=1, ge=1)
    refs: list[str] = Field(default_factory=list)
    superseded_by: str | None = None
    owner: str = Field(..., min_length=1, max_length=100)
    review_by: date | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    projects: list[str] = Field(default_factory=list)

    @field_validator("projects")
    @classmethod
    def normalize_projects(cls, v: list[str]) -> list[str]:
        normalized = []
        for entry in v:
            entry = entry.strip()
            if not entry:
                continue
            if entry.startswith("group:"):
                # Validate group name portion
                name = entry[len("group:"):]
                if not name or not name.replace("-", "").replace("_", "").isalnum():
                    raise ValueError(
                        f"Invalid group reference: {entry}"
                    )
            else:
                # Literal project name: lowercase, alphanumeric + hyphens/underscores
                if not entry.replace("-", "").replace("_", "").isalnum():
                    raise ValueError(
                        f"Project name must be alphanumeric with hyphens/underscores: {entry}"
                    )
                entry = entry.lower()
            normalized.append(entry)
        return sorted(set(normalized))

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, v: list[str]) -> list[str]:
        normalized = []
        for tag in v:
            tag = tag.lower().strip()
            if not tag.replace("-", "").replace("_", "").isalnum():
                raise ValueError(f"Tag must be alphanumeric with hyphens/underscores: {tag}")
            normalized.append(tag)
        return sorted(set(normalized))

    @model_validator(mode="after")
    def validate_code_layer_prefix(self) -> Fact:
        prefix = self.code.split("-")[0]
        allowed = LAYER_PREFIXES.get(self.layer.value, [])
        if prefix not in allowed:
            raise ValueError(
                f"Code prefix '{prefix}' not allowed for layer {self.layer.value}. "
                f"Allowed: {allowed}"
            )
        return self

    @model_validator(mode="after")
    def validate_superseded(self) -> Fact:
        if self.status == FactStatus.SUPERSEDED and not self.superseded_by:
            raise ValueError("superseded_by is required when status is Superseded")
        return self
