"""
Playbook Resources Migration Script

Migrates playbook resources from old workspace paths to new overlay paths.

Migration strategy:
- Reads from old workspace path: {workspace_storage}/playbooks/{playbook_code}/resources/{resource_type}/
- Writes to new overlay path: {workspace_storage}/workspace_overlays/playbooks/{playbook_code}/resources/{resource_type}/

This is a one-time migration script. After migration, the new overlay architecture
will handle both old and new paths (lazy migration).
"""

import json
import logging
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
import argparse

from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.playbook_resource_overlay_service import PlaybookResourceOverlayService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_workspace_resources(
    workspace_id: str,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Migrate playbook resources for a specific workspace

    Args:
        workspace_id: Workspace ID
        dry_run: If True, only report what would be migrated without actually migrating

    Returns:
        Migration report
    """
    store = MindscapeStore()
    overlay_service = PlaybookResourceOverlayService(store=store)

    workspace = store.get_workspace(workspace_id)
    if not workspace:
        logger.error(f"Workspace {workspace_id} not found")
        return {
            "workspace_id": workspace_id,
            "status": "error",
            "error": "Workspace not found",
            "migrated": []
        }

    # Get old workspace resource path
    if workspace.storage_base_path:
        base_path = Path(workspace.storage_base_path)
    else:
        import os
        base_path = Path(os.path.expanduser("~/Documents/Mindscape"))

    old_base_path = base_path / "playbooks"
    new_base_path = base_path / "workspace_overlays" / "playbooks"

    migrated_resources = []
    errors = []

    # Find all playbook directories in old path
    if not old_base_path.exists():
        logger.info(f"No old playbook resources found for workspace {workspace_id}")
        return {
            "workspace_id": workspace_id,
            "status": "success",
            "migrated": [],
            "message": "No resources to migrate"
        }

    for playbook_dir in old_base_path.iterdir():
        if not playbook_dir.is_dir():
            continue

        playbook_code = playbook_dir.name
        resources_dir = playbook_dir / "resources"

        if not resources_dir.exists():
            continue

        # Find all resource types
        for resource_type_dir in resources_dir.iterdir():
            if not resource_type_dir.is_dir():
                continue

            resource_type = resource_type_dir.name

            # Find all resource files
            for resource_file in resource_type_dir.glob("*.json"):
                resource_id = resource_file.stem

                try:
                    # Read resource from old path
                    with open(resource_file, 'r', encoding='utf-8') as f:
                        resource_data = json.load(f)

                    # Determine new path
                    new_resource_dir = new_base_path / playbook_code / "resources" / resource_type
                    new_resource_file = new_resource_dir / f"{resource_id}.json"

                    # Check if already migrated
                    if new_resource_file.exists():
                        logger.debug(
                            f"Resource {resource_type}/{resource_id} for playbook {playbook_code} "
                            f"already exists in new path, skipping"
                        )
                        continue

                    if dry_run:
                        logger.info(
                            f"[DRY RUN] Would migrate: {playbook_code}/{resource_type}/{resource_id}"
                        )
                        migrated_resources.append({
                            "playbook_code": playbook_code,
                            "resource_type": resource_type,
                            "resource_id": resource_id,
                            "old_path": str(resource_file),
                            "new_path": str(new_resource_file),
                            "status": "would_migrate"
                        })
                    else:
                        # Create new directory
                        new_resource_dir.mkdir(parents=True, exist_ok=True)

                        # Write to new path
                        with open(new_resource_file, 'w', encoding='utf-8') as f:
                            json.dump(resource_data, f, indent=2, ensure_ascii=False)

                        logger.info(
                            f"Migrated: {playbook_code}/{resource_type}/{resource_id} "
                            f"from {resource_file} to {new_resource_file}"
                        )

                        migrated_resources.append({
                            "playbook_code": playbook_code,
                            "resource_type": resource_type,
                            "resource_id": resource_id,
                            "old_path": str(resource_file),
                            "new_path": str(new_resource_file),
                            "status": "migrated"
                        })

                except Exception as e:
                    error_msg = f"Failed to migrate {playbook_code}/{resource_type}/{resource_id}: {e}"
                    logger.error(error_msg)
                    errors.append({
                        "playbook_code": playbook_code,
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                        "error": str(e)
                    })

    return {
        "workspace_id": workspace_id,
        "status": "success" if not errors else "partial",
        "migrated": migrated_resources,
        "errors": errors,
        "total_migrated": len(migrated_resources),
        "total_errors": len(errors)
    }


def migrate_all_workspaces(dry_run: bool = False) -> Dict[str, Any]:
    """
    Migrate playbook resources for all workspaces

    Args:
        dry_run: If True, only report what would be migrated without actually migrating

    Returns:
        Migration report for all workspaces
    """
    store = MindscapeStore()
    workspaces = store.list_workspaces()

    all_results = []
    total_migrated = 0
    total_errors = 0

    for workspace in workspaces:
        logger.info(f"Migrating resources for workspace: {workspace.id} ({workspace.name})")
        result = migrate_workspace_resources(workspace.id, dry_run=dry_run)
        all_results.append(result)

        if result["status"] == "success" or result["status"] == "partial":
            total_migrated += result.get("total_migrated", 0)
            total_errors += result.get("total_errors", 0)

    return {
        "status": "success",
        "workspaces": all_results,
        "total_workspaces": len(workspaces),
        "total_migrated": total_migrated,
        "total_errors": total_errors
    }


def main():
    """Main entry point for migration script"""
    parser = argparse.ArgumentParser(
        description="Migrate playbook resources from old workspace paths to new overlay paths"
    )
    parser.add_argument(
        "--workspace-id",
        type=str,
        help="Specific workspace ID to migrate (if not provided, migrates all workspaces)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode: report what would be migrated without actually migrating"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path for migration report (JSON)"
    )

    args = parser.parse_args()

    if args.dry_run:
        logger.info("Running in DRY RUN mode - no files will be modified")

    if args.workspace_id:
        logger.info(f"Migrating resources for workspace: {args.workspace_id}")
        result = migrate_workspace_resources(args.workspace_id, dry_run=args.dry_run)
    else:
        logger.info("Migrating resources for all workspaces")
        result = migrate_all_workspaces(dry_run=args.dry_run)

    # Print summary
    print("\n" + "=" * 80)
    print("Migration Summary")
    print("=" * 80)
    if "workspaces" in result:
        print(f"Total workspaces: {result['total_workspaces']}")
        print(f"Total resources migrated: {result['total_migrated']}")
        print(f"Total errors: {result['total_errors']}")
    else:
        print(f"Workspace: {result['workspace_id']}")
        print(f"Status: {result['status']}")
        if result.get("total_migrated"):
            print(f"Resources migrated: {result['total_migrated']}")
        if result.get("total_errors"):
            print(f"Errors: {result['total_errors']}")

    # Save report if output file specified
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\nMigration report saved to: {args.output}")

    print("=" * 80)


if __name__ == "__main__":
    main()

