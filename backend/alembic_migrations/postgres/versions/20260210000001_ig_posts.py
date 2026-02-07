"""Create ig_posts table

Revision ID: 20260210000001
Revises: 20260210000000
Create Date: 2026-02-10 00:00:01.000000

Creates ig_posts table for storing captured post metadata and content analysis.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260210000001"
down_revision = "20260210000000"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "ig_posts" not in existing_tables:
        op.create_table(
            "ig_posts",
            sa.Column("id", sa.String(36), primary_key=True, nullable=False),
            sa.Column("workspace_id", sa.String(255), nullable=False),
            sa.Column("account_handle", sa.String(255), nullable=False),
            sa.Column("post_shortcode", sa.String(64), nullable=False),
            # Post metadata
            sa.Column(
                "post_type", sa.String(16), nullable=True
            ),  # image|video|carousel|reel
            sa.Column("post_url", sa.String(512), nullable=True),
            sa.Column("thumbnail_url", sa.String(512), nullable=True),
            # Engagement
            sa.Column("like_count", sa.Integer(), nullable=True),
            sa.Column("comment_count", sa.Integer(), nullable=True),
            # Content
            sa.Column("caption", sa.Text(), nullable=True),
            sa.Column("hashtags_json", sa.Text(), nullable=True),
            sa.Column("mentions_json", sa.Text(), nullable=True),
            # LLM-computed fields (filled by playbook step)
            sa.Column("caption_topic", sa.String(64), nullable=True),
            sa.Column("caption_sentiment", sa.String(16), nullable=True),
            sa.Column("caption_locale", sa.String(8), nullable=True),
            # Timestamps
            sa.Column("posted_at", sa.DateTime(), nullable=True),
            sa.Column(
                "captured_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("execution_id", sa.String(64), nullable=True),
            sa.Column("trace_id", sa.String(64), nullable=True),
        )
        # Unique constraint for upsert
        op.create_unique_constraint(
            "uq_ig_posts_workspace_handle_shortcode",
            "ig_posts",
            ["workspace_id", "account_handle", "post_shortcode"],
        )
        op.create_index("ix_ig_posts_workspace", "ig_posts", ["workspace_id"])
        op.create_index("ix_ig_posts_handle", "ig_posts", ["account_handle"])
        op.create_index("ix_ig_posts_topic", "ig_posts", ["caption_topic"])
        op.create_index("ix_ig_posts_posted_at", "ig_posts", ["posted_at"])


def downgrade():
    op.drop_index("ix_ig_posts_posted_at", table_name="ig_posts")
    op.drop_index("ix_ig_posts_topic", table_name="ig_posts")
    op.drop_index("ix_ig_posts_handle", table_name="ig_posts")
    op.drop_index("ix_ig_posts_workspace", table_name="ig_posts")
    op.drop_constraint(
        "uq_ig_posts_workspace_handle_shortcode", "ig_posts", type_="unique"
    )
    op.drop_table("ig_posts")
