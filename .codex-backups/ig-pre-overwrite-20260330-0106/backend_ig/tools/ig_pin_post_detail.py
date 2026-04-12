"""
ig_pin_post_detail — Orchestrate: fetch post detail → pin all images → enqueue analysis.

Supports both single shortcode and batch mode (multiple shortcodes).
For carousel posts, pins each slide as a separate reference linked via carousel_parent_id.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from capabilities.ig.services.pin_failed_attempt_store import PostgresIGPinFailedAttemptStore
from capabilities.ig.tools.ig_fetch_post_detail import ig_fetch_post_detail
from capabilities.ig.tools.ig_pin_reference import ig_pin_reference

logger = logging.getLogger(__name__)


async def _pin_single_post(
    workspace_id: str,
    shortcode: str,
    source_handle: str = "",
    tags: Optional[List[str]] = None,
    browser_profile: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch detail for one post and pin all its images."""
    tags = tags or []

    # Step 1: Fetch post detail via browser
    detail = await ig_fetch_post_detail(
        shortcode=shortcode,
        browser_profile=browser_profile,
    )

    if detail.get("status") != "success":
        return {
            "shortcode": shortcode,
            "status": "error",
            "error": detail.get("error", "Unknown error"),
        }

    images = detail.get("images", [])
    if not images:
        return {
            "shortcode": shortcode,
            "status": "error",
            "error": "No images extracted from post",
        }

    handle = detail.get("source_handle", source_handle)
    caption = detail.get("caption", "")
    like_count = detail.get("like_count")
    comment_count = detail.get("comment_count")
    timestamp = detail.get("timestamp", "")
    media_type = detail.get("media_type", "IMAGE")
    is_carousel = media_type == "CAROUSEL_ALBUM"
    carousel_total = len(images) if is_carousel else None

    # Step 2: Pin each image
    pinned_refs: List[Dict[str, Any]] = []
    parent_ref_id: Optional[str] = None

    for img in images:
        idx = img.get("index", 0)
        image_url = img.get("url", "")
        base64_jpeg = img.get("base64_jpeg")

        # Build shortcode suffix for carousel slides
        pin_shortcode = f"{shortcode}_c{idx}" if is_carousel and idx > 0 else shortcode

        pin_tags = list(tags)
        if is_carousel:
            pin_tags.append("carousel")
            pin_tags.append(f"slide_{idx}")

        try:
            result = await ig_pin_reference(
                workspace_id=workspace_id,
                image_url=image_url,
                source_handle=handle.lstrip("@") if handle.startswith("@") else handle,
                source_shortcode=pin_shortcode,
                source_url=detail.get("post_url", ""),
                tags=pin_tags,
                base64_image=base64_jpeg,
                trigger="post_detail_pin",
            )

            ref_id = result.get("reference_id", "")

            # Track parent reference ID (first slide)
            if idx == 0:
                parent_ref_id = ref_id

            # Update reference metadata with carousel + post-detail fields
            if ref_id and result.get("status") in ("pinned", "duplicate"):
                _update_post_detail_metadata(
                    workspace_id=workspace_id,
                    reference_id=ref_id,
                    carousel_index=idx if is_carousel else None,
                    carousel_parent_id=parent_ref_id if is_carousel and idx > 0 else None,
                    carousel_total=carousel_total,
                    post_caption=caption,
                    post_like_count=like_count,
                    post_comment_count=comment_count,
                    post_timestamp=timestamp,
                )

            # Enqueue analysis for newly pinned refs
            if ref_id and result.get("status") == "pinned":
                try:
                    from capabilities.ig.services.auto_analyze import enqueue_reference_analysis
                    enqueue_reference_analysis(
                        workspace_id=workspace_id,
                        reference_id=ref_id,
                        image_url=image_url,
                        source_handle=handle,
                    )
                except Exception as enq_err:
                    logger.warning(f"[PinPostDetail] Auto-analyze enqueue failed: {enq_err}")

            pinned_refs.append({
                "reference_id": ref_id,
                "shortcode": pin_shortcode,
                "carousel_index": idx if is_carousel else None,
                "status": result.get("status", "unknown"),
            })

        except Exception as e:
            logger.error(f"[PinPostDetail] Failed to pin image {idx} of {shortcode}: {e}")
            try:
                PostgresIGPinFailedAttemptStore().record_failed_attempt(
                    workspace_id=workspace_id,
                    source_handle=handle.lstrip("@") if handle.startswith("@") else handle,
                    source_shortcode=pin_shortcode,
                    source_url=detail.get("post_url", ""),
                    image_url=image_url,
                    parent_execution_id=None,
                    trigger="post_detail_pin",
                    base64_image_present=bool(base64_jpeg),
                    error_kind="pin_exception",
                    error_message=str(e),
                    failure_payload={
                        "exception_type": type(e).__name__,
                        "shortcode": shortcode,
                        "carousel_index": idx if is_carousel else None,
                    },
                )
            except Exception as store_err:
                logger.warning(
                    "[PinPostDetail] Failed to persist pin_exception for %s[%s]: %s",
                    shortcode,
                    idx,
                    store_err,
                )
            pinned_refs.append({
                "shortcode": pin_shortcode,
                "carousel_index": idx if is_carousel else None,
                "status": "error",
                "error": str(e),
            })

    # Backfill parent_ref_id on the parent itself (for carousel)
    if is_carousel and parent_ref_id:
        _update_post_detail_metadata(
            workspace_id=workspace_id,
            reference_id=parent_ref_id,
            carousel_index=0,
            carousel_parent_id=None,  # parent points to itself implicitly
            carousel_total=carousel_total,
            post_caption=caption,
            post_like_count=like_count,
            post_comment_count=comment_count,
            post_timestamp=timestamp,
        )

    new_count = sum(1 for r in pinned_refs if r.get("status") == "pinned")
    dup_count = sum(1 for r in pinned_refs if r.get("status") == "duplicate")

    return {
        "shortcode": shortcode,
        "status": "success",
        "media_type": media_type,
        "caption_length": len(caption),
        "image_count": len(images),
        "reference_ids": [r.get("reference_id") for r in pinned_refs if r.get("reference_id")],
        "carousel_parent_id": parent_ref_id if is_carousel else None,
        "new_pinned": new_count,
        "duplicates": dup_count,
        "details": pinned_refs,
    }


def _update_post_detail_metadata(
    workspace_id: str,
    reference_id: str,
    carousel_index: Optional[int],
    carousel_parent_id: Optional[str],
    carousel_total: Optional[int],
    post_caption: Optional[str],
    post_like_count: Optional[int],
    post_comment_count: Optional[int],
    post_timestamp: Optional[str],
) -> None:
    """Update reference metadata with post-detail and carousel fields."""
    try:
        from capabilities.ig.models.reference_metadata import ReferenceMetadata
        from capabilities.ig.services.reference_index import ReferenceIndex
        from capabilities.ig.services.workspace_storage import WorkspaceStorage
        from capabilities.ig.tools.ig_analyze_reference import _find_metadata_file

        storage = WorkspaceStorage(workspace_id, "ig")
        refs_path = storage.get_references_path()
        index = ReferenceIndex(refs_path)

        metadata_path = _find_metadata_file(refs_path, reference_id, index)
        if not metadata_path or not metadata_path.exists():
            logger.warning(f"[PinPostDetail] Metadata not found for {reference_id}")
            return

        meta = ReferenceMetadata.from_json(metadata_path.read_text(encoding="utf-8"))

        # Update carousel fields
        if carousel_index is not None:
            meta.carousel_index = carousel_index
        if carousel_parent_id is not None:
            meta.carousel_parent_id = carousel_parent_id
        if carousel_total is not None:
            meta.carousel_total = carousel_total

        # Update post-level metadata
        if post_caption:
            meta.post_caption = post_caption
        if post_like_count is not None:
            meta.post_like_count = post_like_count
        if post_comment_count is not None:
            meta.post_comment_count = post_comment_count
        if post_timestamp:
            meta.post_timestamp = post_timestamp

        metadata_path.write_text(meta.to_json(), encoding="utf-8")
        index.add_entry(reference_id, meta.model_dump())

    except Exception as e:
        logger.warning(f"[PinPostDetail] Failed to update metadata for {reference_id}: {e}")


async def ig_pin_post_detail(
    workspace_id: str,
    shortcodes: Optional[List[str]] = None,
    shortcode: Optional[str] = None,
    source_handle: str = "",
    tags: Optional[List[str]] = None,
    browser_profile: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Pin post detail for one or more IG posts.

    Fetches each post via browser, extracts all carousel images,
    pins each image as a reference, and enqueues analysis.

    Args:
        workspace_id: Target workspace.
        shortcodes: List of shortcodes to process (batch mode).
        shortcode: Single shortcode (convenience alias).
        source_handle: Optional handle hint.
        tags: Tags to apply to all pinned references.
        browser_profile: Optional browser profile path.

    Returns:
        Summary with per-post results.
    """
    # Normalize input
    codes = shortcodes or []
    if shortcode and shortcode not in codes:
        codes.append(shortcode)

    if not codes:
        return {"status": "error", "error": "No shortcodes provided"}

    tags = tags or ["post_detail"]

    # Task grouping for batch
    import uuid
    batch_parent_id = None
    _parent_ctx_token = None

    if len(codes) > 1:
        try:
            from backend.app.services.parameter_adapter.context import active_parent_execution_id
            batch_parent_id = f"post-detail-{uuid.uuid4().hex[:8]}"
            _parent_ctx_token = active_parent_execution_id.set(batch_parent_id)
        except ImportError:
            pass

    try:
        results = []
        for code in codes:
            logger.info(f"[PinPostDetail] Processing {code} ({codes.index(code)+1}/{len(codes)})")
            result = await _pin_single_post(
                workspace_id=workspace_id,
                shortcode=code,
                source_handle=source_handle,
                tags=tags,
                browser_profile=browser_profile,
            )
            results.append(result)

        total_new = sum(r.get("new_pinned", 0) for r in results)
        total_dup = sum(r.get("duplicates", 0) for r in results)
        total_images = sum(r.get("image_count", 0) for r in results)
        success_count = sum(1 for r in results if r.get("status") == "success")

        return {
            "status": "success",
            "batch_parent_id": batch_parent_id,
            "posts_processed": len(codes),
            "posts_succeeded": success_count,
            "total_images": total_images,
            "total_new_pinned": total_new,
            "total_duplicates": total_dup,
            "results": results,
        }

    finally:
        if _parent_ctx_token is not None:
            try:
                from backend.app.services.parameter_adapter.context import active_parent_execution_id
                active_parent_execution_id.reset(_parent_ctx_token)
            except Exception:
                pass
