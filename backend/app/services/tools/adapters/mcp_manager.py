"""
MCP Server 管理器

管理多個 MCP servers 的生命週期和工具發現，提供：
- 多 server 管理
- 工具發現和註冊
- Claude mcp.json 配置匯入
- 統一的工具訪問接口

設計原則：
- 集中管理：統一管理所有 MCP servers
- 自動發現：自動發現和註冊工具
- 配置兼容：支援 Claude Desktop 的 mcp.json 格式
- 錯誤隔離：單個 server 失敗不影響其他
"""

import json
import asyncio
from typing import Dict, List, Optional
from pathlib import Path
import logging

from backend.app.services.tools.mcp_client import MCPClient, MCPServerConfig, MCPTransportType
from backend.app.services.tools.mcp_adapter import MCPToolAdapter, discover_mcp_tools
from backend.app.services.tools.base import MindscapeTool
from backend.app.services.registry import register_mindscape_tool

logger = logging.getLogger(__name__)


class MCPServerManager:
    """
    MCP Server 管理器

    管理多個 MCP servers，包括：
    - 啟動和停止 servers
    - 發現和註冊工具
    - 從 Claude mcp.json 匯入配置

    Example:
        >>> manager = MCPServerManager()
        >>>
        >>> # 添加 GitHub MCP server
        >>> await manager.add_server(MCPServerConfig(
        ...     id="github",
        ...     name="GitHub",
        ...     transport=MCPTransportType.STDIO,
        ...     command="npx",
        ...     args=["-y", "@modelcontextprotocol/server-github"],
        ...     env={"GITHUB_TOKEN": token}
        ... ))
        >>>
        >>> # 或從 Claude mcp.json 匯入
        >>> await manager.import_from_claude_config("~/.config/claude/mcp.json")
        >>>
        >>> # 獲取所有工具
        >>> tools = manager.get_all_tools()
    """

    def __init__(self):
        """初始化 MCP Server Manager"""
        self._clients: Dict[str, MCPClient] = {}
        self._tools: Dict[str, List[MCPToolAdapter]] = {}  # server_id -> tools
        self._lock = asyncio.Lock()

    async def add_server(
        self,
        config: MCPServerConfig,
        auto_discover: bool = True
    ) -> List[MCPToolAdapter]:
        """
        添加並啟動 MCP server

        Args:
            config: MCP server 配置
            auto_discover: 是否自動發現和註冊工具

        Returns:
            發現的工具列表

        Raises:
            ValueError: server ID 已存在
            ConnectionError: 連接失敗
        """
        async with self._lock:
            if config.id in self._clients:
                raise ValueError(f"MCP server {config.id} already exists")

            try:
                # 創建並連接客戶端
                client = MCPClient(config)
                await client.connect()

                self._clients[config.id] = client
                logger.info(f"MCP server {config.name} ({config.id}) started")

                # 自動發現工具
                tools = []
                if auto_discover:
                    tools = await discover_mcp_tools(client)
                    self._tools[config.id] = tools

                    # 註冊到全局工具 registry
                    for tool in tools:
                        register_mindscape_tool(f"mcp.{config.id}.{tool.mcp_tool_name}", tool)

                    logger.info(
                        f"Discovered {len(tools)} tools from MCP server {config.name}"
                    )

                return tools

            except Exception as e:
                logger.error(f"Failed to add MCP server {config.id}: {e}")
                # 清理失敗的客戶端
                if config.id in self._clients:
                    try:
                        await self._clients[config.id].disconnect()
                    except:
                        pass
                    del self._clients[config.id]
                raise

    async def remove_server(self, server_id: str):
        """
        移除並停止 MCP server

        Args:
            server_id: Server ID

        Raises:
            KeyError: Server 不存在
        """
        async with self._lock:
            if server_id not in self._clients:
                raise KeyError(f"MCP server {server_id} not found")

            try:
                # 斷開連接
                client = self._clients[server_id]
                await client.disconnect()

                # 清理
                del self._clients[server_id]
                if server_id in self._tools:
                    del self._tools[server_id]

                logger.info(f"MCP server {server_id} removed")

            except Exception as e:
                logger.error(f"Error removing MCP server {server_id}: {e}")
                raise

    async def rediscover_tools(self, server_id: str) -> List[MCPToolAdapter]:
        """
        重新發現指定 server 的工具

        Args:
            server_id: Server ID

        Returns:
            重新發現的工具列表
        """
        async with self._lock:
            if server_id not in self._clients:
                raise KeyError(f"MCP server {server_id} not found")

            client = self._clients[server_id]
            tools = await discover_mcp_tools(client)
            self._tools[server_id] = tools

            logger.info(
                f"Rediscovered {len(tools)} tools from MCP server {server_id}"
            )

            return tools

    def get_server_tools(self, server_id: str) -> List[MCPToolAdapter]:
        """
        獲取指定 server 的所有工具

        Args:
            server_id: Server ID

        Returns:
            工具列表
        """
        return self._tools.get(server_id, [])

    def get_all_tools(self) -> List[MCPToolAdapter]:
        """
        獲取所有 MCP 工具

        Returns:
            所有工具的列表
        """
        all_tools = []
        for tools in self._tools.values():
            all_tools.extend(tools)
        return all_tools

    def get_tool_by_name(self, tool_name: str) -> Optional[MCPToolAdapter]:
        """
        根據名稱獲取工具

        Args:
            tool_name: 工具名稱（可以是 "tool_name" 或 "mcp.server_id.tool_name"）

        Returns:
            工具實例或 None
        """
        for tools in self._tools.values():
            for tool in tools:
                if tool.mcp_tool_name == tool_name or tool.name == tool_name:
                    return tool
        return None

    def list_servers(self) -> List[Dict[str, any]]:
        """
        列出所有 MCP servers

        Returns:
            Server 信息列表
        """
        servers = []
        for server_id, client in self._clients.items():
            servers.append({
                "id": server_id,
                "name": client.config.name,
                "transport": client.config.transport.value,
                "connected": client._connected,
                "tools_count": len(self._tools.get(server_id, []))
            })
        return servers

    # ========== Claude mcp.json 支援 ==========

    async def import_from_claude_config(
        self,
        config_path: str = "~/.config/claude/mcp.json"
    ) -> Dict[str, List[MCPToolAdapter]]:
        """
        從 Claude Desktop 的 mcp.json 配置檔案匯入 servers

        Claude mcp.json 格式：
        {
            "mcpServers": {
                "github": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-github"],
                    "env": {
                        "GITHUB_TOKEN": "your_token"
                    }
                },
                "postgres": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-postgres"],
                    "env": {
                        "DATABASE_URL": "postgresql://..."
                    }
                }
            }
        }

        Args:
            config_path: mcp.json 檔案路徑（支援 ~ 展開）

        Returns:
            {server_id: [tools]}  每個 server 發現的工具

        Raises:
            FileNotFoundError: 配置檔案不存在
            ValueError: 配置格式錯誤
        """
        # 展開路徑
        path = Path(config_path).expanduser()

        if not path.exists():
            raise FileNotFoundError(f"Claude mcp.json not found: {config_path}")

        try:
            with open(path, 'r') as f:
                config_data = json.load(f)

            mcp_servers = config_data.get("mcpServers", {})

            if not mcp_servers:
                logger.warning("No MCP servers found in Claude config")
                return {}

            # 轉換並添加每個 server
            results = {}
            for server_id, server_config in mcp_servers.items():
                try:
                    config = self._parse_claude_server_config(server_id, server_config)
                    tools = await self.add_server(config)
                    results[server_id] = tools

                except Exception as e:
                    logger.error(
                        f"Failed to import Claude MCP server {server_id}: {e}"
                    )
                    # 繼續處理其他 servers

            logger.info(
                f"Imported {len(results)} MCP servers from Claude config"
            )

            return results

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in Claude mcp.json: {e}")
        except Exception as e:
            logger.error(f"Error importing Claude config: {e}")
            raise

    def _parse_claude_server_config(
        self,
        server_id: str,
        server_config: Dict
    ) -> MCPServerConfig:
        """
        解析 Claude mcp.json 中的單個 server 配置

        Args:
            server_id: Server ID
            server_config: Claude 格式的 server 配置

        Returns:
            MCPServerConfig

        Raises:
            ValueError: 配置格式錯誤
        """
        if "command" not in server_config:
            raise ValueError(f"Missing 'command' in server config for {server_id}")

        return MCPServerConfig(
            id=server_id,
            name=server_id.replace("-", " ").replace("_", " ").title(),
            transport=MCPTransportType.STDIO,  # Claude 只支援 stdio
            command=server_config["command"],
            args=server_config.get("args", []),
            env=server_config.get("env", {})
        )

    async def export_to_claude_config(
        self,
        output_path: str = "~/.config/claude/mcp.json"
    ):
        """
        將當前的 MCP servers 導出為 Claude mcp.json 格式

        Args:
            output_path: 輸出檔案路徑
        """
        path = Path(output_path).expanduser()

        # 確保目錄存在
        path.parent.mkdir(parents=True, exist_ok=True)

        # 構建 Claude 格式
        mcp_servers = {}
        for server_id, client in self._clients.items():
            config = client.config

            # 只導出 stdio transport 的 servers（Claude 不支援 HTTP）
            if config.transport == MCPTransportType.STDIO:
                mcp_servers[server_id] = {
                    "command": config.command,
                    "args": config.args or [],
                }
                if config.env:
                    mcp_servers[server_id]["env"] = config.env

        config_data = {"mcpServers": mcp_servers}

        with open(path, 'w') as f:
            json.dump(config_data, f, indent=2)

        logger.info(f"Exported {len(mcp_servers)} MCP servers to {output_path}")

    async def disconnect_all(self):
        """斷開所有 MCP servers"""
        for server_id in list(self._clients.keys()):
            try:
                await self.remove_server(server_id)
            except Exception as e:
                logger.error(f"Error disconnecting server {server_id}: {e}")

    async def __aenter__(self):
        """Context manager 支援"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager 支援"""
        await self.disconnect_all()



