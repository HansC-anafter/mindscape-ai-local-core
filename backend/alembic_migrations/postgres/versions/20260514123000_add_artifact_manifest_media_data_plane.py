"""Add artifact manifest and media data plane tables.

Revision ID: 20260514123000
Revises: 20260514120000
Create Date: 2026-05-14 12:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260514123000"
down_revision = "20260514120000"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "artifact_manifest",
        sa.Column("artifact_id", sa.Text(), primary_key=True),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("task_id", sa.Text(), nullable=True),
        sa.Column("execution_id", sa.Text(), nullable=True),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("storage_ref", sa.Text(), nullable=True),
        sa.Column("result_json_path", sa.Text(), nullable=True),
        sa.Column("checksum_sha256", sa.Text(), nullable=False),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column(
            "payload_schema",
            sa.Text(),
            nullable=False,
            server_default="task_result",
        ),
        sa.Column(
            "schema_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("bytes >= 0", name="ck_artifact_manifest_bytes_nonnegative"),
        sa.UniqueConstraint(
            "workspace_id",
            "execution_id",
            "object_key",
            name="uq_artifact_manifest_workspace_execution_object",
        ),
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_artifact_manifest_workspace_created
        ON artifact_manifest (workspace_id, created_at DESC, artifact_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_artifact_manifest_execution
        ON artifact_manifest (execution_id)
        WHERE execution_id IS NOT NULL
        """
    )

    op.create_table(
        "media_assets",
        sa.Column("asset_id", sa.Text(), primary_key=True),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "content_hash",
            name="uq_media_assets_workspace_hash",
        ),
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_media_assets_workspace_created
        ON media_assets (workspace_id, created_at DESC, asset_id)
        """
    )

    op.create_table(
        "media_objects",
        sa.Column("object_id", sa.Text(), primary_key=True),
        sa.Column("asset_id", sa.Text(), nullable=False),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("object_role", sa.Text(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.Text(), nullable=False),
        sa.Column("storage_class", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.Text(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("bytes >= 0", name="ck_media_objects_bytes_nonnegative"),
        sa.UniqueConstraint("object_key", name="uq_media_objects_object_key"),
        sa.UniqueConstraint(
            "asset_id",
            "object_role",
            name="uq_media_objects_asset_role",
        ),
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_media_objects_asset_role
        ON media_objects (asset_id, object_role)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_media_objects_workspace_created
        ON media_objects (workspace_id, created_at DESC, object_id)
        """
    )

    op.create_table(
        "asset_gallery_projection",
        sa.Column("asset_id", sa.Text(), primary_key=True),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("original_object_key", sa.Text(), nullable=True),
        sa.Column("thumbnail_object_key", sa.Text(), nullable=True),
        sa.Column("preview_object_key", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_gallery_workspace_created
        ON asset_gallery_projection (workspace_id, created_at DESC, asset_id)
        """
    )

    op.create_table(
        "artifact_search_index",
        sa.Column("artifact_id", sa.Text(), primary_key=True),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("task_id", sa.Text(), nullable=True),
        sa.Column("execution_id", sa.Text(), nullable=True),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column(
            "schema_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_artifact_search_workspace_updated
        ON artifact_search_index (workspace_id, updated_at DESC, artifact_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_artifact_search_execution
        ON artifact_search_index (execution_id)
        WHERE execution_id IS NOT NULL
        """
    )


def downgrade():
    op.drop_table("artifact_search_index")
    op.drop_table("asset_gallery_projection")
    op.drop_table("media_objects")
    op.drop_table("media_assets")
    op.drop_table("artifact_manifest")
