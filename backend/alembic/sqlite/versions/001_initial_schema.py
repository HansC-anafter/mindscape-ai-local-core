"""Initial schema baseline

Revision ID: 001_initial
Revises:
Create Date: 2025-12-03

This migration establishes the baseline for all existing tables in my_agent_console.db.
Since tables are already created via direct SQL DDL, this migration serves as a reference
point for future schema changes.

Tables included:
- profiles
- intents
- intent_tags
- agent_executions
- habit_observations, habit_candidates, habit_audit_logs
- workspaces
- mind_events
- intent_logs
- entities, tags, entity_tags
- tasks, task_feedback, task_preference
- timeline_items
- artifacts
- tool_calls
- stage_results
- background_routines
- tool_connections (legacy)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Baseline migration - tables already exist.

    This is a no-op migration that serves as a reference point.
    Future migrations will modify the schema from this baseline.
    """
    pass


def downgrade() -> None:
    """
    Baseline migration - no downgrade needed.

    This is a no-op migration.
    """
    pass

