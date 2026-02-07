"""add_tasks_and_playbook_flows

Revision ID: 20260130000000
Revises: 20260129000000
Create Date: 2026-01-30 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260130000000"
down_revision = "20260129000000"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("message_id", sa.String(), nullable=False),
        sa.Column("execution_id", sa.String(), nullable=True),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("pack_id", sa.String(), nullable=False),
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("execution_context", sa.JSON(), nullable=True),
        sa.Column("storyline_tags", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("notification_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("displayed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_tasks_workspace", "tasks", ["workspace_id"])
    op.create_index("idx_tasks_message", "tasks", ["message_id"])
    op.create_index("idx_tasks_status", "tasks", ["status"])
    op.create_index("idx_tasks_workspace_status", "tasks", ["workspace_id", "status"])
    op.create_index("idx_tasks_created_at", "tasks", ["created_at"])
    op.create_index("idx_tasks_execution_id", "tasks", ["execution_id"])
    op.create_index("idx_tasks_project", "tasks", ["project_id"])

    op.create_table(
        "playbook_flows",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("flow_definition", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_playbook_flows_name", "playbook_flows", ["name"])
    op.create_index(
        "idx_playbook_flows_created_at", "playbook_flows", ["created_at"]
    )


def downgrade():
    op.drop_index("idx_playbook_flows_created_at", table_name="playbook_flows")
    op.drop_index("idx_playbook_flows_name", table_name="playbook_flows")
    op.drop_table("playbook_flows")

    op.drop_index("idx_tasks_project", table_name="tasks")
    op.drop_index("idx_tasks_execution_id", table_name="tasks")
    op.drop_index("idx_tasks_created_at", table_name="tasks")
    op.drop_index("idx_tasks_workspace_status", table_name="tasks")
    op.drop_index("idx_tasks_status", table_name="tasks")
    op.drop_index("idx_tasks_message", table_name="tasks")
    op.drop_index("idx_tasks_workspace", table_name="tasks")
    op.drop_table("tasks")
