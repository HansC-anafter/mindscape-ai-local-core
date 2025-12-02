"""
WordPress 工具集合（v2 架構）

使用新的 MindscapeTool 接口，將單一 WordPressTool 拆分為多個專注的工具類別。
每個工具對應一個具體的 WordPress 操作。

設計原則：
- 單一職責：每個工具只做一件事
- 標準化 Schema：使用 ToolMetadata 定義
- 類型安全：完整的類型提示
- 統一錯誤處理：使用 safe_execute 包裝
"""
from typing import Dict, Any, List
import aiohttp
from base64 import b64encode
import os

from backend.app.services.tools.base import MindscapeTool, ToolConnection
from backend.app.services.tools.schemas import (
    ToolMetadata,
    ToolCategory,
    ToolSourceType,
    ToolDangerLevel,
    create_simple_tool_metadata
)


class WordPressListPostsTool(MindscapeTool):
    """列出 WordPress 文章"""

    def __init__(self, connection: ToolConnection):
        metadata = create_simple_tool_metadata(
            name="wordpress.list_posts",
            description="列出 WordPress 文章，支援分頁、狀態過濾和搜尋功能",
            category=ToolCategory.CONTENT,
            source_type=ToolSourceType.LOCAL,
            danger_level=ToolDangerLevel.SAFE,
            properties={
                "per_page": {
                    "type": "integer",
                    "description": "每頁顯示文章數量",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 100
                },
                "page": {
                    "type": "integer",
                    "description": "頁碼（從 1 開始）",
                    "default": 1,
                    "minimum": 1
                },
                "status": {
                    "type": "string",
                    "description": "文章狀態篩選",
                    "enum": ["publish", "draft", "pending", "private", "any"],
                    "default": "publish"
                },
                "search": {
                    "type": "string",
                    "description": "搜尋關鍵字（搜尋標題和內容）"
                }
            },
            required=[]
        )
        super().__init__(metadata)
        self.connection = connection
        self._init_wp_client()

    def _init_wp_client(self):
        """初始化 WordPress REST API 客戶端"""
        self.wp_base_url = (
            self.connection.base_url or
            os.getenv("WORDPRESS_URL", "http://wordpress:80")
        ).rstrip('/')

        self.wp_username = (
            self.connection.api_key or
            os.getenv("WORDPRESS_USERNAME", "admin")
        )

        self.wp_password = (
            self.connection.api_secret or
            os.getenv("WORDPRESS_APPLICATION_PASSWORD", "")
        )

        # 構建 Basic Auth header
        if self.wp_username and self.wp_password:
            credentials = f"{self.wp_username}:{self.wp_password}"
            token = b64encode(credentials.encode()).decode()
            self.auth_header = f"Basic {token}"
        else:
            self.auth_header = None

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        執行：列出 WordPress 文章

        Args:
            input_data: 已驗證的輸入參數

        Returns:
            {
                "success": True,
                "data": [...],  # 文章列表
                "count": 10,
                "page": 1,
                "per_page": 10
            }
        """
        per_page = input_data.get("per_page", 10)
        page = input_data.get("page", 1)
        status = input_data.get("status", "publish")
        search = input_data.get("search")

        async with aiohttp.ClientSession() as session:
            headers = {"Content-Type": "application/json"}
            if self.auth_header:
                headers["Authorization"] = self.auth_header

            url = f"{self.wp_base_url}/wp-json/wp/v2/posts"
            params = {
                "per_page": per_page,
                "page": page,
                "status": status
            }
            if search:
                params["search"] = search

            async with session.get(
                url,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    posts = await response.json()
                    return {
                        "success": True,
                        "data": posts,
                        "count": len(posts),
                        "page": page,
                        "per_page": per_page
                    }
                else:
                    error_text = await response.text()
                    raise Exception(
                        f"WordPress API 錯誤 {response.status}: {error_text}"
                    )


class WordPressGetPostTool(MindscapeTool):
    """取得單篇 WordPress 文章"""

    def __init__(self, connection: ToolConnection):
        metadata = create_simple_tool_metadata(
            name="wordpress.get_post",
            description="根據 ID 取得單篇 WordPress 文章的完整資訊",
            category=ToolCategory.CONTENT,
            source_type=ToolSourceType.LOCAL,
            danger_level=ToolDangerLevel.SAFE,
            properties={
                "post_id": {
                    "type": "integer",
                    "description": "文章 ID",
                    "minimum": 1
                }
            },
            required=["post_id"]
        )
        super().__init__(metadata)
        self.connection = connection
        self._init_wp_client()

    def _init_wp_client(self):
        """同 WordPressListPostsTool"""
        self.wp_base_url = (
            self.connection.base_url or
            os.getenv("WORDPRESS_URL", "http://wordpress:80")
        ).rstrip('/')
        self.wp_username = self.connection.api_key or os.getenv("WORDPRESS_USERNAME", "admin")
        self.wp_password = self.connection.api_secret or os.getenv("WORDPRESS_APPLICATION_PASSWORD", "")

        if self.wp_username and self.wp_password:
            credentials = f"{self.wp_username}:{self.wp_password}"
            token = b64encode(credentials.encode()).decode()
            self.auth_header = f"Basic {token}"
        else:
            self.auth_header = None

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """執行：取得文章"""
        post_id = input_data["post_id"]

        async with aiohttp.ClientSession() as session:
            headers = {}
            if self.auth_header:
                headers["Authorization"] = self.auth_header

            url = f"{self.wp_base_url}/wp-json/wp/v2/posts/{post_id}"

            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    post = await response.json()
                    return {
                        "success": True,
                        "data": post
                    }
                else:
                    error_text = await response.text()
                    raise Exception(
                        f"無法取得文章 {post_id}: {response.status} - {error_text}"
                    )


class WordPressCreateDraftTool(MindscapeTool):
    """創建 WordPress 草稿文章"""

    def __init__(self, connection: ToolConnection):
        metadata = create_simple_tool_metadata(
            name="wordpress.create_draft",
            description="在 WordPress 創建草稿文章（不會發佈，需手動審核後發佈）",
            category=ToolCategory.CONTENT,
            source_type=ToolSourceType.LOCAL,
            danger_level=ToolDangerLevel.SAFE,
            properties={
                "title": {
                    "type": "string",
                    "description": "文章標題",
                },
                "content": {
                    "type": "string",
                    "description": "文章內容（支援 HTML）",
                },
                "excerpt": {
                    "type": "string",
                    "description": "文章摘要"
                },
                "meta": {
                    "type": "object",
                    "description": "自訂 Meta 欄位"
                }
            },
            required=["title", "content"]
        )
        super().__init__(metadata)
        self.connection = connection
        self._init_wp_client()

    def _init_wp_client(self):
        """同上"""
        self.wp_base_url = (
            self.connection.base_url or
            os.getenv("WORDPRESS_URL", "http://wordpress:80")
        ).rstrip('/')
        self.wp_username = self.connection.api_key or os.getenv("WORDPRESS_USERNAME", "admin")
        self.wp_password = self.connection.api_secret or os.getenv("WORDPRESS_APPLICATION_PASSWORD", "")

        if self.wp_username and self.wp_password:
            credentials = f"{self.wp_username}:{self.wp_password}"
            token = b64encode(credentials.encode()).decode()
            self.auth_header = f"Basic {token}"
        else:
            self.auth_header = None

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """執行：創建草稿"""
        title = input_data["title"]
        content = input_data["content"]
        excerpt = input_data.get("excerpt", "")
        meta = input_data.get("meta", {})

        async with aiohttp.ClientSession() as session:
            headers = {"Content-Type": "application/json"}
            if self.auth_header:
                headers["Authorization"] = self.auth_header

            url = f"{self.wp_base_url}/wp-json/wp/v2/posts"
            payload = {
                "title": title,
                "content": content,
                "status": "draft",  # 強制設為草稿
            }

            if excerpt:
                payload["excerpt"] = excerpt
            if meta:
                payload["meta"] = meta

            async with session.post(
                url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                if response.status in [200, 201]:
                    post = await response.json()
                    return {
                        "success": True,
                        "data": post,
                        "post_id": post["id"],
                        "edit_url": post.get("link")
                    }
                else:
                    error_text = await response.text()
                    raise Exception(
                        f"創建草稿失敗: {response.status} - {error_text}"
                    )


class WordPressUpdatePostTool(MindscapeTool):
    """更新 WordPress 文章"""

    def __init__(self, connection: ToolConnection):
        metadata = create_simple_tool_metadata(
            name="wordpress.update_post",
            description="更新現有的 WordPress 文章內容、標題或其他屬性",
            category=ToolCategory.CONTENT,
            source_type=ToolSourceType.LOCAL,
            danger_level=ToolDangerLevel.MODERATE,  # 修改內容有中等風險
            properties={
                "post_id": {
                    "type": "integer",
                    "description": "要更新的文章 ID",
                    "minimum": 1
                },
                "title": {
                    "type": "string",
                    "description": "新的文章標題（可選）"
                },
                "content": {
                    "type": "string",
                    "description": "新的文章內容（可選）"
                },
                "excerpt": {
                    "type": "string",
                    "description": "新的文章摘要（可選）"
                },
                "status": {
                    "type": "string",
                    "description": "文章狀態（可選）",
                    "enum": ["draft", "pending", "publish"]
                }
            },
            required=["post_id"]
        )
        super().__init__(metadata)
        self.connection = connection
        self._init_wp_client()

    def _init_wp_client(self):
        """同上"""
        self.wp_base_url = (
            self.connection.base_url or
            os.getenv("WORDPRESS_URL", "http://wordpress:80")
        ).rstrip('/')
        self.wp_username = self.connection.api_key or os.getenv("WORDPRESS_USERNAME", "admin")
        self.wp_password = self.connection.api_secret or os.getenv("WORDPRESS_APPLICATION_PASSWORD", "")

        if self.wp_username and self.wp_password:
            credentials = f"{self.wp_username}:{self.wp_password}"
            token = b64encode(credentials.encode()).decode()
            self.auth_header = f"Basic {token}"
        else:
            self.auth_header = None

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """執行：更新文章"""
        post_id = input_data["post_id"]

        # 構建更新 payload（只包含提供的欄位）
        payload = {}
        if "title" in input_data:
            payload["title"] = input_data["title"]
        if "content" in input_data:
            payload["content"] = input_data["content"]
        if "excerpt" in input_data:
            payload["excerpt"] = input_data["excerpt"]
        if "status" in input_data:
            payload["status"] = input_data["status"]

        if not payload:
            raise ValueError("至少需要提供一個要更新的欄位")

        async with aiohttp.ClientSession() as session:
            headers = {"Content-Type": "application/json"}
            if self.auth_header:
                headers["Authorization"] = self.auth_header

            url = f"{self.wp_base_url}/wp-json/wp/v2/posts/{post_id}"

            async with session.post(
                url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                if response.status == 200:
                    post = await response.json()
                    return {
                        "success": True,
                        "data": post,
                        "post_id": post["id"]
                    }
                else:
                    error_text = await response.text()
                    raise Exception(
                        f"更新文章失敗: {response.status} - {error_text}"
                    )


class WordPressListOrdersTool(MindscapeTool):
    """列出 WooCommerce 訂單"""

    def __init__(self, connection: ToolConnection):
        metadata = create_simple_tool_metadata(
            name="wordpress.list_orders",
            description="列出 WooCommerce 訂單，支援狀態和日期範圍篩選",
            category=ToolCategory.COMMERCE,
            source_type=ToolSourceType.LOCAL,
            danger_level=ToolDangerLevel.SAFE,
            properties={
                "per_page": {
                    "type": "integer",
                    "description": "每頁訂單數量",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 100
                },
                "page": {
                    "type": "integer",
                    "description": "頁碼",
                    "default": 1
                },
                "status": {
                    "type": "string",
                    "description": "訂單狀態篩選",
                    "enum": ["pending", "processing", "completed", "cancelled", "refunded", "any"]
                },
                "after": {
                    "type": "string",
                    "description": "起始日期 (ISO 8601 格式)"
                },
                "before": {
                    "type": "string",
                    "description": "結束日期 (ISO 8601 格式)"
                }
            },
            required=[]
        )
        super().__init__(metadata)
        self.connection = connection
        self._init_wp_client()

    def _init_wp_client(self):
        """同上"""
        self.wp_base_url = (
            self.connection.base_url or
            os.getenv("WORDPRESS_URL", "http://wordpress:80")
        ).rstrip('/')
        self.wp_username = self.connection.api_key or os.getenv("WORDPRESS_USERNAME", "admin")
        self.wp_password = self.connection.api_secret or os.getenv("WORDPRESS_APPLICATION_PASSWORD", "")

        if self.wp_username and self.wp_password:
            credentials = f"{self.wp_username}:{self.wp_password}"
            token = b64encode(credentials.encode()).decode()
            self.auth_header = f"Basic {token}"
        else:
            self.auth_header = None

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """執行：列出訂單"""
        per_page = input_data.get("per_page", 10)
        page = input_data.get("page", 1)
        status = input_data.get("status")
        after = input_data.get("after")
        before = input_data.get("before")

        async with aiohttp.ClientSession() as session:
            headers = {}
            if self.auth_header:
                headers["Authorization"] = self.auth_header

            url = f"{self.wp_base_url}/wp-json/wc/v3/orders"
            params = {
                "per_page": per_page,
                "page": page
            }
            if status:
                params["status"] = status
            if after:
                params["after"] = after
            if before:
                params["before"] = before

            async with session.get(
                url,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    orders = await response.json()
                    return {
                        "success": True,
                        "data": orders,
                        "count": len(orders)
                    }
                else:
                    error_text = await response.text()
                    raise Exception(
                        f"WooCommerce API 錯誤: {response.status} - {error_text}"
                    )


class WordPressUpdateOrderStatusTool(MindscapeTool):
    """更新 WooCommerce 訂單狀態（高風險操作）"""

    def __init__(self, connection: ToolConnection):
        metadata = create_simple_tool_metadata(
            name="wordpress.update_order_status",
            description="⚠️ 更新 WooCommerce 訂單狀態（高風險操作，可能影響付款和物流）",
            category=ToolCategory.COMMERCE,
            source_type=ToolSourceType.LOCAL,
            danger_level=ToolDangerLevel.DANGER,  # ⚠️ 高風險
            properties={
                "order_id": {
                    "type": "integer",
                    "description": "訂單 ID",
                    "minimum": 1
                },
                "status": {
                    "type": "string",
                    "description": "新的訂單狀態",
                    "enum": ["pending", "processing", "completed", "cancelled", "refunded"]
                }
            },
            required=["order_id", "status"]
        )
        super().__init__(metadata)
        self.connection = connection
        self._init_wp_client()

    def _init_wp_client(self):
        """同上"""
        self.wp_base_url = (
            self.connection.base_url or
            os.getenv("WORDPRESS_URL", "http://wordpress:80")
        ).rstrip('/')
        self.wp_username = self.connection.api_key or os.getenv("WORDPRESS_USERNAME", "admin")
        self.wp_password = self.connection.api_secret or os.getenv("WORDPRESS_APPLICATION_PASSWORD", "")

        if self.wp_username and self.wp_password:
            credentials = f"{self.wp_username}:{self.wp_password}"
            token = b64encode(credentials.encode()).decode()
            self.auth_header = f"Basic {token}"
        else:
            self.auth_header = None

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        執行：更新訂單狀態

        ⚠️ 注意：此操作應該在 UI 層要求用戶確認
        """
        order_id = input_data["order_id"]
        status = input_data["status"]

        async with aiohttp.ClientSession() as session:
            headers = {"Content-Type": "application/json"}
            if self.auth_header:
                headers["Authorization"] = self.auth_header

            url = f"{self.wp_base_url}/wp-json/wc/v3/orders/{order_id}"
            payload = {"status": status}

            async with session.put(
                url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    order = await response.json()
                    return {
                        "success": True,
                        "data": order,
                        "message": f"訂單 #{order_id} 狀態已更新為 {status}"
                    }
                else:
                    error_text = await response.text()
                    raise Exception(
                        f"更新訂單狀態失敗: {response.status} - {error_text}"
                    )


# ============================================
# 工廠函數
# ============================================

def create_wordpress_tools(connection: ToolConnection) -> List[MindscapeTool]:
    """
    創建所有 WordPress 工具實例

    Args:
        connection: WordPress 連接配置

    Returns:
        WordPress 工具列表

    Example:
        >>> wp_conn = ToolConnection(
        ...     id="my-wp",
        ...     tool_type="wordpress",
        ...     base_url="https://mysite.com",
        ...     api_key="admin",
        ...     api_secret="app_password"
        ... )
        >>> tools = create_wordpress_tools(wp_conn)
        >>> print(f"創建了 {len(tools)} 個工具")
    """
    return [
        # 內容管理
        WordPressListPostsTool(connection),
        WordPressGetPostTool(connection),
        WordPressCreateDraftTool(connection),
        WordPressUpdatePostTool(connection),

        # 電商管理
        WordPressListOrdersTool(connection),
        WordPressUpdateOrderStatusTool(connection),
    ]


def get_wordpress_tool_by_name(
    connection: ToolConnection,
    tool_name: str
) -> MindscapeTool:
    """
    根據名稱獲取特定的 WordPress 工具

    Args:
        connection: WordPress 連接
        tool_name: 工具名稱（如 "wordpress.list_posts"）

    Returns:
        工具實例

    Raises:
        ValueError: 未知的工具名稱
    """
    tool_map = {
        "wordpress.list_posts": WordPressListPostsTool,
        "wordpress.get_post": WordPressGetPostTool,
        "wordpress.create_draft": WordPressCreateDraftTool,
        "wordpress.update_post": WordPressUpdatePostTool,
        "wordpress.list_orders": WordPressListOrdersTool,
        "wordpress.update_order_status": WordPressUpdateOrderStatusTool,
    }

    tool_class = tool_map.get(tool_name)
    if not tool_class:
        available = list(tool_map.keys())
        raise ValueError(
            f"未知的工具名稱: {tool_name}。"
            f"可用工具: {', '.join(available)}"
        )

    return tool_class(connection)
