import enum
import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
    layer = Column(Enum(FactLayer, name="fact_layer", create_constraint=True, values_callable=lambda e: [x.value for x in e]), nullable=False)
    type = Column(String(100), nullable=False)
    fact_text = Column(Text, nullable=False)
    tags = Column(JSONB, nullable=False, default=list)
    status = Column(
        Enum(FactStatus, name="fact_status", create_constraint=True, values_callable=lambda e: [x.value for x in e]), nullable=False, default=FactStatus.DRAFT
    )
    confidence = Column(
        Enum(FactConfidence, name="fact_confidence", create_constraint=True, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=FactConfidence.CONFIRMED,
    )
    version = Column(Integer, nullable=False, default=1)
    superseded_by = Column(String(50), ForeignKey("facts.code", ondelete="SET NULL", use_alter=True, name="fk_facts_superseded_by"), nullable=True)
    owner = Column(String(100), nullable=False)
    review_by = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    refs_outgoing = relationship(
        "FactRef", foreign_keys="FactRef.from_code", back_populates="source", cascade="all, delete-orphan"
    )
    refs_incoming = relationship(
        "FactRef", foreign_keys="FactRef.to_code", back_populates="target", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_facts_layer_status", "layer", "status"),
        Index("idx_facts_tags", "tags", postgresql_using="gin"),
        Index("idx_facts_text_search", text("to_tsvector('english', fact_text)"), postgresql_using="gin"),
        Index("idx_facts_status", "status"),
    )


class FactRef(Base):
    __tablename__ = "fact_refs"

    from_code = Column(String(50), ForeignKey("facts.code", ondelete="CASCADE"), primary_key=True)
    to_code = Column(String(50), ForeignKey("facts.code", ondelete="CASCADE"), primary_key=True)

    source = relationship("Fact", foreign_keys=[from_code], back_populates="refs_outgoing")
    target = relationship("Fact", foreign_keys=[to_code], back_populates="refs_incoming")

    __table_args__ = (
        CheckConstraint("from_code != to_code", name="no_self_ref"),
        Index("idx_fact_refs_to", "to_code"),
    )


class FactHistory(Base):
    __tablename__ = "fact_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(50), nullable=False)
    version = Column(Integer, nullable=False)
    layer = Column(Enum(FactLayer, name="fact_layer", create_constraint=True, values_callable=lambda e: [x.value for x in e]), nullable=False)
    type = Column(String(100), nullable=False)
    fact_text = Column(Text, nullable=False)
    tags = Column(JSONB, nullable=False)
    status = Column(Enum(FactStatus, name="fact_status", create_constraint=True, values_callable=lambda e: [x.value for x in e]), nullable=False)
    confidence = Column(Enum(FactConfidence, name="fact_confidence", create_constraint=True, values_callable=lambda e: [x.value for x in e]), nullable=False)
    owner = Column(String(100), nullable=False)
    superseded_by = Column(String(50), nullable=True)
    review_by = Column(Date, nullable=True)
    changed_by = Column(String(100), nullable=False)
    changed_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    change_reason = Column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("code", "version", name="uq_fact_history_code_version"),
        Index("idx_fact_history_code", "code", text("version DESC")),
    )
