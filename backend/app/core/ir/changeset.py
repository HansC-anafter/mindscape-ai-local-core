"""
ChangeSet IR Schema

Intermediate representation for change sets (patch + preview + rollback).
Used to pass change information between stages in the ChangeSet pipeline.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from enum import Enum


class ChangeSetStatus(str, Enum):
    """ChangeSet status"""
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPLIED_TO_SANDBOX = "applied_to_sandbox"
    APPROVED = "approved"
    PROMOTED_TO_PROD = "promoted_to_prod"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


class ChangeType(str, Enum):
    """Change type"""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    MOVE = "move"
    COPY = "copy"


@dataclass
class ChangePatch:
    """Individual change patch"""
    change_type: ChangeType
    target: str  # Target resource identifier
    path: Optional[str] = None  # Path within target (for nested changes)
    old_value: Optional[Any] = None  # Old value (for update/delete)
    new_value: Optional[Any] = None  # New value (for create/update)
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        result = {
            "change_type": self.change_type.value,
            "target": self.target,
        }
        if self.path:
            result["path"] = self.path
        if self.old_value is not None:
            result["old_value"] = self.old_value
        if self.new_value is not None:
            result["new_value"] = self.new_value
        if self.metadata:
            result["metadata"] = self.metadata
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChangePatch":
        """Create ChangePatch from dictionary"""
        return cls(
            change_type=ChangeType(data["change_type"]),
            target=data["target"],
            path=data.get("path"),
            old_value=data.get("old_value"),
            new_value=data.get("new_value"),
            metadata=data.get("metadata"),
        )


@dataclass
class ChangeSetIR:
    """
    ChangeSet IR Schema

    Structured intermediate representation for change sets.
    Used to pass change information between stages in the ChangeSet pipeline:
    - Plan generation stage → ChangeSet creation stage
    - ChangeSet creation stage → Sandbox application stage
    - Sandbox application stage → Preview/Diff generation stage
    - Preview/Diff generation stage → Approval/Promotion stage
    """
    # ChangeSet identification
    changeset_id: str
    workspace_id: str

    # Change patches
    patches: List[ChangePatch]

    # Status and workflow
    status: ChangeSetStatus = ChangeSetStatus.DRAFT

    # Preview and diff
    preview_url: Optional[str] = None  # Preview URL (after sandbox application)
    diff_summary: Optional[str] = None  # Human-readable diff summary
    diff_details: Optional[Dict[str, Any]] = None  # Detailed diff (structured)

    # Rollback information
    rollback_point_id: Optional[str] = None  # Rollback point ID (if created)
    rollback_available: bool = False  # Whether rollback is available

    # Approval and promotion
    approved_by: Optional[str] = None  # User ID who approved
    approved_at: Optional[datetime] = None
    promoted_at: Optional[datetime] = None

    # Timestamps
    created_at: Optional[datetime] = None
    applied_to_sandbox_at: Optional[datetime] = None

    # Execution context
    execution_id: Optional[str] = None
    plan_id: Optional[str] = None

    # Version for backward compatibility
    version: str = "1.0"

    # Additional metadata
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Initialize default values"""
        if self.created_at is None:
            self.created_at = _utc_now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "version": self.version,
            "changeset_id": self.changeset_id,
            "workspace_id": self.workspace_id,
            "status": self.status.value,
            "patches": [patch.to_dict() for patch in self.patches],
            "rollback_available": self.rollback_available,
        }

        if self.preview_url:
            result["preview_url"] = self.preview_url
        if self.diff_summary:
            result["diff_summary"] = self.diff_summary
        if self.diff_details:
            result["diff_details"] = self.diff_details
        if self.rollback_point_id:
            result["rollback_point_id"] = self.rollback_point_id
        if self.approved_by:
            result["approved_by"] = self.approved_by
        if self.approved_at:
            result["approved_at"] = self.approved_at.isoformat()
        if self.promoted_at:
            result["promoted_at"] = self.promoted_at.isoformat()
        if self.created_at:
            result["created_at"] = self.created_at.isoformat()
        if self.applied_to_sandbox_at:
            result["applied_to_sandbox_at"] = self.applied_to_sandbox_at.isoformat()
        if self.execution_id:
            result["execution_id"] = self.execution_id
        if self.plan_id:
            result["plan_id"] = self.plan_id
        if self.metadata:
            result["metadata"] = self.metadata

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChangeSetIR":
        """Create ChangeSetIR from dictionary"""
        patches = [ChangePatch.from_dict(p) for p in data.get("patches", [])]
        status = ChangeSetStatus(data.get("status", "draft"))

        created_at = None
        if data.get("created_at"):
            created_at = datetime.fromisoformat(data["created_at"])

        applied_to_sandbox_at = None
        if data.get("applied_to_sandbox_at"):
            applied_to_sandbox_at = datetime.fromisoformat(data["applied_to_sandbox_at"])

        approved_at = None
        if data.get("approved_at"):
            approved_at = datetime.fromisoformat(data["approved_at"])

        promoted_at = None
        if data.get("promoted_at"):
            promoted_at = datetime.fromisoformat(data["promoted_at"])

        return cls(
            changeset_id=data["changeset_id"],
            workspace_id=data["workspace_id"],
            patches=patches,
            status=status,
            preview_url=data.get("preview_url"),
            diff_summary=data.get("diff_summary"),
            diff_details=data.get("diff_details"),
            rollback_point_id=data.get("rollback_point_id"),
            rollback_available=data.get("rollback_available", False),
            approved_by=data.get("approved_by"),
            approved_at=approved_at,
            promoted_at=promoted_at,
            created_at=created_at,
            applied_to_sandbox_at=applied_to_sandbox_at,
            execution_id=data.get("execution_id"),
            plan_id=data.get("plan_id"),
            version=data.get("version", "1.0"),
            metadata=data.get("metadata"),
        )










