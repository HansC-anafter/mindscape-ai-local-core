"""Artifact registry orchestration."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

from backend.app.models.task_ir import ArtifactReference
from backend.app.services.artifact_registry_core.storage import (
    ArtifactNotFoundError,
    FilesystemStorageBackend,
    S3StorageBackend,
)

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class ArtifactRegistry:
    """Unified artifact registry for all execution engines."""

    def __init__(self, storage_backend: str = "filesystem", **backend_kwargs):
        """
        Initialize artifact registry.

        Args:
            storage_backend: Storage backend type ("filesystem", "s3", etc.)
            **backend_kwargs: Backend-specific configuration
        """
        self.storage_backend = storage_backend
        self.artifacts: Dict[str, ArtifactReference] = {}

        if storage_backend == "filesystem":
            base_path = backend_kwargs.get("base_path", "/tmp/mindscape-artifacts")
            self.backend = FilesystemStorageBackend(base_path)
        elif storage_backend == "s3":
            bucket_name = backend_kwargs.get("bucket_name")
            if not bucket_name:
                raise ValueError("bucket_name required for S3 backend")
            self.backend = S3StorageBackend(
                bucket_name=bucket_name,
                prefix=backend_kwargs.get("prefix", ""),
                aws_region=backend_kwargs.get("aws_region", "us-east-1"),
            )
        else:
            raise ValueError(f"Unsupported storage backend: {storage_backend}")

    async def register_artifact(
        self, artifact: ArtifactReference, content: Any
    ) -> str:
        """
        Register artifact and store content.

        Args:
            artifact: Artifact reference without URI
            content: Artifact content

        Returns:
            Artifact ID
        """
        uri = await self.backend.store_artifact(artifact, content)
        artifact.uri = uri

        self.artifacts[artifact.id] = artifact

        logger.info(
            f"Registered artifact: {artifact.id} ({artifact.type}) from {artifact.source}"
        )
        return artifact.id

    def get_artifact(self, artifact_id: str) -> Optional[ArtifactReference]:
        """
        Get artifact reference by ID.

        Args:
            artifact_id: Artifact ID

        Returns:
            Artifact reference or None
        """
        return self.artifacts.get(artifact_id)

    async def load_artifact_content(self, artifact_id: str) -> Any:
        """
        Load actual artifact content.

        Args:
            artifact_id: Artifact ID

        Returns:
            Artifact content
        """
        artifact = self.get_artifact(artifact_id)
        if not artifact:
            raise ArtifactNotFoundError(f"Artifact not found: {artifact_id}")

        return await self.backend.load_artifact(artifact.uri)

    async def delete_artifact(self, artifact_id: str) -> bool:
        """
        Delete artifact.

        Args:
            artifact_id: Artifact ID

        Returns:
            True if deleted, False otherwise
        """
        artifact = self.get_artifact(artifact_id)
        if not artifact:
            return False

        deleted = await self.backend.delete_artifact(artifact.uri)
        if deleted:
            del self.artifacts[artifact_id]
            logger.info(f"Deleted artifact: {artifact_id}")

        return deleted

    def list_artifacts(
        self, filters: Optional[Dict[str, Any]] = None
    ) -> List[ArtifactReference]:
        """
        List artifacts with optional filters.

        Args:
            filters: Optional filters (source, type, etc.)

        Returns:
            List of artifact references
        """
        artifacts = list(self.artifacts.values())
        if not filters:
            return artifacts

        filtered = []
        for artifact in artifacts:
            match = True

            if "source" in filters and filters["source"] != artifact.source:
                match = False

            if "type" in filters and not artifact.type.startswith(filters["type"]):
                match = False

            if "created_after" in filters:
                if isinstance(filters["created_after"], str):
                    created_after = datetime.fromisoformat(filters["created_after"])
                else:
                    created_after = filters["created_after"]

                if artifact.created_at < created_after:
                    match = False

            if "created_before" in filters:
                if isinstance(filters["created_before"], str):
                    created_before = datetime.fromisoformat(filters["created_before"])
                else:
                    created_before = filters["created_before"]

                if artifact.created_at > created_before:
                    match = False

            if match:
                filtered.append(artifact)

        return filtered

    async def create_artifact_reference(
        self,
        id: str,
        type: str,
        source: str,
        content: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ArtifactReference:
        """
        Create and register a new artifact.

        Args:
            id: Artifact ID
            type: MIME type
            source: Source engine
            content: Artifact content
            metadata: Optional metadata

        Returns:
            Artifact reference
        """
        artifact = ArtifactReference(
            id=id,
            type=type,
            source=source,
            uri="",
            metadata=metadata,
        )

        await self.register_artifact(artifact, content)
        return artifact

    async def get_artifact_summary(
        self, artifact_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get artifact summary without content.

        Args:
            artifact_id: Artifact ID

        Returns:
            Artifact summary or None
        """
        artifact = self.get_artifact(artifact_id)
        if not artifact:
            return None

        return {
            "id": artifact.id,
            "type": artifact.type,
            "source": artifact.source,
            "uri": artifact.uri,
            "metadata": artifact.metadata,
            "created_at": artifact.created_at.isoformat(),
            "size": await self._get_artifact_size(artifact),
        }

    async def _get_artifact_size(self, artifact: ArtifactReference) -> Optional[int]:
        """
        Get artifact size in bytes.

        Args:
            artifact: Artifact reference

        Returns:
            Size in bytes or None if unknown
        """
        try:
            if artifact.uri.startswith("file://"):
                path = Path(artifact.uri[7:])
                return path.stat().st_size if path.exists() else None
            return None
        except Exception:
            return None

    async def cleanup_old_artifacts(self, days_old: int = 30) -> int:
        """
        Clean up artifacts older than specified days.

        Args:
            days_old: Age threshold in days

        Returns:
            Number of artifacts cleaned up
        """
        cutoff_date = _utc_now()
        cutoff_date = cutoff_date.replace(day=cutoff_date.day - days_old)

        old_artifacts = [
            artifact
            for artifact in self.artifacts.values()
            if artifact.created_at < cutoff_date
        ]

        cleaned_count = 0
        for artifact in old_artifacts:
            if await self.delete_artifact(artifact.id):
                cleaned_count += 1

        if cleaned_count > 0:
            logger.info(
                f"Cleaned up {cleaned_count} artifacts older than {days_old} days"
            )

        return cleaned_count
