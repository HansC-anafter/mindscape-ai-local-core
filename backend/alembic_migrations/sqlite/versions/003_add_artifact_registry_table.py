"""add_artifact_registry_table

Revision ID: 003_add_artifact_registry
Revises: 002_add_projects
Create Date: 2025-12-07

Adds artifact_registry table for tracking artifacts within Projects.
Used for flow orchestration and artifact dependency management.

See: docs/core-architecture/implementation-roadmap-detailed.md
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003_add_artifact_registry'
down_revision: Union[str, None] = '002_add_projects'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create artifact_registry table

    Artifact Registry table structure:
    - id: Unique registry entry identifier
    - project_id: Foreign key to projects.id
    - artifact_id: Artifact identifier (reference to Artifact.id or path)
    - path: Artifact file path within project sandbox
    - type: Artifact type (markdown, json, html, etc.)
    - created_by: Playbook node ID that created this artifact
    - dependencies: JSON array of artifact_ids this depends on
    - created_at, updated_at: Timestamps
    """
    op.create_table(
        'artifact_registry',
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('project_id', sa.String(255), nullable=False),
        sa.Column('artifact_id', sa.String(255), nullable=False),
        sa.Column('path', sa.String(1000), nullable=False),
        sa.Column('type', sa.String(100), nullable=False),
        sa.Column('created_by', sa.String(255), nullable=False),
        sa.Column('dependencies', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='fk_artifact_registry_project')
    )

    # Create indexes
    op.create_index('idx_artifact_registry_project', 'artifact_registry', ['project_id'])
    op.create_index('idx_artifact_registry_artifact_id', 'artifact_registry', ['artifact_id'])
    op.create_index('idx_artifact_registry_created_by', 'artifact_registry', ['created_by'])


def downgrade() -> None:
    """
    Drop artifact_registry table
    """
    op.drop_index('idx_artifact_registry_created_by', table_name='artifact_registry')
    op.drop_index('idx_artifact_registry_artifact_id', table_name='artifact_registry')
    op.drop_index('idx_artifact_registry_project', table_name='artifact_registry')
    op.drop_table('artifact_registry')

