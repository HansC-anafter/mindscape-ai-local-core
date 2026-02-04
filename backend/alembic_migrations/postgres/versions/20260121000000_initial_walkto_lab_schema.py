"""
Initial Walkto Lab schema.

Creates core tables:
- walkto_lens_cards
- walkto_sessions
- walkto_personal_value_systems
- walkto_personal_datasets
- walkto_subscriptions
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260121000000"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "walkto_lens_cards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("ip_name", sa.String(length=255), nullable=False),
        sa.Column("perspective_model", sa.JSON(), nullable=False),
        sa.Column("judgment_criteria", sa.JSON(), nullable=False),
        sa.Column("rejection_rules", sa.JSON(), nullable=False),
        sa.Column("extra_steps", sa.JSON(), nullable=True),
        sa.Column("version", sa.String(length=50), nullable=False, server_default=sa.text("'1.0.0'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_walkto_lens_workspace", "walkto_lens_cards", ["workspace_id"], unique=False)

    op.create_table(
        "walkto_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("lens_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("route_map", sa.JSON(), nullable=False),
        sa.Column("lens_notes", sa.JSON(), nullable=False),
        sa.Column("shared_artifacts", sa.JSON(), nullable=True),
        sa.Column("personal_writeback", sa.JSON(), nullable=True),
        sa.Column("duration_minutes", sa.String(length=10), nullable=True, server_default=sa.text("'0'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["lens_id"], ["walkto_lens_cards.id"], name="fk_walkto_sessions_lens_id"),
    )
    op.create_index("idx_walkto_session_workspace", "walkto_sessions", ["workspace_id"], unique=False)
    op.create_index("idx_walkto_session_user", "walkto_sessions", ["user_id"], unique=False)
    op.create_index("idx_walkto_session_lens", "walkto_sessions", ["lens_id"], unique=False)

    op.create_table(
        "walkto_personal_value_systems",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("state_map", sa.JSON(), nullable=True),
        sa.Column("preferences", sa.JSON(), nullable=True),
        sa.Column("taboos", sa.JSON(), nullable=True),
        sa.Column("trust_evidence", sa.JSON(), nullable=True),
        sa.Column("rules", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_walkto_pvs_workspace", "walkto_personal_value_systems", ["workspace_id"], unique=False)
    op.create_index("idx_walkto_pvs_user", "walkto_personal_value_systems", ["user_id"], unique=False)
    op.create_index(
        "idx_walkto_pvs_workspace_user",
        "walkto_personal_value_systems",
        ["workspace_id", "user_id"],
        unique=True,
    )

    op.create_table(
        "walkto_personal_datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state_map", sa.JSON(), nullable=False),
        sa.Column("preferences", sa.JSON(), nullable=False),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.Column("route_templates", sa.JSON(), nullable=True),
        sa.Column("next_steps", sa.JSON(), nullable=True),
        sa.Column("version", sa.String(length=50), nullable=False, server_default=sa.text("'1.0.0'")),
        sa.Column("format", sa.String(length=50), nullable=False, server_default=sa.text("'json'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_walkto_dataset_workspace", "walkto_personal_datasets", ["workspace_id"], unique=False)
    op.create_index("idx_walkto_dataset_user", "walkto_personal_datasets", ["user_id"], unique=False)
    op.create_index("idx_walkto_dataset_track", "walkto_personal_datasets", ["track_id"], unique=False)
    op.create_index(
        "idx_walkto_dataset_workspace_user_track",
        "walkto_personal_datasets",
        ["workspace_id", "user_id", "track_id"],
        unique=True,
    )

    op.create_table(
        "walkto_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("tier", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'active'")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payment_info", sa.JSON(), nullable=True),
        sa.Column("track_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_walkto_subscription_workspace", "walkto_subscriptions", ["workspace_id"], unique=False)
    op.create_index("idx_walkto_subscription_user", "walkto_subscriptions", ["user_id"], unique=False)
    op.create_index("idx_walkto_subscription_status", "walkto_subscriptions", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_walkto_subscription_status", table_name="walkto_subscriptions")
    op.drop_index("idx_walkto_subscription_user", table_name="walkto_subscriptions")
    op.drop_index("idx_walkto_subscription_workspace", table_name="walkto_subscriptions")
    op.drop_table("walkto_subscriptions")

    op.drop_index("idx_walkto_dataset_workspace_user_track", table_name="walkto_personal_datasets")
    op.drop_index("idx_walkto_dataset_track", table_name="walkto_personal_datasets")
    op.drop_index("idx_walkto_dataset_user", table_name="walkto_personal_datasets")
    op.drop_index("idx_walkto_dataset_workspace", table_name="walkto_personal_datasets")
    op.drop_table("walkto_personal_datasets")

    op.drop_index("idx_walkto_pvs_workspace_user", table_name="walkto_personal_value_systems")
    op.drop_index("idx_walkto_pvs_user", table_name="walkto_personal_value_systems")
    op.drop_index("idx_walkto_pvs_workspace", table_name="walkto_personal_value_systems")
    op.drop_table("walkto_personal_value_systems")

    op.drop_index("idx_walkto_session_lens", table_name="walkto_sessions")
    op.drop_index("idx_walkto_session_user", table_name="walkto_sessions")
    op.drop_index("idx_walkto_session_workspace", table_name="walkto_sessions")
    op.drop_table("walkto_sessions")

    op.drop_index("idx_walkto_lens_workspace", table_name="walkto_lens_cards")
    op.drop_table("walkto_lens_cards")

