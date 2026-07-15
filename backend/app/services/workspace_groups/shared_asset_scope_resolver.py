"""Authorize typed workspace-group shared asset scopes."""

import hashlib
import json
from typing import Optional, Sequence

from pydantic import ValidationError

from backend.app.services.workspace_groups.contracts import (
    AuthorizedSharedAssetScope,
    SharedAssetScopeError,
    SharedAssetScopeResolution,
    SharedAssetSelector,
)
from backend.app.services.workspace_groups.shared_asset_scope_repository import (
    SharedAssetScopeEvidence,
    SharedAssetScopeRepository,
)


class SharedAssetScopeResolver:
    """Apply authorization and typed selector rules to repository evidence."""

    def __init__(self, repository: Optional[SharedAssetScopeRepository] = None):
        self.repository = repository or SharedAssetScopeRepository()

    def resolve(
        self,
        *,
        workspace_id: str,
        actor_user_id: str,
        allowed_workspace_ids: Sequence[str] = (),
        allowed_group_ids: Sequence[str] = (),
        group_id: Optional[str] = None,
    ) -> SharedAssetScopeResolution:
        evidence_rows = self.repository.list_evidence(
            workspace_id=workspace_id,
            group_id=group_id,
        )
        if not evidence_rows:
            raise SharedAssetScopeWorkspaceNotFoundError(workspace_id)
        first_evidence = evidence_rows[0]
        if (
            first_evidence.active_workspace_owner_user_id != actor_user_id
            and workspace_id not in allowed_workspace_ids
        ):
            raise SharedAssetScopeAccessError(workspace_id)
        scopes: list[AuthorizedSharedAssetScope] = []
        errors: list[SharedAssetScopeError] = []
        for evidence in evidence_rows:
            if evidence.binding_id is None or evidence.resource_id is None:
                continue
            scope, error_code = self._authorize(
                evidence,
                actor_user_id=actor_user_id,
                allowed_group_ids=allowed_group_ids,
            )
            if scope is not None:
                scopes.append(scope)
            elif error_code is not None and len(errors) < 20:
                errors.append(
                    SharedAssetScopeError(
                        binding_id=evidence.binding_id,
                        group_id=self._configured_group_id(evidence),
                        code=error_code,
                    )
                )
        scopes.sort(
            key=lambda scope: (
                scope.group_id,
                scope.source_workspace_id,
                scope.resource_id,
                scope.binding_id,
            )
        )
        errors.sort(key=lambda error: (error.group_id or "", error.binding_id))
        return SharedAssetScopeResolution(
            scopes=scopes,
            errors=errors,
            scope_fingerprint=self._scope_fingerprint(scopes),
        )

    def _authorize(
        self,
        evidence: SharedAssetScopeEvidence,
        *,
        actor_user_id: str,
        allowed_group_ids: Sequence[str],
    ) -> tuple[Optional[AuthorizedSharedAssetScope], Optional[str]]:
        if evidence.consumer_access_mode != "read":
            return None, "shared_asset_read_required"
        if evidence.group_id is None:
            return None, "shared_scope_group_missing"
        if (
            evidence.group_owner_user_id != actor_user_id
            and evidence.group_id not in allowed_group_ids
        ):
            return None, "shared_scope_group_access_denied"
        if not evidence.consumer_is_member:
            return None, "shared_scope_consumer_membership_missing"
        if evidence.source_binding_id is None or evidence.source_workspace_id is None:
            return None, "shared_scope_source_binding_missing"
        if evidence.source_access_mode != "read":
            return None, "shared_scope_source_anchor_invalid"
        if not evidence.source_is_member:
            return None, "shared_scope_source_membership_missing"
        if not evidence.topology_is_ready:
            return None, "shared_scope_topology_invalid"
        try:
            selector = SharedAssetSelector.model_validate(
                evidence.consumer_overrides.get("dynamic_selector")
            )
            source_selector = SharedAssetSelector.model_validate(
                evidence.source_overrides.get("dynamic_selector")
            )
        except ValidationError:
            return None, "shared_scope_selector_invalid"
        if selector != source_selector:
            return None, "shared_scope_selector_mismatch"
        if not self._source_anchor_matches(evidence):
            return None, "shared_scope_source_anchor_invalid"
        scope_key = self._scope_key(evidence)
        return (
            AuthorizedSharedAssetScope(
                scope_key=scope_key,
                active_workspace_id=evidence.active_workspace_id,
                source_workspace_id=evidence.source_workspace_id,
                source_workspace_title=evidence.source_workspace_title,
                group_id=evidence.group_id,
                group_title=evidence.group_title or evidence.group_id,
                group_revision=evidence.group_revision or 0,
                binding_id=evidence.binding_id,
                resource_id=evidence.resource_id,
                selector=selector,
            ),
            None,
        )

    @staticmethod
    def _configured_group_id(evidence: SharedAssetScopeEvidence) -> Optional[str]:
        value = evidence.consumer_overrides.get("group_id")
        return value.strip() if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _source_anchor_matches(evidence: SharedAssetScopeEvidence) -> bool:
        source_workspace_id = evidence.source_overrides.get("source_workspace_id")
        source_group_id = evidence.source_overrides.get("group_id")
        return (
            evidence.source_overrides.get("share_scope") == "workspace_group"
            and source_workspace_id == evidence.source_workspace_id
            and source_group_id == evidence.group_id
        )

    @staticmethod
    def _scope_key(evidence: SharedAssetScopeEvidence) -> str:
        if evidence.binding_id is None or evidence.resource_id is None:
            raise ValueError("shared asset scope evidence is incomplete")
        stable_value = "\0".join(
            [
                evidence.binding_id,
                evidence.group_id or "",
                evidence.source_workspace_id or "",
                evidence.resource_id,
            ]
        )
        digest = hashlib.sha256(stable_value.encode("utf-8")).hexdigest()[:20]
        return f"wgs_{digest}"

    @staticmethod
    def _scope_fingerprint(scopes: Sequence[AuthorizedSharedAssetScope]) -> str:
        stable_rows = [
            {
                "binding_id": scope.binding_id,
                "group_id": scope.group_id,
                "group_revision": scope.group_revision,
                "resource_id": scope.resource_id,
                "source_workspace_id": scope.source_workspace_id,
            }
            for scope in scopes
        ]
        payload = json.dumps(
            stable_rows,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SharedAssetScopeAccessError(PermissionError):
    """Raised before scope details are exposed to an unauthorized workspace caller."""


class SharedAssetScopeWorkspaceNotFoundError(LookupError):
    """Raised when the requested workspace does not exist."""
