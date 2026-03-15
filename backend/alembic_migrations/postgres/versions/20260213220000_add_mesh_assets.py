"""
Migration: Add mesh_assets table

Revision ID: 20260213220000
Revises: 20260213210000
Create Date: 2026-02-13 22:00:00.000000

Adds yogacoach_mesh_assets table for storing 3D reconstruction results.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers
revision = "20260213220000"
down_revision = "20260213210000"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "yogacoach_mesh_assets",
        sa.Column("mesh_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False, index=True),
        # Source reference
        sa.Column("segment_id", UUID(as_uuid=True), nullable=True),
        sa.Column("action_id", UUID(as_uuid=True), nullable=True),
        sa.Column("source_image_key", sa.String(512), nullable=True),
        # Provider
        sa.Column("provider", sa.String(64), nullable=False, server_default="sam3d"),
        # Storage
        sa.Column("mesh_storage_key", sa.String(512), nullable=True),
        sa.Column("texture_storage_key", sa.String(512), nullable=True),
        sa.Column("output_format", sa.String(16), server_default="glb"),
        # Quality metrics
        sa.Column("vertex_count", sa.Integer, nullable=True),
        sa.Column("file_size_bytes", sa.Integer, nullable=True),
        sa.Column("reconstruction_time_sec", sa.Float, nullable=True),
        # Metadata
        sa.Column("metadata", JSONB, nullable=True),
        # Timestamps
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.func.now(), nullable=False
        ),
    )

    # Indexes
    op.create_index("idx_mesh_segment", "yogacoach_mesh_assets", ["segment_id"])
    op.create_index("idx_mesh_tenant", "yogacoach_mesh_assets", ["tenant_id"])


def downgrade():
    op.drop_index("idx_mesh_tenant", table_name="yogacoach_mesh_assets")
    op.drop_index("idx_mesh_segment", table_name="yogacoach_mesh_assets")
    op.drop_table("yogacoach_mesh_assets")
