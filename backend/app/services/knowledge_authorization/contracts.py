"""Immutable request-scoped contracts for knowledge authorization."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional


_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/+~-]{0,255}$")
_PRINCIPAL_TYPES = frozenset({"user", "workspace_role", "group_role", "service"})
_SCOPE_TYPES = frozenset({"tenant", "workspace", "group"})
_PERMISSIONS = frozenset(
    {
        "knowledge.read",
        "knowledge.read_all_scope",
        "knowledge.manage_acl",
        "knowledge.project",
    }
)


def _required_token(value: Any, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized or not _TOKEN_RE.fullmatch(normalized):
        raise ValueError(f"knowledge_authorization_invalid_{field_name}")
    return normalized


@dataclass(frozen=True, order=True)
class PrincipalRef:
    """One normalized principal that may appear in an ACL grant."""

    type: str
    id: str

    def __post_init__(self) -> None:
        principal_type = _required_token(self.type, "principal_type")
        if principal_type not in _PRINCIPAL_TYPES:
            raise ValueError("knowledge_authorization_principal_type_forbidden")
        object.__setattr__(self, "type", principal_type)
        object.__setattr__(self, "id", _required_token(self.id, "principal_id"))

    @property
    def key(self) -> str:
        return f"{self.type}:{self.id}"

    def as_dict(self) -> dict[str, str]:
        return {"type": self.type, "id": self.id}


@dataclass(frozen=True, order=True)
class ScopeMembership:
    """Server-verified role at one tenant/workspace/group scope revision."""

    scope_type: str
    scope_id: str
    role: str
    revision: str

    def __post_init__(self) -> None:
        scope_type = _required_token(self.scope_type, "scope_type")
        if scope_type not in _SCOPE_TYPES:
            raise ValueError("knowledge_authorization_scope_type_forbidden")
        object.__setattr__(self, "scope_type", scope_type)
        object.__setattr__(self, "scope_id", _required_token(self.scope_id, "scope_id"))
        object.__setattr__(self, "role", _required_token(self.role, "role"))
        object.__setattr__(
            self,
            "revision",
            _required_token(self.revision, "membership_revision"),
        )

    @property
    def principal(self) -> PrincipalRef:
        if self.scope_type == "workspace":
            return PrincipalRef(
                "workspace_role",
                f"{self.scope_id}:{self.role}",
            )
        if self.scope_type == "group":
            return PrincipalRef(
                "group_role",
                f"{self.scope_id}:{self.role}",
            )
        raise ValueError("knowledge_authorization_tenant_role_principal_unsupported")

    def as_dict(self) -> dict[str, str]:
        return {
            "scope_type": self.scope_type,
            "scope_id": self.scope_id,
            "role": self.role,
            "revision": self.revision,
        }


@dataclass(frozen=True, order=True)
class KnowledgePermission:
    """One fixed permission at a server-verified scope."""

    name: str
    scope_type: str
    scope_id: str

    def __post_init__(self) -> None:
        name = _required_token(self.name, "permission")
        if name not in _PERMISSIONS:
            raise ValueError("knowledge_authorization_permission_forbidden")
        scope_type = _required_token(self.scope_type, "scope_type")
        if scope_type not in _SCOPE_TYPES:
            raise ValueError("knowledge_authorization_scope_type_forbidden")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "scope_type", scope_type)
        object.__setattr__(self, "scope_id", _required_token(self.scope_id, "scope_id"))

    def as_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "scope_type": self.scope_type,
            "scope_id": self.scope_id,
        }


@dataclass(frozen=True)
class AgentExecutionMask:
    """Server-bound agent lens; it may narrow human authorization only."""

    role: str
    policy_revision: str
    topology_snapshot_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", _required_token(self.role, "agent_role"))
        object.__setattr__(
            self,
            "policy_revision",
            _required_token(self.policy_revision, "agent_policy_revision"),
        )
        object.__setattr__(
            self,
            "topology_snapshot_id",
            _required_token(self.topology_snapshot_id, "topology_snapshot_id"),
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "role": self.role,
            "policy_revision": self.policy_revision,
            "topology_snapshot_id": self.topology_snapshot_id,
        }


@dataclass(frozen=True)
class RetrievalAccessContext:
    """Canonical immutable authorization input for one knowledge request."""

    subject_user_id: str
    tenant_id: str
    principals: tuple[PrincipalRef, ...]
    memberships: tuple[ScopeMembership, ...]
    permissions: tuple[KnowledgePermission, ...]
    principal_set_hash: str
    agent_mask: Optional[AgentExecutionMask] = None

    @classmethod
    def create(
        cls,
        *,
        subject_user_id: str,
        tenant_id: str,
        principals: Iterable[PrincipalRef],
        memberships: Iterable[ScopeMembership] = (),
        permissions: Iterable[KnowledgePermission] = (),
        agent_mask: Optional[AgentExecutionMask] = None,
    ) -> "RetrievalAccessContext":
        normalized_subject = _required_token(subject_user_id, "subject_user_id")
        normalized_tenant = _required_token(tenant_id, "tenant_id")
        normalized_memberships = tuple(sorted(set(memberships)))
        normalized_permissions = tuple(sorted(set(permissions)))
        normalized_principals = tuple(
            sorted(
                set(principals)
                | {
                    membership.principal
                    for membership in normalized_memberships
                    if membership.scope_type in {"workspace", "group"}
                }
            )
        )
        if PrincipalRef("user", normalized_subject) not in normalized_principals:
            raise ValueError("knowledge_authorization_subject_principal_required")
        hash_payload: Mapping[str, Any] = {
            "subject_user_id": normalized_subject,
            "tenant_id": normalized_tenant,
            "principals": [item.as_dict() for item in normalized_principals],
            "memberships": [item.as_dict() for item in normalized_memberships],
            "permissions": [item.as_dict() for item in normalized_permissions],
            "agent_mask": agent_mask.as_dict() if agent_mask else None,
        }
        encoded = json.dumps(
            hash_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return cls(
            subject_user_id=normalized_subject,
            tenant_id=normalized_tenant,
            principals=normalized_principals,
            memberships=normalized_memberships,
            permissions=normalized_permissions,
            principal_set_hash=hashlib.sha256(encoded).hexdigest(),
            agent_mask=agent_mask,
        )

    @property
    def principal_keys(self) -> tuple[str, ...]:
        return tuple(item.key for item in self.principals)

    def has_permission(
        self,
        name: str,
        *,
        scope_type: str,
        scope_id: str,
    ) -> bool:
        target = KnowledgePermission(name, scope_type, scope_id)
        return target in self.permissions

    def as_dict(self) -> dict[str, Any]:
        return {
            "subject_user_id": self.subject_user_id,
            "tenant_id": self.tenant_id,
            "principals": [item.as_dict() for item in self.principals],
            "memberships": [item.as_dict() for item in self.memberships],
            "permissions": [item.as_dict() for item in self.permissions],
            "principal_set_hash": self.principal_set_hash,
            "agent_mask": self.agent_mask.as_dict() if self.agent_mask else None,
        }
