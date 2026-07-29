"""Build a verified knowledge authorization context without trusting payload roles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from .contracts import (
    AgentExecutionMask,
    KnowledgePermission,
    PrincipalRef,
    RetrievalAccessContext,
    ScopeMembership,
)
from .workspace_authorization_revision import workspace_authorization_revision


class RetrievalScopeDenied(ValueError):
    """Raised when a requested knowledge scope is not server-verified."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class VerifiedAgentExecution:
    """Agent execution identity admitted by server-side topology policy."""

    role: str
    policy_revision: str
    topology_snapshot_id: str

    def to_mask(self) -> AgentExecutionMask:
        return AgentExecutionMask(
            role=self.role,
            policy_revision=self.policy_revision,
            topology_snapshot_id=self.topology_snapshot_id,
        )


def _mapping_items(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _revision(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "").strip()


def _default_workspace_lookup(workspace_id: str) -> Any:
    from backend.app.services.stores.postgres.workspaces_store import (
        PostgresWorkspacesStore,
    )

    return PostgresWorkspacesStore().get_workspace_sync(workspace_id)


def _default_group_lookup(group_id: str) -> Any:
    from backend.app.services.workspace_groups.topology_repository import (
        WorkspaceGroupTopologyRepository,
    )

    return WorkspaceGroupTopologyRepository().get(group_id)


class RetrievalAccessContextFactory:
    """The only adapter from verified auth/execution state to retrieval ACL input."""

    def __init__(
        self,
        *,
        workspace_lookup: Optional[Callable[[str], Any]] = None,
        group_lookup: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self._workspace_lookup = workspace_lookup or _default_workspace_lookup
        self._group_lookup = group_lookup or _default_group_lookup

    def build(
        self,
        auth: Any,
        *,
        requested_workspace_ids: Iterable[str] = (),
        requested_group_ids: Iterable[str] = (),
        verified_agent_execution: Optional[VerifiedAgentExecution] = None,
        trusted_service_principal: Optional[str] = None,
    ) -> RetrievalAccessContext:
        subject_user_id = str(getattr(auth, "user_id", "") or "").strip()
        tenant_id = str(getattr(auth, "tenant_id", "") or "").strip()
        if not subject_user_id or not tenant_id:
            raise RetrievalScopeDenied("knowledge_verified_identity_required")

        workspace_ids = tuple(
            sorted({str(item).strip() for item in requested_workspace_ids if str(item).strip()})
        )
        group_ids = tuple(
            sorted({str(item).strip() for item in requested_group_ids if str(item).strip()})
        )
        principals = {PrincipalRef("user", subject_user_id)}
        if trusted_service_principal:
            principals.add(PrincipalRef("service", trusted_service_principal))
        memberships: set[ScopeMembership] = set()
        permissions: set[KnowledgePermission] = set()

        if bool(getattr(auth, "is_cloud_mode", False)):
            self._build_cloud_scope(
                auth,
                workspace_ids=workspace_ids,
                group_ids=group_ids,
                memberships=memberships,
                permissions=permissions,
            )
        else:
            self._build_local_scope(
                subject_user_id=subject_user_id,
                workspace_ids=workspace_ids,
                group_ids=group_ids,
                memberships=memberships,
                permissions=permissions,
            )

        return RetrievalAccessContext.create(
            subject_user_id=subject_user_id,
            tenant_id=tenant_id,
            principals=principals,
            memberships=memberships,
            permissions=permissions,
            agent_mask=(
                verified_agent_execution.to_mask()
                if verified_agent_execution is not None
                else None
            ),
        )

    def build_from_governance(
        self,
        governance_context: Any,
        *,
        requested_workspace_id: str,
        requested_group_id: Optional[str] = None,
    ) -> RetrievalAccessContext:
        """Project a non-user-writable tool execution context into ACL input."""

        actor_user_id = str(
            getattr(governance_context, "actor_user_id", "") or ""
        ).strip()
        workspace_id = str(requested_workspace_id or "").strip()
        allowed_workspaces = {
            str(value).strip()
            for value in getattr(
                governance_context,
                "allowed_workspace_ids",
                (),
            )
            if str(value).strip()
        }
        if (
            not actor_user_id
            or not workspace_id
            or workspace_id not in allowed_workspaces
        ):
            raise RetrievalScopeDenied("knowledge_workspace_scope_forbidden")
        revision = str(
            getattr(governance_context, "snapshot_hash", "") or ""
        ).strip()
        if not revision:
            raise RetrievalScopeDenied("knowledge_governance_revision_missing")

        workspace_role = (
            "owner"
            if actor_user_id
            == str(
                getattr(
                    governance_context,
                    "workspace_owner_user_id",
                    "",
                )
                or ""
            )
            else "member"
        )
        memberships = {
            ScopeMembership(
                "workspace",
                workspace_id,
                workspace_role,
                revision,
            )
        }
        permissions = {
            KnowledgePermission("knowledge.read", "workspace", workspace_id)
        }
        if workspace_role == "owner":
            permissions.update(self._owner_permissions("workspace", workspace_id))

        group_id = str(requested_group_id or "").strip()
        agent_role = str(
            getattr(governance_context, "agent_role", "") or ""
        ).strip()
        agent_policy_revision = str(
            getattr(
                governance_context,
                "agent_policy_revision",
                "",
            )
            or ""
        ).strip()
        topology_snapshot_id = str(
            getattr(
                governance_context,
                "topology_snapshot_id",
                "",
            )
            or ""
        ).strip()
        if group_id:
            allowed_groups = {
                str(value).strip()
                for value in getattr(
                    governance_context,
                    "allowed_group_ids",
                    (),
                )
                if str(value).strip()
            }
            if group_id not in allowed_groups:
                raise RetrievalScopeDenied("knowledge_group_scope_forbidden")
            group_role = (
                "owner"
                if actor_user_id
                == str(
                    getattr(
                        governance_context,
                        "group_owner_user_id",
                        "",
                    )
                    or ""
                )
                else "member"
            )
            memberships.add(
                ScopeMembership(
                    "group",
                    group_id,
                    group_role,
                    revision,
                )
            )
            permissions.add(
                KnowledgePermission("knowledge.read", "group", group_id)
            )
            if group_role == "owner":
                permissions.update(self._owner_permissions("group", group_id))
            if not (
                agent_role
                and agent_policy_revision
                and topology_snapshot_id
            ):
                raise RetrievalScopeDenied(
                    "knowledge_agent_execution_mask_missing"
                )
        elif any(
            (
                agent_role,
                agent_policy_revision,
                topology_snapshot_id,
            )
        ):
            raise RetrievalScopeDenied(
                "knowledge_agent_execution_mask_without_group"
            )

        return RetrievalAccessContext.create(
            subject_user_id=actor_user_id,
            tenant_id="local",
            principals=(PrincipalRef("user", actor_user_id),),
            memberships=memberships,
            permissions=permissions,
            agent_mask=(
                AgentExecutionMask(
                    role=agent_role,
                    policy_revision=agent_policy_revision,
                    topology_snapshot_id=topology_snapshot_id,
                )
                if group_id
                else None
            ),
        )

    def _build_local_scope(
        self,
        *,
        subject_user_id: str,
        workspace_ids: tuple[str, ...],
        group_ids: tuple[str, ...],
        memberships: set[ScopeMembership],
        permissions: set[KnowledgePermission],
    ) -> None:
        for workspace_id in workspace_ids:
            workspace = self._workspace_lookup(workspace_id)
            if workspace is None or str(
                getattr(workspace, "owner_user_id", "") or ""
            ) != subject_user_id:
                raise RetrievalScopeDenied("knowledge_workspace_scope_forbidden")
            try:
                revision = workspace_authorization_revision(
                    workspace_id=getattr(workspace, "id", None),
                    owner_user_id=getattr(workspace, "owner_user_id", None),
                    visibility=getattr(workspace, "visibility", None),
                )
            except ValueError as exc:
                raise RetrievalScopeDenied(str(exc)) from exc
            membership = ScopeMembership(
                "workspace",
                workspace_id,
                "owner",
                revision,
            )
            memberships.add(membership)
            permissions.update(self._owner_permissions("workspace", workspace_id))

        for group_id in group_ids:
            group = self._group_lookup(group_id)
            if group is None or str(getattr(group, "owner_user_id", "") or "") != subject_user_id:
                raise RetrievalScopeDenied("knowledge_group_scope_forbidden")
            revision = _revision(getattr(group, "revision", None))
            if not revision:
                raise RetrievalScopeDenied("knowledge_group_owner_revision_missing")
            memberships.add(ScopeMembership("group", group_id, "owner", revision))
            permissions.update(self._owner_permissions("group", group_id))

    def _build_cloud_scope(
        self,
        auth: Any,
        *,
        workspace_ids: tuple[str, ...],
        group_ids: tuple[str, ...],
        memberships: set[ScopeMembership],
        permissions: set[KnowledgePermission],
    ) -> None:
        verified_workspace_ids = {
            str(item).strip()
            for item in getattr(auth, "workspace_ids", ())
            if str(item).strip()
        }
        verified_group_ids = {
            str(item).strip()
            for item in getattr(auth, "group_ids", ())
            if str(item).strip()
        }
        if any(item not in verified_workspace_ids for item in workspace_ids):
            raise RetrievalScopeDenied("knowledge_workspace_scope_forbidden")
        if any(item not in verified_group_ids for item in group_ids):
            raise RetrievalScopeDenied("knowledge_group_scope_forbidden")

        requested = {
            ("workspace", item) for item in workspace_ids
        } | {("group", item) for item in group_ids}
        for raw in (
            *_mapping_items(getattr(auth, "workspace_memberships", ())),
            *_mapping_items(getattr(auth, "group_memberships", ())),
        ):
            scope_type = str(raw.get("scope_type") or "").strip()
            scope_id = str(raw.get("scope_id") or raw.get("id") or "").strip()
            if (scope_type, scope_id) not in requested:
                continue
            role = str(raw.get("role") or "").strip()
            revision = _revision(raw.get("revision"))
            if not role or not revision:
                continue
            memberships.add(ScopeMembership(scope_type, scope_id, role, revision))

        for raw in _mapping_items(getattr(auth, "knowledge_permissions", ())):
            scope_type = str(raw.get("scope_type") or "").strip()
            scope_id = str(raw.get("scope_id") or "").strip()
            if (scope_type, scope_id) not in requested:
                continue
            name = str(raw.get("name") or "").strip()
            if not name:
                continue
            permissions.add(KnowledgePermission(name, scope_type, scope_id))

    @staticmethod
    def _owner_permissions(
        scope_type: str,
        scope_id: str,
    ) -> tuple[KnowledgePermission, ...]:
        return (
            KnowledgePermission("knowledge.read", scope_type, scope_id),
            KnowledgePermission("knowledge.read_all_scope", scope_type, scope_id),
            KnowledgePermission("knowledge.manage_acl", scope_type, scope_id),
            KnowledgePermission("knowledge.project", scope_type, scope_id),
        )
