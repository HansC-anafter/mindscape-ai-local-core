"""
PlanState Schema

LLM plans (can have multiple versions, can be overwritten).
PlanState can be written by LLM (can overwrite previous versions).
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class PlanStatus(str, Enum):
    """Plan status"""
    DRAFT = "draft"
    ACTIVE = "active"
    EXECUTING = "executing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class PlanVersion:
    """
    Plan version

    Represents a single version of a plan.
    Plans can have multiple versions (LLM can overwrite).
    """
    version_id: str
    version_number: int  # Sequential version number

    # Plan content
    plan_data: Dict[str, Any]  # Plan content (e.g., ExecutionPlan)

    # Version metadata
    created_by: str  # Creator identifier (model_name, user_id, etc.)
    created_at: datetime = field(default_factory=datetime.utcnow)
    reasoning: Optional[str] = None  # Reasoning for this version

    # Version status
    is_active: bool = False  # Whether this version is active

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "version_id": self.version_id,
            "version_number": self.version_number,
            "plan_data": self.plan_data,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "reasoning": self.reasoning,
            "is_active": self.is_active,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlanVersion":
        """Create PlanVersion from dictionary"""
        created_at = datetime.fromisoformat(data["created_at"]) if isinstance(data.get("created_at"), str) else data.get("created_at", datetime.utcnow())
        return cls(
            version_id=data["version_id"],
            version_number=data["version_number"],
            plan_data=data["plan_data"],
            created_by=data["created_by"],
            created_at=created_at,
            reasoning=data.get("reasoning"),
            is_active=data.get("is_active", False),
            metadata=data.get("metadata", {}),
        )


@dataclass
class PlanState:
    """
    PlanState Schema

    LLM plans (can have multiple versions, can be overwritten).
    PlanState can be written by LLM (can overwrite previous versions).

    Write rule: LLM can write/overwrite PlanState.
    """
    # State identification
    state_id: str
    workspace_id: str
    plan_id: str  # Associated plan ID (e.g., ExecutionPlan.id)

    # Plan versions (can have multiple versions)
    versions: List[PlanVersion] = field(default_factory=list)

    # Current status
    status: PlanStatus = PlanStatus.DRAFT

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # Version for backward compatibility
    version: str = "1.0"

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_version(self, plan_version: PlanVersion, created_by: str) -> None:
        """
        Add a new version to PlanState

        Args:
            plan_version: PlanVersion to add
            created_by: Creator identifier (model_name, user_id, etc.)

        Note:
            This method deactivates all previous versions and activates the new one.
        """
        # Deactivate all previous versions
        for version in self.versions:
            version.is_active = False

        # Set new version as active
        plan_version.is_active = True
        plan_version.created_by = created_by
        self.versions.append(plan_version)

        # Sort by version number
        self.versions.sort(key=lambda v: v.version_number)

        self.updated_at = datetime.utcnow()

    def get_active_version(self) -> Optional[PlanVersion]:
        """Get active version"""
        for version in self.versions:
            if version.is_active:
                return version
        return None

    def get_latest_version(self) -> Optional[PlanVersion]:
        """Get latest version (by version number)"""
        if not self.versions:
            return None
        return max(self.versions, key=lambda v: v.version_number)

    def get_version(self, version_number: int) -> Optional[PlanVersion]:
        """Get version by version number"""
        for version in self.versions:
            if version.version_number == version_number:
                return version
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "version": self.version,
            "state_id": self.state_id,
            "workspace_id": self.workspace_id,
            "plan_id": self.plan_id,
            "status": self.status.value,
            "versions": [v.to_dict() for v in self.versions],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlanState":
        """Create PlanState from dictionary"""
        versions = [PlanVersion.from_dict(v) for v in data.get("versions", [])]
        status = PlanStatus(data.get("status", "draft"))

        created_at = datetime.fromisoformat(data["created_at"]) if isinstance(data.get("created_at"), str) else data.get("created_at", datetime.utcnow())
        updated_at = datetime.fromisoformat(data["updated_at"]) if isinstance(data.get("updated_at"), str) else data.get("updated_at", datetime.utcnow())

        return cls(
            state_id=data["state_id"],
            workspace_id=data["workspace_id"],
            plan_id=data["plan_id"],
            versions=versions,
            status=status,
            created_at=created_at,
            updated_at=updated_at,
            version=data.get("version", "1.0"),
            metadata=data.get("metadata", {}),
        )

