#!/usr/bin/env python3
"""
Cleanup Validation Workspaces Script (API-based)

Removes all validation workspaces created by validate_playbooks.py
Uses the REST API to delete workspaces.

Usage:
    # List validation workspaces (dry-run)
    python3 scripts/cleanup_validation_workspaces_api.py --dry-run

    # Delete validation workspaces
    python3 scripts/cleanup_validation_workspaces_api.py

    # Use different API URL
    python3 scripts/cleanup_validation_workspaces_api.py --api-url http://localhost:8200
"""

import argparse
import sys
import requests
import os

BASE_URL = os.getenv("BASE_URL", "http://localhost:8200")
OWNER_USER_ID = os.getenv("OWNER_USER_ID", "default-user")


def main():
    parser = argparse.ArgumentParser(description="Cleanup validation workspaces via API")
    parser.add_argument("--dry-run", action="store_true", help="List workspaces without deleting")
    parser.add_argument("--owner-user-id", default=OWNER_USER_ID, help="Owner user ID to filter by")
    parser.add_argument("--api-url", default=BASE_URL, help="API base URL")
    parser.add_argument("--title-prefix", default="Validate:", help="Title prefix to match (default: 'Validate:')")
    parser.add_argument("--include-system", action="store_true", help="Include system workspaces in listing")
    args = parser.parse_args()

    # List all workspaces
    try:
        params = {
            "owner_user_id": args.owner_user_id,
            "limit": 200
        }
        if args.include_system:
            params["include_system"] = "true"

        response = requests.get(
            f"{args.api_url}/api/v1/workspaces",
            params=params,
            timeout=10
        )

        if response.status_code != 200:
            print(f"Error: Failed to list workspaces: {response.status_code} {response.text}")
            return 1

        workspaces = response.json()
        if not isinstance(workspaces, list):
            print(f"Error: Unexpected response format: {workspaces}")
            return 1

    except requests.exceptions.ConnectionError:
        print(f"Error: Cannot connect to API at {args.api_url}")
        print("Make sure the backend service is running.")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1

    # Filter validation workspaces
    validation_workspaces = [
        ws for ws in workspaces
        if ws.get("title", "").startswith(args.title_prefix)
    ]

    if not validation_workspaces:
        print(f"No validation workspaces found with title prefix '{args.title_prefix}'")
        return 0

    print(f"Found {len(validation_workspaces)} validation workspace(s):")
    for ws in validation_workspaces:
        print(f"  - {ws.get('id')}: {ws.get('title')} (created: {ws.get('created_at')})")

    if args.dry_run:
        print("\nDry-run mode: No workspaces deleted. Run without --dry-run to delete.")
        return 0

    # Confirm deletion
    print(f"\nAbout to delete {len(validation_workspaces)} workspace(s).")
    confirm = input("Continue? (yes/no): ")
    if confirm.lower() not in ['yes', 'y']:
        print("Cancelled.")
        return 0

    # Delete validation workspaces
    deleted_count = 0
    failed_count = 0

    for ws in validation_workspaces:
        workspace_id = ws.get("id")
        workspace_title = ws.get("title", "Unknown")

        try:
            response = requests.delete(
                f"{args.api_url}/api/v1/workspaces/{workspace_id}",
                timeout=10
            )

            if response.status_code in [200, 204]:
                print(f"✓ Deleted: {workspace_id} ({workspace_title})")
                deleted_count += 1
            else:
                print(f"✗ Failed to delete {workspace_id}: {response.status_code} {response.text}")
                failed_count += 1

        except Exception as e:
            print(f"✗ Error deleting {workspace_id}: {e}")
            failed_count += 1

    print(f"\nSummary: Deleted {deleted_count}, Failed {failed_count}, Total {len(validation_workspaces)}")
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

