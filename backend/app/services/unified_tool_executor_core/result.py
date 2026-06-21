from typing import Any, Dict, Optional

from backend.app.services.unified_tool_executor_core.clock import _utc_now


class ToolExecutionResult:
    """Unified tool execution result."""

    def __init__(
        self,
        success: bool,
        tool_name: str,
        tool_type: str,
        result: Any = None,
        error: Optional[str] = None,
        execution_time: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.success = success
        self.tool_name = tool_name
        self.tool_type = tool_type
        self.result = result
        self.error = error
        self.execution_time = execution_time
        self.metadata = metadata or {}
        self.timestamp = _utc_now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "tool_name": self.tool_name,
            "tool_type": self.tool_type,
            "result": self.result,
            "error": self.error,
            "execution_time": self.execution_time,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }
