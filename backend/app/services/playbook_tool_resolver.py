"""
Playbook 工具解析和環境變數替換

提供工具依賴的解析、環境變數替換、工具可用性檢查等功能。

設計原則：
- 支援環境變數替換（${VAR}語法）
- 安全的配置處理
- 詳細的錯誤信息
"""

import os
import re
from typing import Dict, Any, List, Optional
import logging

from backend.app.models.playbook import ToolDependency
from backend.app.services.tools.registry import (
    get_tool,
    get_mindscape_tool,
)
from backend.app.services.tools.adapters import (
    is_langchain_available,
    is_mcp_available,
    MCPServerManager,
)

logger = logging.getLogger(__name__)


class ToolDependencyResolver:
    """
    工具依賴解析器

    負責：
    1. 解析工具依賴配置
    2. 環境變數替換
    3. 檢查工具可用性
    4. 自動安裝工具（如可能）

    Example:
        >>> resolver = ToolDependencyResolver()
        >>> result = await resolver.resolve_dependencies(playbook.metadata.tool_dependencies)
        >>> print(result["available"], result["missing"])
    """

    def __init__(self, mcp_manager: Optional[MCPServerManager] = None):
        """
        初始化解析器

        Args:
            mcp_manager: MCP Server Manager（可選，用於 MCP 工具）
        """
        self.mcp_manager = mcp_manager or MCPServerManager()
        self._env_var_pattern = re.compile(r'\$\{([^}]+)\}')

    def substitute_env_vars(
        self,
        config: Dict[str, Any],
        env_overrides: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        替換配置中的環境變數

        支援語法：${VAR_NAME} 或 ${VAR_NAME:default_value}

        Args:
            config: 原始配置（可能包含 ${VAR}）
            env_overrides: 環境變數覆蓋（優先於系統環境變數）

        Returns:
            替換後的配置

        Example:
            >>> config = {"api_key": "${API_KEY}", "timeout": 30}
            >>> result = resolver.substitute_env_vars(config)
            >>> # result = {"api_key": "actual_key_from_env", "timeout": 30}
        """
        def substitute_value(value: Any) -> Any:
            if isinstance(value, str):
                # 查找所有 ${VAR} 模式
                matches = self._env_var_pattern.findall(value)

                for var_expr in matches:
                    # 支援默認值：${VAR:default}
                    if ':' in var_expr:
                        var_name, default_value = var_expr.split(':', 1)
                    else:
                        var_name = var_expr
                        default_value = None

                    # 獲取環境變數值
                    env_value = None
                    if env_overrides and var_name in env_overrides:
                        env_value = env_overrides[var_name]
                    else:
                        env_value = os.getenv(var_name)

                    # 使用默認值（如果指定）
                    if env_value is None and default_value is not None:
                        env_value = default_value

                    # 替換
                    if env_value is not None:
                        value = value.replace(f'${{{var_expr}}}', env_value)
                    else:
                        logger.warning(
                            f"Environment variable {var_name} not found, "
                            f"keeping placeholder ${{{var_expr}}}"
                        )

                return value

            elif isinstance(value, dict):
                return {k: substitute_value(v) for k, v in value.items()}

            elif isinstance(value, list):
                return [substitute_value(item) for item in value]

            else:
                return value

        return substitute_value(config)

    async def check_tool_availability(
        self,
        tool_dep: ToolDependency,
        env_overrides: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        檢查單個工具的可用性

        Args:
            tool_dep: 工具依賴聲明
            env_overrides: 環境變數覆蓋

        Returns:
            {
                "available": bool,
                "tool": MindscapeTool or None,
                "error": str or None,
                "can_auto_install": bool
            }
        """
        result = {
            "name": tool_dep.name,
            "type": tool_dep.type,
            "available": False,
            "tool": None,
            "error": None,
            "can_auto_install": False
        }

        try:
            if tool_dep.type == "builtin":
                # 內建工具：從 registry 查找
                tool = get_mindscape_tool(tool_dep.name)
                if tool:
                    result["available"] = True
                    result["tool"] = tool
                else:
                    result["error"] = f"內建工具 {tool_dep.name} 未註冊"

            elif tool_dep.type == "langchain":
                # LangChain 工具
                if not is_langchain_available():
                    result["error"] = "LangChain 未安裝"
                    result["can_auto_install"] = True
                else:
                    # 嘗試從 registry 查找
                    tool = get_mindscape_tool(f"langchain.{tool_dep.name}")
                    if tool:
                        result["available"] = True
                        result["tool"] = tool
                    else:
                        # 可以自動安裝
                        result["can_auto_install"] = True
                        result["error"] = f"LangChain 工具 {tool_dep.name} 未安裝"

            elif tool_dep.type == "mcp":
                # MCP 工具
                if not is_mcp_available():
                    result["error"] = "MCP 依賴未安裝"
                    result["can_auto_install"] = False
                else:
                    # 檢查 MCP server 是否已連接
                    server_id = tool_dep.source
                    if not server_id:
                        result["error"] = "MCP 工具缺少 source（server ID）"
                    else:
                        tool = self.mcp_manager.get_tool_by_name(tool_dep.name)
                        if tool:
                            result["available"] = True
                            result["tool"] = tool
                        else:
                            result["can_auto_install"] = True
                            result["error"] = f"MCP server {server_id} 未連接或工具不存在"

        except Exception as e:
            logger.error(f"檢查工具 {tool_dep.name} 時出錯: {e}")
            result["error"] = str(e)

        return result

    async def resolve_dependencies(
        self,
        tool_dependencies: List[ToolDependency],
        env_overrides: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        解析所有工具依賴

        Args:
            tool_dependencies: 工具依賴列表
            env_overrides: 環境變數覆蓋

        Returns:
            {
                "available": List[Dict],      # 可用的工具
                "missing": List[Dict],          # 缺失的工具
                "can_auto_install": List[Dict], # 可自動安裝的工具
                "errors": List[str]             # 錯誤信息
            }
        """
        result = {
            "available": [],
            "missing": [],
            "can_auto_install": [],
            "errors": []
        }

        for tool_dep in tool_dependencies:
            # 替換環境變數
            tool_dep_resolved = tool_dep.copy(deep=True)
            tool_dep_resolved.config = self.substitute_env_vars(
                tool_dep.config,
                env_overrides
            )

            # 檢查可用性
            check_result = await self.check_tool_availability(
                tool_dep_resolved,
                env_overrides
            )

            if check_result["available"]:
                result["available"].append({
                    "name": tool_dep.name,
                    "type": tool_dep.type,
                    "tool": check_result["tool"]
                })
            else:
                missing_info = {
                    "name": tool_dep.name,
                    "type": tool_dep.type,
                    "required": tool_dep.required,
                    "error": check_result["error"]
                }

                result["missing"].append(missing_info)

                if check_result["can_auto_install"]:
                    result["can_auto_install"].append(missing_info)

                # 如果是必需工具，記錄錯誤
                if tool_dep.required:
                    error_msg = (
                        f"必需工具 {tool_dep.name} ({tool_dep.type}) 不可用: "
                        f"{check_result['error']}"
                    )
                    result["errors"].append(error_msg)
                    logger.error(error_msg)

        return result

    async def auto_install_tool(
        self,
        tool_dep: ToolDependency,
        env_overrides: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        自動安裝工具（如可能）

        Args:
            tool_dep: 工具依賴聲明
            env_overrides: 環境變數覆蓋

        Returns:
            {
                "success": bool,
                "tool": MindscapeTool or None,
                "error": str or None
            }
        """
        result = {
            "success": False,
            "tool": None,
            "error": None
        }

        try:
            if tool_dep.type == "langchain":
                result = await self._auto_install_langchain_tool(
                    tool_dep,
                    env_overrides
                )

            elif tool_dep.type == "mcp":
                result = await self._auto_install_mcp_tool(
                    tool_dep,
                    env_overrides
                )

            else:
                result["error"] = f"工具類型 {tool_dep.type} 不支援自動安裝"

        except Exception as e:
            logger.error(f"自動安裝工具 {tool_dep.name} 失敗: {e}")
            result["error"] = str(e)

        return result

    async def _auto_install_langchain_tool(
        self,
        tool_dep: ToolDependency,
        env_overrides: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """自動安裝 LangChain 工具"""
        from backend.app.services.tools.adapters import from_langchain
        from backend.app.services.tools.registry import register_mindscape_tool

        try:
            # 動態導入 LangChain 工具
            module_path, class_name = tool_dep.source.rsplit('.', 1)
            module = __import__(module_path, fromlist=[class_name])
            tool_class = getattr(module, class_name)

            # 實例化工具
            config = self.substitute_env_vars(tool_dep.config, env_overrides)
            lc_tool = tool_class(**config)

            # 轉換為 MindscapeTool
            mindscape_tool = from_langchain(lc_tool)

            # 註冊
            register_mindscape_tool(f"langchain.{tool_dep.name}", mindscape_tool)

            logger.info(f"成功安裝 LangChain 工具: {tool_dep.name}")

            return {
                "success": True,
                "tool": mindscape_tool,
                "error": None
            }

        except Exception as e:
            logger.error(f"安裝 LangChain 工具 {tool_dep.name} 失敗: {e}")
            return {
                "success": False,
                "tool": None,
                "error": str(e)
            }

    async def _auto_install_mcp_tool(
        self,
        tool_dep: ToolDependency,
        env_overrides: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """自動安裝 MCP 工具（連接 MCP server）"""
        from backend.app.services.tools.adapters import MCPServerConfig, MCPTransportType

        try:
            server_id = tool_dep.source
            if not server_id:
                return {
                    "success": False,
                    "tool": None,
                    "error": "MCP 工具缺少 source（server ID）"
                }

            # 檢查 server 是否已配置
            servers = self.mcp_manager.list_servers()
            existing_server = next(
                (s for s in servers if s["id"] == server_id),
                None
            )

            if not existing_server:
                return {
                    "success": False,
                    "tool": None,
                    "error": f"MCP server {server_id} 未配置"
                }

            # 連接 server 並發現工具
            if not existing_server["connected"]:
                # TODO: 需要從配置中獲取 MCPServerConfig
                logger.warning(
                    f"MCP server {server_id} 未連接，"
                    f"請先配置並連接 server"
                )
                return {
                    "success": False,
                    "tool": None,
                    "error": f"MCP server {server_id} 未連接"
                }

            # 查找工具
            tool = self.mcp_manager.get_tool_by_name(tool_dep.name)
            if tool:
                logger.info(f"找到 MCP 工具: {tool_dep.name}")
                return {
                    "success": True,
                    "tool": tool,
                    "error": None
                }
            else:
                return {
                    "success": False,
                    "tool": None,
                    "error": f"在 MCP server {server_id} 中找不到工具 {tool_dep.name}"
                }

        except Exception as e:
            logger.error(f"安裝 MCP 工具 {tool_dep.name} 失敗: {e}")
            return {
                "success": False,
                "tool": None,
                "error": str(e)
            }
