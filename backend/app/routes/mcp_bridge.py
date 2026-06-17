"""
MCP Bridge API Routes.

Backend endpoints for MCP Gateway to Workspace communication.
These routes are registered in app_bootstrap/routes.py.
"""

from fastapi import APIRouter

from .mcp_bridge_chat import chat_sync
from .mcp_bridge_intents import intent_layout_execute, intent_submit
from .mcp_bridge_models import (
    ChatMessage,
    ChatSyncRequest,
    DetectedProject,
    ExtractedIntent,
    IDEReceipt,
    IntentLayoutAction,
    IntentLayoutExecuteRequest,
    IntentSubmitRequest,
    LayoutPlan,
    ProjectDetectRequest,
)
from .mcp_bridge_projects import project_detect

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp-bridge"])

router.post("/chat/sync")(chat_sync)
router.post("/intent/submit")(intent_submit)
router.post("/intent/layout/execute")(intent_layout_execute)
router.post("/project/detect")(project_detect)

__all__ = [
    "router",
    "ChatMessage",
    "IDEReceipt",
    "ChatSyncRequest",
    "ExtractedIntent",
    "IntentSubmitRequest",
    "IntentLayoutAction",
    "LayoutPlan",
    "IntentLayoutExecuteRequest",
    "DetectedProject",
    "ProjectDetectRequest",
    "chat_sync",
    "intent_submit",
    "intent_layout_execute",
    "project_detect",
]
