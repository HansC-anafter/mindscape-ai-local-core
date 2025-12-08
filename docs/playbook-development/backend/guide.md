# Backend Development Guide

## Overview

This guide explains how to create backend handlers for your playbook.

## When to Create a Handler

Create a handler when you need:
- Complex business logic beyond simple CRUD
- Custom API endpoints
- Cross-resource operations

For simple CRUD operations, use the [Generic Resources API](./resources-api.md) instead.

## Handler Structure

### Basic Handler Template

```python
# backend/handlers.py
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Path as PathParam

# Import base class (available at runtime)
try:
    from mindscape_ai_local_core.app.services.playbook_handlers.base import PlaybookHandler
except ImportError:
    # Fallback for development
    from abc import ABC, abstractmethod

    class PlaybookHandler(ABC):
        @abstractmethod
        def get_playbook_code(self) -> str:
            pass

        @abstractmethod
        def register_routes(self, router: APIRouter) -> None:
            pass

class YourPlaybookHandler(PlaybookHandler):
    def get_playbook_code(self) -> str:
        return "your_playbook"

    def register_routes(self, router: APIRouter) -> None:
        @router.get("/custom-endpoint", response_model=Dict[str, Any])
        async def get_custom_data(
            workspace_id: str = PathParam(..., description="Workspace ID")
        ):
            # Your implementation
            return {"data": "example"}

def register_handler() -> PlaybookHandler:
    """Factory function called by core"""
    return YourPlaybookHandler()
```

## Using Generic Resources API

For simple CRUD operations, use the generic resources API:

```python
# No handler needed - use generic API directly
GET    /api/v1/workspaces/:workspaceId/playbooks/:playbookCode/resources/:resourceType
POST   /api/v1/workspaces/:workspaceId/playbooks/:playbookCode/resources/:resourceType
PUT    /api/v1/workspaces/:workspaceId/playbooks/:playbookCode/resources/:resourceType/:resourceId
DELETE /api/v1/workspaces/:workspaceId/playbooks/:playbookCode/resources/:resourceType/:resourceId
```

## Accessing Core Services

Handlers can access core services:

```python
from mindscape_ai_local_core.app.services.mindscape_store import MindscapeStore
from mindscape_ai_local_core.app.services.storage_path_resolver import StoragePathResolver

store = MindscapeStore()
storage_resolver = StoragePathResolver()

# Get workspace
workspace = store.get_workspace(workspace_id)

# Get storage path
base_path = Path(workspace.storage_base_path)
resource_path = base_path / "playbooks" / "your_playbook" / "resources"
```

## Storage Structure

Resources are stored in:
```
{workspace_storage_path}/playbooks/{playbook_code}/resources/{resource_type}/{resource_id}.json
```

## Related Documentation

- [Resources API](./resources-api.md) - Generic resource management API
- [Handlers](./handlers.md) - Handler development details

---

**Status**: Framework ready, content to be expanded with detailed examples

