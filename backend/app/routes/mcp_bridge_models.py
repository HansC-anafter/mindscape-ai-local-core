from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ChatMessage(BaseModel):
    role: str = Field(..., description="user | assistant")
    content: str
    timestamp: Optional[str] = None
    message_id: Optional[str] = None


class IDEReceipt(BaseModel):
    """Governance Inv.3 - Receipts over Claims"""

    step: str = Field(
        ..., description="intent_extract | steward_analyze | project_detect"
    )
    trace_id: str
    output_hash: str = Field(..., description="SHA-256 of output")
    output_summary: Optional[Dict[str, Any]] = None
    completed_at: Optional[str] = None


class ChatSyncRequest(BaseModel):
    workspace_id: str
    conversation_id: str
    surface_type: str = Field(
        default="ide", description="cursor | windsurf | copilot | gemini_cli"
    )
    trace_id: Optional[str] = None
    profile_id: Optional[str] = None
    messages: List[ChatMessage]
    playbook_executed: Optional[str] = None
    ide_receipts: Optional[List[IDEReceipt]] = None


class ExtractedIntent(BaseModel):
    label: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str = Field(default="ide")
    metadata: Optional[Dict[str, Any]] = None


class IntentSubmitRequest(BaseModel):
    workspace_id: str
    message: str
    message_id: Optional[str] = None
    profile_id: Optional[str] = None
    extracted_intents: List[ExtractedIntent]
    extracted_themes: Optional[List[str]] = None


class IntentLayoutAction(BaseModel):
    """Maps to IntentOperation structure."""

    operation_type: str = Field(
        ..., description="CREATE_INTENT_CARD | UPDATE_INTENT_CARD | ARCHIVE"
    )
    intent_id: Optional[str] = None
    intent_data: Dict[str, Any] = Field(default_factory=dict)
    relation_signals: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    reasoning: str = ""


class LayoutPlan(BaseModel):
    long_term_intents: List[IntentLayoutAction] = Field(default_factory=list)
    ephemeral_tasks: Optional[List[Dict[str, Any]]] = None


class IntentLayoutExecuteRequest(BaseModel):
    workspace_id: str
    profile_id: Optional[str] = None
    layout_plan: LayoutPlan


class DetectedProject(BaseModel):
    mode: str = Field(
        default="project", description="quick_task | micro_flow | project"
    )
    project_type: Optional[str] = None
    project_title: Optional[str] = None
    playbook_sequence: Optional[List[str]] = None
    initial_spec_md: Optional[str] = None
    confidence: Optional[float] = None


class ProjectDetectRequest(BaseModel):
    workspace_id: str
    message: str
    profile_id: Optional[str] = None
    detected_project: DetectedProject
