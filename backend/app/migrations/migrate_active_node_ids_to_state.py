"""
Migration script: active_node_ids to lens_profile_nodes(state)

This script migrates data from mind_lens_active_nodes bridge table
to the new lens_profile_nodes table with state field.

Part of Phase 0 of Mind-Lens unified implementation roadmap.
See: docs-internal/mind-lens/implementation/implementation-roadmap.md
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timezone
from backend.app.services.stores.graph_store import GraphStore
from backend.app.models.graph import LensNodeState
import logging

logger = logging.getLogger(__name__)


def migrate_active_node_ids_to_state():
    """
    Migrate active_node_ids to lens_profile_nodes(state)

    Migration rules:
    1. For each preset, get active_node_ids from mind_lens_active_nodes
    2. Create lens_profile_nodes entries with state='keep' for active nodes
    3. For nodes not in active_node_ids but is_active=True, create state='off'
    4. For nodes with is_active=False, ensure they are set to is_active=True
       and create state='off' (clarify semantics)
    """
    store = GraphStore()

    with store.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute('SELECT DISTINCT profile_id FROM mind_lens_profiles')
        profile_ids = [row['profile_id'] for row in cursor.fetchall()]

        if not profile_ids:
            logger.info("No lens profiles found, skipping migration")
            return

        all_presets = []
        for profile_id in profile_ids:
            presets = store.list_lens_profiles(profile_id=profile_id)
            all_presets.extend(presets)

        logger.info(f"Found {len(all_presets)} lens profiles to migrate")

        for preset in all_presets:
            logger.info(f"Migrating preset: {preset.id} ({preset.name})")

            cursor.execute('''
                SELECT graph_node_id FROM mind_lens_active_nodes WHERE lens_id = ?
            ''', (preset.id,))
            active_node_rows = cursor.fetchall()
            active_set = {row['graph_node_id'] for row in active_node_rows}

            logger.info(f"  Active nodes: {len(active_set)}")

            all_nodes = store.list_nodes(profile_id=preset.profile_id, is_active=True, limit=10000)

            migrated_count = 0
            for node in all_nodes:
                if node.id in active_set:
                    state = LensNodeState.KEEP
                else:
                    state = LensNodeState.OFF

                store.upsert_lens_profile_node(
                    preset_id=preset.id,
                    node_id=node.id,
                    state=state
                )
                migrated_count += 1

            logger.info(f"  Migrated {migrated_count} nodes")

        conn.commit()

    logger.info("Migration completed successfully")


def verify_migration():
    """Verify migration results"""
    store = GraphStore()

    with store.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute('SELECT DISTINCT profile_id FROM mind_lens_profiles')
        profile_ids = [row['profile_id'] for row in cursor.fetchall()]

        if not profile_ids:
            logger.info("No lens profiles found for verification")
            return True

        all_presets = []
        for profile_id in profile_ids:
            presets = store.list_lens_profiles(profile_id=profile_id)
            all_presets.extend(presets)

        if not all_presets:
            logger.info("No lens profiles found for verification")
            return True

        all_passed = True
        for preset in all_presets:
            cursor.execute('''
                SELECT COUNT(*) FROM mind_lens_active_nodes WHERE lens_id = ?
            ''', (preset.id,))
            old_count = cursor.fetchone()[0]

            new_count = store.count_lens_profile_nodes(
                preset_id=preset.id,
                state=LensNodeState.KEEP
            )

            if old_count != new_count:
                logger.error(
                    f"Preset {preset.id}: mismatch - old={old_count}, new={new_count}"
                )
                all_passed = False
            else:
                logger.info(f"Preset {preset.id}: verified ({new_count} nodes)")

        if all_passed:
            logger.info("All verifications passed")
        else:
            logger.error("Some verifications failed")

        return all_passed


def clarify_is_active_semantics():
    """
    Clarify is_active semantics

    Ensure all GraphNode.is_active = True (node existence, not execution state).
    If a node was previously marked is_active=False to indicate "disabled",
    it should be changed to is_active=True with state=off in lens_profile_nodes.
    """
    store = GraphStore()

    with store.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, profile_id FROM graph_nodes WHERE is_active = 0
        ''')
        inactive_nodes = cursor.fetchall()

        if not inactive_nodes:
            logger.info("No inactive nodes found, semantics already clarified")
            return

        logger.info(f"Found {len(inactive_nodes)} inactive nodes to clarify")

        updated_count = 0
        for row in inactive_nodes:
            node_id = row['id']
            profile_id = row['profile_id']

            cursor.execute('''
                UPDATE graph_nodes SET is_active = 1 WHERE id = ?
            ''', (node_id,))

            presets = store.list_lens_profiles(profile_id=profile_id)
            for preset in presets:
                store.upsert_lens_profile_node(
                    preset_id=preset.id,
                    node_id=node_id,
                    state=LensNodeState.OFF
                )

            updated_count += 1

        conn.commit()
        logger.info(f"Updated {updated_count} nodes (is_active=False -> True, state=off)")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    logger.info("Starting migration: active_node_ids to lens_profile_nodes(state)")
    migrate_active_node_ids_to_state()

    logger.info("Verifying migration...")
    verify_migration()

    logger.info("Clarifying is_active semantics...")
    clarify_is_active_semantics()

    logger.info("Migration script completed")

