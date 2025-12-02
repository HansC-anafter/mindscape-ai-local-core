"""
MCP 工具適配器

將 MCP 工具適配到 Mindscape AI 的工具系統，提供：
- MCP Tool → MindscapeTool 轉換
- 自動 schema 轉換
- 工具執行代理

設計原則：
- 保留 MCP 工具原始行為
- 自動提取和轉換 schema
- 統一的錯誤處理
- 支援 MCP 特殊返回格式
"""

from typing import Dict, Any, List, Optional
import logging

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolMetadata,
    ToolCategory,
    ToolSourceType,
    ToolDangerLevel,
)
from backend.app.services.tools.mcp_client import MCPClient, MCPServerConfig

logger = logging.getLogger(__name__)


class MCPToolAdapter(MindscapeTool):
    """
    將 MCP 工具包裝為 MindscapeTool

    Example:
        >>> client = MCPClient(config)
        >>> await client.connect()
        >>>
        >>> # 從 MCP tool info 創建 adapter
        >>> mcp_tool_info = {
        ...     "name": "github.search_issues",
        ...     "description": "Search GitHub issues",
        ...     "inputSchema": {...}
        ... }
        >>>
        >>> tool = MCPToolAdapter(client, mcp_tool_info)
        >>> result = await tool.execute({"query": "bug"})
    """

    def __init__(self, mcp_client: MCPClient, tool_info: Dict[str, Any]):
        """
        初始化 MCP 工具適配器

        Args:
            mcp_client: 已連接的 MCPClient 實例
            tool_info: MCP tools/list 返回的工具信息
                - name (str): 工具名稱
                - description (str): 工具描述
                - inputSchema (dict): JSON Schema 格式的輸入定義
        """
        self.mcp_client = mcp_client
        self.mcp_tool_name = tool_info["name"]

        # 提取並轉換 metadata
        metadata = self._extract_metadata_from_mcp(tool_info)
        super().__init__(metadata)

    def _extract_metadata_from_mcp(self, tool_info: Dict[str, Any]) -> ToolMetadata:
        """
        從 MCP 工具信息提取 metadata

        Args:
            tool_info: MCP tools/list 返回的工具信息

        Returns:
            ToolMetadata
        """
        name = tool_info["name"]
        description = tool_info.get("description", "")
        input_schema = tool_info.get("inputSchema", {})

        # 推斷危險等級
        danger_level = self._infer_danger_level(name, description)

        # 推斷分類
        category = self._infer_category(name, description)

        return ToolMetadata(
            name=f"mcp.{name}",
            description=description,
            input_schema=input_schema,
            category=category,
            source_type=ToolSourceType.MCP,
            danger_level=danger_level,
            metadata={
                "mcp_server_id": self.mcp_client.config.id,
                "mcp_server_name": self.mcp_client.config.name,
                "mcp_tool_name": name
            }
        )

    def _infer_danger_level(self, name: str, description: str) -> ToolDangerLevel:
        """
        根據工具名稱和描述推斷危險等級

        Args:
            name: 工具名稱
            description: 工具描述

        Returns:
            ToolDangerLevel
        """
        danger_keywords = ['delete', 'remove', 'drop', 'execute', 'run', 'shell']
        moderate_keywords = ['write', 'update', 'modify', 'create', 'send', 'post']

        name_lower = name.lower()
        desc_lower = description.lower()

        # 檢查危險關鍵字
        if any(kw in name_lower or kw in desc_lower for kw in danger_keywords):
            return ToolDangerLevel.DANGER

        # 檢查中等風險關鍵字
        if any(kw in name_lower or kw in desc_lower for kw in moderate_keywords):
            return ToolDangerLevel.MODERATE

        # 默認：安全
        return ToolDangerLevel.SAFE

    def _infer_category(self, name: str, description: str) -> ToolCategory:
        """
        根據工具名稱和描述推斷分類

        Args:
            name: 工具名稱
            description: 工具描述

        Returns:
            ToolCategory
        """
        category_keywords = {
            ToolCategory.SEARCH: ['search', 'query', 'find', 'lookup'],
            ToolCategory.CONTENT: ['write', 'generate', 'create', 'blog'],
            ToolCategory.DATA: ['database', 'sql', 'data', 'csv'],
            ToolCategory.INTEGRATION: ['github', 'jira', 'slack', 'api'],
            ToolCategory.AUTOMATION: ['run', 'execute', 'automate'],
        }

        name_lower = name.lower()
        desc_lower = description.lower()

        for category, keywords in category_keywords.items():
            if any(kw in name_lower or kw in desc_lower for kw in keywords):
                return category

        return ToolCategory.OTHER

    async def execute(self, input_data: Dict[str, Any]) -> Any:
        """
        執行 MCP 工具

        Args:
            input_data: 工具輸入參數（已驗證）

        Returns:
            工具執行結果

        Note:
            MCP tools/call 返回的 content 是一個數組，可能包含：
            - text: 文本內容
            - image: 圖片數據
            - resource: 資源引用

            我們將其轉換為更友好的格式
        """
        try:
            # 調用 MCP 工具
            content_list = await self.mcp_client.call_tool(
                self.mcp_tool_name,
                input_data
            )

            # 轉換 MCP content 格式為更友好的格式
            result = self._parse_mcp_content(content_list)

            return result

        except Exception as e:
            logger.error(
                f"MCP tool {self.mcp_tool_name} execution failed: {e}"
            )
            raise

    def _parse_mcp_content(self, content_list: List[Dict[str, Any]]) -> Any:
        """
        解析 MCP content 數組

        MCP 工具返回格式：
        {
            "content": [
                {"type": "text", "text": "result text"},
                {"type": "image", "data": "base64...", "mimeType": "image/png"},
                ...
            ]
        }

        Args:
            content_list: MCP content 數組

        Returns:
            解析後的結果（根據 content 類型）
        """
        if not content_list:
            return None

        # 如果只有一個 text 內容，直接返回文本
        if len(content_list) == 1 and content_list[0].get("type") == "text":
            return content_list[0].get("text")

        # 如果有多個內容，返回結構化數據
        parsed = {
            "text": [],
            "images": [],
            "resources": [],
            "raw": content_list
        }

        for item in content_list:
            content_type = item.get("type")

            if content_type == "text":
                parsed["text"].append(item.get("text", ""))
            elif content_type == "image":
                parsed["images"].append({
                    "data": item.get("data"),
                    "mimeType": item.get("mimeType"),
                })
            elif content_type == "resource":
                parsed["resources"].append({
                    "uri": item.get("uri"),
                    "mimeType": item.get("mimeType"),
                })

        # 如果只有文本，簡化輸出
        if parsed["images"] == [] and parsed["resources"] == []:
            return "\n".join(parsed["text"])

        return parsed


# ============================================
# 便捷函數
# ============================================

async def discover_mcp_tools(
    mcp_client: MCPClient
) -> List[MCPToolAdapter]:
    """
    從 MCP server 發現並創建所有工具

    Args:
        mcp_client: 已連接的 MCPClient

    Returns:
        MCPToolAdapter 列表

    Example:
        >>> config = MCPServerConfig(...)
        >>> async with MCPClient(config) as client:
        ...     tools = await discover_mcp_tools(client)
        ...     for tool in tools:
        ...         print(tool.name)
    """
    # 列出所有工具
    tools_info = await mcp_client.list_tools()

    # 為每個工具創建 adapter
    adapters = []
    for tool_info in tools_info:
        adapter = MCPToolAdapter(mcp_client, tool_info)
        adapters.append(adapter)
        logger.info(f"Discovered MCP tool: {adapter.name}")

    return adapters


def is_mcp_available() -> bool:
    """
    檢查 MCP 支援是否可用

    Returns:
        bool: True 如果可以使用 MCP
    """
    try:
        from backend.app.services.tools.mcp_client import MCPClient
        return True
    except ImportError:
        return False



