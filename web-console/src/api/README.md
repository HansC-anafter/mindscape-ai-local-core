# Mindscape API Client

Unified API client that automatically handles differences between Local and Cloud environments.

## Usage

### In Playbook Components

```tsx
import { useAPIClient } from '@/hooks/useAPIClient';

export function MyPlaybookComponent({ workspaceId }: { workspaceId: string }) {
  const apiClient = useAPIClient();

  useEffect(() => {
    async function loadData() {
      const response = await apiClient.get(
        `/api/v1/workspaces/${workspaceId}/books/current`
      );
      if (response.ok) {
        const data = await response.json();
      }
    }

    loadData();
  }, [workspaceId, apiClient]);

  const handleSave = async (data: any) => {
    const response = await apiClient.post(
      `/api/v1/workspaces/${workspaceId}/books`,
      data
    );
    if (response.ok) {
      // Handle success
    }
  };

  const handleUpdate = async (id: string, data: any) => {
    const response = await apiClient.put(
      `/api/v1/workspaces/${workspaceId}/books/${id}`,
      data
    );
    if (response.ok) {
      // Handle success
    }
  };

  const handleDelete = async (id: string) => {
    const response = await apiClient.delete(
      `/api/v1/workspaces/${workspaceId}/books/${id}`
    );
    if (response.ok) {
      // Handle success
    }
  };

  return (
    // Component JSX
  );
}
```

## Automatic Handling

### Local Mode
- Uses `NEXT_PUBLIC_API_URL` environment variable (default: `http://localhost:8000`)
- No authentication headers

### Cloud Mode
- Uses `NEXT_PUBLIC_CLOUD_API_URL` or `NEXT_PUBLIC_API_URL`
- Automatically adds `Authorization: Bearer <token>` header
- Automatically adds `X-Tenant-ID` header (if present)
- Automatically adds `X-Group-ID` header (if present)

## Best Practices

### Do
- Use `useAPIClient()` hook to get API client
- Use relative paths (`/api/v1/...`), do not hardcode full URLs
- Let API client automatically handle Local/Cloud differences

### Don't
- Do not directly call `fetch`
- Do not hardcode API endpoints (e.g., `http://localhost:8000`)
- Do not directly read `context.tags.tenant_id`

## Environment Variables

### Local Mode
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Cloud Mode
```bash
NEXT_PUBLIC_CLOUD_API_URL=https://api.mindscape.ai
# or
NEXT_PUBLIC_API_URL=https://api.mindscape.ai
```

## Implementation Details

### ExecutionContext
- `actor_id`: Actor ID (Local: "local-user", Cloud: user ID)
- `workspace_id`: Workspace ID
- `tags`: Additional context (Local: `{ mode: "local" }`, Cloud: `{ mode: "cloud", tenant_id: "...", group_id: "..." }`)

### API Client Behavior
1. Determines API URL based on `ExecutionContext.tags.mode`
2. Automatically adds authentication and tenant headers in Cloud mode
3. All requests automatically include `Content-Type: application/json`
