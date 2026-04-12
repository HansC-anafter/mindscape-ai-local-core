"""
ig_pin_reference — Download, save, dedupe, and trigger analysis job.

Flow:
  1. Download image from URL
  2. Compute content_hash (SHA-256[:16])
  3. Check index for duplicate (content_hash)
     - If duplicate: merge tags, return existing reference_id
  4. Save image + metadata JSON to references/{@handle}/{shortcode}.*
  5. Update _index.json
  6. Create AnalysisJob (PENDING)
  7. Return reference_id + job_id

Follows workspace_storage pattern for file paths.
"""

import base64
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from capabilities.ig.models.reference_metadata import (
    AnalysisJob,
    ReferenceMetadata,
    UsagePolicy,
    content_hash_sha256,
)
from capabilities.ig.services.pin_failed_attempt_store import (
    PostgresIGPinFailedAttemptStore,
)
from capabilities.ig.services.reference_index import ReferenceIndex
from capabilities.ig.services.thumbnail_fetcher import fetch_thumbnail_bytes
from capabilities.ig.services.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)


def _format_download_exception(exc: Exception) -> str:
    parts = [type(exc).__name__]
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        parts.append(f"HTTP {exc.response.status_code}")
    detail = str(exc).strip()
    if detail:
        parts.append(detail)
    return ": ".join(parts)


def _record_failed_pin_attempt(
    *,
    workspace_id: str,
    source_handle: str,
    source_shortcode: str,
    source_url: str,
    image_url: str,
    parent_execution_id: Optional[str],
    trigger: Optional[str],
    base64_image_present: bool,
    error_kind: str,
    error_message: str,
    failure_payload: Optional[Dict[str, Any]] = None,
) -> None:
    try:
        store = PostgresIGPinFailedAttemptStore()
        store.record_failed_attempt(
            workspace_id=workspace_id,
            source_handle=source_handle,
            source_shortcode=source_shortcode,
            source_url=source_url,
            image_url=image_url,
            parent_execution_id=parent_execution_id,
            trigger=trigger,
            base64_image_present=base64_image_present,
            error_kind=error_kind,
            error_message=error_message,
            failure_payload=failure_payload,
        )
    except Exception as store_err:
        logger.warning(
            "[PinRef] Failed to persist pin_failed_attempt for %s/%s: %s",
            source_handle or "<unknown>",
            source_shortcode or "<unknown>",
            store_err,
        )


def _mark_failed_pin_attempt_recovered(
    *,
    workspace_id: str,
    source_handle: str,
    source_shortcode: str,
    source_url: str,
    image_url: str,
    reference_id: Optional[str],
) -> None:
    try:
        store = PostgresIGPinFailedAttemptStore()
        store.mark_recovered(
            workspace_id=workspace_id,
            source_handle=source_handle,
            source_shortcode=source_shortcode,
            source_url=source_url,
            image_url=image_url,
            reference_id=reference_id,
        )
    except Exception as store_err:
        logger.warning(
            "[PinRef] Failed to mark pin_failed_attempt recovered for %s/%s: %s",
            source_handle or "<unknown>",
            source_shortcode or "<unknown>",
            store_err,
        )


async def ig_pin_reference(
    workspace_id: str,
    image_url: str,
    source_handle: str = "",
    source_shortcode: str = "",
    source_url: str = "",
    tags: Optional[List[str]] = None,
    collections: Optional[List[str]] = None,
    pinned_by: str = "",
    base64_image: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Pin a reference image to workspace assets.

    Downloads the image, computes content hash for deduplication,
    saves metadata, and creates a PENDING analysis job.

    Args:
        workspace_id: Target workspace.
        image_url: URL to download the image from.
        source_handle: Instagram handle (e.g. "@fashionista").
        source_shortcode: Instagram post shortcode.
        source_url: Full post URL.
        tags: Manual tags to apply.
        collections: Collections to assign.
        pinned_by: Actor ID.

    Returns:
        Dict with reference_id, content_hash, analysis_job, and status.
    """
    tags = tags or []
    collections = collections or []
    parent_execution_id = str(kwargs.get("parent_execution_id") or "").strip() or None
    trigger = (
        str(kwargs.get("trigger") or kwargs.get("pin_trigger") or "").strip()
        or "manual_pin"
    )

    # Initialize storage
    storage = WorkspaceStorage(workspace_id, "ig")
    refs_path = storage.get_references_path()
    index = ReferenceIndex(refs_path)

    # Step 1: Download image or decode base64
    image_data = None
    etag = None
    resp = None

    if base64_image:
        try:
            # base64_image usually comes as 'data:image/jpeg;base64,/9j/4AAQSkZJ...'
            if "," in base64_image:
                base64_str = base64_image.split(",")[1]
            else:
                base64_str = base64_image
            image_data = base64.b64decode(base64_str)
            logger.info(f"[PinRef] Successfully decoded base64 image ({len(image_data)} bytes)")
        except Exception as e:
            logger.warning(
                f"[PinRef] Failed to decode base64_image: {e}. Falling back to image_url download."
            )
            # Fallback to downloading if base64 fails

    if not image_data:
        try:
            downloaded = await fetch_thumbnail_bytes(
                source_shortcode or None,
                preferred_url=image_url,
                timeout=30.0,
            )
            image_data = downloaded.content
            resp = downloaded.response
            etag = resp.headers.get("ETag")
        except Exception as e:
            formatted_error = _format_download_exception(e)
            logger.error(
                "[PinRef] Failed to download %s: %s. Pin skipped; no reference created; no analysis enqueued.",
                image_url,
                formatted_error,
            )
            http_status = None
            if isinstance(e, httpx.HTTPStatusError) and e.response is not None:
                http_status = e.response.status_code
            _record_failed_pin_attempt(
                workspace_id=workspace_id,
                source_handle=source_handle,
                source_shortcode=source_shortcode,
                source_url=source_url,
                image_url=image_url,
                parent_execution_id=parent_execution_id,
                trigger=trigger,
                base64_image_present=bool(base64_image),
                error_kind="download_failed",
                error_message=f"Failed to download image: {formatted_error}",
                failure_payload={
                    "exception_type": type(e).__name__,
                    "http_status": http_status,
                    "image_url": image_url,
                    "source_url": source_url,
                    "trigger": trigger,
                    "source_shortcode": source_shortcode,
                },
            )
            return {
                "status": "error",
                "error": f"Failed to download image: {formatted_error}",
                "error_kind": "download_failed",
                "final_disposition": "skipped_no_reference",
            }

    # Step 2: Compute content_hash
    c_hash = content_hash_sha256(image_data)

    # Step 2.5: Check against Blacklisted Hashes (CDN Expiry / IG 403 Image)
    BLACKLIST_HASHES = {
        "sha256:16ccd54052738391",  # IG CDN Token Expired Fallback Image
        "sha256:621e08122615f6fd",  # IG generic HTTP 403 error page image bytes
    }
    
    if c_hash in BLACKLIST_HASHES:
        logger.warning(
            "[PinRef] Downloaded image matched known error/fallback hash (%s). "
            "Pin skipped; no reference created; no analysis enqueued.",
            c_hash,
        )
        _record_failed_pin_attempt(
            workspace_id=workspace_id,
            source_handle=source_handle,
            source_shortcode=source_shortcode,
            source_url=source_url,
            image_url=image_url,
            parent_execution_id=parent_execution_id,
            trigger=trigger,
            base64_image_present=bool(base64_image),
            error_kind="invalid_download_payload",
            error_message=(
                f"Downloaded CDN image is invalid or expired (Matched error hash: {c_hash})"
            ),
            failure_payload={
                "content_hash": c_hash,
                "image_url": image_url,
                "source_url": source_url,
                "trigger": trigger,
            },
        )
        return {
            "status": "error",
            "error": f"Downloaded CDN image is invalid or expired (Matched error hash: {c_hash})",
            "error_kind": "invalid_download_payload",
            "final_disposition": "skipped_no_reference",
        }

    # Step 2.8: Pre-populate the proxy cache for the frontend UI grid (Guaranteed hit)
    if source_shortcode:
        try:
            from pathlib import Path
            cache_dir = Path("/app/data/ig_thumbnails")
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = cache_dir / f"{source_shortcode}.jpg"
            cache_path.write_bytes(image_data)
        except Exception as cache_err:
            logger.warning(f"[PinRef] Failed to pre-populate cache for {source_shortcode}: {cache_err}")

    # Step 3: Check for duplicate
    existing = index.find_by_content_hash(c_hash)
    if existing:
        ref_id = existing["reference_id"]
        logger.info("[PinRef] Duplicate found: %s (hash=%s)", ref_id, c_hash)

        # Merge tags into existing metadata
        merged_meta = _merge_tags_on_disk(
            refs_path,
            existing,
            tags,
            source_handle,
            source_shortcode,
        )

        # Rebuild the index entry from canonical metadata, not the stale index view.
        if merged_meta is not None:
            index.add_entry(ref_id, merged_meta.model_dump())
            _mark_failed_pin_attempt_recovered(
                workspace_id=workspace_id,
                source_handle=source_handle,
                source_shortcode=source_shortcode,
                source_url=source_url,
                image_url=image_url,
                reference_id=ref_id,
            )

        return {
            "status": "duplicate",
            "reference_id": ref_id,
            "content_hash": c_hash,
            "message": f"Image already pinned as {ref_id}. Tags merged.",
        }

    # Step 4: Save image + metadata
    if source_handle:
        account_path = storage.get_reference_account_path(source_handle)
    else:
        account_path = storage.get_references_unsorted_path()

    # Determine file extension from content-type
    content_type = resp.headers.get("Content-Type", "image/jpeg") if resp else "image/jpeg"
    ext = _guess_extension(content_type)
    filename_base = source_shortcode or hashlib.md5(image_url.encode()).hexdigest()[:12]

    image_file = account_path / f"{filename_base}{ext}"
    metadata_file = account_path / f"{filename_base}.json"

    # Write image
    image_file.write_bytes(image_data)

    # Create metadata
    handle = source_handle if source_handle.startswith("@") else f"@{source_handle}" if source_handle else ""
    job = AnalysisJob.create_pending()
    job.idempotency_key = AnalysisJob.make_idempotency_key(
        job.job_id, c_hash, "1.0"
    )

    metadata = ReferenceMetadata(
        content_hash=c_hash,
        source_fetch_etag=etag,
        source_handle=handle,
        source_shortcode=source_shortcode,

        source_url=source_url,
        pinned_by=pinned_by,
        tags=tags,
        collections=collections,
        usage_policy=UsagePolicy(),
        analysis_job=job,
    )

    # Write metadata JSON
    metadata_file.write_text(metadata.to_json(), encoding="utf-8")

    # Step 5: Update index
    index.add_entry(metadata.reference_id, metadata.model_dump())
    _mark_failed_pin_attempt_recovered(
        workspace_id=workspace_id,
        source_handle=source_handle,
        source_shortcode=source_shortcode,
        source_url=source_url,
        image_url=image_url,
        reference_id=metadata.reference_id,
    )

    logger.info(
        "[PinRef] Pinned %s → %s (hash=%s, job=%s)",
        image_url[:60],
        metadata.reference_id,
        c_hash,
        job.job_id,
    )

    return {
        "status": "pinned",
        "reference_id": metadata.reference_id,
        "content_hash": c_hash,
        "image_path": str(image_file),
        "metadata_path": str(metadata_file),
        "analysis_job": {
            "job_id": job.job_id,
            "status": job.status,
        },
    }


def _merge_tags_on_disk(
    refs_path: Path,
    existing_entry: Dict[str, Any],
    new_tags: List[str],
    source_handle: str,
    source_shortcode: str,
) -> Optional[ReferenceMetadata]:
    """Merge tags into existing reference metadata on disk and return it."""
    handle_dir = existing_entry.get("source_handle", "_unsorted")
    shortcode = existing_entry.get("source_shortcode", "")

    if handle_dir and not handle_dir.startswith("_"):
        metadata_file = refs_path / handle_dir / f"{shortcode}.json"
    else:
        metadata_file = refs_path / "_unsorted" / f"{shortcode}.json"

    if not metadata_file.exists():
        return None

    try:
        meta = ReferenceMetadata.from_json(metadata_file.read_text(encoding="utf-8"))
        meta.merge_tags(new_tags)

        # Add alias if different source
        if source_handle and source_shortcode:
            norm_handle = source_handle if source_handle.startswith("@") else f"@{source_handle}"
            if norm_handle != meta.source_handle:
                meta.add_alias(norm_handle, source_shortcode)

        metadata_file.write_text(meta.to_json(), encoding="utf-8")
        return meta
    except Exception as e:
        logger.warning("[PinRef] Failed to merge tags for %s: %s", metadata_file, e)
        return None


def _guess_extension(content_type: str) -> str:
    """Guess file extension from content-type."""
    ct = content_type.lower().split(";")[0].strip()
    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    return mapping.get(ct, ".jpg")
