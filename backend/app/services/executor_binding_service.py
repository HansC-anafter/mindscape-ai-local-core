"""
Workspace executor binding state management.

Bindings are persisted in workspace metadata so caller-facing config,
auth-bundle resolution, and later fault handling can converge on the
same workspace-scoped contract without adding a schema migration first.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from backend.app.services.executor_route_resolver import ExecutorRouteSelection


_BINDINGS_KEY = "executor_route_bindings"
_SUPPORTED_SURFACES = frozenset({"codex_cli", "gemini_cli"})
_VALID_BINDING_STATES = frozenset({"configured", "resolved", "faulted"})
_VALID_POLICY_MODES = frozenset({"pinned_runtime", "unbound_runtime", "pool_rotation"})
_VALID_LEASE_STATES = frozenset({"active"})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExecutorBindingService:
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

    def resolve_pool_preference(
        self,
        *,
        selection: ExecutorRouteSelection,
        lease_owner_type: Optional[str] = None,
        lease_owner_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Resolve the concrete pool preference before runtime selection.

        Explicit route bindings win. Otherwise, a previously resolved concrete
        runtime is reused until it is marked faulted. Session-scoped leases win
        over the generic binding snapshot for the matching owner, which gives
        governed callers sticky ownership without enabling runtime substitution.
        """

        workspace_id = selection.effective_workspace_id or selection.requested_workspace_id
        binding_snapshot = (
            self.load_binding_snapshot(workspace_id=workspace_id, surface=selection.surface)
            if workspace_id
            else None
        )
        binding_runtime_id = (
            self._clean_string(binding_snapshot.get("concrete_runtime_id"))
            if binding_snapshot
            else None
        )
        binding_state = (
            self._clean_string(binding_snapshot.get("binding_state")) or "configured"
            if binding_snapshot
            else "configured"
        )
        normalized_lease_owner_type = self._clean_string(lease_owner_type)
        normalized_lease_owner_id = self._clean_string(lease_owner_id)
        binding_lease_runtime_id = (
            self._clean_string(binding_snapshot.get("lease_runtime_id"))
            if binding_snapshot
            else None
        )
        binding_lease_state = (
            self._clean_string(binding_snapshot.get("lease_state"))
            if binding_snapshot
            else None
        )
        binding_lease_owner_type = (
            self._clean_string(binding_snapshot.get("lease_owner_type"))
            if binding_snapshot
            else None
        )
        binding_lease_owner_id = (
            self._clean_string(binding_snapshot.get("lease_owner_id"))
            if binding_snapshot
            else None
        )
        allow_pool_rotation = (
            self._clean_string(selection.selection_reason) == "workspace_pool"
        )

        explicit_runtime_id = self._clean_string(selection.preferred_runtime_id)
        if explicit_runtime_id:
            return {
                "preferred_runtime_id": explicit_runtime_id,
                "allow_runtime_substitution": False,
                "allow_fallback": False,
                "preference_source": "executor_route",
                "binding_runtime_id": binding_runtime_id,
                "binding_state": binding_state,
                "binding_snapshot": binding_snapshot,
                "lease_runtime_id": binding_lease_runtime_id,
                "lease_state": binding_lease_state,
                "lease_owner_type": binding_lease_owner_type,
                "lease_owner_id": binding_lease_owner_id,
            }

        if (
            normalized_lease_owner_type
            and normalized_lease_owner_id
            and binding_state != "faulted"
            and binding_lease_state == "active"
            and binding_lease_runtime_id
            and binding_lease_owner_type == normalized_lease_owner_type
            and binding_lease_owner_id == normalized_lease_owner_id
        ):
            return {
                "preferred_runtime_id": binding_lease_runtime_id,
                "allow_runtime_substitution": allow_pool_rotation,
                "allow_fallback": allow_pool_rotation,
                "preference_source": "session_lease",
                "binding_runtime_id": binding_runtime_id,
                "binding_state": binding_state,
                "binding_snapshot": binding_snapshot,
                "lease_runtime_id": binding_lease_runtime_id,
                "lease_state": binding_lease_state,
                "lease_owner_type": binding_lease_owner_type,
                "lease_owner_id": binding_lease_owner_id,
            }

        if binding_runtime_id and binding_state != "faulted":
            return {
                "preferred_runtime_id": binding_runtime_id,
                "allow_runtime_substitution": False,
                "allow_fallback": False,
                "preference_source": "binding_snapshot",
                "binding_runtime_id": binding_runtime_id,
                "binding_state": binding_state,
                "binding_snapshot": binding_snapshot,
                "lease_runtime_id": binding_lease_runtime_id,
                "lease_state": binding_lease_state,
                "lease_owner_type": binding_lease_owner_type,
                "lease_owner_id": binding_lease_owner_id,
            }

        return {
            "preferred_runtime_id": None,
            "allow_runtime_substitution": allow_pool_rotation,
            "allow_fallback": allow_pool_rotation,
            "preference_source": (
                "pool_rotation" if allow_pool_rotation else "no_bound_runtime"
            ),
            "binding_runtime_id": binding_runtime_id,
            "binding_state": binding_state,
            "binding_snapshot": binding_snapshot,
            "lease_runtime_id": binding_lease_runtime_id,
            "lease_state": binding_lease_state,
            "lease_owner_type": binding_lease_owner_type,
            "lease_owner_id": binding_lease_owner_id,
        }

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

    def record_runtime_fault(
        self,
        *,
        workspace_id: str,
        surface: str,
        runtime_id: Optional[str],
        error_code: Optional[str] = None,
    ) -> Optional[Any]:
        """Mark the currently bound runtime as faulted."""

        normalized_surface = self._normalize_surface(surface)
        workspace = self._workspace_loader(workspace_id)
        if workspace is None:
            return None

        metadata = self._metadata_dict(workspace)
        bindings = self._coerce_bindings(metadata.get(_BINDINGS_KEY))
        existing_entry = bindings.get(normalized_surface)
        if not isinstance(existing_entry, dict):
            return workspace

        normalized_existing = self._normalized_entry(
            surface=normalized_surface,
            entry=existing_entry,
            default_time=_utc_now_iso(),
        )
        bound_runtime_id = self._clean_string(normalized_existing.get("concrete_runtime_id"))
        if bound_runtime_id and runtime_id and bound_runtime_id != runtime_id:
            return workspace

        now = _utc_now_iso()
        next_entry = dict(normalized_existing)
        next_entry.update(
            {
                "binding_state": "faulted",
                "last_fault_runtime_id": self._clean_string(runtime_id),
                "last_fault_code": self._clean_string(error_code),
                "binding_revision": normalized_existing["binding_revision"] + 1,
                "updated_at": now,
            }
        )
        lease_runtime_id = self._clean_string(normalized_existing.get("lease_runtime_id"))
        if lease_runtime_id and (not runtime_id or lease_runtime_id == runtime_id):
            next_entry.update(
                self._cleared_lease_fields(
                    released_at=now,
                    reason=(
                        f"fault:{self._clean_string(error_code)}"
                        if self._clean_string(error_code)
                        else "fault"
                    ),
                )
            )
        next_bindings = {normalized_surface: next_entry}
        if next_bindings == bindings:
            return workspace

        metadata[_BINDINGS_KEY] = next_bindings
        workspace.metadata = metadata
        return self._workspace_saver(workspace)

    def record_runtime_lease(
        self,
        *,
        workspace_id: str,
        surface: str,
        runtime_id: str,
        lease_owner_type: str,
        lease_owner_id: str,
    ) -> Optional[Any]:
        """Persist an active session-scoped lease for a concrete runtime."""

        normalized_surface = self._normalize_surface(surface)
        normalized_runtime_id = self._clean_string(runtime_id)
        normalized_owner_type = self._clean_string(lease_owner_type)
        normalized_owner_id = self._clean_string(lease_owner_id)
        if (
            normalized_surface not in _SUPPORTED_SURFACES
            or not normalized_runtime_id
            or not normalized_owner_type
            or not normalized_owner_id
        ):
            return None

        workspace = self._workspace_loader(workspace_id)
        if workspace is None:
            return None

        self.sync_workspace_state(workspace)
        metadata = self._metadata_dict(workspace)
        bindings = self._coerce_bindings(metadata.get(_BINDINGS_KEY))
        existing_entry = bindings.get(normalized_surface)
        if not isinstance(existing_entry, dict):
            existing_entry = self._configured_entry(
                surface=normalized_surface,
                existing_entry=None,
                existing_bindings=bindings,
            )

        now = _utc_now_iso()
        normalized_existing = self._normalized_entry(
            surface=normalized_surface,
            entry=existing_entry,
            default_time=now,
        )
        same_active_lease = (
            normalized_existing.get("lease_state") == "active"
            and normalized_existing.get("lease_owner_type") == normalized_owner_type
            and normalized_existing.get("lease_owner_id") == normalized_owner_id
            and normalized_existing.get("lease_runtime_id") == normalized_runtime_id
        )
        next_entry = dict(normalized_existing)
        next_entry.update(
            {
                "lease_owner_type": normalized_owner_type,
                "lease_owner_id": normalized_owner_id,
                "lease_runtime_id": normalized_runtime_id,
                "lease_state": "active",
                "lease_acquired_at": (
                    normalized_existing.get("lease_acquired_at")
                    if same_active_lease
                    else now
                ),
                "lease_updated_at": (
                    normalized_existing.get("lease_updated_at")
                    if same_active_lease
                    else now
                ),
            }
        )

        if next_entry == normalized_existing:
            return workspace

        next_entry["binding_revision"] = normalized_existing["binding_revision"] + 1
        next_entry["updated_at"] = now
        next_bindings = {normalized_surface: next_entry}
        metadata[_BINDINGS_KEY] = next_bindings
        workspace.metadata = metadata
        return self._workspace_saver(workspace)

    def clear_runtime_lease(
        self,
        *,
        workspace_id: str,
        surface: str,
        lease_owner_type: Optional[str] = None,
        lease_owner_id: Optional[str] = None,
        runtime_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Optional[Any]:
        """Clear a matching active lease without faulting the whole binding."""

        normalized_surface = self._normalize_surface(surface)
        workspace = self._workspace_loader(workspace_id)
        if workspace is None:
            return None

        metadata = self._metadata_dict(workspace)
        bindings = self._coerce_bindings(metadata.get(_BINDINGS_KEY))
        existing_entry = bindings.get(normalized_surface)
        if not isinstance(existing_entry, dict):
            return workspace

        normalized_existing = self._normalized_entry(
            surface=normalized_surface,
            entry=existing_entry,
            default_time=_utc_now_iso(),
        )
        if normalized_existing.get("lease_state") != "active":
            return workspace

        normalized_owner_type = self._clean_string(lease_owner_type)
        normalized_owner_id = self._clean_string(lease_owner_id)
        normalized_runtime_id = self._clean_string(runtime_id)
        if (
            normalized_owner_type
            and normalized_existing.get("lease_owner_type") != normalized_owner_type
        ):
            return workspace
        if normalized_owner_id and normalized_existing.get("lease_owner_id") != normalized_owner_id:
            return workspace
        if normalized_runtime_id and normalized_existing.get("lease_runtime_id") != normalized_runtime_id:
            return workspace

        now = _utc_now_iso()
        next_entry = dict(normalized_existing)
        next_entry.update(
            self._cleared_lease_fields(
                released_at=now,
                reason=self._clean_string(reason) or "manual_clear",
            )
        )
        if next_entry == normalized_existing:
            return workspace

        next_entry["binding_revision"] = normalized_existing["binding_revision"] + 1
        next_entry["updated_at"] = now
        next_bindings = {normalized_surface: next_entry}
        metadata[_BINDINGS_KEY] = next_bindings
        workspace.metadata = metadata
        return self._workspace_saver(workspace)

    @staticmethod
    def _normalize_surface(surface: Any) -> str:
        return str(surface or "").strip().lower()

    @staticmethod
    def _clean_string(value: Any) -> Optional[str]:
        if not isinstance(value, str):
            return None
        cleaned = value.strip()
        return cleaned or None

    def _configured_entry(
        self,
        *,
        surface: str,
        existing_entry: Any,
        existing_bindings: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        now = _utc_now_iso()
        if isinstance(existing_entry, dict):
            return self._normalized_entry(
                surface=surface,
                entry=existing_entry,
                default_time=now,
            )

        next_revision = (
            max(
                self._coerce_revision(binding.get("binding_revision"))
                for binding in existing_bindings.values()
                if isinstance(binding, dict)
            )
            + 1
            if existing_bindings
            else 1
        )
        return {
            "executor_runtime": surface,
            "preferred_runtime_id": None,
            "concrete_runtime_id": None,
            "binding_revision": next_revision,
            "binding_state": "configured",
            "selection_reason": None,
            "policy_mode": "unbound_runtime",
            "configured_at": now,
            "updated_at": now,
            "last_requested_workspace_id": None,
            "last_effective_workspace_id": None,
            "last_auth_workspace_id": None,
            "last_source_workspace_id": None,
            "lease_owner_type": None,
            "lease_owner_id": None,
            "lease_runtime_id": None,
            "lease_state": None,
            "lease_acquired_at": None,
            "lease_updated_at": None,
            "last_lease_release_reason": None,
            "last_lease_released_at": None,
        }

    def _normalized_entry(
        self,
        *,
        surface: str,
        entry: dict[str, Any],
        default_time: str,
    ) -> dict[str, Any]:
        preferred_runtime_id = self._clean_string(entry.get("preferred_runtime_id"))
        configured_at = self._clean_string(entry.get("configured_at")) or default_time
        updated_at = self._clean_string(entry.get("updated_at")) or configured_at
        binding_state = self._clean_string(entry.get("binding_state")) or "configured"
        if binding_state not in _VALID_BINDING_STATES:
            binding_state = "configured"
        lease_owner_type = self._clean_string(entry.get("lease_owner_type"))
        lease_owner_id = self._clean_string(entry.get("lease_owner_id"))
        lease_runtime_id = self._clean_string(entry.get("lease_runtime_id"))
        lease_state = self._clean_string(entry.get("lease_state"))
        if not (lease_owner_type and lease_owner_id and lease_runtime_id):
            lease_owner_type = None
            lease_owner_id = None
            lease_runtime_id = None
            lease_state = None
        elif lease_state not in _VALID_LEASE_STATES:
            lease_state = "active"
        lease_acquired_at = (
            self._clean_string(entry.get("lease_acquired_at"))
            if lease_state == "active"
            else None
        ) or (updated_at if lease_state == "active" else None)
        lease_updated_at = (
            self._clean_string(entry.get("lease_updated_at"))
            if lease_state == "active"
            else None
        ) or lease_acquired_at
        policy_mode = self._clean_string(entry.get("policy_mode"))
        if policy_mode not in _VALID_POLICY_MODES:
            policy_mode = "pinned_runtime" if preferred_runtime_id else "unbound_runtime"

        return {
            "executor_runtime": surface,
            "preferred_runtime_id": preferred_runtime_id,
            "concrete_runtime_id": self._clean_string(entry.get("concrete_runtime_id")),
            "binding_revision": max(self._coerce_revision(entry.get("binding_revision")), 1),
            "binding_state": binding_state,
            "selection_reason": self._clean_string(entry.get("selection_reason")),
            "policy_mode": policy_mode,
            "configured_at": configured_at,
            "updated_at": updated_at,
            "last_requested_workspace_id": self._clean_string(
                entry.get("last_requested_workspace_id")
            ),
            "last_effective_workspace_id": self._clean_string(
                entry.get("last_effective_workspace_id")
            ),
            "last_auth_workspace_id": self._clean_string(
                entry.get("last_auth_workspace_id")
            ),
            "last_source_workspace_id": self._clean_string(
                entry.get("last_source_workspace_id")
            ),
            "lease_owner_type": lease_owner_type,
            "lease_owner_id": lease_owner_id,
            "lease_runtime_id": lease_runtime_id,
            "lease_state": lease_state,
            "lease_acquired_at": lease_acquired_at,
            "lease_updated_at": lease_updated_at,
            "last_lease_release_reason": self._clean_string(
                entry.get("last_lease_release_reason")
            ),
            "last_lease_released_at": self._clean_string(
                entry.get("last_lease_released_at")
            ),
            "last_fault_runtime_id": self._clean_string(
                entry.get("last_fault_runtime_id")
            ),
            "last_fault_code": self._clean_string(entry.get("last_fault_code")),
        }

    @staticmethod
    def _cleared_lease_fields(
        *,
        released_at: str,
        reason: Optional[str],
    ) -> dict[str, Any]:
        return {
            "lease_owner_type": None,
            "lease_owner_id": None,
            "lease_runtime_id": None,
            "lease_state": None,
            "lease_acquired_at": None,
            "lease_updated_at": None,
            "last_lease_release_reason": reason,
            "last_lease_released_at": released_at,
        }

    @staticmethod
    def _coerce_revision(value: Any) -> int:
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _metadata_dict(workspace: Any) -> dict[str, Any]:
        metadata = getattr(workspace, "metadata", None)
        if isinstance(metadata, dict):
            return dict(metadata)
        return {}

    @staticmethod
    def _coerce_bindings(value: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(value, dict):
            return {}
        bindings: dict[str, dict[str, Any]] = {}
        for surface, entry in value.items():
            normalized_surface = str(surface or "").strip().lower()
            if normalized_surface not in _SUPPORTED_SURFACES:
                continue
            if isinstance(entry, dict):
                bindings[normalized_surface] = dict(entry)
        return bindings

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
