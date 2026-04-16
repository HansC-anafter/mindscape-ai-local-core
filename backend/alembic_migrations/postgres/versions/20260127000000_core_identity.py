"""Core Identity (Workspaces, Profiles, Projects)

Revision ID: 20260127000000
Revises: 20260125000000
Create Date: 2026-01-27 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260127000000"
down_revision = "20260103000000"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())

    # --- Profiles ---
    if not inspector.has_table("profiles"):
        op.create_table(
            "profiles",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("roles", sa.Text(), nullable=True),  # JSON list
            sa.Column("domains", sa.Text(), nullable=True),  # JSON list
            sa.Column("preferences", sa.Text(), nullable=True),  # JSON dict
            sa.Column("onboarding_state", sa.Text(), nullable=True),  # JSON dict
            sa.Column("self_description", sa.Text(), nullable=True),
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
                nullable=False,
            ),
            sa.Column("version", sa.Integer(), server_default="1", nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    # --- Workspaces ---
    if not inspector.has_table("workspaces"):
        op.create_table(
            "workspaces",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("owner_user_id", sa.String(length=36), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("primary_project_id", sa.String(length=36), nullable=True),
            sa.Column("default_playbook_id", sa.String(length=255), nullable=True),
            sa.Column("default_locale", sa.String(length=10), nullable=True),
            sa.Column(
                "workspace_type",
                sa.String(length=64),
                server_default="personal",
                nullable=True,
            ),
            sa.Column("mode", sa.String(length=64), nullable=True),
            sa.Column(
                "execution_mode", sa.String(length=64), server_default="qa", nullable=True
            ),
            sa.Column("expected_artifacts", sa.Text(), nullable=True),
            sa.Column(
                "execution_priority",
                sa.String(length=32),
                server_default="medium",
                nullable=True,
            ),
            sa.Column(
                "project_assignment_mode",
                sa.String(length=64),
                server_default="auto_silent",
                nullable=True,
            ),
            sa.Column("data_sources", sa.Text(), nullable=True),
            sa.Column("playbook_auto_execution_config", sa.Text(), nullable=True),
            sa.Column("suggestion_history", sa.Text(), nullable=True),
            sa.Column("storage_base_path", sa.String(length=512), nullable=True),
            sa.Column("artifacts_dir", sa.String(length=255), nullable=True),
            sa.Column("uploads_dir", sa.String(length=255), nullable=True),
            sa.Column("storage_config", sa.Text(), nullable=True),
            sa.Column("playbook_storage_config", sa.Text(), nullable=True),
            sa.Column("cloud_remote_tools_config", sa.Text(), nullable=True),
            sa.Column("workspace_blueprint", sa.Text(), nullable=True),
            sa.Column(
                "launch_status",
                sa.String(length=32),
                server_default="pending",
                nullable=True,
            ),
            sa.Column("starter_kit_type", sa.String(length=64), nullable=True),
            sa.Column("metadata", sa.Text(), nullable=True),
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
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["owner_user_id"],
                ["profiles.id"],
            ),
        )
    op.execute("CREATE INDEX IF NOT EXISTS ix_workspaces_owner ON workspaces (owner_user_id)")

    # --- Projects ---
    if not inspector.has_table("projects"):
        op.create_table(
            "projects",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("type", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("home_workspace_id", sa.String(length=36), nullable=False),
            sa.Column("flow_id", sa.String(length=255), nullable=False),
            sa.Column("state", sa.String(length=32), server_default="open", nullable=False),
            sa.Column("initiator_user_id", sa.String(length=36), nullable=False),
            sa.Column("human_owner_user_id", sa.String(length=36), nullable=True),
            sa.Column("ai_pm_id", sa.String(length=36), nullable=True),
            sa.Column("metadata", sa.Text(), nullable=True),
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
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["home_workspace_id"],
                ["workspaces.id"],
            ),
        )
    op.execute("CREATE INDEX IF NOT EXISTS ix_projects_home_workspace ON projects (home_workspace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_projects_state ON projects (state)")

    # --- Project Phases ---
    if not inspector.has_table("project_phases"):
        op.create_table(
            "project_phases",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("project_id", sa.String(length=36), nullable=False),
            sa.Column("created_by_message_id", sa.String(length=255), nullable=False),
            sa.Column(
                "kind", sa.String(length=64), server_default="unknown", nullable=True
            ),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("tags", sa.Text(), nullable=True),
            sa.Column("metadata", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        )
    op.execute("CREATE INDEX IF NOT EXISTS ix_project_phases_project ON project_phases (project_id)")

    # --- Backfill Workspace Project Index ---
    # Workspaces reference a primary project, so we add index now that projects table exists?
    # Actually primary_project_id is in workspaces. Not a FK constraint in sqlite schema,
    # but we can enforce it loosely or strictly. Keeping loose for now to match sqlite.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_workspaces_primary_project ON workspaces (primary_project_id)"
    )


def downgrade():
    op.drop_table("project_phases")
    op.drop_table("projects")
    op.drop_table("workspaces")
    op.drop_table("profiles")
