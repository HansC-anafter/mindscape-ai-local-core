from typing import Any, Dict, List, Optional
import logging

from backend.app.models.playbook import ToolDependency
from backend.app.services.playbook_tool_resolver import ToolDependencyResolver
from backend.app.services.tools.adapters import MCPServerManager
from backend.app.services.tools.base import MindscapeTool
from backend.app.services.unified_tool_executor_core.capability import (
    resolve_capability_tool,
)
from backend.app.services.unified_tool_executor_core.clock import _utc_now
from backend.app.services.unified_tool_executor_core.lookup import (
    get_tool,
    parse_tool_name,
)
from backend.app.services.unified_tool_executor_core.result import ToolExecutionResult

logger = logging.getLogger("backend.app.services.unified_tool_executor")


class UnifiedToolExecutor:
    """Unified tool executor."""

    def __init__(
        self,
        mcp_manager: Optional[MCPServerManager] = None,
        tool_resolver: Optional[ToolDependencyResolver] = None,
    ):
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
        self._workspace_tools_loaded = False

    async def execute_tool(
        self, tool_name: str, arguments: Dict[str, Any], timeout: Optional[float] = 30.0
    ) -> ToolExecutionResult:
        """Execute tool through the unified interface."""
        start_time = _utc_now()
        tool_type = "unknown"

        try:
            from backend.app.services.tool_execution_admission import (
                prepare_tool_admission,
            )

            arguments, admission_snapshot = await prepare_tool_admission(
                tool_name=tool_name,
                arguments=arguments,
            )
            tool_type, actual_tool_name = self._parse_tool_name(tool_name)
            tool = await self._get_tool(tool_type, actual_tool_name)

            if not tool:
                return ToolExecutionResult(
                    success=False,
                    tool_name=tool_name,
                    tool_type=tool_type,
                    error=f"Tool {tool_name} not found or not registered",
                )

            logger.info("Executing tool: %s, arguments: %s", tool_name, arguments)
            tool_result = await tool.safe_execute(**arguments)
            tool_result = _normalize_tool_result(tool_result)

            execution_time = (_utc_now() - start_time).total_seconds()
            execution_result = ToolExecutionResult(
                success=tool_result.success,
                tool_name=tool_name,
                tool_type=tool_type,
                result=tool_result.result,
                error=tool_result.error,
                execution_time=execution_time,
                metadata={
                    "tool_description": getattr(tool, "description", ""),
                    "tool_source": getattr(tool.metadata, "source_type", tool_type),
                    **(tool_result.metadata or {}),
                    **(
                        {
                            "admission_snapshot_hash": (
                                admission_snapshot.snapshot_hash
                            )
                        }
                        if admission_snapshot is not None
                        else {}
                    ),
                },
            )

            self._execution_history.append(execution_result)
            logger.info(
                "Tool execution succeeded: %s, duration: %.2fs",
                tool_name,
                execution_time,
            )
            return execution_result

        except Exception as exc:
            execution_time = (_utc_now() - start_time).total_seconds()
            error_msg = f"Tool execution failed: {str(exc)}"
            logger.error(error_msg, exc_info=True)

            execution_result = ToolExecutionResult(
                success=False,
                tool_name=tool_name,
                tool_type=tool_type,
                error=error_msg,
                execution_time=execution_time,
            )
            self._execution_history.append(execution_result)
            return execution_result

    def _parse_tool_name(self, tool_name: str) -> tuple[str, str]:
        return parse_tool_name(tool_name)

    async def _get_tool(
        self, tool_type: str, tool_name: str
    ) -> Optional[MindscapeTool]:
        return await get_tool(self, tool_type, tool_name)

    def _resolve_capability_tool(self, tool_id: str) -> Optional[MindscapeTool]:
        return resolve_capability_tool(tool_id)

    async def execute_tool_dependency(
        self,
        tool_dep: ToolDependency,
        arguments: Dict[str, Any],
        env_overrides: Optional[Dict[str, str]] = None,
    ) -> ToolExecutionResult:
        """Execute tool dependency from Playbook configuration."""
        from backend.app.services.tool_execution_admission import (
            prepare_tool_admission,
        )

        arguments, admission_snapshot = await prepare_tool_admission(
            tool_name=tool_dep.name,
            arguments=arguments,
        )
        result = await self._execute_tool_dependency_resolved(
            tool_dep,
            arguments,
            env_overrides,
        )
        if admission_snapshot is not None:
            result.metadata = {
                **(result.metadata or {}),
                "admission_snapshot_hash": (
                    admission_snapshot.snapshot_hash
                ),
            }
        return result

    async def _execute_tool_dependency_resolved(
        self,
        tool_dep: ToolDependency,
        arguments: Dict[str, Any],
        env_overrides: Optional[Dict[str, str]] = None,
    ) -> ToolExecutionResult:
        tool_dep_resolved = tool_dep.copy(deep=True)
        tool_dep_resolved.config = self.tool_resolver.substitute_env_vars(
            tool_dep.config, env_overrides
        )

        check_result = await self.tool_resolver.check_tool_availability(
            tool_dep_resolved, env_overrides
        )

        if not check_result["available"] and tool_dep.fallback:
            logger.warning(
                "Tool %s unavailable, using fallback: %s",
                tool_dep.name,
                tool_dep.fallback,
            )
            fallback_dep = ToolDependency(
                type=tool_dep.type,
                name=tool_dep.fallback,
                source=tool_dep.source,
                required=tool_dep.required,
            )
            return await self._execute_tool_dependency_resolved(
                fallback_dep, arguments, env_overrides
            )

        if check_result["available"] and check_result["tool"]:
            return await self._execute_available_dependency(
                tool_dep, check_result["tool"], arguments
            )

        return ToolExecutionResult(
            success=False,
            tool_name=tool_dep.name,
            tool_type=tool_dep.type,
            error=check_result["error"] or "Tool unavailable",
        )

    async def _execute_available_dependency(
        self, tool_dep: ToolDependency, tool, arguments: Dict[str, Any]
    ) -> ToolExecutionResult:
        start_time = _utc_now()

        try:
            tool_result = await tool.safe_execute(**arguments)
            tool_result = _normalize_tool_result(tool_result)
            execution_time = (_utc_now() - start_time).total_seconds()
            return ToolExecutionResult(
                success=tool_result.success,
                tool_name=tool_dep.name,
                tool_type=tool_dep.type,
                result=tool_result.result,
                error=tool_result.error,
                execution_time=execution_time,
            )

        except Exception as exc:
            execution_time = (_utc_now() - start_time).total_seconds()
            return ToolExecutionResult(
                success=False,
                tool_name=tool_dep.name,
                tool_type=tool_dep.type,
                error=str(exc),
                execution_time=execution_time,
            )

    def get_execution_history(
        self, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get execution history."""
        history = self._execution_history
        if limit:
            history = history[-limit:]
        return [result.to_dict() for result in history]

    def clear_history(self):
        """Clear execution history."""
        self._execution_history.clear()
        logger.info("Execution history cleared")

    def get_statistics(self) -> Dict[str, Any]:
        """Get execution statistics."""
        if not self._execution_history:
            return {
                "total_executions": 0,
                "success_count": 0,
                "failure_count": 0,
                "success_rate": 0.0,
                "avg_execution_time": 0.0,
            }

        total = len(self._execution_history)
        success_count = sum(1 for item in self._execution_history if item.success)
        execution_times = [
            item.execution_time
            for item in self._execution_history
            if item.execution_time is not None
        ]
        avg_time = (
            sum(execution_times) / len(execution_times) if execution_times else 0.0
        )

        return {
            "total_executions": total,
            "success_count": success_count,
            "failure_count": total - success_count,
            "success_rate": success_count / total if total > 0 else 0.0,
            "avg_execution_time": avg_time,
            "tool_type_distribution": self._get_tool_type_distribution(),
        }

    def _get_tool_type_distribution(self) -> Dict[str, int]:
        """Get tool type distribution."""
        distribution = {}
        for result in self._execution_history:
            tool_type = result.tool_type
            distribution[tool_type] = distribution.get(tool_type, 0) + 1
        return distribution


def _normalize_tool_result(tool_result):
    nested = getattr(tool_result, "result", None)
    if not (
        hasattr(nested, "success")
        and hasattr(nested, "result")
        and hasattr(nested, "error")
    ):
        return tool_result

    outer_metadata = getattr(tool_result, "metadata", None) or {}
    nested_metadata = getattr(nested, "metadata", None) or {}
    return type(
        "NormalizedToolResult",
        (),
        {
            "success": nested.success,
            "result": nested.result,
            "error": nested.error,
            "metadata": {**outer_metadata, **nested_metadata},
        },
    )()
