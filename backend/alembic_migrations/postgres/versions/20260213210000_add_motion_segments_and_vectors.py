"""Add motion segments and action vectors tables

Revision ID: 20260213210000
Revises: 20260114152034
Create Date: 2026-02-13 21:00:00.000000

Adds tables for motion segmentation and vector embeddings:
- yogacoach_motion_segments: Detected motion segments with timing
- yogacoach_action_vectors: Text and pose embeddings for similarity search
- pgvector extension + HNSW/IVFFLAT index based on version
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import warnings

# revision identifiers, used by Alembic.
revision = "20260213210000"
down_revision = "20260114152034"
branch_labels = None
depends_on = None


def upgrade():
    """Create motion segments and action vectors tables with pgvector indexes."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # Ensure pgvector extension
    bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))

    # Check pgvector version for HNSW support (>= 0.5.0)
    use_hnsw = False
    result = bind.execute(
        sa.text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    ).fetchone()
    if result and result[0]:
        try:
            parts = result[0].split(".")
            major = int(parts[0])
            minor = int(parts[1]) if len(parts) > 1 else 0
            use_hnsw = (major > 0) or (major == 0 and minor >= 5)
        except (ValueError, IndexError):
            warnings.warn(f"Cannot parse pgvector version '{result[0]}', using IVFFLAT")
    if use_hnsw:
        print(f"pgvector {result[0]} >= 0.5.0, using HNSW indexes")
    else:
        ver = result[0] if result else "unknown"
        print(f"pgvector {ver} < 0.5.0, using IVFFLAT fallback indexes")

    # --- yogacoach_motion_segments ---
    if "yogacoach_motion_segments" not in existing_tables:
        op.create_table(
            "yogacoach_motion_segments",
            sa.Column(
                "segment_id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
            ),
            sa.Column("tenant_id", sa.String(255), nullable=False),
            # Associations
            sa.Column(
                "library_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("yogacoach_teacher_libraries.library_id"),
                nullable=True,
            ),
            sa.Column(
                "action_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("yogacoach_teacher_library_actions.action_id"),
                nullable=True,
            ),
            sa.Column("video_id", postgresql.UUID(as_uuid=True), nullable=True),
            # Asana identification
            sa.Column("asana_id", sa.String(64), nullable=False),
            # Timing (absolute video time in seconds)
            sa.Column("start_time", sa.Float(), nullable=False),
            sa.Column("end_time", sa.Float(), nullable=False),
            sa.Column("fps", sa.Float(), server_default="15.0"),
            # Phase breakdown
            sa.Column("phases", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            # Keyframe information
            sa.Column(
                "keyframe_timestamps",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column("hold_peak_timestamp", sa.Float(), nullable=True),
            # Detection metadata
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("detection_method", sa.String(64), nullable=True),
            # Timestamps
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                onupdate=sa.text("CURRENT_TIMESTAMP"),
            ),
        )

        op.create_index(
            "idx_motion_seg_tenant", "yogacoach_motion_segments", ["tenant_id"]
        )
        op.create_index(
            "idx_motion_seg_library", "yogacoach_motion_segments", ["library_id"]
        )
        op.create_index(
            "idx_motion_seg_action", "yogacoach_motion_segments", ["action_id"]
        )
        op.create_index(
            "idx_motion_seg_asana", "yogacoach_motion_segments", ["asana_id"]
        )

    # --- yogacoach_action_vectors ---
    if "yogacoach_action_vectors" not in existing_tables:
        op.create_table(
            "yogacoach_action_vectors",
            sa.Column(
                "vector_id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
            ),
            sa.Column("tenant_id", sa.String(255), nullable=False),
            # Association
            sa.Column(
                "action_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("yogacoach_teacher_library_actions.action_id"),
                nullable=False,
            ),
            # Embedding type
            sa.Column("embedding_type", sa.String(32), nullable=False),
            # Text embedding (1536-dim)
            sa.Column("description_text", sa.String(), nullable=True),
            # Normalization params for pose reconstruction
            sa.Column(
                "normalization_params",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            # Timestamps
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
        )

        # Add vector columns via raw SQL (pgvector types)
        bind.execute(
            sa.text(
                "ALTER TABLE yogacoach_action_vectors ADD COLUMN embedding vector(1536)"
            )
        )
        bind.execute(
            sa.text(
                "ALTER TABLE yogacoach_action_vectors ADD COLUMN pose_vector vector(99)"
            )
        )

        # Unique constraint
        op.create_unique_constraint(
            "uq_action_vec_action_type",
            "yogacoach_action_vectors",
            ["action_id", "embedding_type"],
        )

        op.create_index(
            "idx_action_vec_tenant", "yogacoach_action_vectors", ["tenant_id"]
        )

        # Vector indexes: HNSW (preferred) or IVFFLAT (fallback)
        if use_hnsw:
            bind.execute(
                sa.text(
                    "CREATE INDEX idx_action_vec_pose_hnsw ON yogacoach_action_vectors "
                    "USING hnsw (pose_vector vector_l2_ops) WITH (m=16, ef_construction=64)"
                )
            )
            bind.execute(
                sa.text(
                    "CREATE INDEX idx_action_vec_text_hnsw ON yogacoach_action_vectors "
                    "USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)"
                )
            )
        else:
            bind.execute(
                sa.text(
                    "CREATE INDEX idx_action_vec_pose_ivf ON yogacoach_action_vectors "
                    "USING ivfflat (pose_vector vector_l2_ops) WITH (lists=100)"
                )
            )
            bind.execute(
                sa.text(
                    "CREATE INDEX idx_action_vec_text_ivf ON yogacoach_action_vectors "
                    "USING ivfflat (embedding vector_cosine_ops) WITH (lists=100)"
                )
            )


def downgrade():
    """Drop motion segments and action vectors tables."""
    # Drop vector indexes first
    for idx_name in [
        "idx_action_vec_pose_hnsw",
        "idx_action_vec_text_hnsw",
        "idx_action_vec_pose_ivf",
        "idx_action_vec_text_ivf",
    ]:
        try:
            op.drop_index(idx_name, table_name="yogacoach_action_vectors")
        except Exception:
            pass  # Index may not exist depending on pgvector version

    op.drop_index("idx_action_vec_tenant", table_name="yogacoach_action_vectors")
    op.drop_table("yogacoach_action_vectors")

    op.drop_index("idx_motion_seg_asana", table_name="yogacoach_motion_segments")
    op.drop_index("idx_motion_seg_action", table_name="yogacoach_motion_segments")
    op.drop_index("idx_motion_seg_library", table_name="yogacoach_motion_segments")
    op.drop_index("idx_motion_seg_tenant", table_name="yogacoach_motion_segments")
    op.drop_table("yogacoach_motion_segments")
