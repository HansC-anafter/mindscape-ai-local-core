"""Metadata normalization helpers for executor runtime bindings."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


_BINDINGS_KEY = "executor_route_bindings"
_SUPPORTED_SURFACES = frozenset({"codex_cli", "gemini_cli"})
_VALID_BINDING_STATES = frozenset({"configured", "resolved", "faulted"})
_VALID_POLICY_MODES = frozenset({"pinned_runtime", "unbound_runtime", "pool_rotation"})
_VALID_LEASE_STATES = frozenset({"active"})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExecutorBindingMetadataMixin:
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
            "binding_revision": max(
                self._coerce_revision(entry.get("binding_revision")),
                1,
            ),
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
