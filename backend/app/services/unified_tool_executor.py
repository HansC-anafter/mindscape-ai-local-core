"""
統一工具調用接口

提供統一的工具調用接口，支援三種工具類型：
- builtin: 內建工具
- langchain: LangChain 工具
- mcp: MCP 工具

設計原則：
- 統一接口：無論工具來源，調用方式一致
- 錯誤處理：完整的錯誤處理和降級機制
- 異步優先：所有調用都是異步
- 日誌記錄：詳細的執行日誌
"""

from typing import Dict, Any, Optional, List
import logging
from datetime import datetime

from backend.app.models.playbook import ToolDependency
from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.registry import get_mindscape_tool
from backend.app.services.tools.adapters import (
    is_langchain_available,
    is_mcp_available,
    MCPServerManager,
)
from backend.app.services.playbook_tool_resolver import ToolDependencyResolver

logger = logging.getLogger(__name__)


class ToolExecutionResult:
    """
    工具執行結果

    統一的返回格式，包含執行狀態、結果、錯誤信息等。
    """

    def __init__(
        self,
        success: bool,
        tool_name: str,
        tool_type: str,
        result: Any = None,
        error: Optional[str] = None,
        execution_time: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.success = success
        self.tool_name = tool_name
        self.tool_type = tool_type
        self.result = result
        self.error = error
        self.execution_time = execution_time
        self.metadata = metadata or {}
        self.timestamp = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return {
            "success": self.success,
            "tool_name": self.tool_name,
            "tool_type": self.tool_type,
            "result": self.result,
            "error": self.error,
            "execution_time": self.execution_time,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat()
        }


class UnifiedToolExecutor:
    """
    統一工具執行器

    提供統一的工具調用接口，隱藏不同工具類型的差異。

    Example:
        >>> executor = UnifiedToolExecutor()
        >>>
        >>> # 執行內建工具
        >>> result = await executor.execute_tool(
        ...     "wordpress.list_posts",
        ...     {"per_page": 10}
        ... )
        >>>
        >>> # 執行 LangChain 工具
        >>> result = await executor.execute_tool(
        ...     "langchain.wikipedia",
        ...     {"query": "Python programming"}
        ... )
        >>>
        >>> # 執行 MCP 工具
        >>> result = await executor.execute_tool(
        ...     "mcp.github.search_issues",
        ...     {"repo": "owner/repo", "query": "bug"}
        ... )
    """

    def __init__(
        self,
        mcp_manager: Optional[MCPServerManager] = None,
        tool_resolver: Optional[ToolDependencyResolver] = None
    ):
        """
        初始化執行器

        Args:
            mcp_manager: MCP Server Manager（可選）
            tool_resolver: 工具依賴解析器（可選）
        """
        self.mcp_manager = mcp_manager or MCPServerManager()
        self.tool_resolver = tool_resolver or ToolDependencyResolver(self.mcp_manager)
        self._execution_history: List[ToolExecutionResult] = []

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: Optional[float] = 30.0
    ) -> ToolExecutionResult:
        """
        執行工具（統一接口）

        Args:
            tool_name: 工具名稱（支援多種格式）
                - "wordpress" -> 內建工具
                - "langchain.wikipedia" -> LangChain 工具
                - "mcp.github.search_issues" -> MCP 工具
            arguments: 工具參數
            timeout: 超時時間（秒）

        Returns:
            ToolExecutionResult: 執行結果

        Example:
            >>> result = await executor.execute_tool(
            ...     "wikipedia",
            ...     {"query": "Python"}
            ... )
            >>> if result.success:
            ...     print(result.result)
            ... else:
            ...     print(result.error)
        """
        start_time = datetime.utcnow()

        try:
            # 解析工具類型
            tool_type, actual_tool_name = self._parse_tool_name(tool_name)

            # 獲取工具實例
            tool = await self._get_tool(tool_type, actual_tool_name)

            if not tool:
                return ToolExecutionResult(
                    success=False,
                    tool_name=tool_name,
                    tool_type=tool_type,
                    error=f"工具 {tool_name} 不存在或未註冊"
                )

            # 執行工具
            logger.info(f"執行工具: {tool_name}, 參數: {arguments}")
            result = await tool.safe_execute(arguments)

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            execution_result = ToolExecutionResult(
                success=True,
                tool_name=tool_name,
                tool_type=tool_type,
                result=result,
                execution_time=execution_time,
                metadata={
                    "tool_description": getattr(tool, "description", ""),
                    "tool_source": getattr(tool.metadata, "source_type", tool_type)
                }
            )

            # 記錄歷史
            self._execution_history.append(execution_result)

            logger.info(
                f"工具執行成功: {tool_name}, "
                f"耗時: {execution_time:.2f}s"
            )

            return execution_result

        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds()

            error_msg = f"工具執行失敗: {str(e)}"
            logger.error(error_msg, exc_info=True)

            execution_result = ToolExecutionResult(
                success=False,
                tool_name=tool_name,
                tool_type=tool_type or "unknown",
                error=error_msg,
                execution_time=execution_time
            )

            self._execution_history.append(execution_result)

            return execution_result

    def _parse_tool_name(self, tool_name: str) -> tuple[str, str]:
        """
        解析工具名稱，確定工具類型

        Args:
            tool_name: 工具名稱

        Returns:
            (tool_type, actual_name)

        Example:
            >>> _parse_tool_name("langchain.wikipedia")
            >>> ("langchain", "wikipedia")
            >>>
            >>> _parse_tool_name("wordpress")
            >>> ("builtin", "wordpress")
        """
        if "." in tool_name:
            parts = tool_name.split(".", 1)
            if parts[0] in ["builtin", "langchain", "mcp"]:
                return parts[0], parts[1]

        # 默認為內建工具
        return "builtin", tool_name

    async def _get_tool(
        self,
        tool_type: str,
        tool_name: str
    ) -> Optional[MindscapeTool]:
        """
        獲取工具實例

        Args:
            tool_type: 工具類型（builtin/langchain/mcp）
            tool_name: 工具名稱

        Returns:
            工具實例或 None
        """
        if tool_type == "builtin":
            # 從 registry 獲取內建工具
            return get_mindscape_tool(tool_name)

        elif tool_type == "langchain":
            # 獲取 LangChain 工具
            if not is_langchain_available():
                logger.warning("LangChain 未安裝")
                return None

            # 嘗試從 registry 獲取（已註冊的）
            full_name = f"langchain.{tool_name}"
            tool = get_mindscape_tool(full_name)

            if not tool:
                logger.warning(f"LangChain 工具 {tool_name} 未註冊")

            return tool

        elif tool_type == "mcp":
            # 獲取 MCP 工具
            if not is_mcp_available():
                logger.warning("MCP 依賴未安裝")
                return None

            # 從 MCP manager 獲取
            tool = self.mcp_manager.get_tool_by_name(tool_name)

            if not tool:
                logger.warning(f"MCP 工具 {tool_name} 不存在")

            return tool

        else:
            logger.error(f"不支援的工具類型: {tool_type}")
            return None

    async def execute_tool_dependency(
        self,
        tool_dep: ToolDependency,
        arguments: Dict[str, Any],
        env_overrides: Optional[Dict[str, str]] = None
    ) -> ToolExecutionResult:
        """
        執行工具依賴（從 Playbook 配置）

        自動處理：
        - 環境變數替換
        - 工具查找
        - Fallback 機制

        Args:
            tool_dep: 工具依賴聲明
            arguments: 工具參數
            env_overrides: 環境變數覆蓋

        Returns:
            ToolExecutionResult: 執行結果
        """
        # 1. 替換環境變數
        tool_dep_resolved = tool_dep.copy(deep=True)
        tool_dep_resolved.config = self.tool_resolver.substitute_env_vars(
            tool_dep.config,
            env_overrides
        )

        # 2. 檢查工具可用性
        check_result = await self.tool_resolver.check_tool_availability(
            tool_dep_resolved,
            env_overrides
        )

        # 3. 如果工具不可用且有 fallback
        if not check_result["available"] and tool_dep.fallback:
            logger.warning(
                f"工具 {tool_dep.name} 不可用，"
                f"使用 fallback: {tool_dep.fallback}"
            )

            # 創建 fallback 工具依賴
            fallback_dep = ToolDependency(
                type=tool_dep.type,
                name=tool_dep.fallback,
                source=tool_dep.source,
                required=tool_dep.required
            )

            return await self.execute_tool_dependency(
                fallback_dep,
                arguments,
                env_overrides
            )

        # 4. 執行工具
        if check_result["available"] and check_result["tool"]:
            tool = check_result["tool"]

            start_time = datetime.utcnow()

            try:
                result = await tool.safe_execute(arguments)
                execution_time = (datetime.utcnow() - start_time).total_seconds()

                return ToolExecutionResult(
                    success=True,
                    tool_name=tool_dep.name,
                    tool_type=tool_dep.type,
                    result=result,
                    execution_time=execution_time
                )

            except Exception as e:
                execution_time = (datetime.utcnow() - start_time).total_seconds()

                return ToolExecutionResult(
                    success=False,
                    tool_name=tool_dep.name,
                    tool_type=tool_dep.type,
                    error=str(e),
                    execution_time=execution_time
                )

        else:
            # 工具不可用
            return ToolExecutionResult(
                success=False,
                tool_name=tool_dep.name,
                tool_type=tool_dep.type,
                error=check_result["error"] or "工具不可用"
            )

    def get_execution_history(
        self,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        獲取執行歷史

        Args:
            limit: 限制返回數量（最新的 N 條）

        Returns:
            執行歷史列表
        """
        history = self._execution_history

        if limit:
            history = history[-limit:]

        return [result.to_dict() for result in history]

    def clear_history(self):
        """清空執行歷史"""
        self._execution_history.clear()
        logger.info("執行歷史已清空")

    def get_statistics(self) -> Dict[str, Any]:
        """
        獲取執行統計

        Returns:
            統計信息（成功率、平均執行時間等）
        """
        if not self._execution_history:
            return {
                "total_executions": 0,
                "success_count": 0,
                "failure_count": 0,
                "success_rate": 0.0,
                "avg_execution_time": 0.0
            }

        total = len(self._execution_history)
        success_count = sum(1 for r in self._execution_history if r.success)
        failure_count = total - success_count

        execution_times = [
            r.execution_time
            for r in self._execution_history
            if r.execution_time is not None
        ]

        avg_time = sum(execution_times) / len(execution_times) if execution_times else 0.0

        return {
            "total_executions": total,
            "success_count": success_count,
            "failure_count": failure_count,
            "success_rate": success_count / total if total > 0 else 0.0,
            "avg_execution_time": avg_time,
            "tool_type_distribution": self._get_tool_type_distribution()
        }

    def _get_tool_type_distribution(self) -> Dict[str, int]:
        """獲取工具類型分布"""
        distribution = {}

        for result in self._execution_history:
            tool_type = result.tool_type
            distribution[tool_type] = distribution.get(tool_type, 0) + 1

        return distribution



