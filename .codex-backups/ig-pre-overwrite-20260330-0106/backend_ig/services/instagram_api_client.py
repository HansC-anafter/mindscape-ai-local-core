"""
Instagram Graph API client.

Provides a thin async wrapper with basic rate limiting, retries/backoff,
and optional appsecret_proof support.
"""

import os
import logging
import httpx
import hmac
import hashlib
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


class InstagramAPIClient:
    """Instagram Graph API client."""

    def __init__(
        self,
        channel_config_id: int,
        access_token: str,
        app_secret: Optional[str] = None,
    ):
        """
        Initialize the IG Graph API client.

        Args:
            channel_config_id: ChannelConfig ID
            access_token: Access token
            app_secret: App secret (optional, for appsecret_proof)
        """
        self.base_url = "https://graph.facebook.com/v18.0"
        self.channel_config_id = channel_config_id
        self.access_token = access_token
        self.app_secret = app_secret

        # Rate limit configuration.
        self.rate_limit_per_second = 10  # 10 req/s per app
        self._request_times: List[datetime] = []
        self._lock = asyncio.Lock()

    def generate_app_secret_proof(self) -> Optional[str]:
        """
        Generate appsecret_proof (HMAC-SHA256(app_secret, access_token)).

        Returns:
            appsecret_proof string, or None if app_secret is not available
        """
        if not self.app_secret:
            return None

        return hmac.new(
            self.app_secret.encode("utf-8"),
            self.access_token.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def _wait_for_rate_limit(self):
        """
        Enforce a simple per-second rate limit.
        """
        async with self._lock:
            now = datetime.now()
            # Drop request timestamps older than 1 second.
            self._request_times = [
                t for t in self._request_times if (now - t).total_seconds() < 1.0
            ]

            # If we've reached the limit, sleep until the window advances.
            if len(self._request_times) >= self.rate_limit_per_second:
                wait_time = 1.0 - (now - self._request_times[0]).total_seconds()
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                    # Recompute after sleep.
                    now = datetime.now()
                    self._request_times = [
                        t
                        for t in self._request_times
                        if (now - t).total_seconds() < 1.0
                    ]

            # Record this request timestamp.
            self._request_times.append(now)

    async def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
        initial_delay: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Send a request with retries and exponential backoff.

        Args:
            method: HTTP method (GET, POST)
            endpoint: API endpoint (without base_url)
            params: Query/body params
            max_retries: Max retry attempts
            initial_delay: Initial delay (seconds)

        Returns:
            Parsed JSON response.

        Raises:
            Exception: if all retries fail
        """
        # Rate limiting.
        await self._wait_for_rate_limit()

        # Build request params.
        request_params = params or {}
        request_params["access_token"] = self.access_token

        # Add appsecret_proof when available.
        app_secret_proof = self.generate_app_secret_proof()
        if app_secret_proof:
            request_params["appsecret_proof"] = app_secret_proof

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        delay = initial_delay

        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    if method.upper() == "GET":
                        response = await client.get(url, params=request_params)
                    elif method.upper() == "POST":
                        response = await client.post(url, json=request_params)
                    else:
                        raise ValueError(f"Unsupported HTTP method: {method}")

                    # Handle response status codes.
                    if response.status_code == 200:
                        data = response.json()

                        # Inspect X-App-Usage header (quota usage), and slow down when near limits.
                        app_usage = response.headers.get("X-App-Usage")
                        if app_usage:
                            try:
                                usage_data = eval(
                                    app_usage
                                )  # Facebook returns a Python-dict-like string
                                call_count = usage_data.get("call_count", 0)
                                total_cputime = usage_data.get("total_cputime", 0)

                                # If usage approaches 100%, slow down proactively.
                                if call_count > 80 or total_cputime > 80:
                                    logger.warning(
                                        f"IG API quota usage high: {app_usage}, "
                                        f"slowing down requests for channel {self.channel_config_id}"
                                    )
                                    await asyncio.sleep(2.0)  # extra delay
                            except Exception as e:
                                logger.warning(
                                    f"Failed to parse X-App-Usage header: {e}"
                                )

                        return data

                    elif response.status_code == 429:
                        # Rate limit (429): retry with backoff.
                        retry_after = int(response.headers.get("Retry-After", delay))
                        logger.warning(
                            f"IG API rate limit (429) for channel {self.channel_config_id}, "
                            f"retrying after {retry_after}s (attempt {attempt + 1}/{max_retries + 1})"
                        )

                        if attempt < max_retries:
                            await asyncio.sleep(
                                min(retry_after, 60.0)
                            )  # cap sleep at 60s
                            delay = min(
                                delay * 2, 60.0
                            )  # exponential backoff, capped at 60s
                            continue
                        else:
                            error_data = response.json() if response.content else {}
                            raise Exception(
                                f"IG API rate limit exceeded after {max_retries + 1} attempts: "
                                f"{error_data.get('error', {}).get('message', 'Unknown error')}"
                            )

                    elif response.status_code == 401:
                        # Token invalid/expired.
                        error_data = response.json() if response.content else {}
                        error_message = error_data.get("error", {}).get(
                            "message", "Unknown error"
                        )
                        raise Exception(
                            f"IG API authentication failed (401): {error_message}. "
                            f"Please re-authorize in cloud registry (channel_config_id: {self.channel_config_id})"
                        )

                    else:
                        # Other errors.
                        error_data = response.json() if response.content else {}
                        error_message = error_data.get("error", {}).get(
                            "message", "Unknown error"
                        )
                        raise Exception(
                            f"IG API error ({response.status_code}): {error_message}"
                        )

            except httpx.TimeoutException:
                if attempt < max_retries:
                    logger.warning(
                        f"IG API request timeout for channel {self.channel_config_id}, "
                        f"retrying after {delay}s (attempt {attempt + 1}/{max_retries + 1})"
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60.0)
                    continue
                else:
                    raise Exception(
                        f"IG API request timeout after {max_retries + 1} attempts"
                    )

            except Exception as e:
                if attempt < max_retries:
                    logger.warning(
                        f"IG API request error for channel {self.channel_config_id}: {e}, "
                        f"retrying after {delay}s (attempt {attempt + 1}/{max_retries + 1})"
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60.0)
                    continue
                else:
                    raise

        raise Exception(f"IG API request failed after {max_retries + 1} attempts")

    async def get_ig_business_account_id(self, page_id: str) -> str:
        """
        Get ig_business_account_id from a Facebook Page id mapping.

        Endpoint: GET /{page-id}?fields=instagram_business_account

        Args:
            page_id: Facebook Page ID

        Returns:
            ig_business_account_id
        """
        data = await self._request_with_retry(
            method="GET",
            endpoint=f"/{page_id}",
            params={"fields": "instagram_business_account"},
        )

        ig_business_account = data.get("instagram_business_account")
        if not ig_business_account:
            raise ValueError(f"No Instagram Business Account found for page {page_id}")

        return ig_business_account.get("id")

    async def get_user_profile(self, ig_business_account_id: str) -> Dict[str, Any]:
        """
        Fetch Instagram Business Account profile fields.

        Endpoint: GET /{ig_business_account_id}
        Fields: id, username, account_type, media_count, profile_picture_url

        Args:
            ig_business_account_id: Instagram Business Account ID

        Returns:
            Profile payload
        """
        return await self._request_with_retry(
            method="GET",
            endpoint=f"/{ig_business_account_id}",
            params={
                "fields": "id,username,account_type,media_count,profile_picture_url"
            },
        )

    async def get_media_list(
        self,
        ig_business_account_id: str,
        media_type: Optional[str] = None,  # IMAGE, VIDEO, CAROUSEL_ALBUM
        limit: int = 25,
        since: Optional[str] = None,  # ISO timestamp
        until: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch media list (posts/reels).

        Endpoint: GET /{ig_business_account_id}/media
        Fields: id, caption, media_type, media_url, thumbnail_url, timestamp, permalink

        Args:
            ig_business_account_id: Instagram Business Account ID
            media_type: Media type filter (IMAGE, VIDEO, CAROUSEL_ALBUM)
            limit: Page size
            since: Start time (ISO 8601)
            until: End time (ISO 8601)

        Returns:
            Media list payload
        """
        params = {
            "fields": "id,caption,media_type,media_url,thumbnail_url,timestamp,permalink,like_count,comments_count",
            "limit": limit,
        }

        if media_type:
            params["media_type"] = media_type

        if since:
            params["since"] = since

        if until:
            params["until"] = until

        return await self._request_with_retry(
            method="GET", endpoint=f"/{ig_business_account_id}/media", params=params
        )

    async def get_media_details(self, media_id: str) -> Dict[str, Any]:
        """
        Fetch media details.

        Endpoint: GET /{media-id}
        Fields: id, caption, media_type, media_url, timestamp, permalink, insights

        Args:
            media_id: Media ID

        Returns:
            Media detail payload
        """
        return await self._request_with_retry(
            method="GET",
            endpoint=f"/{media_id}",
            params={
                "fields": "id,caption,media_type,media_url,thumbnail_url,timestamp,permalink,like_count,comments_count"
            },
        )

    async def get_media_insights(
        self,
        media_id: str,
        metrics: Optional[
            List[str]
        ] = None,  # impressions, reach, engagement, saved, video_views
    ) -> Dict[str, Any]:
        """
        Fetch media insights (requires instagram_manage_insights permission).

        Endpoint: GET /{media-id}/insights
        Metrics: impressions, reach, engagement, saved, video_views

        Args:
            media_id: Media ID
            metrics: Metrics list

        Returns:
            Insights payload
        """
        metrics = metrics or ["impressions", "reach", "engagement", "saved"]

        return await self._request_with_retry(
            method="GET",
            endpoint=f"/{media_id}/insights",
            params={"metric": ",".join(metrics)},
        )

    async def get_stories(
        self, ig_business_account_id: str, limit: int = 25
    ) -> Dict[str, Any]:
        """
        Fetch stories (requires pages_read_user_content permission).

        Endpoint: GET /{ig_business_account_id}/stories

        Args:
            ig_business_account_id: Instagram Business Account ID
            limit: Page size

        Returns:
            Stories payload
        """
        return await self._request_with_retry(
            method="GET",
            endpoint=f"/{ig_business_account_id}/stories",
            params={
                "fields": "id,media_type,media_url,timestamp,permalink",
                "limit": limit,
            },
        )

    async def publish_photo(
        self,
        ig_business_account_id: str,
        image_url: str,
        caption: str,
        location_id: Optional[str] = None,
        user_tags: Optional[List[Dict[str, Any]]] = None,
        scheduled_publish_time: Optional[str] = None,  # ISO timestamp
    ) -> Dict[str, Any]:
        """
        Publish a photo.

        Endpoints:
        - POST /{ig_business_account_id}/media
        - POST /{ig_business_account_id}/media_publish

        Args:
            ig_business_account_id: Instagram Business Account ID
            image_url: Public image URL
            caption: Caption text
            location_id: Location id (optional)
            user_tags: User tags (optional)
            scheduled_publish_time: ISO 8601 timestamp (optional)

        Returns:
            Publish result payload
        """
        # Step 1: create media container.
        container_params = {"image_url": image_url, "caption": caption}

        if location_id:
            container_params["location_id"] = location_id

        if user_tags:
            container_params["user_tags"] = user_tags

        if scheduled_publish_time:
            container_params["scheduled_publish_time"] = scheduled_publish_time

        container_response = await self._request_with_retry(
            method="POST",
            endpoint=f"/{ig_business_account_id}/media",
            params=container_params,
        )

        creation_id = container_response.get("id")
        if not creation_id:
            raise Exception("Failed to create media container")

        # Step 2: publish (or return creation_id when scheduled).
        if not scheduled_publish_time:
            publish_response = await self._request_with_retry(
                method="POST",
                endpoint=f"/{ig_business_account_id}/media_publish",
                params={"creation_id": creation_id},
            )

            return {
                "media_id": publish_response.get("id"),
                "permalink": f"https://www.instagram.com/p/{publish_response.get('id')}/",
                "creation_id": creation_id,
                "scheduled": False,
            }
        else:
            # Scheduled publish: return creation_id.
            return {
                "creation_id": creation_id,
                "scheduled": True,
                "scheduled_publish_time": scheduled_publish_time,
            }

    async def publish_reel(
        self,
        ig_business_account_id: str,
        video_url: str,
        caption: str,
        cover_url: Optional[str] = None,
        share_to_feed: bool = True,
    ) -> Dict[str, Any]:
        """
        Publish a reel.

        Endpoints:
        - POST /{ig_business_account_id}/media
        - POST /{ig_business_account_id}/media_publish

        Args:
            ig_business_account_id: Instagram Business Account ID
            video_url: Public video URL
            caption: Caption text
            cover_url: Cover URL (optional)
            share_to_feed: Share to feed (default True)

        Returns:
            Publish result payload
        """
        # Step 1: create reel container.
        container_params = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": share_to_feed,
        }

        if cover_url:
            container_params["cover_url"] = cover_url

        container_response = await self._request_with_retry(
            method="POST",
            endpoint=f"/{ig_business_account_id}/media",
            params=container_params,
        )

        creation_id = container_response.get("id")
        if not creation_id:
            raise Exception("Failed to create Reel container")

        # Step 2: wait until processing completes (poll status).
        max_wait_time = 300  # max 5 minutes
        wait_interval = 5  # poll every 5 seconds
        elapsed_time = 0

        while elapsed_time < max_wait_time:
            status_response = await self._request_with_retry(
                method="GET",
                endpoint=f"/{creation_id}",
                params={"fields": "status_code"},
            )

            status_code = status_response.get("status_code")
            if status_code == "FINISHED":
                break
            elif status_code == "ERROR":
                raise Exception(
                    f"Reel processing failed: {status_response.get('status')}"
                )

            await asyncio.sleep(wait_interval)
            elapsed_time += wait_interval

        if elapsed_time >= max_wait_time:
            raise Exception("Reel processing timeout")

        # Step 3: publish reel.
        publish_response = await self._request_with_retry(
            method="POST",
            endpoint=f"/{ig_business_account_id}/media_publish",
            params={"creation_id": creation_id},
        )

        return {
            "media_id": publish_response.get("id"),
            "permalink": f"https://www.instagram.com/reel/{publish_response.get('id')}/",
            "creation_id": creation_id,
            "scheduled": False,
        }

    async def publish_carousel(
        self,
        ig_business_account_id: str,
        children: List[str],  # List of media container IDs
        caption: str,
        location_id: Optional[str] = None,
        scheduled_publish_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Publish a carousel (multiple images).

        Endpoints:
        - POST /{ig_business_account_id}/media
        - POST /{ig_business_account_id}/media_publish

        Args:
            ig_business_account_id: Instagram Business Account ID
            children: List of child media container IDs
            caption: Caption text
            location_id: Location id (optional)
            scheduled_publish_time: ISO 8601 timestamp (optional)

        Returns:
            Publish result payload
        """
        # Step 1: create carousel container.
        container_params = {
            "media_type": "CAROUSEL",
            "children": ",".join(children),
            "caption": caption,
        }

        if location_id:
            container_params["location_id"] = location_id

        if scheduled_publish_time:
            container_params["scheduled_publish_time"] = scheduled_publish_time

        container_response = await self._request_with_retry(
            method="POST",
            endpoint=f"/{ig_business_account_id}/media",
            params=container_params,
        )

        creation_id = container_response.get("id")
        if not creation_id:
            raise Exception("Failed to create Carousel container")

        # Step 2: publish (or return creation_id when scheduled).
        if not scheduled_publish_time:
            publish_response = await self._request_with_retry(
                method="POST",
                endpoint=f"/{ig_business_account_id}/media_publish",
                params={"creation_id": creation_id},
            )

            return {
                "media_id": publish_response.get("id"),
                "permalink": f"https://www.instagram.com/p/{publish_response.get('id')}/",
                "creation_id": creation_id,
                "scheduled": False,
            }
        else:
            # Scheduled publish.
            return {
                "creation_id": creation_id,
                "scheduled": True,
                "scheduled_publish_time": scheduled_publish_time,
            }
