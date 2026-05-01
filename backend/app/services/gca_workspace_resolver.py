"""
Workspace-aware GCA runtime selection.

Resolves which GCA pool account should be used for a Gemini CLI execution.
Selection is workspace-scoped and fail-closed:
- Prefer an explicit runtime binding on the requested workspace.
- If the workspace is bound to gemini_cli without an explicit runtime,
  use the shared GCA pool scoped to that workspace.
- Do not fall back across workspaces.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable, Dict, List, Optional

from backend.app.services.executor_routing_policy_service import (
    ExecutorRoutingPolicyService,
)

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class GCAWorkspaceSelection:
    requested_workspace_id: str
    effective_workspace_id: str
    selected_runtime_id: Optional[str]
    selection_reason: str
    auth_workspace_id: Optional[str] = None
    source_workspace_id: Optional[str] = None
    trace: tuple[Dict[str, Any], ...] = ()


class GCAWorkspaceResolver:
    """Resolve the workspace-scoped GCA pool runtime for an execution."""

    def __init__(
        self,
        workspace_loader: Optional[Callable[[str], Any]] = None,
    ):
        self._workspace_loader = workspace_loader or self._load_workspace

    def resolve(
        self,
        *,
        workspace_id: str,
        auth_workspace_id: Optional[str] = None,
        source_workspace_id: Optional[str] = None,
    ) -> GCAWorkspaceSelection:
        if not workspace_id:
            raise ValueError("workspace_id is required for workspace-scoped GCA selection")

        requested_workspace = self._workspace_loader(workspace_id)
        if requested_workspace is None:
            raise ValueError(f"Workspace not found: {workspace_id}")

        trace: List[Dict[str, Any]] = []
        own_runtime = self._preferred_runtime_from_workspace(requested_workspace, trace)
        if own_runtime:
            return GCAWorkspaceSelection(
                requested_workspace_id=workspace_id,
                effective_workspace_id=workspace_id,
                selected_runtime_id=own_runtime,
                selection_reason="workspace_binding",
                auth_workspace_id=auth_workspace_id,
                source_workspace_id=source_workspace_id,
                trace=tuple(trace),
            )
        if self._workspace_uses_gemini_cli(requested_workspace, trace):
            return GCAWorkspaceSelection(
                requested_workspace_id=workspace_id,
                effective_workspace_id=workspace_id,
                selected_runtime_id=None,
                selection_reason="workspace_pool",
                auth_workspace_id=auth_workspace_id,
                source_workspace_id=source_workspace_id,
                trace=tuple(trace),
            )

        raise ValueError(
            "No workspace-scoped GCA pool policy configured for "
            f"workspace '{workspace_id}'. Bind the workspace to gemini_cli "
            "or configure a model-routing-registry preferred runtime binding."
        )

    def _preferred_runtime_from_workspace(
        self,
        workspace: Any,
        trace: List[Dict[str, Any]],
    ) -> Optional[str]:
        workspace_id = getattr(workspace, "id", None) or ""
        policy_snapshot = ExecutorRoutingPolicyService.extract_workspace_policy_snapshot(
            workspace
        )
        policy_entry = policy_snapshot.get("surfaces", {}).get("gemini_cli", {})
        policy_runtime = policy_entry.get("preferred_runtime_id")
        if isinstance(policy_runtime, str) and policy_runtime.strip():
            runtime_id = policy_runtime.strip()
            trace.append(
                {
                    "workspace_id": workspace_id,
                    "runtime_id": runtime_id,
                    "via": "model_routing_registry.executor_route_policy.surfaces.gemini_cli.preferred_runtime_id",
                }
            )
            return runtime_id

        trace.append({"workspace_id": workspace_id, "runtime_id": None, "via": "none"})
        return None

    def _workspace_uses_gemini_cli(
        self,
        workspace: Any,
        trace: List[Dict[str, Any]],
    ) -> bool:
        workspace_id = getattr(workspace, "id", None) or ""
        policy_snapshot = ExecutorRoutingPolicyService.extract_workspace_policy_snapshot(
            workspace
        )
        policy_primary = policy_snapshot.get("primary_executor_runtime")
        policy_entry = policy_snapshot.get("surfaces", {}).get("gemini_cli", {})
        if policy_primary == "gemini_cli" or bool(policy_entry.get("enabled")):
            trace.append(
                {
                    "workspace_id": workspace_id,
                    "runtime_id": None,
                    "via": "model_routing_registry.executor_route_policy",
                }
            )
            return True

        return False

    def _load_workspace(self, workspace_id: str):
        from backend.app.services.stores.postgres.workspaces_store import (
            PostgresWorkspacesStore,
        )

        return PostgresWorkspacesStore().get_workspace_sync(workspace_id)
