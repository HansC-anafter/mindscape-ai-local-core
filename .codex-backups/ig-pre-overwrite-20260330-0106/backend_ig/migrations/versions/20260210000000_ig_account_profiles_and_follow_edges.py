"""Create ig_account_profiles and ig_follow_edges tables

Revision ID: 20260210000000
Revises: 20260124170000
Create Date: 2026-02-10 00:00:00.000000

Creates:
- ig_account_profiles: Computed profile tags (type, tier, bio keywords)
- ig_follow_edges: Follow relationship edges for network analysis
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260210000000"
down_revision = "20260124170000"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # Create ig_account_profiles table
    if "ig_account_profiles" not in existing_tables:
        op.create_table(
            "ig_account_profiles",
            sa.Column("id", sa.String(36), primary_key=True, nullable=False),
            sa.Column("workspace_id", sa.String(255), nullable=False),
            sa.Column("seed", sa.String(255), nullable=False),
            sa.Column("account_handle", sa.String(255), nullable=False),
            # Classification
            sa.Column(
                "account_type", sa.String(32), nullable=True
            ),  # kol|brand|personal|media|unknown
            sa.Column(
                "influence_tier", sa.String(16), nullable=True
            ),  # nano|micro|mid|macro|mega
            # Computed fields
            sa.Column("engagement_potential", sa.Float(), nullable=True),
            sa.Column("follower_following_ratio", sa.Float(), nullable=True),
            sa.Column("activity_score", sa.Float(), nullable=True),
            # Bio extraction
            sa.Column("bio_keywords_json", sa.Text(), nullable=True),
            sa.Column("bio_detected_locale", sa.String(8), nullable=True),
            sa.Column("bio_has_contact", sa.Boolean(), nullable=True),
            sa.Column("bio_has_link", sa.Boolean(), nullable=True),
            # References
            sa.Column("source_snapshot_id", sa.String(36), nullable=True),
            sa.Column(
                "computed_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column(
                "schema_version",
                sa.String(32),
                server_default="ig.profile.v1",
                nullable=True,
            ),
        )
        # Unique constraint for upsert
        op.create_unique_constraint(
            "uq_ig_account_profiles_workspace_seed_handle",
            "ig_account_profiles",
            ["workspace_id", "seed", "account_handle"],
        )
        op.create_index(
            "ix_ig_account_profiles_workspace", "ig_account_profiles", ["workspace_id"]
        )
        op.create_index(
            "ix_ig_account_profiles_type", "ig_account_profiles", ["account_type"]
        )
        op.create_index(
            "ix_ig_account_profiles_tier", "ig_account_profiles", ["influence_tier"]
        )

    # Create ig_follow_edges table
    if "ig_follow_edges" not in existing_tables:
        op.create_table(
            "ig_follow_edges",
            sa.Column("id", sa.String(36), primary_key=True, nullable=False),
            sa.Column("workspace_id", sa.String(255), nullable=False),
            sa.Column(
                "source_handle", sa.String(255), nullable=False
            ),  # seed (target_username)
            sa.Column(
                "target_handle", sa.String(255), nullable=False
            ),  # following account
            sa.Column("discovered_via_seed", sa.String(255), nullable=False),
            sa.Column(
                "discovered_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("execution_id", sa.String(64), nullable=True),
        )
        # Unique constraint for upsert
        op.create_unique_constraint(
            "uq_ig_follow_edges_workspace_source_target",
            "ig_follow_edges",
            ["workspace_id", "source_handle", "target_handle"],
        )
        op.create_index(
            "ix_ig_follow_edges_source", "ig_follow_edges", ["source_handle"]
        )
        op.create_index(
            "ix_ig_follow_edges_target", "ig_follow_edges", ["target_handle"]
        )
        op.create_index(
            "ix_ig_follow_edges_workspace", "ig_follow_edges", ["workspace_id"]
        )


def downgrade():
    # Drop ig_follow_edges
    op.drop_index("ix_ig_follow_edges_workspace", table_name="ig_follow_edges")
    op.drop_index("ix_ig_follow_edges_target", table_name="ig_follow_edges")
    op.drop_index("ix_ig_follow_edges_source", table_name="ig_follow_edges")
    op.drop_constraint(
        "uq_ig_follow_edges_workspace_source_target", "ig_follow_edges", type_="unique"
    )
    op.drop_table("ig_follow_edges")

    # Drop ig_account_profiles
    op.drop_index("ix_ig_account_profiles_tier", table_name="ig_account_profiles")
    op.drop_index("ix_ig_account_profiles_type", table_name="ig_account_profiles")
    op.drop_index("ix_ig_account_profiles_workspace", table_name="ig_account_profiles")
    op.drop_constraint(
        "uq_ig_account_profiles_workspace_seed_handle",
        "ig_account_profiles",
        type_="unique",
    )
    op.drop_table("ig_account_profiles")
