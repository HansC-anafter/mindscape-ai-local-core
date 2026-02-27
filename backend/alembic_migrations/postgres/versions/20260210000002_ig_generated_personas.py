"""Create ig_generated_personas table

Revision ID: 20260210000002
Revises: 20260210000001
Create Date: 2026-02-10 00:00:02.000000

Creates ig_generated_personas table for AI-generated user personas.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260210000002"
down_revision = "20260210000001"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "ig_generated_personas" not in existing_tables:
        op.create_table(
            "ig_generated_personas",
            sa.Column("id", sa.String(36), primary_key=True, nullable=False),
            sa.Column("workspace_id", sa.String(255), nullable=False),
            sa.Column("account_handle", sa.String(255), nullable=False),
            # Persona summary
            sa.Column("persona_summary", sa.Text(), nullable=True),
            sa.Column("persona_locale", sa.String(8), nullable=True),
            # Structured traits
            sa.Column("key_traits_json", sa.Text(), nullable=True),
            sa.Column("content_themes_json", sa.Text(), nullable=True),
            sa.Column("demographics_json", sa.Text(), nullable=True),
            # Brand fit
            sa.Column("brand_affinity_scores_json", sa.Text(), nullable=True),
            sa.Column("collaboration_potential", sa.Float(), nullable=True),
            sa.Column("recommended_approach", sa.Text(), nullable=True),
            # Metadata
            sa.Column(
                "generated_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("model_used", sa.String(64), nullable=True),
            sa.Column("input_data_version", sa.String(32), nullable=True),
        )
        # Unique constraint for upsert
        op.create_unique_constraint(
            "uq_ig_generated_personas_workspace_handle",
            "ig_generated_personas",
            ["workspace_id", "account_handle"],
        )
        op.create_index(
            "ix_ig_personas_workspace", "ig_generated_personas", ["workspace_id"]
        )
        op.create_index(
            "ix_ig_personas_handle", "ig_generated_personas", ["account_handle"]
        )


def downgrade():
    op.drop_index("ix_ig_personas_handle", table_name="ig_generated_personas")
    op.drop_index("ix_ig_personas_workspace", table_name="ig_generated_personas")
    op.drop_constraint(
        "uq_ig_generated_personas_workspace_handle",
        "ig_generated_personas",
        type_="unique",
    )
    op.drop_table("ig_generated_personas")
