"""Canonical service seam for workspace resource binding operations."""

from typing import Optional
from uuid import uuid4

from backend.app.models.workspace_resource_binding import (
    CreateWorkspaceResourceBindingRequest,
    ResourceType,
    UpdateWorkspaceResourceBindingRequest,
    WorkspaceResourceBinding,
)
from backend.app.services.stores.workspace_resource_binding_store import (
    WorkspaceResourceBindingStore,
)


class WorkspaceResourceBindingError(RuntimeError):
    """Base error for workspace resource binding operations."""


class WorkspaceResourceBindingWorkspaceMismatchError(WorkspaceResourceBindingError):
    """Raised when the request body targets a different workspace."""


class WorkspaceResourceBindingConflictError(WorkspaceResourceBindingError):
    """Raised when a workspace already binds the requested resource."""


class WorkspaceResourceBindingNotFoundError(WorkspaceResourceBindingError):
    """Raised when the requested binding does not exist."""


class WorkspaceResourceBindingFacade:
    """Own binding validation and persistence orchestration behind HTTP routes."""

    def __init__(self, store: Optional[WorkspaceResourceBindingStore] = None):
        self.store = store or WorkspaceResourceBindingStore()

    def create(
        self,
        *,
        workspace_id: str,
        request: CreateWorkspaceResourceBindingRequest,
    ) -> WorkspaceResourceBinding:
        if request.workspace_id != workspace_id:
            raise WorkspaceResourceBindingWorkspaceMismatchError(
                "Workspace ID in path must match request body"
            )
        existing = self.store.get_binding_by_resource(
            workspace_id=workspace_id,
            resource_type=request.resource_type,
            resource_id=request.resource_id,
        )
        if existing is not None:
            raise WorkspaceResourceBindingConflictError(
                self._resource_message(
                    "Binding already exists for",
                    request.resource_type,
                    request.resource_id,
                )
            )
        return self.store.save_binding(
            WorkspaceResourceBinding(
                id=str(uuid4()),
                workspace_id=workspace_id,
                resource_type=request.resource_type,
                resource_id=request.resource_id,
                access_mode=request.access_mode,
                overrides=request.overrides,
            )
        )

    def list_for_workspace(
        self,
        *,
        workspace_id: str,
        resource_type: Optional[ResourceType] = None,
    ) -> list[WorkspaceResourceBinding]:
        return self.store.list_bindings_by_workspace(
            workspace_id=workspace_id,
            resource_type=resource_type,
        )

    def get(
        self,
        *,
        workspace_id: str,
        resource_type: ResourceType,
        resource_id: str,
    ) -> WorkspaceResourceBinding:
        binding = self.store.get_binding_by_resource(
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        if binding is None:
            raise WorkspaceResourceBindingNotFoundError(
                self._resource_message(
                    "Binding not found for", resource_type, resource_id
                )
            )
        return binding

    def update(
        self,
        *,
        workspace_id: str,
        resource_type: ResourceType,
        resource_id: str,
        request: UpdateWorkspaceResourceBindingRequest,
    ) -> WorkspaceResourceBinding:
        binding = self.get(
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        if request.access_mode is not None:
            binding.access_mode = request.access_mode
        if request.overrides is not None:
            binding.overrides = request.overrides
        return self.store.save_binding(binding)

    def delete(
        self,
        *,
        workspace_id: str,
        resource_type: ResourceType,
        resource_id: str,
    ) -> None:
        deleted = self.store.delete_binding_by_resource(
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        if not deleted:
            raise WorkspaceResourceBindingNotFoundError(
                self._resource_message(
                    "Binding not found for", resource_type, resource_id
                )
            )

    def list_workspaces_using_resource(
        self,
        *,
        resource_type: ResourceType,
        resource_id: str,
    ) -> list[WorkspaceResourceBinding]:
        return self.store.list_bindings_by_resource(
            resource_type=resource_type,
            resource_id=resource_id,
        )

    @staticmethod
    def _resource_message(
        prefix: str,
        resource_type: ResourceType,
        resource_id: str,
    ) -> str:
        return f"{prefix} {resource_type}:{resource_id}"
