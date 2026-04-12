"""
IG data fetch utilities.

Fetch posts/reels/stories via the IG Graph API and store media files in the workspace.
"""

import logging
import httpx
import asyncio
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime

try:
    from capabilities.ig.services.cloud_registry_client import CloudRegistryClient
    from capabilities.ig.services.instagram_api_client import InstagramAPIClient
    from capabilities.ig.services.workspace_storage import WorkspaceStorage
except ImportError:
    # Fallback for local development
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from services.cloud_registry_client import CloudRegistryClient
    from services.instagram_api_client import InstagramAPIClient
    from services.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)


async def ig_fetch_posts(
    channel_config_id: int,
    workspace_id: str,
    media_type: Optional[str] = None,  # IMAGE, VIDEO, CAROUSEL_ALBUM
    limit: int = 25,
    since: Optional[str] = None,  # ISO timestamp
    until: Optional[str] = None,
    trace_id: Optional[str] = None,
    runtime_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch Instagram posts via the IG Graph API.

    Args:
        channel_config_id: ChannelConfig ID (managed by cloud registry)
        workspace_id: Mindscape workspace ID
        media_type: Media type filter (IMAGE, VIDEO, CAROUSEL_ALBUM)
        limit: Page size
        since: Start time (ISO 8601)
        until: End time (ISO 8601)
        trace_id: Trace ID (optional)
        runtime_id: Runtime environment ID (resolve registry URL from DB)

    Returns:
        {"posts": [...], "media_files": [...], "metadata": {...}}
    """
    try:
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

        # Fetch media list.
        media_data = await api_client.get_media_list(
            ig_business_account_id=ig_business_account_id,
            media_type=media_type,
            limit=limit,
            since=since,
            until=until,
        )

        posts = media_data.get("data", [])

        # Download media files into workspace storage.
        storage = WorkspaceStorage(workspace_id=workspace_id)
        media_files = []

        for post in posts:
            media_url = post.get("media_url")
            if media_url:
                try:
                    # Download media file.
                    media_file_path = await _download_media_file(
                        media_url=media_url,
                        media_id=post.get("id"),
                        workspace_id=workspace_id,
                        storage=storage,
                    )
                    if media_file_path:
                        media_files.append(media_file_path)
                        post["local_media_path"] = media_file_path
                except Exception as e:
                    logger.warning(
                        f"Failed to download media for post {post.get('id')}: {e}"
                    )

        # Build metadata.
        metadata = {
            "channel_config_id": channel_config_id,
            "workspace_id": workspace_id,
            "fetched_at": datetime.now().isoformat(),
            "count": len(posts),
            "media_type": media_type,
            "since": since,
            "until": until,
        }

        logger.info(
            f"Fetched {len(posts)} posts from Instagram "
            f"(channel_config_id={channel_config_id}, workspace_id={workspace_id})"
        )

        return {"posts": posts, "media_files": media_files, "metadata": metadata}

    except Exception as e:
        logger.error(f"Failed to fetch posts: {e}", exc_info=True)
        raise


async def ig_fetch_reels(
    channel_config_id: int,
    workspace_id: str,
    limit: int = 25,
    trace_id: Optional[str] = None,
    runtime_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch Instagram reels via the IG Graph API.

    Args:
        channel_config_id: ChannelConfig ID (managed by cloud registry)
        workspace_id: Mindscape workspace ID
        limit: Page size
        trace_id: Trace ID (optional)
        runtime_id: Runtime environment ID (resolve registry URL from DB)

    Returns:
        {"reels": [...], "media_files": [...], "metadata": {...}}
    """
    try:
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

        # Fetch reels (media_type=VIDEO filter).
        media_data = await api_client.get_media_list(
            ig_business_account_id=ig_business_account_id,
            media_type="VIDEO",  # Reels are typically VIDEO media
            limit=limit,
        )

        reels = media_data.get("data", [])

        # Download media files into workspace storage.
        storage = WorkspaceStorage(workspace_id=workspace_id)
        media_files = []

        for reel in reels:
            media_url = reel.get("media_url") or reel.get("thumbnail_url")
            if media_url:
                try:
                    media_file_path = await _download_media_file(
                        media_url=media_url,
                        media_id=reel.get("id"),
                        workspace_id=workspace_id,
                        storage=storage,
                    )
                    if media_file_path:
                        media_files.append(media_file_path)
                        reel["local_media_path"] = media_file_path
                except Exception as e:
                    logger.warning(
                        f"Failed to download media for reel {reel.get('id')}: {e}"
                    )

        # Build metadata.
        metadata = {
            "channel_config_id": channel_config_id,
            "workspace_id": workspace_id,
            "fetched_at": datetime.now().isoformat(),
            "count": len(reels),
        }

        logger.info(
            f"Fetched {len(reels)} reels from Instagram "
            f"(channel_config_id={channel_config_id}, workspace_id={workspace_id})"
        )

        return {"reels": reels, "media_files": media_files, "metadata": metadata}

    except Exception as e:
        logger.error(f"Failed to fetch reels: {e}", exc_info=True)
        raise


async def ig_fetch_stories(
    channel_config_id: int,
    workspace_id: str,
    limit: int = 25,
    trace_id: Optional[str] = None,
    runtime_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch Instagram stories (available within ~24 hours).

    Args:
        channel_config_id: ChannelConfig ID (managed by cloud registry)
        workspace_id: Mindscape workspace ID
        limit: Page size
        trace_id: Trace ID (optional)
        runtime_id: Runtime environment ID (resolve registry URL from DB)

    Returns:
        {"stories": [...], "media_files": [...], "metadata": {...}}
    """
    try:
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

        # Fetch stories.
        stories_data = await api_client.get_stories(
            ig_business_account_id=ig_business_account_id, limit=limit
        )

        stories = stories_data.get("data", [])

        # Download media files into workspace storage.
        storage = WorkspaceStorage(workspace_id=workspace_id)
        media_files = []

        for story in stories:
            media_url = story.get("media_url")
            if media_url:
                try:
                    media_file_path = await _download_media_file(
                        media_url=media_url,
                        media_id=story.get("id"),
                        workspace_id=workspace_id,
                        storage=storage,
                    )
                    if media_file_path:
                        media_files.append(media_file_path)
                        story["local_media_path"] = media_file_path
                except Exception as e:
                    logger.warning(
                        f"Failed to download media for story {story.get('id')}: {e}"
                    )

        # Build metadata.
        metadata = {
            "channel_config_id": channel_config_id,
            "workspace_id": workspace_id,
            "fetched_at": datetime.now().isoformat(),
            "count": len(stories),
            "note": "Stories are only available within 24 hours",
        }

        logger.info(
            f"Fetched {len(stories)} stories from Instagram "
            f"(channel_config_id={channel_config_id}, workspace_id={workspace_id})"
        )

        return {"stories": stories, "media_files": media_files, "metadata": metadata}

    except Exception as e:
        logger.error(f"Failed to fetch stories: {e}", exc_info=True)
        raise


async def _download_media_file(
    media_url: str, media_id: str, workspace_id: str, storage: WorkspaceStorage
) -> Optional[str]:
    """
    Download a media file into workspace storage.

    Args:
        media_url: Media URL
        media_id: Media ID
        workspace_id: Workspace ID
        storage: WorkspaceStorage instance

    Returns:
        Relative file path in the workspace, or None if download fails.
    """
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(media_url)
            response.raise_for_status()

            # Determine file extension.
            content_type = response.headers.get("content-type", "")
            if "image" in content_type:
                ext = ".jpg" if "jpeg" in content_type else ".png"
            elif "video" in content_type:
                ext = ".mp4"
            else:
                ext = Path(media_url).suffix or ".bin"

            # Save to workspace storage.
            relative_path = f"ig_media/{media_id}{ext}"
            file_path = storage.get_path(relative_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, "wb") as f:
                f.write(response.content)

            logger.debug(f"Downloaded media {media_id} to {relative_path}")
            return relative_path

    except Exception as e:
        logger.error(f"Failed to download media {media_id}: {e}")
        return None
