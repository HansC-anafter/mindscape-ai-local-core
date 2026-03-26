from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PolicyMode(str, Enum):
    LOCAL_REQUIRED = "local_required"
    CLOUD_REQUIRED = "cloud_required"
    PREFER_LOCAL = "prefer_local"
    PREFER_CLOUD = "prefer_cloud"
    PORTABLE = "portable"


class BindingMode(str, Enum):
    LIVE_PROFILE_BINDING = "live_profile_binding"
    FROZEN_WORKLOAD_SNAPSHOT = "frozen_workload_snapshot"


class ResolutionMode(str, Enum):
    FIXED = "fixed"
    LIVE_WORKSPACE_POLICY = "live_workspace_policy"


class ExecutionBackend(str, Enum):
    LOCAL = "local"
    REMOTE = "remote"


class WorkloadExecutionIntent(BaseModel):
    """Portable workload-intent contract with backward-compatible aliases."""

    workload_kind: str
    kind: Optional[str] = None
    resolution_mode: Optional[str] = None
    policy_mode: Optional[str] = None
    binding_mode: Optional[str] = None
    deployment_scope_hint: Optional[str] = None
    capability_profile: Optional[str] = None
    logical_target: Optional[str] = None
    site_key: Optional[str] = None
    preference_ref: Optional[str] = None
    execution_backend: Optional[str] = None
    target_device_id: Optional[str] = None
    workspace_id: Optional[str] = None
    allow_local_fallback: bool = False
    allow_cloud_fallback: bool = False
    meta: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="before")
    @classmethod
    def _normalize_kind_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        workload_kind = str(
            payload.get("workload_kind") or payload.get("kind") or ""
        ).strip()
        if workload_kind:
            payload["workload_kind"] = workload_kind
            payload.setdefault("kind", workload_kind)
        return payload

    @classmethod
    def from_payload(
        cls,
        payload: Optional[Dict[str, Any]],
        *,
        fallback_workload_kind: Optional[str] = None,
    ) -> Optional["WorkloadExecutionIntent"]:
        if not isinstance(payload, dict):
            return None
        data = dict(payload)
        if fallback_workload_kind and not (
            data.get("workload_kind") or data.get("kind")
        ):
            data["workload_kind"] = fallback_workload_kind
        return cls(**data)

    def to_payload(self, *, include_legacy_aliases: bool = True) -> Dict[str, Any]:
        payload = self.model_dump(mode="json", exclude_none=True)
        if include_legacy_aliases:
            payload["kind"] = str(payload.get("kind") or self.workload_kind)
        return payload
