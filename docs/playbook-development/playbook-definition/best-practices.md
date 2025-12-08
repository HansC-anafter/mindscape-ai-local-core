# Best Practices

Guidelines for creating well-designed playbooks.

## Playbook Design

### 1. Clear Purpose

Each playbook should have a single, clear purpose.

✅ **Good**: "Organize monthly chapters from annual conversations"
❌ **Bad**: "Do everything related to writing"

### 2. Logical Step Flow

Steps should follow a logical sequence:

```json
{
  "steps": [
    { "id": "collect", ... },
    { "id": "process", "depends_on": ["collect"] },
    { "id": "generate", "depends_on": ["process"] }
  ]
}
```

### 3. Meaningful Step IDs

Use descriptive step IDs:

✅ **Good**: `"collect_annual_data"`, `"generate_monthly_chapters"`
❌ **Bad**: `"step1"`, `"step2"`

### 4. Clear Inputs/Outputs

Define clear inputs and outputs:

```json
{
  "inputs": {
    "user_request": {
      "type": "string",
      "description": "What the user wants to accomplish",
      "required": true
    }
  },
  "outputs": {
    "result": {
      "description": "The final result of the workflow",
      "source": "step.final_step.result"
    }
  }
}
```

## UI Design

### 1. Use Common Components

Prefer core common components over custom implementations:

✅ **Good**: Use `BinderView` for hierarchical lists
❌ **Bad**: Implement custom tree view from scratch

### 2. Responsive Design

Design for all screen sizes:

```typescript
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
  {/* Responsive grid */}
</div>
```

### 3. Dark Mode Support

Always support dark mode:

```typescript
<div className="bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100">
  {/* Content */}
</div>
```

### 4. Loading States

Show loading indicators:

```typescript
if (loading) {
  return <div>Loading...</div>;
}
```

### 5. Error Handling

Display error messages:

```typescript
if (error) {
  return <div className="text-red-500">{error}</div>;
}
```

## Backend Design

### 1. Use Generic API When Possible

Prefer generic resources API over custom handlers:

✅ **Good**: Use `/resources/chapters` for simple CRUD
❌ **Bad**: Create custom handler for simple operations

### 2. Create Handlers Only When Needed

Use handlers for:
- Complex business logic
- Cross-resource operations

### 3. Error Handling

Always handle errors gracefully:

```python
try:
    result = process_data()
    return result
except Exception as e:
    logger.error(f"Failed to process: {e}")
    raise HTTPException(status_code=500, detail=str(e))
```

### 4. Logging

Log important operations:

```python
logger.info(f"Processing chapter {chapter_id} for workspace {workspace_id}")
```

## Code Organization

### 1. Separate Concerns

- UI components in `components/`
- Backend handlers in `backend/`
- Types in separate files

### 2. Type Safety

Use TypeScript types:

```typescript
interface Chapter {
  id: string;
  title: string;
  content: string;
}
```

### 3. Reusable Code

Extract reusable functions:

```typescript
async function loadResource(apiClient, workspaceId, playbookCode, resourceType) {
  // Reusable loading logic
}
```

## Testing

### 1. Test Locally

Test your playbook locally before publishing:

```bash
npm install ./my-playbook
# Test in Mindscape AI
```

### 2. Validate JSON

Validate playbook JSON before publishing:

```bash
# Use JSON schema validator
```

## Documentation

### 1. README

Include a comprehensive README:

- Overview
- Features
- Installation
- Usage
- Development

### 2. Code Comments

Comment complex logic:

```typescript
// Extract key points from content
const keyPoints = await extractKeyPoints(content);
```

## Versioning

### 1. Semantic Versioning

Follow semantic versioning:
- `1.0.0` - Initial release
- `1.1.0` - New features
- `1.1.1` - Bug fixes

### 2. Breaking Changes

Increment major version for breaking changes:
- `1.x.x` → `2.0.0` - Breaking changes

---

**Status**: Content completed with best practices

