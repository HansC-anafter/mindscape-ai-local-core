"""DB-backed admission receipt for the hidden projection runner tool."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InternalProjectionSourceBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    intake_id: str = Field(min_length=1, max_length=128)
    source_instance_id: str = Field(min_length=1, max_length=128)
    source_revision: str = Field(min_length=1, max_length=256)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class InternalProjectionAdmissionReceipt(BaseModel):
    """Prove that a runner task came from the source-intake transaction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[
        "mindscape.knowledge-projection-internal-admission.v1"
    ] = "mindscape.knowledge-projection-internal-admission.v1"
    task_id: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=128)
    actor_user_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=128)
    group_id: str | None = Field(default=None, max_length=128)
    capability_code: str = Field(pattern=r"^[a-z0-9_]+$")
    descriptor_id: str = Field(pattern=r"^[a-z0-9_]+$")
    descriptor_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    sources: tuple[InternalProjectionSourceBinding, ...] = Field(
        min_length=1,
        max_length=256,
    )
    trigger_mode: Literal["source_revision", "explicit_reindex", "revoke"]
    receipt_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_hash(self) -> "InternalProjectionAdmissionReceipt":
        if len({item.intake_id for item in self.sources}) != len(
            self.sources
        ):
            raise ValueError(
                "knowledge_projection_internal_admission_intake_duplicate"
            )
        if len({item.source_instance_id for item in self.sources}) != len(
            self.sources
        ):
            raise ValueError(
                "knowledge_projection_internal_admission_source_duplicate"
            )
        if self.receipt_hash != _receipt_hash(
            self.model_dump(mode="json", exclude={"receipt_hash"})
        ):
            raise ValueError(
                "knowledge_projection_internal_admission_hash_mismatch"
            )
        return self


def build_internal_projection_admission(
    **payload: Any,
) -> InternalProjectionAdmissionReceipt:
    normalized_payload = dict(payload)
    normalized_payload["sources"] = tuple(
        InternalProjectionSourceBinding.model_validate(item)
        for item in payload.get("sources") or ()
    )
    unsigned = InternalProjectionAdmissionReceipt.model_construct(
        **normalized_payload,
        receipt_hash="0" * 64,
    ).model_dump(mode="json", exclude={"receipt_hash"})
    return InternalProjectionAdmissionReceipt.model_validate(
        {
            **unsigned,
            "receipt_hash": _receipt_hash(unsigned),
        }
    )


def _receipt_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


__all__ = [
    "InternalProjectionAdmissionReceipt",
    "InternalProjectionSourceBinding",
    "build_internal_projection_admission",
]
