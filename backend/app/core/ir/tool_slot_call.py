"""
ToolSlotCall IR Schema

Intermediate representation for tool slot call requests and results.
Used to pass tool execution information between stages.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class ToolSlotCallStatus(str, Enum):
    """Tool slot call status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ToolSlotCallIR:
    """
    ToolSlotCall IR Schema

    Structured intermediate representation for tool slot call requests and results.
    Used to pass tool execution information between stages:
    - Plan generation stage → Tool execution stage
    - Tool execution stage → Result formatting stage
    """
    # Tool identification
    tool_slot: str  # e.g., "cms.footer.apply_style"
    tool_id: Optional[str] = None  # Resolved tool ID (if available)

    # Call parameters
    parameters: Dict[str, Any] = None  # Tool call parameters

    # Execution metadata
    status: ToolSlotCallStatus = ToolSlotCallStatus.PENDING
    error_message: Optional[str] = None
    error_code: Optional[str] = None

    # Results
    result: Optional[Dict[str, Any]] = None  # Tool execution result
    result_type: Optional[str] = None  # Result type: "text", "json", "file", etc.

    # Timestamps
    requested_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Execution context
    workspace_id: Optional[str] = None
    project_id: Optional[str] = None
    execution_id: Optional[str] = None

    # Policy and validation
    policy_checked: bool = False
    policy_result: Optional[Dict[str, Any]] = None  # Policy check result

    # Version for backward compatibility
    version: str = "1.0"

    # Additional metadata
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Initialize default values"""
        if self.parameters is None:
            self.parameters = {}
        if self.requested_at is None:
            self.requested_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "version": self.version,
            "tool_slot": self.tool_slot,
            "status": self.status.value,
            "parameters": self.parameters,
            "policy_checked": self.policy_checked,
        }

        if self.tool_id:
            result["tool_id"] = self.tool_id
        if self.error_message:
            result["error_message"] = self.error_message
        if self.error_code:
            result["error_code"] = self.error_code
        if self.result:
            result["result"] = self.result
        if self.result_type:
            result["result_type"] = self.result_type
        if self.requested_at:
            result["requested_at"] = self.requested_at.isoformat()
        if self.started_at:
            result["started_at"] = self.started_at.isoformat()
        if self.completed_at:
            result["completed_at"] = self.completed_at.isoformat()
        if self.workspace_id:
            result["workspace_id"] = self.workspace_id
        if self.project_id:
            result["project_id"] = self.project_id
        if self.execution_id:
            result["execution_id"] = self.execution_id
        if self.policy_result:
            result["policy_result"] = self.policy_result
        if self.metadata:
            result["metadata"] = self.metadata

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolSlotCallIR":
        """Create ToolSlotCallIR from dictionary"""
        requested_at = None
        if data.get("requested_at"):
            requested_at = datetime.fromisoformat(data["requested_at"])

        started_at = None
        if data.get("started_at"):
            started_at = datetime.fromisoformat(data["started_at"])

        completed_at = None
        if data.get("completed_at"):
            completed_at = datetime.fromisoformat(data["completed_at"])

        status = ToolSlotCallStatus(data.get("status", "pending"))

        return cls(
            tool_slot=data["tool_slot"],
            tool_id=data.get("tool_id"),
            parameters=data.get("parameters", {}),
            status=status,
            error_message=data.get("error_message"),
            error_code=data.get("error_code"),
            result=data.get("result"),
            result_type=data.get("result_type"),
            requested_at=requested_at,
            started_at=started_at,
            completed_at=completed_at,
            workspace_id=data.get("workspace_id"),
            project_id=data.get("project_id"),
            execution_id=data.get("execution_id"),
            policy_checked=data.get("policy_checked", False),
            policy_result=data.get("policy_result"),
            version=data.get("version", "1.0"),
            metadata=data.get("metadata"),
        )









