"""Legacy authoring adapters backed by the versioned v1 contract package."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class CheckpointArtifact:
    artifact_id: str
    type: str
    data: Any
    should_embed: bool = False
    is_artifact: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "type": self.type,
            "data": self.data if self.should_embed else None,
            "should_embed": self.should_embed,
            "is_artifact": self.is_artifact,
        }


@dataclass
class Checkpoint:
    checkpoint_schema_version: str = "1.0.0"
    step_id: str = ""
    step_name: str = ""
    state: str = "pending"
    bundle_version: str | None = None
    playbook_version: str | None = None
    artifacts: list[CheckpointArtifact] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.checkpoint_schema_version:
            raise ValueError("checkpoint_schema_version cannot be empty")
        if not self.step_id:
            raise ValueError("step_id cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_schema_version": self.checkpoint_schema_version,
            "step_id": self.step_id,
            "step_name": self.step_name,
            "state": self.state,
            "bundle_version": self.bundle_version,
            "playbook_version": self.playbook_version,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Checkpoint":
        return cls(
            checkpoint_schema_version=data.get("checkpoint_schema_version", "1.0.0"),
            step_id=data.get("step_id", ""),
            step_name=data.get("step_name", ""),
            state=data.get("state", "pending"),
            bundle_version=data.get("bundle_version"),
            playbook_version=data.get("playbook_version"),
            artifacts=[
                CheckpointArtifact(
                    artifact_id=item.get("artifact_id", ""),
                    type=item.get("type", ""),
                    data=item.get("data"),
                    should_embed=item.get("should_embed", False),
                    is_artifact=item.get("is_artifact", True),
                )
                for item in data.get("artifacts", [])
            ],
            metadata=dict(data.get("metadata", {})),
        )

    def add_metadata(self, key: str, value: Any) -> None:
        self.metadata[key] = value

    def set_execution_info(self, execution_id: str, trace_id: str) -> None:
        self.metadata.update(
            {
                "execution_id": execution_id,
                "trace_id": trace_id,
                "checkpoint_at": datetime.now(timezone.utc).isoformat(),
            }
        )


@dataclass
class EventArtifact:
    artifact_id: str
    type: str
    data: Any
    is_artifact: bool = True
    is_final: bool = False
    should_embed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "type": self.type,
            "data": self.data if self.should_embed else None,
            "is_artifact": self.is_artifact,
            "is_final": self.is_final,
            "should_embed": self.should_embed,
        }


@dataclass
class Event:
    event_schema_version: str = "1.0.0"
    event_id: str = ""
    execution_id: str | None = None
    trace_id: str | None = None
    step_id: str = ""
    step_name: str = ""
    bundle_version: str | None = None
    playbook_version: str | None = None
    status: str = "pending"
    artifacts: list[EventArtifact] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_schema_version:
            raise ValueError("event_schema_version cannot be empty")
        if not self.event_id:
            raise ValueError("event_id cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_schema_version": self.event_schema_version,
            "event_id": self.event_id,
            "execution_id": self.execution_id,
            "trace_id": self.trace_id,
            "step_id": self.step_id,
            "step_name": self.step_name,
            "bundle_version": self.bundle_version,
            "playbook_version": self.playbook_version,
            "status": self.status,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        return cls(
            event_schema_version=data.get("event_schema_version", "1.0.0"),
            event_id=data.get("event_id", ""),
            execution_id=data.get("execution_id"),
            trace_id=data.get("trace_id"),
            step_id=data.get("step_id", ""),
            step_name=data.get("step_name", ""),
            bundle_version=data.get("bundle_version"),
            playbook_version=data.get("playbook_version"),
            status=data.get("status", "pending"),
            artifacts=[
                EventArtifact(
                    artifact_id=item.get("artifact_id", ""),
                    type=item.get("type", ""),
                    data=item.get("data"),
                    is_artifact=item.get("is_artifact", True),
                    is_final=item.get("is_final", False),
                    should_embed=item.get("should_embed", True),
                )
                for item in data.get("artifacts", [])
            ],
            metadata=dict(data.get("metadata", {})),
        )

    def add_metadata(self, key: str, value: Any) -> None:
        self.metadata[key] = value

    def set_execution_info(
        self,
        execution_id: str,
        trace_id: str,
        tenant_id: str,
        user_id: str | None = None,
        capability_code: str | None = None,
    ) -> None:
        self.execution_id = execution_id
        self.trace_id = trace_id
        self.metadata["tenant_id"] = tenant_id
        if user_id:
            self.metadata["user_id"] = user_id
        if capability_code:
            self.metadata["capability_code"] = capability_code
        self.metadata["timestamp"] = datetime.now(timezone.utc).isoformat()

    def set_provider_info(
        self,
        provider: str,
        model: str,
        cost: dict[str, Any] | None = None,
    ) -> None:
        self.metadata["provider"] = provider
        self.metadata["model"] = model
        if cost:
            self.metadata["cost"] = cost
