"""
Canonical executor routing policy authority for workspace-scoped runtimes.

This service owns the policy contract for executor runtime selection:
- which executor runtime is primary for a workspace
- whether runtime substitution is allowed
- which concrete pool runtime is preferred for codex_cli / gemini_cli

Policy authority lives under
`workspace.metadata.model_routing_registry.executor_route_policy`.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from backend.app.services.executor_binding_service import ExecutorBindingService


_METADATA_ROOT_KEY = "model_routing_registry"
_EXECUTOR_POLICY_KEY = "executor_route_policy"
_SUPPORTED_POOL_SURFACES = ("codex_cli", "gemini_cli")
_PREFERRED_RUNTIME_KEYS = {
    "codex_cli": ("preferred_codex_runtime_id", "codex_runtime_id", "codex_pool_runtime_id"),
    "gemini_cli": ("preferred_gca_runtime_id", "gca_runtime_id", "gca_pool_runtime_id"),
}
_NESTED_METADATA_KEYS = {
    "codex_cli": ("codex", "preferred_runtime_id"),
    "gemini_cli": ("gca", "preferred_runtime_id"),
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ExecutorRoutingPolicyService:
    """Single policy authority for workspace executor routing."""

    def __init__(
        self,
        workspace_loader: Optional[Callable[[str], Any]] = None,
        workspace_saver: Optional[Callable[[Any], Any]] = None,
    ) -> None:
        self._workspace_loader = workspace_loader or self._load_workspace_sync
        self._workspace_saver = workspace_saver or self._save_workspace_sync

    @classmethod
    def extract_workspace_policy_snapshot(cls, workspace: Any) -> dict[str, Any]:
        metadata = cls._metadata_dict(workspace)
        registry_root = metadata.get(_METADATA_ROOT_KEY)
        if not isinstance(registry_root, dict):
            registry_root = {}
        policy = registry_root.get(_EXECUTOR_POLICY_KEY)
        if not isinstance(policy, dict):
            policy = {}

        primary_runtime = cls._normalize_runtime(policy.get("primary_executor_runtime"))

        surface_entries = policy.get("surfaces")
        if not isinstance(surface_entries, dict):
            surface_entries = {}

        surfaces: dict[str, dict[str, Any]] = {}
        for surface in _SUPPORTED_POOL_SURFACES:
            entry = surface_entries.get(surface)
            if not isinstance(entry, dict):
                entry = {}
            preferred_runtime_id = cls._normalize_runtime(entry.get("preferred_runtime_id"))
            enabled = bool(entry.get("enabled", primary_runtime == surface))
            surfaces[surface] = {
                "surface": surface,
                "enabled": enabled,
                "preferred_runtime_id": preferred_runtime_id,
                "source": (
                    "model-routing-registry.workspace.executor_route_policy.surfaces"
                    if preferred_runtime_id
                    else "none"
                ),
            }

        return {
            "route_authority": "model-routing-registry",
            "primary_executor_runtime": primary_runtime,
            "allow_runtime_substitution": bool(policy.get("allow_runtime_substitution", False)),
            "surfaces": surfaces,
        }

    @classmethod
    def build_registry_summary(cls) -> dict[str, Any]:
        fallback_policy = {
            "allowed": False,
            "mode": "fail_closed",
            "summary": "If the preferred runtime is unavailable, selection stops with an error instead of substituting another runtime.",
        }
        return {
            "route_authority": "model-routing-registry",
            "summary": "Executor runtime policy is resolved through model-routing-registry and then enforced by runtime binding state.",
            "precedence": [
                {
                    "key": "workspace_executor_override",
                    "label": "Workspace Executor Override",
                    "summary": "workspace metadata route policy chooses the primary executor runtime",
                    "active": True,
                },
                {
                    "key": "workspace_surface_binding",
                    "label": "Workspace Surface Runtime Binding",
                    "summary": "workspace metadata route policy chooses the preferred concrete runtime for codex_cli / gemini_cli",
                    "active": True,
                },
                {
                    "key": "runtime_binding_state",
                    "label": "Runtime Binding State",
                    "summary": "binding snapshots and leases apply only after route policy resolution",
                    "active": True,
                },
            ],
            "fallback_policy": fallback_policy,
            "runtime_substitution_policy": fallback_policy,
            "supported_pool_surfaces": list(_SUPPORTED_POOL_SURFACES),
        }

    def build_workspace_executor_payload(self, workspace_id: str) -> dict[str, Any]:
        workspace = self._load_required_workspace(workspace_id)
        snapshot = self.extract_workspace_policy_snapshot(workspace)
        primary_runtime = snapshot["primary_executor_runtime"]
        return {
            **snapshot,
            "workspace_id": workspace.id,
            "resolved_executor_runtime": primary_runtime,
            "dispatch_chain": self._build_dispatch_chain(snapshot),
            "fallback_policy": {
                "allowed": False,
                "mode": "fail_closed",
                "summary": "Workspace executor routing stops with an error when the preferred runtime is unavailable.",
            },
            "workspace_override": {
                "enabled": primary_runtime is not None,
                "summary": (
                    f"workspace override pinned to {primary_runtime}"
                    if primary_runtime
                    else "no workspace executor override configured"
                ),
            },
            "precedence": [
                {
                    "key": "workspace_executor_override",
                    "label": "Workspace Executor Override",
                    "summary": "workspace primary executor runtime is authoritative",
                    "active": primary_runtime is not None,
                },
                {
                    "key": "workspace_surface_binding",
                    "label": "Workspace Surface Runtime Binding",
                    "summary": "preferred concrete runtime ids are workspace-scoped",
                    "active": any(
                        item.get("preferred_runtime_id")
                        for item in snapshot["surfaces"].values()
                    ),
                },
                {
                    "key": "runtime_binding_state",
                    "label": "Runtime Binding State",
                    "summary": "leases and resolved runtime snapshots apply after route policy",
                    "active": True,
                },
            ],
        }

    def set_workspace_primary_runtime(
        self,
        *,
        workspace_id: str,
        executor_runtime: Optional[str],
    ) -> dict[str, Any]:
        workspace = self._load_required_workspace(workspace_id)
        normalized_runtime = self._normalize_runtime(executor_runtime)

        metadata = self._metadata_dict(workspace)
        policy = self._ensure_policy(metadata)
        policy["primary_executor_runtime"] = normalized_runtime
        policy["allow_runtime_substitution"] = False

        surfaces = policy.setdefault("surfaces", {})
        if not isinstance(surfaces, dict):
            surfaces = {}
            policy["surfaces"] = surfaces
        for surface in _SUPPORTED_POOL_SURFACES:
            entry = surfaces.get(surface)
            if not isinstance(entry, dict):
                entry = {}
                surfaces[surface] = entry
            entry["enabled"] = normalized_runtime == surface

        workspace.metadata = metadata
        ExecutorBindingService().sync_workspace_state(workspace)
        workspace.updated_at = _utc_now()
        self._workspace_saver(workspace)
        return self.build_workspace_executor_payload(workspace.id)

    def set_workspace_surface_preferred_runtime(
        self,
        *,
        workspace_id: str,
        surface: str,
        preferred_runtime_id: Optional[str],
    ) -> dict[str, Any]:
        normalized_surface = self._normalize_runtime(surface)
        if normalized_surface not in _SUPPORTED_POOL_SURFACES:
            supported = ", ".join(_SUPPORTED_POOL_SURFACES)
            raise ValueError(
                f"Unsupported executor surface '{surface}'. Supported: {supported}"
            )

        workspace = self._load_required_workspace(workspace_id)
        metadata = self._metadata_dict(workspace)
        policy = self._ensure_policy(metadata)
        policy["allow_runtime_substitution"] = False

        surfaces = policy.setdefault("surfaces", {})
        if not isinstance(surfaces, dict):
            surfaces = {}
            policy["surfaces"] = surfaces
        entry = surfaces.get(normalized_surface)
        if not isinstance(entry, dict):
            entry = {}
            surfaces[normalized_surface] = entry

        normalized_runtime_id = self._normalize_runtime(preferred_runtime_id)
        entry["preferred_runtime_id"] = normalized_runtime_id
        entry["enabled"] = bool(
            entry.get("enabled", self.extract_workspace_policy_snapshot(workspace)["primary_executor_runtime"] == normalized_surface)
        )

        self._clear_legacy_preferred_runtime_metadata(metadata, normalized_surface)
        workspace.metadata = metadata
        workspace.updated_at = _utc_now()
        self._workspace_saver(workspace)
        return self.build_workspace_executor_payload(workspace.id)

    @classmethod
    def _metadata_dict(cls, workspace: Any) -> dict[str, Any]:
        metadata = getattr(workspace, "metadata", None)
        return deepcopy(metadata) if isinstance(metadata, dict) else {}

    @classmethod
    def _normalize_runtime(cls, value: Any) -> Optional[str]:
        if not isinstance(value, str):
            return None
        cleaned = value.strip()
        return cleaned or None

    @classmethod
    def _ensure_policy(cls, metadata: dict[str, Any]) -> dict[str, Any]:
        registry_root = metadata.get(_METADATA_ROOT_KEY)
        if not isinstance(registry_root, dict):
            registry_root = {}
            metadata[_METADATA_ROOT_KEY] = registry_root
        policy = registry_root.get(_EXECUTOR_POLICY_KEY)
        if not isinstance(policy, dict):
            policy = {}
            registry_root[_EXECUTOR_POLICY_KEY] = policy
        return policy

    @classmethod
    def _clear_legacy_preferred_runtime_metadata(
        cls,
        metadata: dict[str, Any],
        surface: str,
    ) -> None:
        for key in _PREFERRED_RUNTIME_KEYS[surface]:
            metadata.pop(key, None)
        nested_root, nested_key = _NESTED_METADATA_KEYS[surface]
        nested = metadata.get(nested_root)
        if isinstance(nested, dict):
            next_nested = deepcopy(nested)
            next_nested.pop(nested_key, None)
            if next_nested:
                metadata[nested_root] = next_nested
            else:
                metadata.pop(nested_root, None)

    @classmethod
    def _build_dispatch_chain(cls, snapshot: dict[str, Any]) -> list[str]:
        primary_runtime = cls._normalize_runtime(snapshot.get("primary_executor_runtime"))
        if primary_runtime:
            return [primary_runtime]

        dispatch_chain: list[str] = []
        for surface in _SUPPORTED_POOL_SURFACES:
            surface_entry = snapshot.get("surfaces", {}).get(surface, {})
            if bool(surface_entry.get("enabled")):
                dispatch_chain.append(surface)
        return dispatch_chain

    def _load_required_workspace(self, workspace_id: str) -> Any:
        normalized_workspace_id = self._normalize_runtime(workspace_id)
        if not normalized_workspace_id:
            raise ValueError("workspace_id is required")
        workspace = self._workspace_loader(normalized_workspace_id)
        if workspace is None:
            raise ValueError(f"Workspace not found: {normalized_workspace_id}")
        return workspace

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
