"""Bind projection generations to an exact authorization revision.

Revision ID: 20260727035000
Revises: 20260727030000
"""

from alembic import op


revision = "20260727035000"
down_revision = "20260727030000"
branch_labels = None
depends_on = None


_OLD_COLUMNS = [
    "knowledge_resource_id",
    "source_revision",
    "content_hash",
    "projector_revision",
    "embedding_profile_revision",
]
_NEW_COLUMNS = [
    *_OLD_COLUMNS,
    "authz_revision",
    "visibility_partition_hash",
]


def upgrade() -> None:
    op.drop_constraint(
        "uq_knowledge_projection_idempotency",
        "knowledge_resource_projections",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_knowledge_projection_idempotency",
        "knowledge_resource_projections",
        _NEW_COLUMNS,
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_knowledge_projection_idempotency",
        "knowledge_resource_projections",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_knowledge_projection_idempotency",
        "knowledge_resource_projections",
        _OLD_COLUMNS,
    )
