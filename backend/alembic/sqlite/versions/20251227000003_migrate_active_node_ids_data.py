"""migrate_active_node_ids_data

Revision ID: 20251227000003
Revises: 20251227000002
Create Date: 2025-12-27

Migrates data from mind_lens_active_nodes bridge table to lens_profile_nodes table.

This migration:
1. Migrates active_node_ids from mind_lens_active_nodes to lens_profile_nodes(state)
2. Clarifies is_active semantics (node existence, not execution state)
3. Sets state='keep' for active nodes, state='off' for inactive nodes

Part of Phase 0 of Mind-Lens unified implementation roadmap.
See: docs-internal/mind-lens/implementation/implementation-roadmap.md

IMPORTANT: This migration requires Python code execution, not just SQL.
It should be run after 20251227000001 (table creation) and 20251227000002 (snapshots).
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = '20251227000003'
down_revision: Union[str, None] = '20251227000002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Migrate data from mind_lens_active_nodes to lens_profile_nodes

    This migration:
    1. For each preset, get active_node_ids from mind_lens_active_nodes
    2. Create lens_profile_nodes entries with state='keep' for active nodes
    3. For nodes not in active_node_ids but is_active=True, create state='off'
    4. Ensure all GraphNode.is_active = True (clarify semantics)
    """
    conn = op.get_bind()

    # Check if mind_lens_active_nodes table exists
    inspector = sa.inspect(conn)
    if 'mind_lens_active_nodes' not in inspector.get_table_names():
        print("mind_lens_active_nodes table not found, skipping data migration")
        return

    # Get all presets
    result = conn.execute(text('SELECT DISTINCT id, profile_id FROM mind_lens_profiles'))
    presets = result.fetchall()

    if not presets:
        print("No lens profiles found, skipping data migration")
        return

    print(f"Found {len(presets)} lens profiles to migrate")

    migrated_count = 0
    for preset_row in presets:
        preset_id = preset_row[0]
        profile_id = preset_row[1]

        # Get active nodes from bridge table
        result = conn.execute(
            text('SELECT graph_node_id FROM mind_lens_active_nodes WHERE lens_id = :lens_id'),
            {'lens_id': preset_id}
        )
        active_node_rows = result.fetchall()
        active_set = {row[0] for row in active_node_rows}

        # Get all nodes for this profile
        result = conn.execute(
            text('SELECT id FROM graph_nodes WHERE profile_id = :profile_id AND is_active = 1'),
            {'profile_id': profile_id}
        )
        all_nodes = [row[0] for row in result.fetchall()]

        # Migrate each node
        for node_id in all_nodes:
            if node_id in active_set:
                state = 'keep'
            else:
                state = 'off'

            # Insert or replace
            conn.execute(
                text('''
                    INSERT OR REPLACE INTO lens_profile_nodes (id, preset_id, node_id, state, updated_at)
                    VALUES (
                        lower(hex(randomblob(16))),
                        :preset_id,
                        :node_id,
                        :state,
                        datetime('now')
                    )
                '''),
                {
                    'preset_id': preset_id,
                    'node_id': node_id,
                    'state': state
                }
            )
            migrated_count += 1

        print(f"  Migrated preset {preset_id}: {len(active_set)} active, {len(all_nodes)} total nodes")

    # Clarify is_active semantics: ensure all nodes are is_active=True
    # (is_active now means node existence, not execution state)
    result = conn.execute(
        text('SELECT id FROM graph_nodes WHERE is_active = 0')
    )
    inactive_nodes = result.fetchall()

    if inactive_nodes:
        print(f"Found {len(inactive_nodes)} inactive nodes, setting is_active=1")
        for node_row in inactive_nodes:
            node_id = node_row[0]
            conn.execute(
                text('UPDATE graph_nodes SET is_active = 1 WHERE id = :node_id'),
                {'node_id': node_id}
            )

            # For each preset, ensure state='off' for these nodes
            for preset_row in presets:
                preset_id = preset_row[0]
                conn.execute(
                    text('''
                        INSERT OR REPLACE INTO lens_profile_nodes (id, preset_id, node_id, state, updated_at)
                        VALUES (
                            lower(hex(randomblob(16))),
                            :preset_id,
                            :node_id,
                            'off',
                            datetime('now')
                        )
                    '''),
                    {
                        'preset_id': preset_id,
                        'node_id': node_id
                    }
                )

    print(f"Migration completed: {migrated_count} nodes migrated")


def downgrade() -> None:
    """
    Downgrade: Cannot fully reverse data migration.
    This would require restoring from mind_lens_active_nodes which may not exist.
    """
    print("Warning: Data migration downgrade is not fully reversible.")
    print("Legacy bridge table mind_lens_active_nodes may not have all data.")
    # We don't delete lens_profile_nodes data as it may be the only source of truth

