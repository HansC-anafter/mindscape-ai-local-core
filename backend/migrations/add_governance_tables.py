"""
Migration: Add governance tables for Cloud environment

This migration adds:
1. governance_decisions table - stores governance decision history
2. cost_usage table - stores cost tracking data

Revision ID: add_governance_tables
Revises: add_workspace_type_and_storyline_tags
Create Date: 2025-12-19

Note: These tables are Cloud-only. Local-Core does not need them.
"""

import sqlite3
import os
from typing import Optional


def upgrade_sqlite(db_path: str):
    """
    Create governance tables in SQLite database (for Local-Core testing)

    Args:
        db_path: Path to SQLite database file
    """
    if not db_path:
        return

    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # Create governance_decisions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS governance_decisions (
                decision_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                execution_id TEXT,
                timestamp TEXT NOT NULL,
                layer TEXT NOT NULL CHECK(layer IN ('cost', 'node', 'policy', 'preflight')),
                approved INTEGER NOT NULL DEFAULT 1,
                reason TEXT,
                playbook_code TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indexes for governance_decisions
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_governance_decisions_workspace_timestamp
            ON governance_decisions(workspace_id, timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_governance_decisions_execution
            ON governance_decisions(execution_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_governance_decisions_layer_approved
            ON governance_decisions(layer, approved)
        """)

        # Create cost_usage table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cost_usage (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                execution_id TEXT,
                date TEXT NOT NULL,
                cost REAL NOT NULL DEFAULT 0.0,
                playbook_code TEXT,
                model_name TEXT,
                token_count INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indexes for cost_usage
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_cost_usage_workspace_date
            ON cost_usage(workspace_id, date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_cost_usage_execution
            ON cost_usage(execution_id)
        """)

        conn.commit()
        print("Created governance tables: governance_decisions, cost_usage")


def upgrade_postgresql(connection_string: Optional[str] = None):
    """
    Create governance tables in PostgreSQL database (for Cloud environment)

    Args:
        connection_string: PostgreSQL connection string
    """
    # TODO: Implement PostgreSQL migration using Alembic or raw SQL
    # This would be used in Cloud environment
    # Example SQL:
    """
    CREATE TABLE IF NOT EXISTS governance_decisions (
        decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        workspace_id UUID NOT NULL,
        execution_id UUID,
        timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
        layer VARCHAR(20) NOT NULL CHECK(layer IN ('cost', 'node', 'policy', 'preflight')),
        approved BOOLEAN NOT NULL DEFAULT TRUE,
        reason TEXT,
        playbook_code VARCHAR(255),
        metadata JSONB,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_governance_decisions_workspace_timestamp
    ON governance_decisions(workspace_id, timestamp);

    CREATE INDEX IF NOT EXISTS idx_governance_decisions_execution
    ON governance_decisions(execution_id);

    CREATE INDEX IF NOT EXISTS idx_governance_decisions_layer_approved
    ON governance_decisions(layer, approved);

    CREATE TABLE IF NOT EXISTS cost_usage (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        workspace_id UUID NOT NULL,
        execution_id UUID,
        date DATE NOT NULL,
        cost DECIMAL(10, 2) NOT NULL DEFAULT 0.0,
        playbook_code VARCHAR(255),
        model_name VARCHAR(255),
        token_count INTEGER,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_cost_usage_workspace_date
    ON cost_usage(workspace_id, date);

    CREATE INDEX IF NOT EXISTS idx_cost_usage_execution
    ON cost_usage(execution_id);
    """
    pass


def downgrade():
    """
    Remove governance tables

    Note: In production, this should be handled carefully.
    """
    # TODO: Implement table removal
    # For SQLite: DROP TABLE IF EXISTS governance_decisions; DROP TABLE IF EXISTS cost_usage;
    # For PostgreSQL: Same SQL
    pass


def run_migration(db_path: Optional[str] = None, db_type: str = "sqlite"):
    """
    Run migration based on database type

    Args:
        db_path: Database path (for SQLite) or connection string (for PostgreSQL)
        db_type: Database type ('sqlite' or 'postgresql')
    """
    if db_type == "sqlite":
        if db_path:
            upgrade_sqlite(db_path)
        else:
            # Default path for Local-Core
            default_path = "./data/mindscape.db"
            upgrade_sqlite(default_path)
    elif db_type == "postgresql":
        upgrade_postgresql(db_path)
    else:
        raise ValueError(f"Unsupported database type: {db_type}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
        run_migration(db_path)
    else:
        run_migration()




