# Resources API

## Overview

The Generic Resources API provides CRUD operations for playbook-specific resources. All playbooks can use these endpoints without implementing custom handlers.

## Endpoints

### List Resources

```http
GET /api/v1/workspaces/:workspaceId/playbooks/:playbookCode/resources/:resourceType
```

**Response**:
```json
[
  {
    "id": "resource-1",
    "title": "Resource 1",
    "content": "...",
    "created_at": "2025-12-05T10:00:00Z",
    "updated_at": "2025-12-05T10:00:00Z"
  }
]
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
  "id": "resource-1",
  "title": "Resource 1",
  "content": "..."
}
```

### Update Resource

```http
PUT /api/v1/workspaces/:workspaceId/playbooks/:playbookCode/resources/:resourceType/:resourceId
Content-Type: application/json

{
  "title": "Updated Title",
  "content": "Updated content"
}
```

### Delete Resource

```http
DELETE /api/v1/workspaces/:workspaceId/playbooks/:playbookCode/resources/:resourceType/:resourceId
```

## Storage

Resources are stored as JSON files:
```
{workspace_storage_path}/playbooks/{playbook_code}/resources/{resource_type}/{resource_id}.json
```

## Examples

### Yearly Book

```typescript
// List chapters
GET /api/v1/workspaces/123/playbooks/yearly_personal_book/resources/chapters

// Get chapter
GET /api/v1/workspaces/123/playbooks/yearly_personal_book/resources/chapters/chapter-01

// Create chapter
POST /api/v1/workspaces/123/playbooks/yearly_personal_book/resources/chapters
{
  "id": "chapter-01",
  "month": "January",
  "title": "Chapter 1",
  "content": "..."
}
```

### Course Writing

```typescript
// List lessons
GET /api/v1/workspaces/123/playbooks/course_writing/resources/lessons

// Get lesson
GET /api/v1/workspaces/123/playbooks/course_writing/resources/lessons/lesson-01
```

## Resource Types

Define your resource types in your playbook. Common patterns:
- `chapters`, `lessons`, `sections` - Content items
- `structure`, `outline` - Structure definitions
- `metadata`, `settings` - Configuration

---

**Status**: Framework ready, content to be expanded with more examples

