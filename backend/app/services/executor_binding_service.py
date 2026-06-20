"""
Workspace executor binding state management.

Bindings are persisted in workspace metadata so caller-facing config,
auth-bundle resolution, and later fault handling can converge on the
same workspace-scoped contract without adding a schema migration first.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Optional

from backend.app.services.executor_binding_leases import ExecutorBindingLeaseMixin
from backend.app.services.executor_binding_metadata import (
    _BINDINGS_KEY,
    _SUPPORTED_SURFACES,
    _utc_now_iso,
    ExecutorBindingMetadataMixin,
)
from backend.app.services.executor_binding_pool_preference import (
    ExecutorBindingPoolPreferenceMixin,
)
from backend.app.services.executor_route_resolver import ExecutorRouteSelection


class ExecutorBindingService(
    ExecutorBindingPoolPreferenceMixin,
    ExecutorBindingLeaseMixin,
    ExecutorBindingMetadataMixin,
):
    """Maintain workspace-scoped executor binding metadata."""

    def __init__(
        self,
        workspace_loader: Optional[Callable[[str], Any]] = None,
        workspace_saver: Optional[Callable[[Any], Any]] = None,
    ):
        self._workspace_loader = workspace_loader or self._load_workspace_sync
        self._workspace_saver = workspace_saver or self._save_workspace_sync

    def sync_workspace_state(self, workspace: Any) -> dict[str, dict[str, Any]]:
        """
        Keep workspace binding metadata aligned with resolved executor runtime.

        This mutates the passed workspace object but does not persist it.
        """

        metadata = self._metadata_dict(workspace)
        bindings = self._coerce_bindings(metadata.get(_BINDINGS_KEY))
        active_surface = self._normalize_surface(
            getattr(workspace, "resolved_executor_runtime", None)
        )

        if active_surface not in _SUPPORTED_SURFACES:
            if bindings:
                metadata.pop(_BINDINGS_KEY, None)
                workspace.metadata = metadata
            return {}

        existing_entry = bindings.get(active_surface)
        next_entry = self._configured_entry(
            surface=active_surface,
            existing_entry=existing_entry,
            existing_bindings=bindings,
        )
        next_bindings = {active_surface: next_entry}
        if next_bindings != bindings:
            metadata[_BINDINGS_KEY] = next_bindings
            workspace.metadata = metadata
        return deepcopy(next_bindings)

    def get_binding_snapshot(
        self,
        *,
        workspace: Any,
        surface: str,
    ) -> Optional[dict[str, Any]]:
        """Return a normalized in-memory snapshot for a workspace binding."""

        normalized_surface = self._normalize_surface(surface)
        if normalized_surface not in _SUPPORTED_SURFACES:
            return None

        metadata = self._metadata_dict(workspace)
        bindings = self._coerce_bindings(metadata.get(_BINDINGS_KEY))
        entry = bindings.get(normalized_surface)
        if not isinstance(entry, dict):
            return None

        return deepcopy(
            self._normalized_entry(
                surface=normalized_surface,
                entry=entry,
                default_time=_utc_now_iso(),
            )
        )

    def load_binding_snapshot(
        self,
        *,
        workspace_id: str,
        surface: str,
    ) -> Optional[dict[str, Any]]:
        """Load the persisted binding snapshot for a workspace surface."""

        normalized_workspace_id = self._clean_string(workspace_id)
        if not normalized_workspace_id:
            return None

        workspace = self._workspace_loader(normalized_workspace_id)
        if workspace is None:
            return None
        return self.get_binding_snapshot(workspace=workspace, surface=surface)

    def record_route_resolution(
        self,
        *,
        selection: ExecutorRouteSelection,
        resolved_runtime_id: Optional[str],
    ) -> Optional[Any]:
        """Persist the latest concrete runtime selected for a route."""

        target_workspace_id = (
            selection.effective_workspace_id or selection.requested_workspace_id
        )
        if not target_workspace_id:
            return None

        workspace = self._workspace_loader(target_workspace_id)
        if workspace is None:
            return None

        self.sync_workspace_state(workspace)
        metadata = self._metadata_dict(workspace)
        bindings = self._coerce_bindings(metadata.get(_BINDINGS_KEY))
        existing_entry = bindings.get(selection.surface)
        if not isinstance(existing_entry, dict):
            existing_entry = self._configured_entry(
                surface=selection.surface,
                existing_entry=None,
                existing_bindings=bindings,
            )

        now = _utc_now_iso()
        preferred_runtime_id = self._clean_string(selection.preferred_runtime_id)
        concrete_runtime_id = self._clean_string(resolved_runtime_id)
        normalized_existing = self._normalized_entry(
            surface=selection.surface,
            entry=existing_entry,
            default_time=now,
        )

        changed = any(
            (
                normalized_existing.get("preferred_runtime_id") != preferred_runtime_id,
                normalized_existing.get("concrete_runtime_id") != concrete_runtime_id,
                normalized_existing.get("selection_reason") != selection.selection_reason,
                normalized_existing.get("policy_mode") != selection.policy_mode,
                normalized_existing.get("binding_state") != "resolved",
                normalized_existing.get("last_requested_workspace_id")
                != selection.requested_workspace_id,
                normalized_existing.get("last_effective_workspace_id")
                != selection.effective_workspace_id,
                normalized_existing.get("last_auth_workspace_id")
                != selection.auth_workspace_id,
                normalized_existing.get("last_source_workspace_id")
                != selection.source_workspace_id,
            )
        )

        next_entry = dict(normalized_existing)
        next_entry.update(
            {
                "preferred_runtime_id": preferred_runtime_id,
                "concrete_runtime_id": concrete_runtime_id,
                "binding_state": "resolved",
                "selection_reason": selection.selection_reason,
                "policy_mode": selection.policy_mode,
                "last_requested_workspace_id": selection.requested_workspace_id,
                "last_effective_workspace_id": selection.effective_workspace_id,
                "last_auth_workspace_id": selection.auth_workspace_id,
                "last_source_workspace_id": selection.source_workspace_id,
            }
        )
        if changed:
            next_entry["binding_revision"] = normalized_existing["binding_revision"] + 1
            next_entry["updated_at"] = now

        next_bindings = {selection.surface: next_entry}
        if next_bindings == bindings:
            return workspace

        metadata[_BINDINGS_KEY] = next_bindings
        workspace.metadata = metadata
        return self._workspace_saver(workspace)

    @staticmethod
    def _load_workspace_sync(workspace_id: str):
        from backend.app.services.stores.postgres.workspaces_store import (
            PostgresWorkspacesStore,
        )

        return PostgresWorkspacesStore().get_workspace_sync(workspace_id)

    @staticmethod
    def _save_workspace_sync(workspace: Any):
        from backend.app.services.stores.postgres.workspaces_store import (
            PostgresWorkspacesStore,
        )

        return PostgresWorkspacesStore().update_workspace_sync(workspace)
