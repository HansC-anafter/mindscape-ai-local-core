"""
Compatibility wrapper for the Gemini-specific import path.

The shared host bridge task executor now lives under external_agents.bridge.
"""

from backend.app.services.external_agents.bridge.task_executor import (
    ExecutionContext,
    ExecutionResult,
    HostBridgeTaskExecutor,
)

TaskExecutor = HostBridgeTaskExecutor

__all__ = [
    "ExecutionContext",
    "ExecutionResult",
    "HostBridgeTaskExecutor",
    "TaskExecutor",
]
