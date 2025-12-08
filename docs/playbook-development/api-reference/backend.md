# Backend API Reference

## Generic Resources API

**Base Path**: `/api/v1/workspaces/{workspace_id}/playbooks/{playbook_code}/resources`

### List Resources

```http
GET /api/v1/workspaces/:workspaceId/playbooks/:playbookCode/resources/:resourceType
```

### Get Resource

```http
GET /api/v1/workspaces/:workspaceId/playbooks/:playbookCode/resources/:resourceType/:resourceId
```

### Create Resource

```http
POST /api/v1/workspaces/:workspaceId/playbooks/:playbookCode/resources/:resourceType
Content-Type: application/json

{
  "id": "resource-id",
  // ... resource data
}
```

### Update Resource

```http
PUT /api/v1/workspaces/:workspaceId/playbooks/:playbookCode/resources/:resourceType/:resourceId
Content-Type: application/json

{
  // ... updated resource data
}
```

### Delete Resource

```http
DELETE /api/v1/workspaces/:workspaceId/playbooks/:playbookCode/resources/:resourceType/:resourceId
```

## Playbook Handler API

Handlers register custom routes under:
```
/api/v1/workspaces/{workspace_id}/playbooks/{playbook_code}/your-route
```

## Core Services

### MindscapeStore

**Location**: `mindscape_ai_local_core.app.services.mindscape_store.MindscapeStore`

**Methods**:
- `get_workspace(workspace_id)`: Get workspace
- `list_workspaces(...)`: List workspaces

### StoragePathResolver

**Location**: `mindscape_ai_local_core.app.services.storage_path_resolver.StoragePathResolver`

**Methods**:
- `resolve_workspace_storage_path(workspace)`: Get storage path

---

**Status**: Framework ready, content to be expanded with full API documentation

