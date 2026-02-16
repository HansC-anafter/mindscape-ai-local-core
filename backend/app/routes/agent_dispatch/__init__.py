"""
Agent Dispatch — Package entry point.

Re-exports public API from sub-modules and provides a unified router
that merges WebSocket and REST endpoints.
"""

from fastapi import APIRouter

from .models import (
    AgentClient,
    AgentControlClient,
    PendingTask,
    InflightTask,
    ReservedTask,
    AgentResultRequest,
    AgentResultResponse,
    AckRequest,
    ProgressRequest,
)
from .dispatch_manager import (
    AgentDispatchManager,
    get_agent_dispatch_manager,
    agent_dispatch_manager,
)
from .ws_endpoints import router as ws_router
from .rest_endpoints import router as rest_router

router = APIRouter()
router.include_router(ws_router)
router.include_router(rest_router)

__all__ = [
    "router",
    "AgentDispatchManager",
    "get_agent_dispatch_manager",
    "agent_dispatch_manager",
    "AgentClient",
    "AgentControlClient",
    "PendingTask",
    "InflightTask",
    "ReservedTask",
    "AgentResultRequest",
    "AgentResultResponse",
    "AckRequest",
    "ProgressRequest",
]
