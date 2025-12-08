# Frontend API Reference

## PlaybookRegistry

**Location**: `@mindscape/ai-local-core/playbook`

**Methods**:
- `register(playbook: PlaybookPackage)`: Register a playbook
- `get(playbookCode: string)`: Get a playbook by code
- `getComponent(playbookCode, componentName)`: Get a component
- `list()`: List all registered playbooks

## useAPIClient

**Location**: `@mindscape/ai-local-core/hooks/useAPIClient`

**Usage**:
```typescript
const apiClient = useAPIClient();
const response = await apiClient.get('/api/v1/...');
```

**Methods**:
- `get(endpoint, options?)`: GET request
- `post(endpoint, data?, options?)`: POST request
- `put(endpoint, data?, options?)`: PUT request
- `patch(endpoint, data?, options?)`: PATCH request
- `delete(endpoint, options?)`: DELETE request

## useExecutionContext

**Location**: `@mindscape/ai-local-core/contexts/ExecutionContextContext`

**Usage**:
```typescript
const context = useExecutionContext();
// context.actor_id, context.workspace_id, context.tags
```

## Common Components

**Location**: `@mindscape/ai-local-core/components/playbooks/common`

### BinderView

Tree-like file browser view.

**Props**:
- `items: T[]` - Items to display
- `selectedId?: string` - Selected item ID
- `onSelect?: (item: T) => void` - Selection handler
- `onReorder?: (items: T[]) => void` - Reorder handler
- `getItemIcon?: (item: T) => ReactNode` - Icon renderer
- `getItemStatus?: (item: T) => string` - Status renderer
- `allowReorder?: boolean` - Enable drag-and-drop

### CorkboardView

Card view for items.

**Props**: Similar to BinderView

### OutlinerView

Table/outline view.

**Props**: Similar to BinderView, plus `columns` prop

---

**Status**: Framework ready, content to be expanded with full API documentation

