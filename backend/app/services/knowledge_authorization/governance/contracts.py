"""Strict governance commands for knowledge ACL replacement."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..contracts import PrincipalRef, RetrievalAccessContext
from ..write_contracts import KnowledgeAclMutation, KnowledgeGrant


class KnowledgeAccessGrantInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    principal_type: Literal[
        "user",
        "workspace_role",
        "group_role",
        "service",
    ]
    principal_id: str = Field(min_length=1, max_length=256)
    relation: Literal["reader", "editor", "owner", "ingester"]
    effect: Literal["allow", "deny"] = "allow"
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None

    def to_domain(self) -> KnowledgeGrant:
        return KnowledgeGrant(
            principal=PrincipalRef(
                self.principal_type,
                self.principal_id,
            ),
            relation=self.relation,
            effect=self.effect,
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )


class KnowledgeAgentMaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_role: str = Field(
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:@/+~-]{0,255}$",
    )
    effect: Literal["allow", "deny"]


class KnowledgeAccessReplacementCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_authz_revision: int = Field(ge=1)
    acknowledge_complete_replacement: Literal[True]
    grants: tuple[KnowledgeAccessGrantInput, ...] = Field(
        min_length=1,
        max_length=200,
    )
    agent_masks: tuple[KnowledgeAgentMaskInput, ...] = Field(
        max_length=100,
    )

    @model_validator(mode="after")
    def reject_duplicate_grants(self) -> "KnowledgeAccessReplacementCommand":
        canonical = tuple(grant.to_domain() for grant in self.grants)
        if len(set(canonical)) != len(canonical):
            raise ValueError("knowledge_access_duplicate_grant")
        masks = tuple(
            (mask.agent_role, mask.effect)
            for mask in self.agent_masks
        )
        if len(set(masks)) != len(masks):
            raise ValueError("knowledge_access_duplicate_agent_mask")
        return self

    def to_domain(self) -> KnowledgeAclMutation:
        return KnowledgeAclMutation(
            expected_authz_revision=self.expected_authz_revision,
            grants=tuple(grant.to_domain() for grant in self.grants),
        )


class KnowledgeProjectionActionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["reindex", "retry", "revoke", "restore"]
    expected_authz_revision: int = Field(ge=1)
    expected_source_revision: str = Field(min_length=1, max_length=256)


class KnowledgeAccessScope:
    """Verified service input; never construct from request payload identity."""

    def __init__(
        self,
        *,
        access_context: RetrievalAccessContext,
        workspace_id: str,
    ) -> None:
        self.access_context = access_context
        self.workspace_id = workspace_id


__all__ = [
    "KnowledgeAccessGrantInput",
    "KnowledgeAgentMaskInput",
    "KnowledgeAccessReplacementCommand",
    "KnowledgeAccessScope",
    "KnowledgeProjectionActionCommand",
]
