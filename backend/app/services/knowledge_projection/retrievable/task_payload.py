"""Compact pointer-only payload for the existing tool_execution lane."""

from __future__ import annotations

import json
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


MAX_KNOWLEDGE_PROJECTION_TASK_BYTES = 32 * 1024
_MAX_POINTER_STRING_BYTES = 2048
_MAX_POINTER_COLLECTION_ITEMS = 256
_MAX_POINTER_DEPTH = 8
_FORBIDDEN_POINTER_KEY_FRAGMENTS = (
    "api_key",
    "authorization",
    "base64",
    "binary",
    "body",
    "credential",
    "password",
    "private_key",
    "raw_content",
    "refresh_token",
    "secret",
    "token",
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DescriptorPointer(_StrictModel):
    capability_code: str = Field(pattern=r"^[a-z0-9_]+$")
    capability_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    descriptor_id: str = Field(pattern=r"^[a-z0-9_]+$")
    descriptor_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class SourcePointer(_StrictModel):
    source_kind: Literal["object", "artifact", "memory", "document"]
    source_instance_id: str = Field(min_length=1, max_length=128)
    source_ref: str = Field(min_length=1, max_length=1024)
    source_revision: str = Field(min_length=1, max_length=256)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    object_kind: Optional[str] = Field(default=None, max_length=128)
    artifact_selector: Optional[str] = Field(default=None, max_length=256)


class KnowledgeProjectionTaskPayload(_StrictModel):
    contract_version: Literal["knowledge.project-source.v1"] = (
        "knowledge.project-source.v1"
    )
    internal_task_id: str = Field(min_length=1, max_length=128)
    intake_id: str = Field(min_length=1, max_length=128)
    actor_user_id: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=128)
    group_id: Optional[str] = Field(default=None, max_length=128)
    trigger_mode: Literal["source_revision", "explicit_reindex", "revoke"]
    descriptor: DescriptorPointer
    source: SourcePointer
    sources: tuple[SourcePointer, ...] = Field(
        default=(),
        min_length=0,
        max_length=256,
    )
    checkpoint: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_pointer_only_checkpoint(
        self,
    ) -> "KnowledgeProjectionTaskPayload":
        if self.sources and self.sources[0] != self.source:
            raise ValueError(
                "knowledge_projection_task_primary_source_mismatch"
            )
        if self.sources and len(
            {item.source_instance_id for item in self.sources}
        ) != len(self.sources):
            raise ValueError(
                "knowledge_projection_task_source_instance_duplicate"
            )
        _validate_pointer_value(self.checkpoint, path="checkpoint", depth=0)
        return self

    @property
    def source_page(self) -> tuple[SourcePointer, ...]:
        return self.sources or (self.source,)

    def bounded_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_KNOWLEDGE_PROJECTION_TASK_BYTES:
            raise ValueError("knowledge_projection_task_payload_budget_exceeded")
        return payload


def _validate_pointer_value(value: Any, *, path: str, depth: int) -> None:
    """Reject secrets and source bodies from the queue's pointer-only envelope."""

    if depth > _MAX_POINTER_DEPTH:
        raise ValueError("knowledge_projection_task_pointer_depth_exceeded")
    if value is None or isinstance(value, (bool, int, float)):
        return
    if isinstance(value, str):
        if len(value.encode("utf-8")) > _MAX_POINTER_STRING_BYTES:
            raise ValueError(
                f"knowledge_projection_task_pointer_string_too_large:{path}"
            )
        return
    if isinstance(value, dict):
        if len(value) > _MAX_POINTER_COLLECTION_ITEMS:
            raise ValueError(
                f"knowledge_projection_task_pointer_mapping_too_large:{path}"
            )
        for key, nested in value.items():
            normalized_key = str(key or "").strip().lower()
            if not normalized_key:
                raise ValueError(
                    f"knowledge_projection_task_pointer_key_invalid:{path}"
                )
            if any(
                fragment in normalized_key
                for fragment in _FORBIDDEN_POINTER_KEY_FRAGMENTS
            ):
                raise ValueError(
                    f"knowledge_projection_task_secret_or_body_forbidden:"
                    f"{path}.{normalized_key}"
                )
            _validate_pointer_value(
                nested,
                path=f"{path}.{normalized_key}",
                depth=depth + 1,
            )
        return
    if isinstance(value, (list, tuple)):
        if len(value) > _MAX_POINTER_COLLECTION_ITEMS:
            raise ValueError(
                f"knowledge_projection_task_pointer_sequence_too_large:{path}"
            )
        for index, nested in enumerate(value):
            _validate_pointer_value(
                nested,
                path=f"{path}[{index}]",
                depth=depth + 1,
            )
        return
    raise ValueError(
        f"knowledge_projection_task_pointer_value_forbidden:{path}"
    )


__all__ = [
    "DescriptorPointer",
    "KnowledgeProjectionTaskPayload",
    "MAX_KNOWLEDGE_PROJECTION_TASK_BYTES",
    "SourcePointer",
]
