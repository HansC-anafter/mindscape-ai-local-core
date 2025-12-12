# Storyline Tags API Documentation

> **Document Date**: 2025-12-12
> **Status**: Active
> **Version**: v1.0

---

## Overview

The `storyline_tags` field enables cross-project story tracking by allowing Intent, Task, and Execution objects to be tagged with storyline identifiers. This is particularly useful for brand workspaces to track brand storylines across multiple projects and executions.

---

## Field Definition

### IntentCard

**Field**: `storyline_tags: List[str]`

**Description**: List of storyline tags associated with this intent. Used to group related intents and executions by story theme.

**Example**:
```json
{
  "id": "intent-123",
  "title": "Q4 Campaign Launch",
  "storyline_tags": ["brand-storyline-1", "campaign-2024"]
}
```

### Task

**Field**: `storyline_tags: List[str]`

**Description**: Storyline tags inherited from the originating intent or manually assigned during task creation.

**Example**:
```json
{
  "id": "task-456",
  "workspace_id": "workspace-1",
  "storyline_tags": ["brand-storyline-1", "campaign-2024"]
}
```

### ExecutionSession

**Field**: `storyline_tags: List[str]`

**Description**: Storyline tags extracted from the underlying Task when creating an ExecutionSession view.

**Example**:
```json
{
  "execution_id": "exec-789",
  "workspace_id": "workspace-1",
  "storyline_tags": ["brand-storyline-1", "campaign-2024"]
}
```

---

## API Endpoints

### GET /api/v1/workspaces/{workspace_id}/intents

**Response includes**: `storyline_tags` field in each intent object.

**Example Response**:
```json
{
  "intents": [
    {
      "id": "intent-123",
      "title": "Q4 Campaign Launch",
      "storyline_tags": ["brand-storyline-1", "campaign-2024"],
      "status": "CONFIRMED"
    }
  ]
}
```

### GET /api/v1/workspaces/{workspace_id}/executions

**Response includes**: `storyline_tags` field in each execution object.

**Example Response**:
```json
{
  "executions": [
    {
      "execution_id": "exec-789",
      "workspace_id": "workspace-1",
      "storyline_tags": ["brand-storyline-1", "campaign-2024"],
      "status": "succeeded"
    }
  ]
}
```

### GET /api/v1/workspaces/{workspace_id}/executions-with-steps

**Response includes**: `storyline_tags` field in each execution object, including step details.

**Example Response**:
```json
{
  "executions": [
    {
      "execution_id": "exec-789",
      "workspace_id": "workspace-1",
      "storyline_tags": ["brand-storyline-1", "campaign-2024"],
      "steps": [...]
    }
  ]
}
```

### POST /api/v1/workspaces/{workspace_id}/intents

**Request Body**:
```json
{
  "title": "New Intent",
  "description": "Intent description",
  "storyline_tags": ["brand-storyline-1", "campaign-2024"]
}
```

### PUT /api/v1/workspaces/{workspace_id}/intents/{intent_id}

**Request Body**:
```json
{
  "title": "Updated Intent",
  "storyline_tags": ["brand-storyline-1", "campaign-2024", "new-tag"]
}
```

---

## Usage Examples

### Filtering Executions by Storyline

```python
# Get all executions for a specific storyline
executions = [
    exec for exec in all_executions
    if "brand-storyline-1" in exec.get("storyline_tags", [])
]
```

### Grouping Intents by Storyline

```python
# Group intents by storyline tag
storyline_groups = {}
for intent in intents:
    for tag in intent.get("storyline_tags", []):
        if tag not in storyline_groups:
            storyline_groups[tag] = []
        storyline_groups[tag].append(intent)
```

---

## Implementation Notes

- `storyline_tags` is stored as a JSON array in the database (SQLite TEXT column)
- Empty arrays `[]` are the default value if no tags are assigned
- Tags are case-sensitive and should follow a consistent naming convention
- Tags are inherited from Intent to Task to ExecutionSession automatically

---

**Last Updated**: 2025-12-12
**Maintainer**: Mindscape AI Development Team
