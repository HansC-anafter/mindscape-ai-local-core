"""add_webhook_url_to_privacy_audit_logs

Revision ID: 20260106230000
Revises: 20251227181638
Create Date: 2026-01-06 23:00:00.000000

添加 webhook_url 字段到 yogacoach_privacy_audit_logs 表
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260106230000'
down_revision = '20260105000000'  # Based on latest migration
branch_labels = None
depends_on = None


def upgrade():
    """添加 webhook_url 字段到 yogacoach_privacy_audit_logs 表"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if 'yogacoach_privacy_audit_logs' in existing_tables:
        # Check if column already exists
        columns = [col['name'] for col in inspector.get_columns('yogacoach_privacy_audit_logs')]
        if 'webhook_url' not in columns:
            op.add_column(
                'yogacoach_privacy_audit_logs',
                sa.Column('webhook_url', sa.Text(), nullable=True)
            )


def downgrade():
    """移除 webhook_url 字段"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if 'yogacoach_privacy_audit_logs' in existing_tables:
        columns = [col['name'] for col in inspector.get_columns('yogacoach_privacy_audit_logs')]
        if 'webhook_url' in columns:
            op.drop_column('yogacoach_privacy_audit_logs', 'webhook_url')

