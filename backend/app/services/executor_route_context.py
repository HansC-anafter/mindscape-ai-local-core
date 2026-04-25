"""
Helpers for surfacing workspace executor route context to caller chains.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional

from backend.app.services.executor_binding_service import ExecutorBindingService


_BINDING_SURFACES = frozenset({"codex_cli", "gemini_cli"})


def _normalize_runtime(value: Any) -> Optional[str]:
    cleaned = str(value or "").strip().lower()
    return cleaned or None


def build_executor_route_context(
    workspace: Any,
    *,
    binding_service: Optional[ExecutorBindingService] = None,
) -> Optional[dict[str, Any]]:
    """Return a normalized route context snapshot for a workspace."""

    workspace_id = str(getattr(workspace, "id", "") or "").strip()
    if not workspace_id:
        return None

    executor_runtime = _normalize_runtime(
        getattr(workspace, "resolved_executor_runtime", None)
        or getattr(workspace, "executor_runtime", None)
    )
    context: dict[str, Any] = {
        "workspace_id": workspace_id,
        "executor_runtime": executor_runtime,
    }

    if executor_runtime not in _BINDING_SURFACES:
        return context

    binding_service = binding_service or ExecutorBindingService()
    binding_snapshot = binding_service.get_binding_snapshot(
        workspace=workspace,
        surface=executor_runtime,
    )
    if binding_snapshot:
        context.update(deepcopy(binding_snapshot))
    return context


async def load_executor_route_context(
    workspace_id: str,
    *,
    binding_service: Optional[ExecutorBindingService] = None,
) -> Optional[dict[str, Any]]:
    """Load route context for a workspace from the store."""

    normalized_workspace_id = str(workspace_id or "").strip()
    if not normalized_workspace_id:
        return None

    from backend.app.services.stores.postgres.workspaces_store import (
        PostgresWorkspacesStore,
    )

    workspace = await PostgresWorkspacesStore().get_workspace(normalized_workspace_id)
    if workspace is None:
        return None
    return build_executor_route_context(
        workspace,
        binding_service=binding_service,
    )
