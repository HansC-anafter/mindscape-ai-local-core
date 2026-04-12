"""
IG publishing utilities.

Publish content to Instagram (supports photo, reel, carousel) via the IG Graph API.
"""

import logging
import os
import mimetypes
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime

import httpx

# --- Resilient imports: each service imported independently so a single
#     missing transitive dep (e.g. cloud_integration_config) doesn't null
#     out unrelated symbols like WorkspaceStorage.

CloudRegistryClient = None  # type: ignore[assignment,misc]
InstagramAPIClient = None  # type: ignore[assignment,misc]
WorkspaceStorage = None  # type: ignore[assignment,misc]


def get_storage_slot():  # type: ignore[misc]
    raise ImportError(
        "cloud_registry_client / storage_slot not available in this environment"
    )


def _try_import(primary: str, fallback: str, attr: str):
    """Try two import paths, return the attribute or None."""
    import importlib

    for mod_path in (primary, fallback):
        if not mod_path:
            continue
        try:
            mod = importlib.import_module(mod_path)
            return getattr(mod, attr)
        except Exception:
            continue
    return None


CloudRegistryClient = (
    _try_import(
        "capabilities.ig.services.cloud_registry_client",
        "services.cloud_registry_client",
        "CloudRegistryClient",
    )
    or CloudRegistryClient
)

InstagramAPIClient = (
    _try_import(
        "capabilities.ig.services.instagram_api_client",
        "services.instagram_api_client",
        "InstagramAPIClient",
    )
    or InstagramAPIClient
)

WorkspaceStorage = (
    _try_import(
        "capabilities.ig.services.workspace_storage",
        "services.workspace_storage",
        "WorkspaceStorage",
    )
    or WorkspaceStorage
)

_slot_fn = _try_import(
    "capabilities.ig.services.storage_slot",
    "services.storage_slot",
    "get_storage_slot",
)
if _slot_fn is not None:
    get_storage_slot = _slot_fn  # type: ignore[assignment]


logger = logging.getLogger(__name__)


async def ig_validate_media(
    media_path: str,
    media_type: str,  # photo, reel, carousel
    workspace_id: str,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Validate media file format and size limits.

    Args:
        media_path: Media path (workspace-relative or absolute)
        media_type: Media type (photo, reel, carousel)
        workspace_id: Mindscape workspace ID
        trace_id: Trace ID (optional)

    Returns:
        {"valid": bool, "media_info": {...}, "errors": [...]}
    """
    errors = []
    media_info = {}

    try:
        # If media_path is a URL, skip local file validation.
        if media_path.startswith("http://") or media_path.startswith("https://"):
            logger.info(f"Media path is a URL, skipping local validation: {media_path}")
            vr = {"valid": True, "errors": [], "source": "url"}
            mi = {"media_url": media_path, "source": "url"}
            return {"validation_result": vr, "media_info": mi}

        # Resolve file path.
        storage = WorkspaceStorage(workspace_id=workspace_id, capability_code="ig")

        if os.path.isabs(media_path):
            file_path = Path(media_path)
        else:
            file_path = storage.get_capability_root() / media_path

        if not file_path.exists():
            vr = {"valid": False, "errors": [f"Media file not found: {media_path}"]}
            return {"validation_result": vr, "media_info": {}}

        # Check file size.
        file_size = file_path.stat().st_size
        file_size_mb = file_size / (1024 * 1024)

        media_info["file_path"] = str(file_path)
        media_info["file_size"] = file_size
        media_info["file_size_mb"] = round(file_size_mb, 2)

        # Validate per media type.
        if media_type == "photo":
            # Photo: JPEG/PNG, max 30MB
            if file_size_mb > 30:
                errors.append(
                    f"Photo file size ({file_size_mb}MB) exceeds limit (30MB)"
                )

            # Validate format.
            mime_type, _ = mimetypes.guess_type(str(file_path))
            if mime_type not in ["image/jpeg", "image/png"]:
                errors.append(
                    f"Photo format ({mime_type}) not supported. Only JPEG/PNG allowed."
                )

            # Validate image dimensions.
            try:
                from PIL import Image  # lazy import — Pillow optional

                with Image.open(file_path) as img:
                    width, height = img.size
                    media_info["width"] = width
                    media_info["height"] = height

                    if width > 8192 or height > 8192:
                        errors.append(
                            f"Photo dimensions ({width}x{height}) exceed limit (8192x8192 pixels)"
                        )
            except Exception as e:
                errors.append(f"Failed to read image: {e}")

        elif media_type == "reel":
            # Reel: MP4/MOV, 3-90s, max 100MB (duration not validated here)
            if file_size_mb > 100:
                errors.append(
                    f"Reel file size ({file_size_mb}MB) exceeds limit (100MB)"
                )

            # Validate format.
            mime_type, _ = mimetypes.guess_type(str(file_path))
            if mime_type not in ["video/mp4", "video/quicktime"]:
                errors.append(
                    f"Reel format ({mime_type}) not supported. Only MP4/MOV allowed."
                )

            # TODO: Validate video duration (requires a video processing library).
            media_info["note"] = (
                "Video length validation requires video processing library"
            )

        elif media_type == "carousel":
            # Carousel: media_path must be a directory containing images.
            if file_path.is_dir():
                image_files = list(file_path.glob("*.jpg")) + list(
                    file_path.glob("*.png")
                )
                if not image_files:
                    errors.append("Carousel directory contains no image files")
                else:
                    media_info["image_count"] = len(image_files)
                    # Validate each image.
                    for img_file in image_files:
                        img_size = img_file.stat().st_size / (1024 * 1024)
                        if img_size > 30:
                            errors.append(
                                f"Carousel image {img_file.name} size ({img_size}MB) exceeds limit (30MB)"
                            )
            else:
                errors.append(
                    "Carousel media_path must be a directory containing image files"
                )

        elif media_type == "story":
            # Story publishing is not supported via Graph API.
            errors.append(
                "Stories publishing is not supported by Graph API (can only sync)"
            )

        else:
            errors.append(f"Unknown media_type: {media_type}")

        vr = {"valid": len(errors) == 0, "errors": errors}
        return {"validation_result": vr, "media_info": media_info}

    except Exception as e:
        logger.error(f"Failed to validate media: {e}", exc_info=True)
        vr = {"valid": False, "errors": [str(e)]}
        return {"validation_result": vr, "media_info": media_info}


async def ig_publish_post(
    channel_config_id: int,
    workspace_id: str,
    post_id: str,  # Post id generated by openseo/ig capability
    media_type: str,  # photo, reel, carousel
    media_path: str,  # Local media file path (workspace-relative or absolute)
    caption: str,
    hashtags: Optional[List[str]] = None,
    scheduled_publish_time: Optional[str] = None,  # ISO timestamp (photo only)
    location_id: Optional[str] = None,
    user_tags: Optional[List[Dict[str, Any]]] = None,
    cover_url: Optional[str] = None,  # reel only
    share_to_feed: bool = True,  # reel only
    trace_id: Optional[str] = None,
    runtime_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Publish an IG post/reel/carousel via the IG Graph API.

    Args:
        channel_config_id: ChannelConfig ID (managed by cloud registry)
        workspace_id: Mindscape workspace ID
        post_id: Post id (app-level)
        media_type: photo | reel | carousel
        media_path: Media path (workspace-relative or absolute)
        caption: Caption text
        hashtags: Hashtags to append to caption
        scheduled_publish_time: ISO 8601 timestamp (photo only)
        location_id: Optional location id
        user_tags: Optional user tags
        cover_url: Optional reel cover URL (reel only)
        share_to_feed: Share reel to feed (reel only)
        trace_id: Trace ID (optional)
        runtime_id: Runtime environment ID (resolve registry URL from DB)

    Returns:
        {"published_post": {...}, "media_id": "...", "permalink": "..."}
    """
    try:
        # Validate media file.
        validation_result = await ig_validate_media(
            media_path=media_path,
            media_type=media_type,
            workspace_id=workspace_id,
            trace_id=trace_id,
        )

        vr = validation_result.get("validation_result", validation_result)
        if not vr.get("valid", False):
            raise ValueError(
                f"Media validation failed: {', '.join(vr.get('errors', []))}"
            )

        # Fetch token/config from cloud registry.
        if runtime_id:
            registry_client = await CloudRegistryClient.from_runtime(runtime_id)
        else:
            registry_client = CloudRegistryClient()
        access_token = await registry_client.get_access_token(
            channel_config_id, workspace_id
        )
        app_secret = await registry_client.get_app_secret(
            channel_config_id, workspace_id
        )
        ig_business_account_id = await registry_client.get_ig_business_account_id(
            channel_config_id, workspace_id
        )

        if not ig_business_account_id:
            raise ValueError(
                f"ig_business_account_id not found for channel config {channel_config_id}. "
                f"Please ensure OAuth authorization is completed in cloud registry."
            )

        # Initialize IG Graph API client.
        api_client = InstagramAPIClient(
            channel_config_id=channel_config_id,
            access_token=access_token,
            app_secret=app_secret,
        )

        # Prepare caption (append hashtags).
        final_caption = caption
        if hashtags:
            hashtag_text = " ".join([f"#{tag}" for tag in hashtags])
            final_caption = f"{caption}\n\n{hashtag_text}"

        # Upload media to a public URL (IG Graph API requires publicly accessible URLs).

        if media_path.startswith("http://") or media_path.startswith("https://"):
            # Already a public URL — use directly, skip upload.
            media_url = media_path
            file_path = None
        else:
            storage = WorkspaceStorage(workspace_id=workspace_id, capability_code="ig")
            if os.path.isabs(media_path):
                file_path = Path(media_path)
            else:
                file_path = storage.get_capability_root() / media_path

            media_url = await _upload_media_to_public_storage(
                file_path=file_path, media_type=media_type, workspace_id=workspace_id
            )

        # Publish per media type.
        if media_type == "photo":
            result = await api_client.publish_photo(
                ig_business_account_id=ig_business_account_id,
                image_url=media_url,
                caption=final_caption,
                location_id=location_id,
                user_tags=user_tags,
                scheduled_publish_time=scheduled_publish_time,
            )

        elif media_type == "reel":
            if scheduled_publish_time:
                raise ValueError(
                    "Reel does not support scheduled publishing (must publish immediately)"
                )

            result = await api_client.publish_reel(
                ig_business_account_id=ig_business_account_id,
                video_url=media_url,
                caption=final_caption,
                cover_url=cover_url,
                share_to_feed=share_to_feed,
            )

        elif media_type == "carousel":
            # Carousel: create child containers for each image first.
            if file_path.is_dir():
                image_files = list(file_path.glob("*.jpg")) + list(
                    file_path.glob("*.png")
                )
                children = []

                for img_file in image_files:
                    img_url = await _upload_media_to_public_storage(
                        file_path=img_file,
                        media_type="photo",
                        workspace_id=workspace_id,
                    )

                    # Create a container for each image.
                    container_result = await api_client._request_with_retry(
                        method="POST",
                        endpoint=f"/{ig_business_account_id}/media",
                        params={"image_url": img_url, "is_carousel_item": True},
                    )
                    children.append(container_result.get("id"))

                result = await api_client.publish_carousel(
                    ig_business_account_id=ig_business_account_id,
                    children=children,
                    caption=final_caption,
                    location_id=location_id,
                    scheduled_publish_time=scheduled_publish_time,
                )
            else:
                raise ValueError(
                    "Carousel media_path must be a directory containing image files"
                )

        else:
            raise ValueError(f"Unsupported media_type: {media_type}")

        # Build result payload.
        published_post = {
            "post_id": post_id,
            "media_type": media_type,
            "media_id": result.get("media_id") or result.get("creation_id"),
            "permalink": result.get("permalink"),
            "scheduled": result.get("scheduled", False),
            "scheduled_publish_time": result.get("scheduled_publish_time"),
            "published_at": (
                datetime.now().isoformat() if not result.get("scheduled") else None
            ),
            "channel_config_id": channel_config_id,
            "workspace_id": workspace_id,
        }

        logger.info(
            f"Published {media_type} to Instagram "
            f"(channel_config_id={channel_config_id}, workspace_id={workspace_id}, "
            f"media_id={published_post['media_id']})"
        )

        return {
            "published_post": published_post,
            "media_id": published_post["media_id"],
            "permalink": published_post["permalink"],
        }

    except Exception as e:
        logger.error(f"Failed to publish post: {e}", exc_info=True)
        raise


async def _upload_media_to_public_storage(
    file_path: Path, media_type: str, workspace_id: str, trace_id: Optional[str] = None
) -> str:
    """
    Upload a media file to public storage via the configured StorageSlot.

    The backend is selected by MINDSCAPE_STORAGE_SLOT env var:
      - "site_hub" (default): upload via site-hub asset proxy
      - "s3": upload to S3-compatible bucket
      - "local": localhost serve (development only)

    Args:
        file_path: Local file path
        media_type: Media type
        workspace_id: Workspace ID
        trace_id: Optional trace ID

    Returns:
        Public HTTPS URL
    """
    slot = get_storage_slot()
    return await slot.upload(
        file_path=file_path,
        media_type=media_type,
        workspace_id=workspace_id,
        trace_id=trace_id,
    )
