"""
Instance Syncer
Handles bidirectional synchronization of instances with conflict detection and merge strategies
"""

import logging
from typing import Optional, Dict, Any, List
from enum import Enum

from .instance_store import InstanceStore
from .sync_client import SyncClient, NetworkError
from .offline_mode import OfflineModeManager

logger = logging.getLogger(__name__)


class SyncDirection(Enum):
    """Sync direction"""
    PULL = "pull"
    PUSH = "push"
    MERGE = "merge"


class SyncStatus(Enum):
    """Sync status"""
    SYNCED = "synced"
    CONFLICT = "conflict"
    MERGED = "merged"
    FAILED = "failed"


class ConflictResolution(Enum):
    """Conflict resolution strategy"""
    USE_LOCAL = "use_local"
    USE_CLOUD = "use_cloud"
    MANUAL_MERGE = "manual_merge"


class InstanceSyncer:
    """Handles bidirectional instance synchronization"""

    def __init__(
        self,
        instance_store: InstanceStore,
        sync_client: SyncClient,
        offline_mode_manager: Optional[OfflineModeManager] = None,
    ):
        """
        Initialize instance syncer

        Args:
            instance_store: InstanceStore instance
            sync_client: SyncClient instance
            offline_mode_manager: OfflineModeManager instance (optional)
        """
        self.instance_store = instance_store
        self.sync_client = sync_client
        self.offline_mode_manager = offline_mode_manager

    async def sync_instance(
        self,
        instance_type: str,
        instance_id: str,
        direction: SyncDirection = SyncDirection.MERGE,
        conflict_resolution: Optional[ConflictResolution] = None,
    ) -> Dict[str, Any]:
        """
        Sync instance with cloud

        Args:
            instance_type: Instance type
            instance_id: Instance ID
            direction: Sync direction
            conflict_resolution: Conflict resolution strategy (optional)

        Returns:
            Sync result dict
        """
        if self.offline_mode_manager and self.offline_mode_manager.is_offline():
            logger.warning(f"Cannot sync {instance_type}/{instance_id}: offline mode")
            return {
                "status": SyncStatus.FAILED.value,
                "error": "Offline mode",
            }

        try:
            if direction == SyncDirection.PULL:
                return await self._pull_instance(instance_type, instance_id)
            elif direction == SyncDirection.PUSH:
                return await self._push_instance(instance_type, instance_id)
            elif direction == SyncDirection.MERGE:
                return await self._merge_instance(instance_type, instance_id, conflict_resolution)
            else:
                raise ValueError(f"Unknown sync direction: {direction}")

        except NetworkError as e:
            logger.error(f"Network error syncing {instance_type}/{instance_id}: {e}")
            if self.offline_mode_manager:
                self.offline_mode_manager.queue_sync_task(
                    lambda: self.sync_instance(instance_type, instance_id, direction, conflict_resolution)
                )
            return {
                "status": SyncStatus.FAILED.value,
                "error": str(e),
            }
        except Exception as e:
            logger.error(f"Error syncing {instance_type}/{instance_id}: {e}")
            return {
                "status": SyncStatus.FAILED.value,
                "error": str(e),
            }

    async def _pull_instance(
        self,
        instance_type: str,
        instance_id: str,
    ) -> Dict[str, Any]:
        """Pull instance from cloud"""
        metadata = self.instance_store.get_instance_metadata(instance_type, instance_id)
        if not metadata:
            logger.warning(f"Instance not found locally: {instance_type}/{instance_id}")
            return {
                "status": SyncStatus.FAILED.value,
                "error": "Instance not found locally",
            }

        local_version = metadata.get("local_version", 0)

        try:
            response = await self.sync_client.sync_instances(
                direction="pull",
                instances=[
                    {
                        "id": instance_id,
                        "type": instance_type,
                    }
                ],
            )

            results = response.get("results", [])
            if not results:
                return {
                    "status": SyncStatus.FAILED.value,
                    "error": "No results from sync",
                }

            result = results[0]
            status = result.get("status")

            if status == "synced":
                cloud_data = result.get("cloud_data", {})
                cloud_version = cloud_data.get("version", 0)

                if cloud_version > local_version:
                    self.instance_store.update_instance(
                        instance_type,
                        instance_id,
                        cloud_data.get("content", {}),
                        track_change=False,
                    )

                    metadata["cloud_version"] = cloud_version
                    metadata["local_version"] = cloud_version
                    metadata["has_local_changes"] = False
                    metadata["last_sync"] = cloud_data.get("updated_at")

                    instance_path = self.instance_store.get_instance_path(instance_type, instance_id)
                    metadata_file = instance_path / "metadata.json"
                    import json
                    with open(metadata_file, "w", encoding="utf-8") as f:
                        json.dump(metadata, f, indent=2, ensure_ascii=False)

                    logger.info(f"Pulled instance {instance_type}/{instance_id} (version {cloud_version})")
                    return {
                        "status": SyncStatus.SYNCED.value,
                        "cloud_version": cloud_version,
                    }

            elif status == "conflict":
                return {
                    "status": SyncStatus.CONFLICT.value,
                    "conflict": result.get("conflict", {}),
                }

            return {
                "status": SyncStatus.SYNCED.value,
            }

        except Exception as e:
            logger.error(f"Failed to pull instance {instance_type}/{instance_id}: {e}")
            raise

    async def _push_instance(
        self,
        instance_type: str,
        instance_id: str,
    ) -> Dict[str, Any]:
        """Push instance to cloud"""
        instance_data = self.instance_store.get_instance(instance_type, instance_id)
        metadata = self.instance_store.get_instance_metadata(instance_type, instance_id)

        if not instance_data or not metadata:
            logger.warning(f"Instance not found: {instance_type}/{instance_id}")
            return {
                "status": SyncStatus.FAILED.value,
                "error": "Instance not found",
            }

        local_version = metadata.get("local_version", 0)

        try:
            response = await self.sync_client.sync_instances(
                direction="push",
                instances=[
                    {
                        "id": instance_id,
                        "type": instance_type,
                        "local_data": {
                            "version": local_version,
                            "updated_at": metadata.get("updated_at"),
                            "content": instance_data,
                        },
                    }
                ],
            )

            results = response.get("results", [])
            if not results:
                return {
                    "status": SyncStatus.FAILED.value,
                    "error": "No results from sync",
                }

            result = results[0]
            status = result.get("status")

            if status == "synced":
                cloud_version = result.get("cloud_version", local_version)

                metadata["cloud_version"] = cloud_version
                metadata["local_version"] = cloud_version
                metadata["has_local_changes"] = False
                metadata["last_sync"] = result.get("synced_at")

                instance_path = self.instance_store.get_instance_path(instance_type, instance_id)
                metadata_file = instance_path / "metadata.json"
                import json
                with open(metadata_file, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)

                self.instance_store.clear_synced_changes(instance_type, instance_id)

                logger.info(f"Pushed instance {instance_type}/{instance_id} (version {cloud_version})")
                return {
                    "status": SyncStatus.SYNCED.value,
                    "cloud_version": cloud_version,
                }

            elif status == "conflict":
                return {
                    "status": SyncStatus.CONFLICT.value,
                    "conflict": result.get("conflict", {}),
                }

            return {
                "status": SyncStatus.SYNCED.value,
            }

        except Exception as e:
            logger.error(f"Failed to push instance {instance_type}/{instance_id}: {e}")
            raise

    async def _merge_instance(
        self,
        instance_type: str,
        instance_id: str,
        conflict_resolution: Optional[ConflictResolution] = None,
    ) -> Dict[str, Any]:
        """Merge instance with cloud"""
        metadata = self.instance_store.get_instance_metadata(instance_type, instance_id)
        if not metadata:
            logger.warning(f"Instance not found: {instance_type}/{instance_id}")
            return {
                "status": SyncStatus.FAILED.value,
                "error": "Instance not found",
            }

        local_version = metadata.get("local_version", 0)
        cloud_version = metadata.get("cloud_version", 0)

        if local_version == cloud_version and not metadata.get("has_local_changes", False):
            return {
                "status": SyncStatus.SYNCED.value,
                "message": "Already in sync",
            }

        try:
            response = await self.sync_client.sync_instances(
                direction="merge",
                instances=[
                    {
                        "id": instance_id,
                        "type": instance_type,
                        "local_version": local_version,
                    }
                ],
            )

            results = response.get("results", [])
            if not results:
                return {
                    "status": SyncStatus.FAILED.value,
                    "error": "No results from sync",
                }

            result = results[0]
            status = result.get("status")

            if status == "synced":
                cloud_data = result.get("cloud_data", {})
                new_version = cloud_data.get("version", local_version)

                self.instance_store.update_instance(
                    instance_type,
                    instance_id,
                    cloud_data.get("content", {}),
                    track_change=False,
                )

                metadata["cloud_version"] = new_version
                metadata["local_version"] = new_version
                metadata["has_local_changes"] = False
                metadata["last_sync"] = cloud_data.get("updated_at")

                instance_path = self.instance_store.get_instance_path(instance_type, instance_id)
                metadata_file = instance_path / "metadata.json"
                import json
                with open(metadata_file, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)

                self.instance_store.clear_synced_changes(instance_type, instance_id)

                logger.info(f"Merged instance {instance_type}/{instance_id} (version {new_version})")
                return {
                    "status": SyncStatus.MERGED.value,
                    "cloud_version": new_version,
                }

            elif status == "conflict":
                if conflict_resolution == ConflictResolution.USE_LOCAL:
                    return await self._push_instance(instance_type, instance_id)
                elif conflict_resolution == ConflictResolution.USE_CLOUD:
                    return await self._pull_instance(instance_type, instance_id)
                else:
                    return {
                        "status": SyncStatus.CONFLICT.value,
                        "conflict": result.get("conflict", {}),
                        "resolution_options": [
                            ConflictResolution.USE_LOCAL.value,
                            ConflictResolution.USE_CLOUD.value,
                            ConflictResolution.MANUAL_MERGE.value,
                        ],
                    }

            return {
                "status": SyncStatus.SYNCED.value,
            }

        except Exception as e:
            logger.error(f"Failed to merge instance {instance_type}/{instance_id}: {e}")
            raise

    async def sync_all_instances(
        self,
        instance_type: Optional[str] = None,
        direction: SyncDirection = SyncDirection.MERGE,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Sync all instances

        Args:
            instance_type: Filter by instance type (optional)
            direction: Sync direction

        Returns:
            Dictionary mapping instance IDs to sync results
        """
        instances = self.instance_store.list_instances(instance_type)
        results = {}

        for instance_info in instances:
            instance_id = instance_info["instance_id"]
            inst_type = instance_info["instance_type"]

            result = await self.sync_instance(inst_type, instance_id, direction)
            results[instance_id] = result

        return results

