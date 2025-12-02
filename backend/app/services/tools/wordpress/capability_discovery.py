"""
WordPress Capability Discovery Service.

This service discovers available capabilities from a WordPress site,
either through the mindscape plugin or fallback heuristics.
"""
import aiohttp
from typing import Dict, Any, List, Optional
from datetime import datetime


class WordPressCapability:
    """Represents a WordPress capability"""

    def __init__(
        self,
        id: str,
        category: str,
        label: str,
        description: str,
        endpoint: str,
        methods: List[str],
        danger_level: str = "low",  # "low", "medium", "high"
        input_schema: Optional[Dict[str, Any]] = None,
    ):
        self.id = id
        self.category = category
        self.label = label
        self.description = description
        self.endpoint = endpoint
        self.methods = methods
        self.danger_level = danger_level
        self.input_schema = input_schema or {}


class WordPressCapabilityDiscovery:
    """Discovers WordPress capabilities from a site"""

    def __init__(self, wp_base_url: str, auth_header: Optional[str] = None):
        self.wp_base_url = wp_base_url.rstrip('/')
        self.auth_header = auth_header

    async def discover(self) -> Dict[str, Any]:
        """
        Discover all capabilities from WordPress site.

        Returns:
            {
                "site": {...},
                "capabilities": [...],
                "discovery_method": "plugin" | "fallback"
            }
        """
        # Step 0: Verify this is WordPress
        site_info = await self._verify_wordpress()
        if not site_info:
            raise ValueError("Not a valid WordPress site")

        # Step 1: Try to discover via mindscape plugin
        plugin_capabilities = await self._discover_via_plugin()

        if plugin_capabilities:
            return {
                "site": site_info,
                "capabilities": plugin_capabilities,
                "discovery_method": "plugin",
            }

        # Step 2: Fallback to heuristic discovery
        fallback_capabilities = await self._discover_via_fallback(site_info)

        return {
            "site": site_info,
            "capabilities": fallback_capabilities,
            "discovery_method": "fallback",
        }

    async def _verify_wordpress(self) -> Optional[Dict[str, Any]]:
        """Verify this is WordPress and get basic info"""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {}
                if self.auth_header:
                    headers["Authorization"] = self.auth_header

                url = f"{self.wp_base_url}/wp-json/"
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        return None

                    data = await response.json()

                    # Extract site info
                    site_info = {
                        "url": self.wp_base_url,
                        "name": data.get("name", "WordPress Site"),
                        "description": data.get("description", ""),
                        "wp_version": data.get("_links", {}).get("wp:version", [{}])[0].get("href", "").split("/")[-1] if data.get("_links") else "unknown",
                        "namespaces": list(data.get("namespaces", [])),
                    }

                    return site_info
        except Exception as e:
            print(f"Error verifying WordPress: {e}")
            return None

    async def _discover_via_plugin(self) -> Optional[List[Dict[str, Any]]]:
        """Discover capabilities via mindscape plugin"""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {}
                if self.auth_header:
                    headers["Authorization"] = self.auth_header

                url = f"{self.wp_base_url}/wp-json/mindscape/v1/capabilities"
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("capabilities", [])
        except Exception:
            pass

        return None

    async def _discover_via_fallback(self, site_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback discovery using heuristics"""
        capabilities = []
        namespaces = site_info.get("namespaces", [])

        # Core WordPress capabilities
        if "wp/v2" in namespaces:
            capabilities.extend([
                {
                    "id": "wp.post.read",
                    "category": "content",
                    "label": "讀取文章",
                    "description": "列出與讀取現有文章與頁面。",
                    "endpoint": "/wp-json/wp/v2/posts",
                    "methods": ["GET"],
                    "danger_level": "low",
                },
                {
                    "id": "wp.post.create_draft",
                    "category": "content",
                    "label": "建立文章草稿",
                    "description": "建立尚未發佈的文章草稿。",
                    "endpoint": "/wp-json/wp/v2/posts",
                    "methods": ["POST"],
                    "danger_level": "medium",
                },
                {
                    "id": "wp.post.update",
                    "category": "content",
                    "label": "更新文章",
                    "description": "更新現有文章內容。",
                    "endpoint": "/wp-json/wp/v2/posts/{id}",
                    "methods": ["PUT", "PATCH"],
                    "danger_level": "medium",
                },
                {
                    "id": "wp.media.upload",
                    "category": "media",
                    "label": "上傳媒體",
                    "description": "上傳圖片或其他媒體檔案。",
                    "endpoint": "/wp-json/wp/v2/media",
                    "methods": ["POST"],
                    "danger_level": "low",
                },
            ])

        # WooCommerce capabilities
        if "wc/v3" in namespaces:
            capabilities.extend([
                {
                    "id": "wc.order.read",
                    "category": "commerce",
                    "label": "讀取訂單",
                    "description": "列出與讀取 WooCommerce 訂單。",
                    "endpoint": "/wp-json/wc/v3/orders",
                    "methods": ["GET"],
                    "danger_level": "low",
                },
                {
                    "id": "wc.order.update_status",
                    "category": "commerce",
                    "label": "更新訂單狀態",
                    "description": "更改 WooCommerce 訂單狀態（高風險）。",
                    "endpoint": "/wp-json/wc/v3/orders/{id}",
                    "methods": ["PUT", "PATCH"],
                    "danger_level": "high",
                },
            ])

        # SEO Plugin capabilities (heuristic)
        if "yoast/v1" in namespaces:
            capabilities.append({
                "id": "yoast.seo.update",
                "category": "seo",
                "label": "更新 SEO 設定",
                "description": "更新 Yoast SEO 設定（有限支援）。",
                "endpoint": "/wp-json/yoast/v1/...",
                "methods": ["POST"],
                "danger_level": "medium",
            })

        if "rankmath/v1" in namespaces:
            capabilities.append({
                "id": "rankmath.seo.update",
                "category": "seo",
                "label": "更新 RankMath SEO 設定",
                "description": "更新 RankMath SEO 設定（有限支援）。",
                "endpoint": "/wp-json/rankmath/v1/...",
                "methods": ["POST"],
                "danger_level": "medium",
            })

        return capabilities

