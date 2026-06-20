"""Lease and fault mutation methods for executor runtime bindings."""

from __future__ import annotations

from typing import Any, Optional

from backend.app.services.executor_binding_metadata import (
    _SUPPORTED_SURFACES,
    _utc_now_iso,
)


class ExecutorBindingLeaseMixin:
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
        bindings = self._coerce_bindings(metadata.get("executor_route_bindings"))
        existing_entry = bindings.get(normalized_surface)
        if not isinstance(existing_entry, dict):
            return workspace

        normalized_existing = self._normalized_entry(
            surface=normalized_surface,
            entry=existing_entry,
            default_time=_utc_now_iso(),
        )
        bound_runtime_id = self._clean_string(
            normalized_existing.get("concrete_runtime_id")
        )
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
        lease_runtime_id = self._clean_string(
            normalized_existing.get("lease_runtime_id")
        )
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

        metadata["executor_route_bindings"] = next_bindings
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
        bindings = self._coerce_bindings(metadata.get("executor_route_bindings"))
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
        metadata["executor_route_bindings"] = next_bindings
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
        bindings = self._coerce_bindings(metadata.get("executor_route_bindings"))
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
        if (
            normalized_owner_id
            and normalized_existing.get("lease_owner_id") != normalized_owner_id
        ):
            return workspace
        if (
            normalized_runtime_id
            and normalized_existing.get("lease_runtime_id") != normalized_runtime_id
        ):
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
        metadata["executor_route_bindings"] = next_bindings
        workspace.metadata = metadata
        return self._workspace_saver(workspace)
