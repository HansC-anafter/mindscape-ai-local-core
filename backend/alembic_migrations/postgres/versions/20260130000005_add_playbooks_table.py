"""add_playbooks_table

Revision ID: 20260130000005
Revises: 20260130000004
Create Date: 2026-01-30 00:00:05.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260130000005"
down_revision = "20260130000004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "playbooks",
        sa.Column("playbook_code", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=True),
        sa.Column("locale", sa.String(), nullable=False, server_default="zh-TW"),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("entry_agent_type", sa.String(), nullable=True),
        sa.Column("onboarding_task", sa.String(), nullable=True),
        sa.Column("icon", sa.String(), nullable=True),
        sa.Column("required_tools", sa.JSON(), nullable=True),
        sa.Column("scope", sa.JSON(), nullable=True),
        sa.Column("owner", sa.JSON(), nullable=True),
        sa.Column("sop_content", sa.Text(), nullable=True),
        sa.Column("user_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("playbook_code", "locale"),
    )
    op.create_index("idx_playbooks_code", "playbooks", ["playbook_code"])
    op.create_index("idx_playbooks_locale", "playbooks", ["locale"])
    op.create_index("idx_playbooks_name", "playbooks", ["name"])


def downgrade():
    op.drop_index("idx_playbooks_name", table_name="playbooks")
    op.drop_index("idx_playbooks_locale", table_name="playbooks")
    op.drop_index("idx_playbooks_code", table_name="playbooks")
    op.drop_table("playbooks")
