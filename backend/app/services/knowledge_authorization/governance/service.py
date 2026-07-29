"""Canonical authorization and projection governance facade."""

from __future__ import annotations

import base64
from dataclasses import asdict
from datetime import datetime
from typing import Any, Callable

from psycopg2.extras import RealDictCursor

from backend.app.services.knowledge_projection.retrievable.repository import (
    RetrievableKnowledgeProjectionRepository,
)
from backend.app.services.knowledge_projection.facade import (
    KnowledgeProjectionFacade,
)
from backend.app.services.knowledge_retrieval.store import (
    AuthorizationAwareKnowledgeRetrievalStore,
)
from backend.app.services.vector_search import VectorSearchService

from ..contracts import RetrievalAccessContext
from ..store import KnowledgeAuthorizationStore
from .agent_mask_store import KnowledgeAgentMaskStore
from .contracts import (
    KnowledgeAccessReplacementCommand,
    KnowledgeProjectionActionCommand,
)
from .projection_actions import KnowledgeProjectionActionSourceRepository
from .repository import KnowledgeAccessRepository


_MODALITIES = ("text", "image", "video", "audio")


class KnowledgeAccessForbiddenError(PermissionError):
    pass


class KnowledgeAccessNotFoundError(LookupError):
    pass


class KnowledgeAccessService:
    """Expose one bounded governance path over existing ACL/projection owners."""

    def __init__(
        self,
        *,
        repository: KnowledgeAccessRepository | None = None,
        authorization_store: KnowledgeAuthorizationStore | None = None,
        projection_repository: (
            RetrievableKnowledgeProjectionRepository | None
        ) = None,
        agent_mask_store: KnowledgeAgentMaskStore | None = None,
        projection_action_source_repository: (
            KnowledgeProjectionActionSourceRepository | None
        ) = None,
        projection_facade: KnowledgeProjectionFacade | None = None,
        connection_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._connection_factory = (
            connection_factory or VectorSearchService()._get_connection
        )
        self._repository = repository or KnowledgeAccessRepository(
            self._connection_factory
        )
        self._authorization_store = (
            authorization_store or KnowledgeAuthorizationStore()
        )
        self._projection_repository = (
            projection_repository
            or RetrievableKnowledgeProjectionRepository()
        )
        self._agent_mask_store = (
            agent_mask_store or KnowledgeAgentMaskStore()
        )
        self._projection_action_source_repository = (
            projection_action_source_repository
            or KnowledgeProjectionActionSourceRepository()
        )
        self._projection_facade = (
            projection_facade or KnowledgeProjectionFacade()
        )

    def list_summary(
        self,
        *,
        context: RetrievalAccessContext,
        workspace_id: str,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        self._require_manage(context, workspace_id)
        bounded_limit = max(1, min(int(limit), 100))
        before_updated_at, before_resource_id = self._decode_cursor(cursor)
        result = self._repository.list_summary(
            context=context,
            workspace_id=workspace_id,
            limit=bounded_limit,
            before_updated_at=before_updated_at,
            before_resource_id=before_resource_id,
        )
        items = [
            self._normalize_summary_item(item)
            for item in result["items"]
        ]
        next_cursor = None
        if result["has_more"] and items:
            last = items[-1]
            next_cursor = self._encode_cursor(
                str(last["updated_at"]),
                str(last["knowledge_resource_id"]),
            )
        return {
            "contract_version": "knowledge_access.v1",
            "workspace_id": workspace_id,
            "items": items,
            "total_count": result["total_count"],
            "state_counts": result["state_counts"],
            "next_cursor": next_cursor,
            "request_budget": {
                "initial_summary_requests": 1,
                "polling": False,
            },
        }

    def get_detail(
        self,
        *,
        context: RetrievalAccessContext,
        workspace_id: str,
        resource_id: str,
    ) -> dict[str, Any]:
        self._require_manage(context, workspace_id)
        detail = self._repository.get_detail(
            context=context,
            workspace_id=workspace_id,
            resource_id=resource_id,
        )
        if detail is None:
            raise KnowledgeAccessNotFoundError(
                "knowledge_resource_not_found"
            )
        return self._normalize_detail(detail)

    def replace_grants(
        self,
        *,
        context: RetrievalAccessContext,
        workspace_id: str,
        resource_id: str,
        command: KnowledgeAccessReplacementCommand,
    ) -> dict[str, Any]:
        self._require_manage(context, workspace_id)
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            AuthorizationAwareKnowledgeRetrievalStore._set_local_context(
                cursor,
                context,
            )
            binding = (
                self._authorization_store.replace_existing_resource_grants(
                    cursor,
                    knowledge_resource_id=resource_id,
                    tenant_id=context.tenant_id,
                    scope_type="workspace",
                    scope_id=workspace_id,
                    access_context=context,
                    mutation=command.to_domain(),
                )
            )
            graph_invalidated = (
                self._projection_repository.rebind_active_authorization(
                    cursor,
                    resource_id=resource_id,
                    authz_revision=binding.authz_revision,
                    visibility_partition_hash=(
                        binding.visibility_partition_hash
                    ),
                )
            )
            agent_policy_revision = self._agent_mask_store.replace(
                cursor,
                resource_id=resource_id,
                authz_revision=binding.authz_revision,
                masks=(
                    (mask.agent_role, mask.effect)
                    for mask in command.agent_masks
                ),
                context=context,
            )
            detail_cursor = connection.cursor(
                cursor_factory=RealDictCursor
            )
            detail = self._repository.detail_with_cursor(
                detail_cursor,
                context=context,
                workspace_id=workspace_id,
                resource_id=resource_id,
            )
            if detail is None:
                raise RuntimeError(
                    "knowledge_access_mutation_detail_missing"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        normalized = self._normalize_detail(detail)
        normalized["mutation"] = {
            "state": "replaced",
            "graph_reindex_required": graph_invalidated,
            "agent_policy_revision": agent_policy_revision,
            "follow_up_get_required": False,
        }
        return normalized

    def run_projection_action(
        self,
        *,
        context: RetrievalAccessContext,
        workspace_id: str,
        resource_id: str,
        command: KnowledgeProjectionActionCommand,
    ) -> dict[str, Any]:
        """Admit one exact source action through the existing task lane."""

        self._require_manage(context, workspace_id)
        detail = self._repository.get_detail(
            context=context,
            workspace_id=workspace_id,
            resource_id=resource_id,
        )
        if detail is None:
            raise KnowledgeAccessNotFoundError(
                "knowledge_resource_not_found"
            )
        resource = dict(detail["resource"])
        if (
            int(resource["authz_revision"])
            != command.expected_authz_revision
            or str(resource["source_revision"])
            != command.expected_source_revision
        ):
            from ..store import KnowledgeAuthorizationConflictError

            raise KnowledgeAuthorizationConflictError(
                "knowledge_projection_action_revision_conflict"
            )
        active = bool(resource.get("active"))
        if command.action == "restore" and active:
            raise ValueError(
                "knowledge_projection_restore_requires_revoked_resource"
            )
        if command.action == "revoke" and not active:
            raise ValueError(
                "knowledge_projection_revoke_requires_active_resource"
            )
        trigger_mode = (
            "revoke"
            if command.action == "revoke"
            else "explicit_reindex"
        )
        admission_command = (
            self._projection_action_source_repository.resolve(
                workspace_id=workspace_id,
                source_instance_id=str(resource["source_id"]),
                source_revision=command.expected_source_revision,
                owner_capability_code=str(
                    resource["owner_capability_code"]
                ),
                source_kind=str(resource["source_kind"]),
                source_ref=str(resource["source_ref"]),
                trigger_mode=trigger_mode,
            )
        )
        if admission_command is None:
            raise ValueError(
                "knowledge_projection_action_source_intake_not_found"
            )
        receipt = self._projection_facade.admit_retrievable_source(
            admission_command,
            access_context=context,
        )
        return {
            "contract_version": "knowledge_access.v1",
            "knowledge_resource_id": resource_id,
            "action": command.action,
            "expected_authz_revision": command.expected_authz_revision,
            "expected_source_revision": command.expected_source_revision,
            "admission": asdict(receipt),
            "request_budget": {
                "mutation_requests": 1,
                "follow_up_get_required": False,
                "polling": False,
            },
        }

    @staticmethod
    def _require_manage(
        context: RetrievalAccessContext,
        workspace_id: str,
    ) -> None:
        if not context.has_permission(
            "knowledge.manage_acl",
            scope_type="workspace",
            scope_id=workspace_id,
        ):
            raise KnowledgeAccessForbiddenError(
                "knowledge_manage_acl_permission_required"
            )

    @staticmethod
    def _normalize_summary_item(item: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(item)
        normalized["channels"] = list(item.get("channels") or [])
        normalized["allowed_principal_types"] = list(
            item.get("allowed_principal_types") or []
        )
        normalized["deny_present"] = int(
            item.get("deny_count") or 0
        ) > 0
        normalized["agent_deny_present"] = int(
            item.get("agent_deny_count") or 0
        ) > 0
        normalized["effective_visibility"] = {
            "classification": item.get("classification"),
            "allowed_principal_types": normalized[
                "allowed_principal_types"
            ],
            "deny_present": normalized["deny_present"],
        }
        return normalized

    @classmethod
    def _normalize_detail(
        cls,
        detail: dict[str, Any],
    ) -> dict[str, Any]:
        channels = list(detail.get("channels") or [])
        grouped: dict[str, list[dict[str, Any]]] = {
            modality: [] for modality in _MODALITIES
        }
        for channel in channels:
            modality = str(channel.get("modality") or "")
            if modality in grouped:
                grouped[modality].append(dict(channel))
        modality_truth = [
            {
                "modality": modality,
                "state": (
                    "active"
                    if any(
                        channel.get("state") == "active"
                        for channel in grouped[modality]
                    )
                    else (
                        str(grouped[modality][0].get("state"))
                        if grouped[modality]
                        else "not_admitted"
                    )
                ),
                "channels": grouped[modality],
                "pointer_only_is_active": False,
            }
            for modality in _MODALITIES
        ]
        grants = list(detail.get("grants") or [])
        total_grants = int(detail.get("total_grant_count") or 0)
        agent_masks = list(detail.get("agent_masks") or [])
        total_agent_masks = int(
            detail.get("total_agent_mask_count") or 0
        )
        return {
            "contract_version": "knowledge_access.v1",
            "resource": dict(detail["resource"]),
            "projection": (
                dict(detail["projection"])
                if detail.get("projection")
                else None
            ),
            "grants": grants[:200],
            "grant_count": total_grants,
            "grants_truncated": total_grants > 200,
            "modality_truth": modality_truth,
            "graph": dict(detail.get("graph") or {}),
            "audit": list(detail.get("audits") or []),
            "agent_mask": {
                "mode": "runtime_intersection_only",
                "can_grant_human_access": False,
                "persisted_masks": agent_masks[:100],
                "mask_count": total_agent_masks,
                "masks_truncated": total_agent_masks > 100,
                "audit": list(detail.get("agent_audits") or []),
            },
            "request_budget": {
                "selected_detail_requests": 1,
                "polling": False,
            },
        }

    @staticmethod
    def _encode_cursor(updated_at: str, resource_id: str) -> str:
        raw = f"{updated_at}\x1f{resource_id}".encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_cursor(
        cursor: str | None,
    ) -> tuple[datetime | None, str | None]:
        if not cursor:
            return None, None
        if len(cursor) > 1024:
            raise ValueError("knowledge_access_cursor_invalid")
        try:
            padding = "=" * (-len(cursor) % 4)
            decoded = base64.urlsafe_b64decode(
                (cursor + padding).encode("ascii")
            ).decode("utf-8")
            updated_at, resource_id = decoded.split("\x1f", 1)
            parsed = datetime.fromisoformat(updated_at)
        except (ValueError, UnicodeError) as exc:
            raise ValueError("knowledge_access_cursor_invalid") from exc
        if not resource_id:
            raise ValueError("knowledge_access_cursor_invalid")
        return parsed, resource_id

__all__ = [
    "KnowledgeAccessForbiddenError",
    "KnowledgeAccessNotFoundError",
    "KnowledgeAccessService",
]
