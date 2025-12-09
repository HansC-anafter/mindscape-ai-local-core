"""
Instance Store
Manages local instance storage with change tracking and version management
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


class InstanceStore:
    """Manages local instance storage with change tracking"""

    def __init__(self, instances_root: Optional[Path] = None):
        """
        Initialize instance store

        Args:
            instances_root: Root directory for instances (defaults to ~/.mindscape/instances)
        """
        if instances_root is None:
            instances_root = Path.home() / ".mindscape" / "instances"

        self.instances_root = Path(instances_root)
        self.instances_root.mkdir(parents=True, exist_ok=True)

    def get_instance_path(self, instance_type: str, instance_id: str) -> Path:
        """
        Get path for instance directory

        Args:
            instance_type: Instance type (e.g., "brand_identity")
            instance_id: Instance ID

        Returns:
            Path to instance directory
        """
        return self.instances_root / instance_type / instance_id

    def create_instance(
        self,
        instance_type: str,
        instance_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Create new instance

        Args:
            instance_type: Instance type
            instance_id: Instance ID (generated if not provided)
            data: Instance data

        Returns:
            Created instance ID
        """
        if instance_id is None:
            instance_id = str(uuid.uuid4())

        instance_path = self.get_instance_path(instance_type, instance_id)
        instance_path.mkdir(parents=True, exist_ok=True)

        data_file = instance_path / "data.json"
        metadata_file = instance_path / "metadata.json"
        local_changes_dir = instance_path / "local_changes"
        local_changes_dir.mkdir(exist_ok=True)

        instance_data = data or {}
        instance_data["_id"] = instance_id
        instance_data["_type"] = instance_type
        instance_data["_created_at"] = datetime.utcnow().isoformat()
        instance_data["_updated_at"] = datetime.utcnow().isoformat()

        metadata = {
            "instance_id": instance_id,
            "instance_type": instance_type,
            "local_version": 1,
            "cloud_version": 0,
            "last_sync": None,
            "has_local_changes": False,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        with open(data_file, "w", encoding="utf-8") as f:
            json.dump(instance_data, f, indent=2, ensure_ascii=False)

        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        logger.info(f"Created instance: {instance_type}/{instance_id}")
        return instance_id

    def get_instance(self, instance_type: str, instance_id: str) -> Optional[Dict[str, Any]]:
        """
        Get instance data

        Args:
            instance_type: Instance type
            instance_id: Instance ID

        Returns:
            Instance data dict or None if not found
        """
        instance_path = self.get_instance_path(instance_type, instance_id)
        data_file = instance_path / "data.json"

        if not data_file.exists():
            return None

        try:
            with open(data_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read instance {instance_type}/{instance_id}: {e}")
            return None

    def get_instance_metadata(self, instance_type: str, instance_id: str) -> Optional[Dict[str, Any]]:
        """
        Get instance metadata

        Args:
            instance_type: Instance type
            instance_id: Instance ID

        Returns:
            Instance metadata dict or None if not found
        """
        instance_path = self.get_instance_path(instance_type, instance_id)
        metadata_file = instance_path / "metadata.json"

        if not metadata_file.exists():
            return None

        try:
            with open(metadata_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read instance metadata {instance_type}/{instance_id}: {e}")
            return None

    def update_instance(
        self,
        instance_type: str,
        instance_id: str,
        data: Dict[str, Any],
        track_change: bool = True,
    ) -> bool:
        """
        Update instance data

        Args:
            instance_type: Instance type
            instance_id: Instance ID
            data: Updated data
            track_change: Whether to track this change

        Returns:
            True if update successful
        """
        instance_path = self.get_instance_path(instance_type, instance_id)
        data_file = instance_path / "data.json"
        metadata_file = instance_path / "metadata.json"

        if not data_file.exists():
            logger.warning(f"Instance not found: {instance_type}/{instance_id}")
            return False

        try:
            old_data = self.get_instance(instance_type, instance_id)
            if old_data is None:
                return False

            if track_change:
                self._track_change(instance_type, instance_id, old_data, data)

            data["_id"] = instance_id
            data["_type"] = instance_type
            data["_updated_at"] = datetime.utcnow().isoformat()

            if "_created_at" not in data:
                data["_created_at"] = old_data.get("_created_at", datetime.utcnow().isoformat())

            with open(data_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            metadata = self.get_instance_metadata(instance_type, instance_id)
            if metadata:
                metadata["local_version"] = metadata.get("local_version", 0) + 1
                metadata["has_local_changes"] = True
                metadata["updated_at"] = datetime.utcnow().isoformat()

                with open(metadata_file, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)

            logger.debug(f"Updated instance: {instance_type}/{instance_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to update instance {instance_type}/{instance_id}: {e}")
            return False

    def delete_instance(self, instance_type: str, instance_id: str) -> bool:
        """
        Delete instance

        Args:
            instance_type: Instance type
            instance_id: Instance ID

        Returns:
            True if deletion successful
        """
        instance_path = self.get_instance_path(instance_type, instance_id)

        if not instance_path.exists():
            return False

        try:
            import shutil
            shutil.rmtree(instance_path)
            logger.info(f"Deleted instance: {instance_type}/{instance_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete instance {instance_type}/{instance_id}: {e}")
            return False

    def list_instances(self, instance_type: Optional[str] = None) -> List[Dict[str, str]]:
        """
        List all instances

        Args:
            instance_type: Filter by instance type (optional)

        Returns:
            List of instance info dicts
        """
        instances = []

        if instance_type:
            type_dir = self.instances_root / instance_type
            if type_dir.exists():
                for instance_dir in type_dir.iterdir():
                    if instance_dir.is_dir():
                        metadata = self.get_instance_metadata(instance_type, instance_dir.name)
                        if metadata:
                            instances.append({
                                "instance_id": instance_dir.name,
                                "instance_type": instance_type,
                                "local_version": metadata.get("local_version", 0),
                                "cloud_version": metadata.get("cloud_version", 0),
                                "has_local_changes": metadata.get("has_local_changes", False),
                            })
        else:
            for type_dir in self.instances_root.iterdir():
                if type_dir.is_dir():
                    for instance_dir in type_dir.iterdir():
                        if instance_dir.is_dir():
                            metadata = self.get_instance_metadata(type_dir.name, instance_dir.name)
                            if metadata:
                                instances.append({
                                    "instance_id": instance_dir.name,
                                    "instance_type": type_dir.name,
                                    "local_version": metadata.get("local_version", 0),
                                    "cloud_version": metadata.get("cloud_version", 0),
                                    "has_local_changes": metadata.get("has_local_changes", False),
                                })

        return instances

    def _track_change(
        self,
        instance_type: str,
        instance_id: str,
        old_data: Dict[str, Any],
        new_data: Dict[str, Any],
    ):
        """
        Track change for offline sync

        Args:
            instance_type: Instance type
            instance_id: Instance ID
            old_data: Old data
            new_data: New data
        """
        instance_path = self.get_instance_path(instance_type, instance_id)
        local_changes_dir = instance_path / "local_changes"

        change_id = str(uuid.uuid4())
        change_file = local_changes_dir / f"change_{change_id}.json"

        change_data = {
            "change_id": change_id,
            "created_at": datetime.utcnow().isoformat(),
            "type": "update",
            "old_data": old_data,
            "new_data": new_data,
            "synced": False,
        }

        try:
            with open(change_file, "w", encoding="utf-8") as f:
                json.dump(change_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to track change for {instance_type}/{instance_id}: {e}")

    def get_local_changes(self, instance_type: str, instance_id: str) -> List[Dict[str, Any]]:
        """
        Get list of local changes

        Args:
            instance_type: Instance type
            instance_id: Instance ID

        Returns:
            List of change records
        """
        instance_path = self.get_instance_path(instance_type, instance_id)
        local_changes_dir = instance_path / "local_changes"

        if not local_changes_dir.exists():
            return []

        changes = []
        for change_file in local_changes_dir.glob("change_*.json"):
            try:
                with open(change_file, "r", encoding="utf-8") as f:
                    change_data = json.load(f)
                    if not change_data.get("synced", False):
                        changes.append(change_data)
            except Exception as e:
                logger.error(f"Failed to read change file {change_file}: {e}")

        return sorted(changes, key=lambda x: x.get("created_at", ""))

    def mark_change_synced(self, instance_type: str, instance_id: str, change_id: str):
        """
        Mark change as synced

        Args:
            instance_type: Instance type
            instance_id: Instance ID
            change_id: Change ID
        """
        instance_path = self.get_instance_path(instance_type, instance_id)
        local_changes_dir = instance_path / "local_changes"
        change_file = local_changes_dir / f"change_{change_id}.json"

        if change_file.exists():
            try:
                with open(change_file, "r", encoding="utf-8") as f:
                    change_data = json.load(f)

                change_data["synced"] = True
                change_data["synced_at"] = datetime.utcnow().isoformat()

                with open(change_file, "w", encoding="utf-8") as f:
                    json.dump(change_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Failed to mark change as synced {change_id}: {e}")

    def clear_synced_changes(self, instance_type: str, instance_id: str):
        """
        Clear synced changes

        Args:
            instance_type: Instance type
            instance_id: Instance ID
        """
        instance_path = self.get_instance_path(instance_type, instance_id)
        local_changes_dir = instance_path / "local_changes"

        if not local_changes_dir.exists():
            return

        for change_file in local_changes_dir.glob("change_*.json"):
            try:
                with open(change_file, "r", encoding="utf-8") as f:
                    change_data = json.load(f)

                if change_data.get("synced", False):
                    change_file.unlink()
            except Exception as e:
                logger.error(f"Failed to clear synced change {change_file}: {e}")

