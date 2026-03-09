"""
Workspace-aware GCA runtime selection.

Resolves which GCA pool account should be used for a Gemini CLI execution.
Selection is workspace-scoped by default and only falls back to another
workspace when the target workspace is discoverable and has no explicit
binding of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable, Dict, List, Optional

from backend.app.models.executor_spec import ExecutorSpec
from backend.app.models.workspace.enums import WorkspaceVisibility

logger = logging.getLogger(__name__)

_PREFERRED_GCA_KEYS = (
    "preferred_gca_runtime_id",
    "gca_runtime_id",
    "gca_pool_runtime_id",
)


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
        group_loader: Optional[Callable[[str], Any]] = None,
    ):
        self._workspace_loader = workspace_loader or self._load_workspace
        self._group_loader = group_loader or self._load_group_for_workspace

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

        requested_visibility = self._workspace_visibility(requested_workspace)
        fallback_workspace_id = source_workspace_id or auth_workspace_id
        if (
            requested_visibility == WorkspaceVisibility.DISCOVERABLE.value
            and fallback_workspace_id
            and fallback_workspace_id != workspace_id
        ):
            fallback_workspace = self._workspace_loader(fallback_workspace_id)
            if fallback_workspace is not None:
                fallback_runtime = self._preferred_runtime_from_workspace(
                    fallback_workspace,
                    trace,
                )
                if fallback_runtime:
                    return GCAWorkspaceSelection(
                        requested_workspace_id=workspace_id,
                        effective_workspace_id=fallback_workspace_id,
                        selected_runtime_id=fallback_runtime,
                        selection_reason="source_workspace_fallback",
                        auth_workspace_id=auth_workspace_id or fallback_workspace_id,
                        source_workspace_id=source_workspace_id or fallback_workspace_id,
                        trace=tuple(trace),
                    )
                if self._workspace_uses_gemini_cli(fallback_workspace, trace):
                    return GCAWorkspaceSelection(
                        requested_workspace_id=workspace_id,
                        effective_workspace_id=fallback_workspace_id,
                        selected_runtime_id=None,
                        selection_reason="source_workspace_pool",
                        auth_workspace_id=auth_workspace_id or fallback_workspace_id,
                        source_workspace_id=source_workspace_id or fallback_workspace_id,
                        trace=tuple(trace),
                    )

        if requested_visibility == WorkspaceVisibility.DISCOVERABLE.value:
            group = self._group_loader(workspace_id)
            dispatch_workspace_id = getattr(group, "dispatch_workspace_id", None) if group else None
            if dispatch_workspace_id and dispatch_workspace_id != workspace_id:
                dispatch_workspace = self._workspace_loader(dispatch_workspace_id)
                if dispatch_workspace is not None:
                    dispatch_runtime = self._preferred_runtime_from_workspace(
                        dispatch_workspace,
                        trace,
                    )
                    if dispatch_runtime:
                        return GCAWorkspaceSelection(
                            requested_workspace_id=workspace_id,
                            effective_workspace_id=dispatch_workspace_id,
                            selected_runtime_id=dispatch_runtime,
                            selection_reason="group_dispatch_fallback",
                            auth_workspace_id=auth_workspace_id or dispatch_workspace_id,
                            source_workspace_id=source_workspace_id or dispatch_workspace_id,
                            trace=tuple(trace),
                        )
                    if self._workspace_uses_gemini_cli(dispatch_workspace, trace):
                        return GCAWorkspaceSelection(
                            requested_workspace_id=workspace_id,
                            effective_workspace_id=dispatch_workspace_id,
                            selected_runtime_id=None,
                            selection_reason="group_dispatch_pool",
                            auth_workspace_id=auth_workspace_id or dispatch_workspace_id,
                            source_workspace_id=source_workspace_id or dispatch_workspace_id,
                            trace=tuple(trace),
                        )

        raise ValueError(
            "No workspace-scoped GCA pool policy configured for "
            f"workspace '{workspace_id}'. Bind the workspace to gemini_cli "
            "or configure an explicit preferred_gca_runtime_id override."
        )

    def _preferred_runtime_from_workspace(
        self,
        workspace: Any,
        trace: List[Dict[str, Any]],
    ) -> Optional[str]:
        workspace_id = getattr(workspace, "id", None) or ""
        for spec in self._iter_executor_specs(workspace):
            for key in _PREFERRED_GCA_KEYS:
                value = (spec.config or {}).get(key)
                if isinstance(value, str) and value.strip():
                    runtime_id = value.strip()
                    trace.append(
                        {
                            "workspace_id": workspace_id,
                            "runtime_id": runtime_id,
                            "via": f"executor_spec.config.{key}",
                        }
                    )
                    return runtime_id

        metadata = getattr(workspace, "metadata", None) or {}
        for key in _PREFERRED_GCA_KEYS:
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                runtime_id = value.strip()
                trace.append(
                    {
                        "workspace_id": workspace_id,
                        "runtime_id": runtime_id,
                        "via": f"workspace.metadata.{key}",
                    }
                )
                return runtime_id

        gca_meta = metadata.get("gca") if isinstance(metadata.get("gca"), dict) else {}
        nested_value = gca_meta.get("preferred_runtime_id")
        if isinstance(nested_value, str) and nested_value.strip():
            runtime_id = nested_value.strip()
            trace.append(
                {
                    "workspace_id": workspace_id,
                    "runtime_id": runtime_id,
                    "via": "workspace.metadata.gca.preferred_runtime_id",
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
        resolved_runtime = getattr(workspace, "resolved_executor_runtime", None)
        legacy_runtime = getattr(workspace, "executor_runtime", None)

        for runtime_id, via in (
            (resolved_runtime, "workspace.resolved_executor_runtime"),
            (legacy_runtime, "workspace.executor_runtime"),
        ):
            if runtime_id == "gemini_cli":
                trace.append(
                    {
                        "workspace_id": workspace_id,
                        "runtime_id": None,
                        "via": via,
                    }
                )
                return True

        for spec in self._iter_executor_specs(workspace):
            if spec.runtime_id == "gemini_cli":
                trace.append(
                    {
                        "workspace_id": workspace_id,
                        "runtime_id": None,
                        "via": "executor_spec.runtime_id",
                    }
                )
                return True

        return False

    def _iter_executor_specs(self, workspace: Any) -> List[ExecutorSpec]:
        specs = []
        for raw in getattr(workspace, "executor_specs", None) or []:
            if isinstance(raw, dict):
                try:
                    specs.append(ExecutorSpec.from_dict(raw))
                except Exception:
                    logger.debug("Invalid executor spec ignored for workspace %s", getattr(workspace, "id", None))
        specs.sort(key=lambda spec: (not spec.is_primary, spec.priority))
        return specs

    def _workspace_visibility(self, workspace: Any) -> str:
        visibility = getattr(workspace, "visibility", None)
        return getattr(visibility, "value", visibility) or WorkspaceVisibility.PRIVATE.value

    def _load_workspace(self, workspace_id: str):
        from backend.app.services.stores.postgres.workspaces_store import (
            PostgresWorkspacesStore,
        )

        return PostgresWorkspacesStore().get_workspace_sync(workspace_id)

    def _load_group_for_workspace(self, workspace_id: str):
        from backend.app.services.stores.postgres.workspace_group_store import (
            PostgresWorkspaceGroupStore,
        )

        return PostgresWorkspaceGroupStore().get_by_workspace_id(workspace_id)
