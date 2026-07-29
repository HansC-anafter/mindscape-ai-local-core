"""Strict owner, grant, mutation, and resource-binding write contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .contracts import PrincipalRef


_SOURCE_KINDS = frozenset({"object", "artifact", "memory", "document"})
_SCOPE_TYPES = frozenset({"tenant", "workspace", "group"})
_CLASSIFICATIONS = frozenset({"private", "workspace", "group"})
_RELATIONS = frozenset({"reader", "editor", "owner", "ingester"})
_EFFECTS = frozenset({"allow", "deny"})


def _required(value: str, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"knowledge_write_{field_name}_required")
    return normalized


@dataclass(frozen=True)
class KnowledgeResourceIdentity:
    tenant_id: str
    owner_capability_code: str
    source_kind: str
    source_app: str
    source_id: str
    source_ref: str
    source_revision: str
    owner_scope_type: str
    owner_scope_id: str
    classification: str = "private"

    def __post_init__(self) -> None:
        for field_name in (
            "tenant_id",
            "owner_capability_code",
            "source_app",
            "source_id",
            "source_ref",
            "source_revision",
            "owner_scope_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _required(getattr(self, field_name), field_name),
            )
        if self.source_kind not in _SOURCE_KINDS:
            raise ValueError("knowledge_write_source_kind_forbidden")
        if self.owner_scope_type not in _SCOPE_TYPES:
            raise ValueError("knowledge_write_owner_scope_type_forbidden")
        if self.classification not in _CLASSIFICATIONS:
            raise ValueError("knowledge_write_classification_forbidden")


@dataclass(frozen=True)
class KnowledgeGrant:
    principal: PrincipalRef
    relation: str
    effect: str = "allow"
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None

    def __post_init__(self) -> None:
        if self.relation not in _RELATIONS:
            raise ValueError("knowledge_write_grant_relation_forbidden")
        if self.effect not in _EFFECTS:
            raise ValueError("knowledge_write_grant_effect_forbidden")
        if (
            self.valid_from is not None
            and self.valid_until is not None
            and self.valid_until <= self.valid_from
        ):
            raise ValueError("knowledge_write_grant_validity_invalid")


@dataclass(frozen=True)
class KnowledgeAclMutation:
    expected_authz_revision: int
    grants: tuple[KnowledgeGrant, ...]

    def __post_init__(self) -> None:
        if self.expected_authz_revision < 1:
            raise ValueError("knowledge_write_expected_revision_invalid")
        normalized = tuple(
            sorted(
                set(self.grants),
                key=lambda grant: (
                    grant.principal.type,
                    grant.principal.id,
                    grant.relation,
                    grant.effect,
                    grant.valid_from.isoformat() if grant.valid_from else "",
                    grant.valid_until.isoformat() if grant.valid_until else "",
                ),
            )
        )
        if not normalized:
            raise ValueError("knowledge_write_acl_grants_required")
        object.__setattr__(self, "grants", normalized)


@dataclass(frozen=True)
class KnowledgeResourceBinding:
    knowledge_resource_id: str
    security_label_id: str
    authz_revision: int
    visibility_partition_hash: str
    created: bool

    def __post_init__(self) -> None:
        if len(self.visibility_partition_hash) != 64:
            raise ValueError("knowledge_visibility_partition_hash_invalid")


__all__ = [
    "KnowledgeAclMutation",
    "KnowledgeGrant",
    "KnowledgeResourceBinding",
    "KnowledgeResourceIdentity",
]
