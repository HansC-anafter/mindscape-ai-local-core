"""Persist one immutable internal admission receipt per projection task/source.

Revision ID: 20260727100000
Revises: 20260725140000
Create Date: 2026-07-27 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260727100000"
down_revision = "20260725140000"
branch_labels = ("knowledge_projection_task_admission",)
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_projection_task_admissions",
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("intake_id", sa.String(length=64), nullable=False),
        sa.Column("receipt_hash", sa.String(length=64), nullable=False),
        sa.Column("trigger_mode", sa.String(length=32), nullable=False),
        sa.Column("source_ordinal", sa.Integer(), nullable=False),
        sa.Column("source_instance_id", sa.String(length=128), nullable=False),
        sa.Column("source_revision", sa.String(length=256), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["intake_id"],
            ["knowledge_source_intakes.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "task_id",
            "intake_id",
            name="pk_knowledge_projection_task_admissions",
        ),
        sa.UniqueConstraint(
            "task_id",
            "source_ordinal",
            name="uq_knowledge_projection_task_admission_ordinal",
        ),
        sa.CheckConstraint(
            "trigger_mode IN ('source_revision', 'explicit_reindex', "
            "'revoke')",
            name="chk_knowledge_projection_task_admission_trigger",
        ),
        sa.CheckConstraint(
            "source_ordinal >= 0 AND source_ordinal < 256",
            name="chk_knowledge_projection_task_admission_ordinal",
        ),
    )
    op.create_index(
        "idx_knowledge_projection_task_admissions_intake_created",
        "knowledge_projection_task_admissions",
        ["intake_id", "created_at", "task_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_knowledge_projection_task_admissions_intake_created",
        table_name="knowledge_projection_task_admissions",
    )
    op.drop_table("knowledge_projection_task_admissions")
