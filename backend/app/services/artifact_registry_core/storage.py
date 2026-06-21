"""Storage backend implementations for the artifact registry."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, List
import json
import logging

from backend.app.models.task_ir import ArtifactReference

logger = logging.getLogger(__name__)


class ArtifactStorageError(Exception):
    """Base exception for artifact storage operations."""


class ArtifactNotFoundError(ArtifactStorageError):
    """Artifact not found."""


class ArtifactStorageBackend(ABC):
    """Abstract base class for artifact storage backends."""

    @abstractmethod
    async def store_artifact(self, artifact: ArtifactReference, content: Any) -> str:
        """
        Store artifact content.

        Args:
            artifact: Artifact reference
            content: Artifact content

        Returns:
            Storage URI
        """

    @abstractmethod
    async def load_artifact(self, uri: str) -> Any:
        """
        Load artifact content.

        Args:
            uri: Storage URI

        Returns:
            Artifact content
        """

    @abstractmethod
    async def delete_artifact(self, uri: str) -> bool:
        """
        Delete artifact.

        Args:
            uri: Storage URI

        Returns:
            True if deleted, False otherwise
        """

    @abstractmethod
    async def list_artifacts(self, prefix: str = "") -> List[str]:
        """
        List artifacts under a prefix.

        Args:
            prefix: URI prefix to list

        Returns:
            List of URIs
        """


class FilesystemStorageBackend(ArtifactStorageBackend):
    """Filesystem-based artifact storage."""

    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def store_artifact(self, artifact: ArtifactReference, content: Any) -> str:
        """Store artifact to filesystem."""
        artifact_path = self.base_path / artifact.id
        artifact_path.parent.mkdir(parents=True, exist_ok=True)

        if artifact.type.startswith("text/"):
            with open(artifact_path, "w", encoding="utf-8") as f:
                f.write(str(content))
        elif artifact.type == "application/json":
            with open(artifact_path, "w", encoding="utf-8") as f:
                json.dump(content, f, ensure_ascii=False, indent=2)
        else:
            with open(artifact_path, "wb") as f:
                f.write(
                    content if isinstance(content, bytes) else str(content).encode()
                )

        uri = f"file://{artifact_path.absolute()}"
        logger.debug(f"Stored artifact {artifact.id} to {uri}")
        return uri

    async def load_artifact(self, uri: str) -> Any:
        """Load artifact from filesystem."""
        if not uri.startswith("file://"):
            raise ArtifactStorageError(f"Invalid filesystem URI: {uri}")

        file_path = Path(uri[7:])
        if not file_path.exists():
            raise ArtifactNotFoundError(f"Artifact not found: {uri}")

        if file_path.suffix == ".json":
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            with open(file_path, "rb") as f:
                return f.read()

    async def delete_artifact(self, uri: str) -> bool:
        """Delete artifact from filesystem."""
        if not uri.startswith("file://"):
            return False

        file_path = Path(uri[7:])
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    async def list_artifacts(self, prefix: str = "") -> List[str]:
        """List artifacts under prefix."""
        search_path = self.base_path / prefix if prefix else self.base_path
        if not search_path.exists():
            return []

        uris = []
        for file_path in search_path.rglob("*"):
            if file_path.is_file():
                uris.append(f"file://{file_path.absolute()}")

        return uris


class S3StorageBackend(ArtifactStorageBackend):
    """S3-based artifact storage."""

    def __init__(
        self, bucket_name: str, prefix: str = "", aws_region: str = "us-east-1"
    ):
        self.bucket_name = bucket_name
        self.prefix = prefix.rstrip("/")
        self.aws_region = aws_region

        try:
            import boto3

            self.s3_client = boto3.client("s3", region_name=aws_region)
        except ImportError:
            logger.warning("boto3 not available, S3 storage will not work")
            self.s3_client = None

    async def store_artifact(self, artifact: ArtifactReference, content: Any) -> str:
        """Store artifact to S3."""
        if not self.s3_client:
            raise ArtifactStorageError("S3 client not available")

        key = f"{self.prefix}/{artifact.id}".lstrip("/")
        if isinstance(content, str):
            body = content.encode("utf-8")
        elif isinstance(content, dict):
            body = json.dumps(content, ensure_ascii=False).encode("utf-8")
        elif isinstance(content, bytes):
            body = content
        else:
            body = str(content).encode("utf-8")

        self.s3_client.put_object(
            Bucket=self.bucket_name, Key=key, Body=body, ContentType=artifact.type
        )

        uri = f"s3://{self.bucket_name}/{key}"
        logger.debug(f"Stored artifact {artifact.id} to {uri}")
        return uri

    async def load_artifact(self, uri: str) -> Any:
        """Load artifact from S3."""
        if not self.s3_client:
            raise ArtifactStorageError("S3 client not available")

        if not uri.startswith("s3://"):
            raise ArtifactStorageError(f"Invalid S3 URI: {uri}")

        path_parts = uri[5:].split("/", 1)
        if len(path_parts) != 2:
            raise ArtifactStorageError(f"Invalid S3 URI format: {uri}")

        bucket, key = path_parts
        try:
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            body = response["Body"].read()

            content_type = response.get("ContentType", "")
            if content_type == "application/json":
                return json.loads(body.decode("utf-8"))
            if content_type.startswith("text/"):
                return body.decode("utf-8")
            return body
        except self.s3_client.exceptions.NoSuchKey:
            raise ArtifactNotFoundError(f"Artifact not found: {uri}")

    async def delete_artifact(self, uri: str) -> bool:
        """Delete artifact from S3."""
        if not self.s3_client:
            return False

        if not uri.startswith("s3://"):
            return False

        path_parts = uri[5:].split("/", 1)
        if len(path_parts) != 2:
            return False

        bucket, key = path_parts
        try:
            self.s3_client.delete_object(Bucket=bucket, Key=key)
            return True
        except Exception as exc:
            logger.warning(f"Failed to delete S3 object {uri}: {exc}")
            return False

    async def list_artifacts(self, prefix: str = "") -> List[str]:
        """List artifacts under prefix."""
        if not self.s3_client:
            return []

        search_prefix = f"{self.prefix}/{prefix}".strip("/")
        if search_prefix:
            search_prefix += "/"

        uris = []
        paginator = self.s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=search_prefix):
            if "Contents" in page:
                for obj in page["Contents"]:
                    uris.append(f"s3://{self.bucket_name}/{obj['Key']}")

        return uris
