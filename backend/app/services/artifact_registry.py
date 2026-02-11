"""
Artifact Registry - Unified artifact indexing and storage

The Artifact Registry is the "media library" in our video editing analogy.
It provides unified access to all artifacts (files, data, outputs) produced
during task execution, regardless of which engine created them.

Supports multiple storage backends: filesystem, S3, weaviate, etc.
"""

import os
import json
import logging
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import Dict, Any, List, Optional, Union, Callable
from pathlib import Path
from abc import ABC, abstractmethod

from backend.app.models.task_ir import ArtifactReference, ArtifactType

logger = logging.getLogger(__name__)


class ArtifactStorageError(Exception):
    """Base exception for artifact storage operations"""
    pass


class ArtifactNotFoundError(ArtifactStorageError):
    """Artifact not found"""
    pass


class ArtifactStorageBackend(ABC):
    """
    Abstract base class for artifact storage backends

    Different storage backends (filesystem, S3, weaviate) implement this interface.
    """

    @abstractmethod
    async def store_artifact(self, artifact: ArtifactReference, content: Any) -> str:
        """
        Store artifact content

        Args:
            artifact: Artifact reference
            content: Artifact content

        Returns:
            Storage URI
        """
        pass

    @abstractmethod
    async def load_artifact(self, uri: str) -> Any:
        """
        Load artifact content

        Args:
            uri: Storage URI

        Returns:
            Artifact content
        """
        pass

    @abstractmethod
    async def delete_artifact(self, uri: str) -> bool:
        """
        Delete artifact

        Args:
            uri: Storage URI

        Returns:
            True if deleted, False otherwise
        """
        pass

    @abstractmethod
    async def list_artifacts(self, prefix: str = "") -> List[str]:
        """
        List artifacts under a prefix

        Args:
            prefix: URI prefix to list

        Returns:
            List of URIs
        """
        pass


class FilesystemStorageBackend(ArtifactStorageBackend):
    """
    Filesystem-based artifact storage

    Stores artifacts as files in a local directory structure.
    """

    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def store_artifact(self, artifact: ArtifactReference, content: Any) -> str:
        """Store artifact to filesystem"""
        # Create directory structure based on artifact ID
        artifact_path = self.base_path / artifact.id
        artifact_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content based on type
        if artifact.type.startswith('text/'):
            with open(artifact_path, 'w', encoding='utf-8') as f:
                f.write(str(content))
        elif artifact.type == 'application/json':
            with open(artifact_path, 'w', encoding='utf-8') as f:
                json.dump(content, f, ensure_ascii=False, indent=2)
        else:
            # Binary content
            with open(artifact_path, 'wb') as f:
                f.write(content if isinstance(content, bytes) else str(content).encode())

        uri = f"file://{artifact_path.absolute()}"
        logger.debug(f"Stored artifact {artifact.id} to {uri}")
        return uri

    async def load_artifact(self, uri: str) -> Any:
        """Load artifact from filesystem"""
        if not uri.startswith('file://'):
            raise ArtifactStorageError(f"Invalid filesystem URI: {uri}")

        file_path = Path(uri[7:])  # Remove 'file://' prefix

        if not file_path.exists():
            raise ArtifactNotFoundError(f"Artifact not found: {uri}")

        # Read based on file extension or content analysis
        if file_path.suffix == '.json':
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            # Try text first, fall back to binary
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except UnicodeDecodeError:
                with open(file_path, 'rb') as f:
                    return f.read()

    async def delete_artifact(self, uri: str) -> bool:
        """Delete artifact from filesystem"""
        if not uri.startswith('file://'):
            return False

        file_path = Path(uri[7:])
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    async def list_artifacts(self, prefix: str = "") -> List[str]:
        """List artifacts under prefix"""
        search_path = self.base_path / prefix if prefix else self.base_path
        if not search_path.exists():
            return []

        uris = []
        for file_path in search_path.rglob('*'):
            if file_path.is_file():
                relative_path = file_path.relative_to(self.base_path)
                uris.append(f"file://{file_path.absolute()}")

        return uris


class S3StorageBackend(ArtifactStorageBackend):
    """
    S3-based artifact storage

    Stores artifacts in Amazon S3 or compatible services.
    """

    def __init__(self, bucket_name: str, prefix: str = "", aws_region: str = "us-east-1"):
        self.bucket_name = bucket_name
        self.prefix = prefix.rstrip('/')
        self.aws_region = aws_region

        # Lazy import boto3
        try:
            import boto3
            self.s3_client = boto3.client('s3', region_name=aws_region)
        except ImportError:
            logger.warning("boto3 not available, S3 storage will not work")
            self.s3_client = None

    async def store_artifact(self, artifact: ArtifactReference, content: Any) -> str:
        """Store artifact to S3"""
        if not self.s3_client:
            raise ArtifactStorageError("S3 client not available")

        key = f"{self.prefix}/{artifact.id}".lstrip('/')

        # Convert content to bytes
        if isinstance(content, str):
            body = content.encode('utf-8')
        elif isinstance(content, dict):
            body = json.dumps(content, ensure_ascii=False).encode('utf-8')
        elif isinstance(content, bytes):
            body = content
        else:
            body = str(content).encode('utf-8')

        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=body,
            ContentType=artifact.type
        )

        uri = f"s3://{self.bucket_name}/{key}"
        logger.debug(f"Stored artifact {artifact.id} to {uri}")
        return uri

    async def load_artifact(self, uri: str) -> Any:
        """Load artifact from S3"""
        if not self.s3_client:
            raise ArtifactStorageError("S3 client not available")

        if not uri.startswith('s3://'):
            raise ArtifactStorageError(f"Invalid S3 URI: {uri}")

        # Parse S3 URI: s3://bucket/key
        path_parts = uri[5:].split('/', 1)
        if len(path_parts) != 2:
            raise ArtifactStorageError(f"Invalid S3 URI format: {uri}")

        bucket, key = path_parts

        try:
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            body = response['Body'].read()

            # Parse based on content type
            content_type = response.get('ContentType', '')
            if content_type == 'application/json':
                return json.loads(body.decode('utf-8'))
            elif content_type.startswith('text/'):
                return body.decode('utf-8')
            else:
                return body

        except self.s3_client.exceptions.NoSuchKey:
            raise ArtifactNotFoundError(f"Artifact not found: {uri}")

    async def delete_artifact(self, uri: str) -> bool:
        """Delete artifact from S3"""
        if not self.s3_client:
            return False

        if not uri.startswith('s3://'):
            return False

        path_parts = uri[5:].split('/', 1)
        if len(path_parts) != 2:
            return False

        bucket, key = path_parts

        try:
            self.s3_client.delete_object(Bucket=bucket, Key=key)
            return True
        except Exception as e:
            logger.warning(f"Failed to delete S3 object {uri}: {e}")
            return False

    async def list_artifacts(self, prefix: str = "") -> List[str]:
        """List artifacts under prefix"""
        if not self.s3_client:
            return []

        search_prefix = f"{self.prefix}/{prefix}".strip('/')
        if search_prefix:
            search_prefix += '/'

        uris = []
        paginator = self.s3_client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=search_prefix):
            if 'Contents' in page:
                for obj in page['Contents']:
                    uris.append(f"s3://{self.bucket_name}/{obj['Key']}")

        return uris


class ArtifactRegistry:
    """
    Unified artifact registry for all execution engines

    This is the "media library" that indexes all artifacts produced during
    task execution, providing unified access regardless of storage backend.
    """

    def __init__(self, storage_backend: str = "filesystem", **backend_kwargs):
        """
        Initialize artifact registry

        Args:
            storage_backend: Storage backend type ("filesystem", "s3", etc.)
            **backend_kwargs: Backend-specific configuration
        """
        self.storage_backend = storage_backend
        self.artifacts: Dict[str, ArtifactReference] = {}

        # Initialize storage backend
        if storage_backend == "filesystem":
            base_path = backend_kwargs.get('base_path', '/tmp/mindscape-artifacts')
            self.backend = FilesystemStorageBackend(base_path)
        elif storage_backend == "s3":
            bucket_name = backend_kwargs.get('bucket_name')
            if not bucket_name:
                raise ValueError("bucket_name required for S3 backend")
            self.backend = S3StorageBackend(
                bucket_name=bucket_name,
                prefix=backend_kwargs.get('prefix', ''),
                aws_region=backend_kwargs.get('aws_region', 'us-east-1')
            )
        else:
            raise ValueError(f"Unsupported storage backend: {storage_backend}")

    async def register_artifact(
        self,
        artifact: ArtifactReference,
        content: Any
    ) -> str:
        """
        Register artifact and store content

        Args:
            artifact: Artifact reference (without URI)
            content: Artifact content

        Returns:
            Artifact ID
        """
        # Store content using backend
        uri = await self.backend.store_artifact(artifact, content)
        artifact.uri = uri

        # Register in index
        self.artifacts[artifact.id] = artifact

        logger.info(f"Registered artifact: {artifact.id} ({artifact.type}) from {artifact.source}")
        return artifact.id

    def get_artifact(self, artifact_id: str) -> Optional[ArtifactReference]:
        """
        Get artifact reference by ID

        Args:
            artifact_id: Artifact ID

        Returns:
            Artifact reference or None
        """
        return self.artifacts.get(artifact_id)

    async def load_artifact_content(self, artifact_id: str) -> Any:
        """
        Load actual artifact content

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
        Delete artifact

        Args:
            artifact_id: Artifact ID

        Returns:
            True if deleted, False otherwise
        """
        artifact = self.get_artifact(artifact_id)
        if not artifact:
            return False

        # Delete from storage
        deleted = await self.backend.delete_artifact(artifact.uri)

        if deleted:
            # Remove from index
            del self.artifacts[artifact_id]
            logger.info(f"Deleted artifact: {artifact_id}")

        return deleted

    def list_artifacts(self, filters: Optional[Dict[str, Any]] = None) -> List[ArtifactReference]:
        """
        List artifacts with optional filters

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

            if 'source' in filters and filters['source'] != artifact.source:
                match = False

            if 'type' in filters and not artifact.type.startswith(filters['type']):
                match = False

            if 'created_after' in filters:
                if isinstance(filters['created_after'], str):
                    created_after = datetime.fromisoformat(filters['created_after'])
                else:
                    created_after = filters['created_after']

                if artifact.created_at < created_after:
                    match = False

            if 'created_before' in filters:
                if isinstance(filters['created_before'], str):
                    created_before = datetime.fromisoformat(filters['created_before'])
                else:
                    created_before = filters['created_before']

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
        metadata: Optional[Dict[str, Any]] = None
    ) -> ArtifactReference:
        """
        Create and register a new artifact

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
            uri="",  # Will be set by register_artifact
            metadata=metadata
        )

        await self.register_artifact(artifact, content)
        return artifact

    async def get_artifact_summary(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        """
        Get artifact summary (metadata without content)

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
            "size": await self._get_artifact_size(artifact)
        }

    async def _get_artifact_size(self, artifact: ArtifactReference) -> Optional[int]:
        """
        Get artifact size in bytes

        Args:
            artifact: Artifact reference

        Returns:
            Size in bytes or None if unknown
        """
        try:
            if artifact.uri.startswith('file://'):
                path = Path(artifact.uri[7:])
                return path.stat().st_size if path.exists() else None
            # For other backends, size calculation would be backend-specific
            return None
        except Exception:
            return None

    async def cleanup_old_artifacts(self, days_old: int = 30) -> int:
        """
        Clean up artifacts older than specified days

        Args:
            days_old: Age threshold in days

        Returns:
            Number of artifacts cleaned up
        """
        cutoff_date = _utc_now()
        cutoff_date = cutoff_date.replace(day=cutoff_date.day - days_old)

        old_artifacts = [
            artifact for artifact in self.artifacts.values()
            if artifact.created_at < cutoff_date
        ]

        cleaned_count = 0
        for artifact in old_artifacts:
            if await self.delete_artifact(artifact.id):
                cleaned_count += 1

        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} artifacts older than {days_old} days")

        return cleaned_count
