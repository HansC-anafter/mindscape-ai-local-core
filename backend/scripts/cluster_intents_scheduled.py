#!/usr/bin/env python3
"""
Scheduled Intent Clustering Script

Runs intent clustering for all workspaces/profiles.
Can be scheduled to run nightly via cron or manually.

Usage:
    python scripts/cluster_intents_scheduled.py [--workspace-id <id>] [--profile-id <id>]
"""

import argparse
import sys
import os
from typing import Optional
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.mindscape_store import MindscapeStore
from app.services.conversation.intent_cluster_service import IntentClusterService
from app.services.stores.workspaces_store import WorkspacesStore


async def cluster_all_workspaces(db_path: str, workspace_id: Optional[str] = None,
                                 profile_id: Optional[str] = None):
    """
    Cluster intents for all workspaces or specific workspace/profile

    Args:
        db_path: Database path
        workspace_id: Optional workspace ID to filter
        profile_id: Optional profile ID to filter
    """
    store = MindscapeStore(db_path=db_path)
    cluster_service = IntentClusterService(store=store)

    if workspace_id and profile_id:
        # Cluster specific workspace/profile
        print(f"Clustering intents for workspace={workspace_id}, profile={profile_id}...")
        clusters = await cluster_service.cluster_intents(
            workspace_id=workspace_id,
            profile_id=profile_id
        )
        print(f"Created {len(clusters)} clusters")
        for cluster in clusters:
            print(f"  - {cluster.label}: {len(cluster.intent_card_ids)} intents")
    else:
        # Cluster all workspaces
        workspaces_store = WorkspacesStore(db_path=db_path)
        workspaces = workspaces_store.list_workspaces()

        total_clusters = 0
        for workspace in workspaces:
            # Use default profile for now (can be extended to support multiple profiles)
            profile_id = "default-user"

            print(f"Clustering intents for workspace={workspace.id}, profile={profile_id}...")
            try:
                clusters = await cluster_service.cluster_intents(
                    workspace_id=workspace.id,
                    profile_id=profile_id
                )
                total_clusters += len(clusters)
                print(f"  Created {len(clusters)} clusters")
            except Exception as e:
                print(f"  Error: {e}")

        print(f"\nTotal: Created {total_clusters} clusters across {len(workspaces)} workspaces")


def main():
    parser = argparse.ArgumentParser(description='Run scheduled intent clustering')
    parser.add_argument('--db-path', type=str, default=None, help='Path to SQLite database')
    parser.add_argument('--workspace-id', type=str, default=None, help='Filter by workspace ID')
    parser.add_argument('--profile-id', type=str, default=None, help='Filter by profile ID')

    args = parser.parse_args()

    # Determine database path
    if args.db_path:
        db_path = args.db_path
    else:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        db_path = os.path.join(data_dir, "mindscape.db")
        if not os.path.exists(db_path):
            db_path = '/app/data/mindscape.db'

    print(f"Intent Clustering - Scheduled Task")
    print(f"Database: {db_path}")
    print(f"Started at: {datetime.utcnow().isoformat()}")
    print("=" * 80)

    import asyncio
    asyncio.run(cluster_all_workspaces(
        db_path=db_path,
        workspace_id=args.workspace_id,
        profile_id=args.profile_id
    ))

    print("=" * 80)
    print(f"Completed at: {datetime.utcnow().isoformat()}")


if __name__ == '__main__':
    main()

