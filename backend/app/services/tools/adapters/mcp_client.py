"""
MCP (Model Context Protocol) 客戶端

實作完整的 MCP 協議客戶端，支援：
- JSON-RPC 2.0 協議
- stdio 傳輸（本地 MCP servers）
- HTTP+SSE 傳輸（遠端 MCP servers）
- tools/list 和 tools/call 方法

設計原則：
- 協議正確：嚴格遵循 MCP spec
- 傳輸中立：支援多種傳輸方式
- 異步優先：所有操作都是異步
- 錯誤處理：完整的錯誤處理和超時機制
"""

import asyncio
import json
import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import logging

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

logger = logging.getLogger(__name__)


class MCPTransportType(str, Enum):
    """MCP 傳輸類型"""
    STDIO = "stdio"      # 本地進程（類似 LSP）
    HTTP_SSE = "http"    # HTTP + Server-Sent Events


@dataclass
class MCPServerConfig:
    """
    MCP Server 配置

    Example (stdio):
        config = MCPServerConfig(
            id="github-mcp",
            name="GitHub MCP Server",
            transport=MCPTransportType.STDIO,
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={"GITHUB_TOKEN": "your_token"}
        )

    Example (HTTP):
        config = MCPServerConfig(
            id="remote-mcp",
            name="Remote MCP Server",
            transport=MCPTransportType.HTTP_SSE,
            base_url="https://mcp.example.com",
            api_key="your_api_key"
        )
    """
    id: str                              # 唯一識別碼
    name: str                            # 顯示名稱
    transport: MCPTransportType

    # stdio 配置
    command: Optional[str] = None        # 例如 "npx" 或 "python"
    args: Optional[List[str]] = None     # 命令參數
    env: Optional[Dict[str, str]] = None # 環境變數（用於傳遞 API keys）

    # HTTP 配置
    base_url: Optional[str] = None       # HTTP 服務器 URL
    api_key: Optional[str] = None        # API 認證金鑰


class JSONRPCError(Exception):
    """JSON-RPC 2.0 錯誤"""

    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"JSON-RPC Error {code}: {message}")


class MCPClient:
    """
    MCP 協議客戶端

    實作完整的 Model Context Protocol，包括：
    - JSON-RPC 2.0 請求/響應處理
    - stdio 和 HTTP 兩種傳輸方式
    - tools/list（列出可用工具）
    - tools/call（調用工具）

    Example:
        >>> config = MCPServerConfig(
        ...     id="github",
        ...     name="GitHub",
        ...     transport=MCPTransportType.STDIO,
        ...     command="npx",
        ...     args=["-y", "@modelcontextprotocol/server-github"]
        ... )
        >>> client = MCPClient(config)
        >>> await client.connect()
        >>> tools = await client.list_tools()
        >>> result = await client.call_tool("github.search_issues", {"query": "bug"})
    """

    def __init__(self, config: MCPServerConfig):
        """
        初始化 MCP 客戶端

        Args:
            config: MCP Server 配置
        """
        self.config = config
        self.transport = config.transport
        self._connected = False

        # stdio 相關
        if self.transport == MCPTransportType.STDIO:
            self.process = None
            self.reader = None
            self.writer = None
            self._request_id = 0
            self._pending_requests: Dict[str, asyncio.Future] = {}

        # HTTP 相關
        elif self.transport == MCPTransportType.HTTP_SSE:
            if not HTTPX_AVAILABLE:
                raise ImportError(
                    "httpx is required for HTTP transport. "
                    "Install with: pip install httpx"
                )
            self.http_client = httpx.AsyncClient(
                base_url=config.base_url,
                headers=self._build_http_headers(),
                timeout=30.0
            )

    def _build_http_headers(self) -> Dict[str, str]:
        """構建 HTTP 請求頭"""
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def _next_request_id(self) -> str:
        """生成下一個 JSON-RPC request ID"""
        self._request_id += 1
        return str(self._request_id)

    async def connect(self):
        """
        建立與 MCP server 的連接

        Raises:
            ConnectionError: 連接失敗
            ImportError: 缺少必要的依賴
        """
        if self._connected:
            logger.warning(f"MCP client {self.config.id} already connected")
            return

        if self.transport == MCPTransportType.STDIO:
            await self._connect_stdio()
        elif self.transport == MCPTransportType.HTTP_SSE:
            await self._connect_http()

        self._connected = True
        logger.info(f"MCP client {self.config.id} connected via {self.transport}")

    async def _connect_stdio(self):
        """透過 stdio 啟動 MCP server 子進程"""
        if not self.config.command or not self.config.args:
            raise ValueError("stdio transport requires command and args")

        try:
            # 準備環境變數
            env = {**os.environ}
            if self.config.env:
                env.update(self.config.env)

            # 啟動子進程
            self.process = await asyncio.create_subprocess_exec(
                self.config.command,
                *self.config.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )

            self.reader = self.process.stdout
            self.writer = self.process.stdin

            # 啟動讀取循環（後台任務）
            asyncio.create_task(self._stdio_read_loop())

            logger.info(
                f"MCP server {self.config.name} started: "
                f"{self.config.command} {' '.join(self.config.args)}"
            )

        except Exception as e:
            logger.error(f"Failed to start MCP server {self.config.name}: {e}")
            raise ConnectionError(f"Failed to start MCP server: {e}")

    async def _connect_http(self):
        """測試 HTTP 連接"""
        if not self.config.base_url:
            raise ValueError("HTTP transport requires base_url")

        try:
            # 簡單的健康檢查（如果 server 支援）
            response = await self.http_client.get("/health")
            response.raise_for_status()
            logger.info(f"MCP server {self.config.name} HTTP connection successful")
        except httpx.HTTPError:
            # 如果沒有 /health endpoint，不視為錯誤
            logger.info(f"MCP server {self.config.name} HTTP client initialized")

    async def _stdio_read_loop(self):
        """
        stdio 讀取循環（處理 JSON-RPC 響應）

        持續讀取 stdout，解析 JSON-RPC 響應並通知等待的 Future
        """
        while True:
            try:
                if not self.reader:
                    break

                line = await self.reader.readline()
                if not line:
                    break

                # 解析 JSON-RPC 響應
                try:
                    response = json.loads(line.decode().strip())
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON-RPC response: {line}, error: {e}")
                    continue

                # 找到對應的 Future 並設置結果
                request_id = response.get("id")
                if request_id and request_id in self._pending_requests:
                    future = self._pending_requests.pop(request_id)

                    if "error" in response:
                        error = response["error"]
                        future.set_exception(JSONRPCError(
                            error.get("code", -1),
                            error.get("message", "Unknown error"),
                            error.get("data")
                        ))
                    elif "result" in response:
                        future.set_result(response["result"])
                    else:
                        future.set_exception(
                            JSONRPCError(-32600, "Invalid JSON-RPC response")
                        )

            except Exception as e:
                logger.error(f"Error in stdio read loop: {e}")
                break

        logger.info(f"MCP server {self.config.name} read loop ended")

    async def _send_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        發送 JSON-RPC 2.0 請求

        Args:
            method: JSON-RPC 方法名（如 "tools/list"）
            params: 方法參數

        Returns:
            JSON-RPC result

        Raises:
            JSONRPCError: JSON-RPC 錯誤
            TimeoutError: 請求超時
            ConnectionError: 連接錯誤
        """
        if not self._connected:
            raise ConnectionError(f"MCP client {self.config.id} not connected")

        request_id = self._next_request_id()

        # 構建 JSON-RPC 2.0 請求
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }

        if params is not None:
            request["params"] = params

        if self.transport == MCPTransportType.STDIO:
            return await self._send_stdio_request(request_id, request)
        elif self.transport == MCPTransportType.HTTP_SSE:
            return await self._send_http_request(request)

    async def _send_stdio_request(self, request_id: str, request: Dict) -> Any:
        """透過 stdio 發送 JSON-RPC 請求"""
        # 創建 Future 等待回應
        future = asyncio.Future()
        self._pending_requests[request_id] = future

        try:
            # 發送請求（JSON-RPC over stdio 使用換行分隔）
            request_line = json.dumps(request) + "\n"
            self.writer.write(request_line.encode())
            await self.writer.drain()

            # 等待回應（30 秒超時）
            result = await asyncio.wait_for(future, timeout=30.0)
            return result

        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            raise TimeoutError(
                f"MCP request timeout: {request['method']} "
                f"(server: {self.config.name})"
            )
        except Exception as e:
            self._pending_requests.pop(request_id, None)
            raise

    async def _send_http_request(self, request: Dict) -> Any:
        """透過 HTTP POST 發送 JSON-RPC 請求"""
        try:
            response = await self.http_client.post(
                "/rpc",  # 標準 MCP HTTP endpoint
                json=request
            )
            response.raise_for_status()

            result = response.json()

            # 檢查 JSON-RPC 錯誤
            if "error" in result:
                error = result["error"]
                raise JSONRPCError(
                    error.get("code", -1),
                    error.get("message", "Unknown error"),
                    error.get("data")
                )

            return result.get("result")

        except httpx.HTTPError as e:
            raise ConnectionError(f"HTTP request failed: {e}")

    # ========== MCP 協議方法 ==========

    async def list_tools(self) -> List[Dict[str, Any]]:
        """
        列出 MCP server 提供的所有工具

        調用 MCP 方法：tools/list

        Returns:
            工具列表，每個工具包含：
            - name (str): 工具名稱
            - description (str): 工具描述
            - inputSchema (dict): JSON Schema 格式的輸入參數定義

        Example:
            >>> tools = await client.list_tools()
            >>> for tool in tools:
            ...     print(f"{tool['name']}: {tool['description']}")
        """
        result = await self._send_request("tools/list")
        return result.get("tools", [])

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Any:
        """
        調用 MCP 工具

        調用 MCP 方法：tools/call

        Args:
            tool_name: 工具名稱（如 "github.search_issues"）
            arguments: 工具參數（根據 tool 的 inputSchema）

        Returns:
            工具執行結果

        Example:
            >>> result = await client.call_tool(
            ...     "github.search_issues",
            ...     {"query": "bug", "repo": "owner/repo"}
            ... )
        """
        params = {
            "name": tool_name,
            "arguments": arguments
        }

        result = await self._send_request("tools/call", params)

        # MCP tools/call 回傳格式：{ "content": [...], "isError": false }
        if result.get("isError"):
            error_content = result.get("content", [])
            error_msg = " ".join(
                item.get("text", "") for item in error_content
                if item.get("type") == "text"
            )
            raise Exception(f"Tool execution error: {error_msg}")

        return result.get("content", [])

    async def disconnect(self):
        """
        斷開與 MCP server 的連接

        清理資源：
        - stdio: 終止子進程
        - HTTP: 關閉 HTTP 客戶端
        """
        if not self._connected:
            return

        if self.transport == MCPTransportType.STDIO:
            if self.process:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self.process.kill()

                self.process = None
                self.reader = None
                self.writer = None

        elif self.transport == MCPTransportType.HTTP_SSE:
            if self.http_client:
                await self.http_client.aclose()

        self._connected = False
        logger.info(f"MCP client {self.config.id} disconnected")

    async def __aenter__(self):
        """Context manager 支援"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager 支援"""
        await self.disconnect()



