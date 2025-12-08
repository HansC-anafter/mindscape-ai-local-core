#!/usr/bin/env python3
"""
Cleanup test connections from tool registry

Removes test connections created by verification scripts.
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.app.services.tool_registry import ToolRegistryService

def cleanup_test_connections(auto_confirm=False):
    """Remove test connections from tool registry"""
    registry = ToolRegistryService()

    # Get all connections
    connections = registry.get_connections()

    # Find test connections by name
    test_names = ["Test Connection", "Registration Test Connection", "Test"]
    test_connections_by_name = [
        conn for conn in connections
        if conn.tool_type == "local_filesystem" and conn.name in test_names
    ]

    # Find test connections by directory (containing /tmp)
    test_connections_by_dir = []
    for conn in connections:
        if conn.tool_type == "local_filesystem":
            dirs = conn.config.get("allowed_directories", [])
            if any("/tmp" in str(d) for d in dirs):
                # Exclude if it's a legitimate connection (not test)
                if conn.name not in test_names and "test" not in conn.id.lower():
                    continue
                test_connections_by_dir.append(conn)

    # Combine and deduplicate
    all_test_connections = list({conn.id: conn for conn in test_connections_by_name + test_connections_by_dir}.values())

    print(f"Found {len(all_test_connections)} test connections to remove:")
    for conn in all_test_connections:
        dirs = conn.config.get("allowed_directories", [])
        print(f"  - {conn.id}: {conn.name} (dirs: {dirs})")

    if not all_test_connections:
        print("No test connections found.")
        return

    # Confirm deletion
    if not auto_confirm:
        response = input(f"\nDelete {len(all_test_connections)} test connections? (yes/no): ")
        if response.lower() != 'yes':
            print("Cancelled.")
            return

    # Delete test connections
    deleted_count = 0
    for conn in all_test_connections:
        try:
            registry.delete_connection(conn.id, conn.profile_id)
            deleted_count += 1
            print(f"Deleted: {conn.id} - {conn.name}")
        except Exception as e:
            print(f"Error deleting {conn.id}: {e}")

    print(f"\nDeleted {deleted_count} test connections.")

if __name__ == "__main__":
    cleanup_test_connections()

