"""
Unified tool execution interface

Provides unified tool execution interface supporting three tool types:
- builtin: Built-in tools
- langchain: LangChain tools
- mcp: MCP tools
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
    Tool execution result

    Unified return format containing execution status, result, error information.
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
        """Convert to dictionary"""
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
    Unified tool executor

    Provides unified tool execution interface, hiding differences between tool types.
    """

    def __init__(
        self,
        mcp_manager: Optional[MCPServerManager] = None,
        tool_resolver: Optional[ToolDependencyResolver] = None
    ):
        """
        Initialize executor

        Args:
            mcp_manager: MCP Server Manager (optional)
            tool_resolver: Tool dependency resolver (optional)
        """
        if mcp_manager is None:
            if MCPServerManager is not None:
                self.mcp_manager = MCPServerManager()
            else:
                self.mcp_manager = None
        else:
            self.mcp_manager = mcp_manager

        if tool_resolver is None:
            self.tool_resolver = ToolDependencyResolver(self.mcp_manager)
        else:
            self.tool_resolver = tool_resolver

        self._execution_history: List[ToolExecutionResult] = []

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: Optional[float] = 30.0
    ) -> ToolExecutionResult:
        """
        Execute tool (unified interface)

        Args:
            tool_name: Tool name (supports multiple formats)
                - "wordpress" -> builtin tool
                - "langchain.wikipedia" -> LangChain tool
                - "mcp.github.search_issues" -> MCP tool
            arguments: Tool arguments
            timeout: Timeout in seconds

        Returns:
            ToolExecutionResult: Execution result
        """
        start_time = datetime.utcnow()

        try:
            tool_type, actual_tool_name = self._parse_tool_name(tool_name)
            tool = await self._get_tool(tool_type, actual_tool_name)

            if not tool:
                return ToolExecutionResult(
                    success=False,
                    tool_name=tool_name,
                    tool_type=tool_type,
                    error=f"Tool {tool_name} not found or not registered"
                )

            logger.info(f"Executing tool: {tool_name}, arguments: {arguments}")
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

            self._execution_history.append(execution_result)

            logger.info(
                f"Tool execution succeeded: {tool_name}, "
                f"duration: {execution_time:.2f}s"
            )

            return execution_result

        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds()

            error_msg = f"Tool execution failed: {str(e)}"
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
        Parse tool name to determine tool type

        Args:
            tool_name: Tool name

        Returns:
            (tool_type, actual_name)
        """
        if "." in tool_name:
            parts = tool_name.split(".", 1)
            if parts[0] in ["builtin", "langchain", "mcp"]:
                return parts[0], parts[1]

        return "builtin", tool_name

    async def _get_tool(
        self,
        tool_type: str,
        tool_name: str
    ) -> Optional[MindscapeTool]:
        """
        Get tool instance

        Args:
            tool_type: Tool type (builtin/langchain/mcp)
            tool_name: Tool name

        Returns:
            Tool instance or None
        """
        if tool_type == "builtin":
            return get_mindscape_tool(tool_name)

        elif tool_type == "langchain":
            if not is_langchain_available():
                logger.warning("LangChain not installed")
                return None

            full_name = f"langchain.{tool_name}"
            tool = get_mindscape_tool(full_name)

            if not tool:
                logger.warning(f"LangChain tool {tool_name} not registered")

            return tool

        elif tool_type == "mcp":
            if not is_mcp_available():
                logger.warning("MCP dependencies not installed")
                return None

            if self.mcp_manager is None:
                logger.warning("MCP Manager not initialized")
                return None

            tool = self.mcp_manager.get_tool_by_name(tool_name)

            if not tool:
                logger.warning(f"MCP tool {tool_name} not found")

            return tool

        else:
            logger.error(f"Unsupported tool type: {tool_type}")
            return None

    async def execute_tool_dependency(
        self,
        tool_dep: ToolDependency,
        arguments: Dict[str, Any],
        env_overrides: Optional[Dict[str, str]] = None
    ) -> ToolExecutionResult:
        """
        Execute tool dependency (from Playbook configuration)

        Automatically handles:
        - Environment variable substitution
        - Tool lookup
        - Fallback mechanism

        Args:
            tool_dep: Tool dependency declaration
            arguments: Tool arguments
            env_overrides: Environment variable overrides

        Returns:
            ToolExecutionResult: Execution result
        """
        tool_dep_resolved = tool_dep.copy(deep=True)
        tool_dep_resolved.config = self.tool_resolver.substitute_env_vars(
            tool_dep.config,
            env_overrides
        )

        check_result = await self.tool_resolver.check_tool_availability(
            tool_dep_resolved,
            env_overrides
        )

        if not check_result["available"] and tool_dep.fallback:
            logger.warning(
                f"Tool {tool_dep.name} unavailable, "
                f"using fallback: {tool_dep.fallback}"
            )
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
            return ToolExecutionResult(
                success=False,
                tool_name=tool_dep.name,
                tool_type=tool_dep.type,
                error=check_result["error"] or "Tool unavailable"
            )

    def get_execution_history(
        self,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get execution history

        Args:
            limit: Limit number of results (latest N records)

        Returns:
            List of execution history records
        """
        history = self._execution_history

        if limit:
            history = history[-limit:]

        return [result.to_dict() for result in history]

    def clear_history(self):
        """Clear execution history"""
        self._execution_history.clear()
        logger.info("Execution history cleared")

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get execution statistics

        Returns:
            Statistics (success rate, average execution time, etc.)
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
        """Get tool type distribution"""
        distribution = {}

        for result in self._execution_history:
            tool_type = result.tool_type
            distribution[tool_type] = distribution.get(tool_type, 0) + 1

        return distribution



