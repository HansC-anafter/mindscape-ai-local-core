from enum import Enum
from typing import Any, Dict, Optional


class ExecutionMode(str, Enum):
    """Execution mode."""

    SYNC = "sync"
    ASYNC = "async"
    STREAM = "stream"


class ExecutionResult:
    """Execution result."""

    def __init__(
        self,
        execution_id: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        progress: float = 0.0,
    ):
        self.execution_id = execution_id
        self.status = status
        self.result = result
        self.error = error
        self.progress = progress
