"""Add MindLens and Artifacts tables

Revision ID: 20260125000000
Revises: 20251227000000
Create Date: 2026-01-25 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260125000000"
down_revision: Union[str, None] = "20251227000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Mind Lens Tables ---
    op.create_table(
        "mind_lens_schemas",
        sa.Column("schema_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column(
            "dimensions", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("version", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("schema_id"),
    )
    op.create_index(
        "idx_mind_lens_schemas_role", "mind_lens_schemas", ["role"], unique=False
    )

    op.create_table(
        "lens_specs",
        sa.Column("lens_id", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column(
            "applies_to", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("inject", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "params_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "transformers", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("lens_id"),
    )
    op.create_index("idx_lens_specs_category", "lens_specs", ["category"], unique=False)

    op.create_table(
        "mind_lens_instances",
        sa.Column("mind_lens_id", sa.String(), nullable=False),
        sa.Column("schema_id", sa.String(), nullable=False),
        sa.Column("owner_user_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("version", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("mind_lens_id"),
    )
    op.create_index(
        "idx_mind_lens_instances_owner",
        "mind_lens_instances",
        ["owner_user_id"],
        unique=False,
    )
    op.create_index(
        "idx_mind_lens_instances_role", "mind_lens_instances", ["role"], unique=False
    )
    op.create_index(
        "idx_mind_lens_instances_schema",
        "mind_lens_instances",
        ["schema_id"],
        unique=False,
    )

    # --- Artifacts Table ---
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("intent_id", sa.String(), nullable=True),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("execution_id", sa.String(), nullable=True),
        sa.Column("playbook_code", sa.String(), nullable=False),
        sa.Column("artifact_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("summary", sa.String(), nullable=True),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("storage_ref", sa.String(), nullable=True),
        sa.Column("sync_state", sa.String(), nullable=True),
        sa.Column("primary_action_type", sa.String(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("source_execution_id", sa.String(), nullable=True),
        sa.Column("source_step_id", sa.String(), nullable=True),
        sa.Column("thread_id", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_artifacts_created_at", "artifacts", ["created_at"], unique=False
    )
    op.create_index(
        "idx_artifacts_execution", "artifacts", ["source_execution_id"], unique=False
    )
    op.create_index("idx_artifacts_intent", "artifacts", ["intent_id"], unique=False)
    op.create_index(
        "idx_artifacts_playbook", "artifacts", ["playbook_code"], unique=False
    )
    op.create_index("idx_artifacts_step", "artifacts", ["source_step_id"], unique=False)
    op.create_index("idx_artifacts_task", "artifacts", ["task_id"], unique=False)
    op.create_index(
        "idx_artifacts_thread",
        "artifacts",
        ["workspace_id", "thread_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_artifacts_workspace", "artifacts", ["workspace_id"], unique=False
    )
    op.create_index(
        "idx_artifacts_workspace_created_at",
        "artifacts",
        ["workspace_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_artifacts_workspace_intent",
        "artifacts",
        ["workspace_id", "intent_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("artifacts")
    op.drop_table("mind_lens_instances")
    op.drop_table("lens_specs")
    op.drop_table("mind_lens_schemas")
