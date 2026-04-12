"""
StorageSlot — Pluggable public media storage for ig_publisher.

Selects the backend via MINDSCAPE_STORAGE_SLOT env var:
  - "gcs"      : Google Cloud Storage with V4 signed URL (default)
  - "mindscape_cloud_integration" : upload to cloud-integration public asset API
  - "cloud_integration" : alias for "mindscape_cloud_integration"
  - "mindscape_cloud_generation" : transitional alias for compatibility
  - "cloud_generation" : transitional alias for compatibility
  - "site_hub" : legacy alias for "mindscape_cloud_integration"
  - "s3"       : S3-compatible storage (MinIO / AWS S3)
  - "local"    : localhost dev stub (URL not publicly accessible)

New slots can be added by implementing the MediaStorageSlot protocol and
registering in _SLOT_REGISTRY without touching ig_publisher.py.
"""

import abc
import logging
import os
from pathlib import Path
from typing import Optional

from services.cloud_integration_config import (
    get_cloud_integration_api_base,
    get_cloud_integration_upload_token,
)

logger = logging.getLogger(__name__)


class MediaStorageSlot(abc.ABC):
    """Protocol for public media storage backends."""

    @abc.abstractmethod
    async def upload(
        self,
        file_path: Path,
        media_type: str,
        workspace_id: str,
        trace_id: Optional[str] = None,
    ) -> str:
        """
        Upload a local file and return a publicly accessible HTTPS URL.

        Args:
            file_path: Absolute local file path.
            media_type: "photo" | "reel" | "carousel_item"
            workspace_id: Mindscape workspace ID.
            trace_id: Optional trace ID for logging.

        Returns:
            Public HTTPS URL (suitable for IG Graph API image_url / video_url).

        Raises:
            RuntimeError: If upload fails.
        """


# ---------------------------------------------------------------------------
# Slot: gcs  (Google Cloud Storage + V4 Signed URL)
# ---------------------------------------------------------------------------


class GCSStorageSlot(MediaStorageSlot):
    """
    Upload media to Google Cloud Storage and return a V4 Signed URL.

    Object key:  ig-media/{workspace_id}/{uuid}{ext}
    Bucket ACL:  private  (signed URL provides time-limited public access)
    Signed URL TTL: 30 minutes (IG Graph API fetches within seconds)

    Lifecycle:   set a GCS lifecycle rule to delete objects after 7 days.

    Required env vars:
      GCS_IG_MEDIA_BUCKET          – target GCS bucket name
      GOOGLE_APPLICATION_CREDENTIALS – path to service-account JSON
                                       (or use Workload Identity on GKE/Cloud Run)
    """

    async def upload(
        self,
        file_path: Path,
        media_type: str,
        workspace_id: str,
        trace_id: Optional[str] = None,
    ) -> str:
        import asyncio
        import datetime
        import uuid as _uuid

        try:
            from google.cloud import storage as gcs
        except ImportError:
            raise RuntimeError(
                "GCSStorageSlot requires google-cloud-storage: "
                "pip install google-cloud-storage"
            )

        bucket_name = os.getenv("GCS_IG_MEDIA_BUCKET")
        if not bucket_name:
            raise RuntimeError("GCSStorageSlot: GCS_IG_MEDIA_BUCKET env var not set")

        suffix = file_path.suffix or ""
        object_key = f"ig-media/{workspace_id}/{_uuid.uuid4().hex}{suffix}"

        client = gcs.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_key)

        # Upload file (run in thread to avoid blocking the event loop)
        await asyncio.to_thread(blob.upload_from_filename, str(file_path))

        # Generate V4 signed URL — 30-minute window is plenty for IG to fetch
        signed_url: str = await asyncio.to_thread(
            blob.generate_signed_url,
            version="v4",
            expiration=datetime.timedelta(minutes=30),
            method="GET",
        )

        logger.info(
            "GCSStorageSlot: uploaded gs://%s/%s workspace=%s trace=%s",
            bucket_name,
            object_key,
            workspace_id,
            trace_id,
        )
        return signed_url


# ---------------------------------------------------------------------------
# Slot: s3
# ---------------------------------------------------------------------------


class S3StorageSlot(MediaStorageSlot):
    """
    Upload media to an S3-compatible bucket and return a public URL.

    Env vars:
      S3_ENDPOINT_URL     - endpoint (default: AWS S3, set for MinIO/GCS)
      S3_BUCKET_NAME      - target bucket
      S3_ACCESS_KEY_ID    - access key
      S3_SECRET_ACCESS_KEY - secret key
      S3_PUBLIC_BASE_URL  - public base URL (default: https://{bucket}.s3.amazonaws.com)
    """

    async def upload(
        self,
        file_path: Path,
        media_type: str,
        workspace_id: str,
        trace_id: Optional[str] = None,
    ) -> str:
        try:
            import boto3
            from botocore.client import Config
        except ImportError:
            raise RuntimeError("S3StorageSlot requires boto3: pip install boto3")

        bucket = os.getenv("S3_BUCKET_NAME")
        if not bucket:
            raise RuntimeError("S3StorageSlot: S3_BUCKET_NAME env var not set")

        session = boto3.session.Session()
        kwargs = {
            "service_name": "s3",
            "aws_access_key_id": os.getenv("S3_ACCESS_KEY_ID"),
            "aws_secret_access_key": os.getenv("S3_SECRET_ACCESS_KEY"),
        }
        endpoint = os.getenv("S3_ENDPOINT_URL")
        if endpoint:
            kwargs["endpoint_url"] = endpoint
            kwargs["config"] = Config(signature_version="s3v4")

        client = session.client(**kwargs)
        key = f"ig-media/{workspace_id}/{file_path.name}"

        import asyncio

        await asyncio.to_thread(
            client.upload_file,
            str(file_path),
            bucket,
            key,
            ExtraArgs={"ACL": "public-read"},
        )

        public_base = os.getenv(
            "S3_PUBLIC_BASE_URL", f"https://{bucket}.s3.amazonaws.com"
        )
        url = f"{public_base.rstrip('/')}/{key}"
        logger.info(f"S3StorageSlot: uploaded {file_path.name} → {url}")
        return url


# ---------------------------------------------------------------------------
# Slot: local (development only)
# ---------------------------------------------------------------------------


class LocalDevStorageSlot(MediaStorageSlot):
    """
    Serve media from local-core's static file endpoint.

    ONLY for development — the URL is not publicly accessible.

    Env vars:
      MINDSCAPE_LOCAL_CORE_URL - base URL (default: http://localhost:8200)
    """

    async def upload(
        self,
        file_path: Path,
        media_type: str,
        workspace_id: str,
        trace_id: Optional[str] = None,
    ) -> str:
        local_core_url = os.getenv(
            "MINDSCAPE_LOCAL_CORE_URL", "http://localhost:8200"
        ).rstrip("/")
        # local-core serves files under /api/v1/files/{workspace_id}/{filename}
        # This requires the file to already be in the workspace storage path.
        url = f"{local_core_url}/api/v1/files/{workspace_id}/{file_path.name}"
        logger.warning(
            f"LocalDevStorageSlot: using non-public URL {url} — suitable for dev only"
        )
        return url


# ---------------------------------------------------------------------------
# Slot: mindscape_cloud_integration
# ---------------------------------------------------------------------------


class MindscapeCloudIntegrationStorageSlot(MediaStorageSlot):
    """
    Upload media to cloud-integration and return its publicly accessible serve URL.

    Cloud-integration exposes:
      POST  /api/v1/assets/upload   → {url, asset_id, content_type}
      GET   /api/v1/assets/serve/{id}

    Required env var:
      MINDSCAPE_CLOUD_INTEGRATION_API_BASE – preferred base URL
      (legacy aliases: CLOUD_PROVIDER_API_BASE / SITE_HUB_API_BASE)
    Optional env var:
      MINDSCAPE_CLOUD_INTEGRATION_UPLOAD_TOKEN – Bearer token
      (legacy aliases: CLOUD_PROVIDER_UPLOAD_TOKEN / SITE_HUB_UPLOAD_TOKEN)
    """

    async def upload(
        self,
        file_path: Path,
        media_type: str,
        workspace_id: str,
        trace_id: Optional[str] = None,
    ) -> str:
        import httpx

        base = (get_cloud_integration_api_base() or "").rstrip("/")
        if not base:
            raise RuntimeError(
                "MindscapeCloudIntegrationStorageSlot: cloud-integration API base env var not set"
            )

        upload_url = f"{base}/api/v1/assets/upload"
        token = get_cloud_integration_upload_token() or ""
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        mime, _ = __import__("mimetypes").guess_type(str(file_path))
        mime = mime or "application/octet-stream"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                with file_path.open("rb") as fh:
                    resp = await client.post(
                        upload_url,
                        headers=headers,
                        files={"file": (file_path.name, fh, mime)},
                        data={
                            "workspace_id": workspace_id or "",
                            "media_type": media_type or "",
                            "filename": file_path.name,
                        },
                    )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            raise RuntimeError(
                f"MindscapeCloudIntegrationStorageSlot: upload to {upload_url} failed: {exc}"
            ) from exc

        public_url = payload.get("url")
        if not public_url:
            raise RuntimeError(
                f"MindscapeCloudIntegrationStorageSlot: response missing 'url' field: {payload}"
            )

        logger.info(
            "MindscapeCloudIntegrationStorageSlot: uploaded %s → %s workspace=%s trace=%s",
            file_path.name,
            public_url,
            workspace_id,
            trace_id,
        )
        return public_url


class MindscapeCloudGenerationStorageSlot(MindscapeCloudIntegrationStorageSlot):
    """Backward-compatible alias."""


class SiteHubStorageSlot(MindscapeCloudIntegrationStorageSlot):
    """Backward-compatible alias. Prefer MindscapeCloudIntegrationStorageSlot."""


# ---------------------------------------------------------------------------
# Registry + factory
# ---------------------------------------------------------------------------

_SLOT_REGISTRY: dict[str, type[MediaStorageSlot]] = {
    "gcs": GCSStorageSlot,
    "mindscape_cloud_integration": MindscapeCloudIntegrationStorageSlot,
    "cloud_integration": MindscapeCloudIntegrationStorageSlot,
    "mindscape_cloud_generation": MindscapeCloudIntegrationStorageSlot,
    "cloud_generation": MindscapeCloudIntegrationStorageSlot,
    "site_hub": MindscapeCloudIntegrationStorageSlot,
    "s3": S3StorageSlot,
    "local": LocalDevStorageSlot,
}


def get_storage_slot() -> MediaStorageSlot:
    """
    Return the configured storage slot instance.

    Reads MINDSCAPE_STORAGE_SLOT env var (default: "gcs").
    Raises ValueError if the slot name is not registered.
    """
    slot_name = os.getenv("MINDSCAPE_STORAGE_SLOT", "gcs").strip().lower()
    slot_cls = _SLOT_REGISTRY.get(slot_name)
    if slot_cls is None:
        raise ValueError(
            f"Unknown MINDSCAPE_STORAGE_SLOT={slot_name!r}. "
            f"Available: {list(_SLOT_REGISTRY)}"
        )
    return slot_cls()
