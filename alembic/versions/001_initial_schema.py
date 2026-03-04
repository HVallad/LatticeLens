"""Initial schema - facts, fact_refs, fact_history

Revision ID: 001_initial
Revises:
Create Date: 2026-03-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

fact_layer = postgresql.ENUM("WHY", "GUARDRAILS", "HOW", name="fact_layer", create_type=False)
fact_status = postgresql.ENUM("Draft", "Under Review", "Active", "Deprecated", "Superseded", name="fact_status", create_type=False)
fact_confidence = postgresql.ENUM("Confirmed", "Provisional", "Assumed", name="fact_confidence", create_type=False)


def upgrade() -> None:
    # Create enums
    op.execute("CREATE TYPE fact_layer AS ENUM ('WHY', 'GUARDRAILS', 'HOW')")
    op.execute("CREATE TYPE fact_status AS ENUM ('Draft', 'Under Review', 'Active', 'Deprecated', 'Superseded')")
    op.execute("CREATE TYPE fact_confidence AS ENUM ('Confirmed', 'Provisional', 'Assumed')")

    # Facts table
    op.create_table(
        "facts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("layer", fact_layer, nullable=False),
        sa.Column("type", sa.String(100), nullable=False),
        sa.Column("fact_text", sa.Text, nullable=False),
        sa.Column("tags", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", fact_status, nullable=False, server_default=sa.text("'Draft'")),
        sa.Column("confidence", fact_confidence, nullable=False, server_default=sa.text("'Confirmed'")),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("superseded_by", sa.String(50), sa.ForeignKey("facts.code", ondelete="SET NULL"), nullable=True),
        sa.Column("owner", sa.String(100), nullable=False),
        sa.Column("review_by", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_index("idx_facts_layer_status", "facts", ["layer", "status"])
    op.create_index("idx_facts_tags", "facts", ["tags"], postgresql_using="gin")
    op.create_index("idx_facts_text_search", "facts", [sa.text("to_tsvector('english', fact_text)")], postgresql_using="gin")
    op.create_index("idx_facts_status", "facts", ["status"])

    # Fact references table
    op.create_table(
        "fact_refs",
        sa.Column("from_code", sa.String(50), sa.ForeignKey("facts.code", ondelete="CASCADE"), primary_key=True),
        sa.Column("to_code", sa.String(50), sa.ForeignKey("facts.code", ondelete="CASCADE"), primary_key=True),
        sa.CheckConstraint("from_code != to_code", name="no_self_ref"),
    )

    op.create_index("idx_fact_refs_to", "fact_refs", ["to_code"])

    # Fact history table
    op.create_table(
        "fact_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("layer", fact_layer, nullable=False),
        sa.Column("type", sa.String(100), nullable=False),
        sa.Column("fact_text", sa.Text, nullable=False),
        sa.Column("tags", postgresql.JSONB, nullable=False),
        sa.Column("status", fact_status, nullable=False),
        sa.Column("confidence", fact_confidence, nullable=False),
        sa.Column("owner", sa.String(100), nullable=False),
        sa.Column("superseded_by", sa.String(50), nullable=True),
        sa.Column("review_by", sa.Date, nullable=True),
        sa.Column("changed_by", sa.String(100), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("change_reason", sa.Text, nullable=False),
        sa.UniqueConstraint("code", "version", name="uq_fact_history_code_version"),
    )

    op.create_index("idx_fact_history_code", "fact_history", ["code", sa.text("version DESC")])


def downgrade() -> None:
    op.drop_table("fact_history")
    op.drop_table("fact_refs")
    op.drop_table("facts")
    op.execute("DROP TYPE IF EXISTS fact_confidence")
    op.execute("DROP TYPE IF EXISTS fact_status")
    op.execute("DROP TYPE IF EXISTS fact_layer")
