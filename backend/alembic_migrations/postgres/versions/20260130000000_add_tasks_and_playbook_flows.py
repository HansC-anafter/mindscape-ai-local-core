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


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _index_exists(
    inspector: sa.Inspector,
    table_name: str,
    index_name: str,
) -> bool:
    try:
        indexes = inspector.get_indexes(table_name)
    except Exception:
        return False
    return any(index.get("name") == index_name for index in indexes)


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "tasks"):
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
        inspector = sa.inspect(bind)

    for index_name, columns in [
        ("idx_tasks_workspace", ["workspace_id"]),
        ("idx_tasks_message", ["message_id"]),
        ("idx_tasks_status", ["status"]),
        ("idx_tasks_workspace_status", ["workspace_id", "status"]),
        ("idx_tasks_created_at", ["created_at"]),
        ("idx_tasks_execution_id", ["execution_id"]),
        ("idx_tasks_project", ["project_id"]),
    ]:
        if not _index_exists(inspector, "tasks", index_name):
            op.create_index(index_name, "tasks", columns)
            inspector = sa.inspect(bind)

    if not _table_exists(inspector, "playbook_flows"):
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
        inspector = sa.inspect(bind)

    for index_name, columns in [
        ("idx_playbook_flows_name", ["name"]),
        ("idx_playbook_flows_created_at", ["created_at"]),
    ]:
        if not _index_exists(inspector, "playbook_flows", index_name):
            op.create_index(index_name, "playbook_flows", columns)
            inspector = sa.inspect(bind)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, "playbook_flows"):
        for index_name in [
            "idx_playbook_flows_created_at",
            "idx_playbook_flows_name",
        ]:
            if _index_exists(inspector, "playbook_flows", index_name):
                op.drop_index(index_name, table_name="playbook_flows")
                inspector = sa.inspect(bind)
        op.drop_table("playbook_flows")
        inspector = sa.inspect(bind)

    if _table_exists(inspector, "tasks"):
        for index_name in [
            "idx_tasks_project",
            "idx_tasks_execution_id",
            "idx_tasks_created_at",
            "idx_tasks_workspace_status",
            "idx_tasks_status",
            "idx_tasks_message",
            "idx_tasks_workspace",
        ]:
            if _index_exists(inspector, "tasks", index_name):
                op.drop_index(index_name, table_name="tasks")
                inspector = sa.inspect(bind)
        op.drop_table("tasks")
