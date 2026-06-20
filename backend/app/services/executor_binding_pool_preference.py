"""Pool preference resolution for executor runtime bindings."""

from __future__ import annotations

from typing import Any, Optional

from backend.app.services.executor_route_resolver import ExecutorRouteSelection


class ExecutorBindingPoolPreferenceMixin:
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
                "preference_source": "session_lease",
                "binding_runtime_id": binding_runtime_id,
                "binding_state": binding_state,
                "binding_snapshot": binding_snapshot,
                "lease_runtime_id": binding_lease_runtime_id,
                "lease_state": binding_lease_state,
                "lease_owner_type": binding_lease_owner_type,
                "lease_owner_id": binding_lease_owner_id,
            }

        if binding_runtime_id and binding_state != "faulted" and not allow_pool_rotation:
            return {
                "preferred_runtime_id": binding_runtime_id,
                "allow_runtime_substitution": False,
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
