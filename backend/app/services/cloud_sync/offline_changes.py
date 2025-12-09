"""
Offline Change Tracker
Tracks and replays offline changes with conflict resolution UI support
"""

import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path

from .instance_store import InstanceStore
from .instance_syncer import InstanceSyncer, ConflictResolution

logger = logging.getLogger(__name__)


class OfflineChangeTracker:
    """Tracks offline changes and supports replay and conflict resolution"""

    def __init__(
        self,
        instance_store: InstanceStore,
        instance_syncer: Optional[InstanceSyncer] = None,
    ):
        """
        Initialize offline change tracker

        Args:
            instance_store: InstanceStore instance
            instance_syncer: InstanceSyncer instance (optional)
        """
        self.instance_store = instance_store
        self.instance_syncer = instance_syncer

    def get_pending_changes(
        self,
        instance_type: Optional[str] = None,
        instance_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get list of pending changes

        Args:
            instance_type: Filter by instance type (optional)
            instance_id: Filter by instance ID (optional)

        Returns:
            List of pending change records
        """
        if instance_type and instance_id:
            return self.instance_store.get_local_changes(instance_type, instance_id)

        instances = self.instance_store.list_instances(instance_type)
        all_changes = []

        for instance_info in instances:
            inst_type = instance_info["instance_type"]
            inst_id = instance_info["instance_id"]
            changes = self.instance_store.get_local_changes(inst_type, inst_id)
            for change in changes:
                change["instance_type"] = inst_type
                change["instance_id"] = inst_id
            all_changes.extend(changes)

        return sorted(all_changes, key=lambda x: x.get("created_at", ""))

    def get_change_summary(self) -> Dict[str, Any]:
        """
        Get summary of pending changes

        Returns:
            Change summary dict
        """
        pending_changes = self.get_pending_changes()
        instances = self.instance_store.list_instances()

        summary = {
            "total_changes": len(pending_changes),
            "affected_instances": len(set(
                (c.get("instance_type"), c.get("instance_id"))
                for c in pending_changes
            )),
            "instances_with_changes": [
                {
                    "instance_type": inst["instance_type"],
                    "instance_id": inst["instance_id"],
                    "change_count": len(
                        self.instance_store.get_local_changes(
                            inst["instance_type"],
                            inst["instance_id"]
                        )
                    ),
                }
                for inst in instances
                if inst.get("has_local_changes", False)
            ],
        }

        return summary

    async def replay_changes(
        self,
        instance_type: str,
        instance_id: str,
        conflict_resolution: Optional[ConflictResolution] = None,
    ) -> Dict[str, Any]:
        """
        Replay pending changes for instance

        Args:
            instance_type: Instance type
            instance_id: Instance ID
            conflict_resolution: Conflict resolution strategy (optional)

        Returns:
            Replay result dict
        """
        if not self.instance_syncer:
            return {
                "status": "failed",
                "error": "InstanceSyncer not available",
            }

        changes = self.instance_store.get_local_changes(instance_type, instance_id)
        if not changes:
            return {
                "status": "success",
                "message": "No pending changes",
            }

        results = {
            "total_changes": len(changes),
            "synced": 0,
            "failed": 0,
            "conflicts": 0,
        }

        for change in changes:
            try:
                sync_result = await self.instance_syncer.sync_instance(
                    instance_type,
                    instance_id,
                    conflict_resolution=conflict_resolution,
                )

                if sync_result.get("status") == "synced" or sync_result.get("status") == "merged":
                    self.instance_store.mark_change_synced(
                        instance_type,
                        instance_id,
                        change.get("change_id"),
                    )
                    results["synced"] += 1
                elif sync_result.get("status") == "conflict":
                    results["conflicts"] += 1
                else:
                    results["failed"] += 1

            except Exception as e:
                logger.error(f"Failed to replay change {change.get('change_id')}: {e}")
                results["failed"] += 1

        return results

    async def replay_all_changes(
        self,
        conflict_resolution: Optional[ConflictResolution] = None,
    ) -> Dict[str, Any]:
        """
        Replay all pending changes

        Args:
            conflict_resolution: Conflict resolution strategy (optional)

        Returns:
            Replay result dict
        """
        instances = self.instance_store.list_instances()
        all_results = {
            "total_instances": len(instances),
            "total_changes": 0,
            "synced": 0,
            "failed": 0,
            "conflicts": 0,
        }

        for instance_info in instances:
            if instance_info.get("has_local_changes", False):
                inst_type = instance_info["instance_type"]
                inst_id = instance_info["instance_id"]

                changes = self.instance_store.get_local_changes(inst_type, inst_id)
                all_results["total_changes"] += len(changes)

                result = await self.replay_changes(inst_type, inst_id, conflict_resolution)
                all_results["synced"] += result.get("synced", 0)
                all_results["failed"] += result.get("failed", 0)
                all_results["conflicts"] += result.get("conflicts", 0)

        return all_results

    def get_conflict_info(
        self,
        instance_type: str,
        instance_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get conflict information for UI display

        Args:
            instance_type: Instance type
            instance_id: Instance ID

        Returns:
            Conflict info dict or None if no conflict
        """
        metadata = self.instance_store.get_instance_metadata(instance_type, instance_id)
        if not metadata:
            return None

        local_version = metadata.get("local_version", 0)
        cloud_version = metadata.get("cloud_version", 0)

        if local_version == cloud_version:
            return None

        local_data = self.instance_store.get_instance(instance_type, instance_id)
        changes = self.instance_store.get_local_changes(instance_type, instance_id)

        return {
            "instance_type": instance_type,
            "instance_id": instance_id,
            "local_version": local_version,
            "cloud_version": cloud_version,
            "has_local_changes": metadata.get("has_local_changes", False),
            "pending_changes_count": len(changes),
            "local_data": local_data,
            "last_sync": metadata.get("last_sync"),
            "resolution_options": [
                ConflictResolution.USE_LOCAL.value,
                ConflictResolution.USE_CLOUD.value,
                ConflictResolution.MANUAL_MERGE.value,
            ],
        }

    def resolve_conflict(
        self,
        instance_type: str,
        instance_id: str,
        resolution: ConflictResolution,
        merged_data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Resolve conflict manually

        Args:
            instance_type: Instance type
            instance_id: Instance ID
            resolution: Resolution strategy
            merged_data: Merged data (required for MANUAL_MERGE)

        Returns:
            True if resolution successful
        """
        metadata = self.instance_store.get_instance_metadata(instance_type, instance_id)
        if not metadata:
            return False

        if resolution == ConflictResolution.USE_LOCAL:
            metadata["cloud_version"] = metadata.get("local_version", 0)
            metadata["has_local_changes"] = True
        elif resolution == ConflictResolution.USE_CLOUD:
            metadata["local_version"] = metadata.get("cloud_version", 0)
            metadata["has_local_changes"] = False
        elif resolution == ConflictResolution.MANUAL_MERGE:
            if merged_data is None:
                logger.error("Merged data required for MANUAL_MERGE resolution")
                return False

            self.instance_store.update_instance(
                instance_type,
                instance_id,
                merged_data,
                track_change=False,
            )

            metadata["local_version"] = metadata.get("local_version", 0) + 1
            metadata["cloud_version"] = metadata.get("local_version", 0)
            metadata["has_local_changes"] = False

        instance_path = self.instance_store.get_instance_path(instance_type, instance_id)
        metadata_file = instance_path / "metadata.json"
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        logger.info(f"Resolved conflict for {instance_type}/{instance_id} using {resolution.value}")
        return True

    def clear_pending_changes(
        self,
        instance_type: str,
        instance_id: str,
    ):
        """
        Clear all pending changes (use with caution)

        Args:
            instance_type: Instance type
            instance_id: Instance ID
        """
        instance_path = self.instance_store.get_instance_path(instance_type, instance_id)
        local_changes_dir = instance_path / "local_changes"

        if local_changes_dir.exists():
            for change_file in local_changes_dir.glob("change_*.json"):
                try:
                    change_file.unlink()
                except Exception as e:
                    logger.error(f"Failed to clear change file {change_file}: {e}")

        metadata = self.instance_store.get_instance_metadata(instance_type, instance_id)
        if metadata:
            metadata["has_local_changes"] = False
            instance_path = self.instance_store.get_instance_path(instance_type, instance_id)
            metadata_file = instance_path / "metadata.json"
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

