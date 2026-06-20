import { getApiBaseUrl } from '../../lib/api-url';
import { sharedGetFetch } from '../../lib/resilient-fetch';
import type { ExecutionSession, SystemStatus, Task, Workspace } from './types';

function getApiUrl() {
  return getApiBaseUrl();
}

export async function fetchWorkspaceSummary(
  workspaceId: string,
  signal: AbortSignal
): Promise<Workspace> {
  const url = `${getApiBaseUrl()}/api/v1/workspaces/${workspaceId}/summary`;

  let response: Response;
  try {
    response = await sharedGetFetch(url, {
      method: 'GET',
      signal,
      cache: 'no-store',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
    });
  } catch (fetchErr: any) {
    if (fetchErr.name === 'AbortError' || fetchErr.message?.includes('timeout')) {
      throw new Error('Request timeout - backend may be unreachable or slow to respond');
    }
    throw fetchErr;
  }

  if (!response.ok) {
    const errorText = response.status === 404
      ? 'Workspace not found'
      : `Failed to load workspace: ${response.status}`;
    throw new Error(errorText);
  }

  return await response.json();
}

export async function fetchWorkspaceDetails(
  workspaceId: string,
  signal: AbortSignal
): Promise<Workspace> {
  const response = await sharedGetFetch(
    `${getApiBaseUrl()}/api/v1/workspaces/${workspaceId}`,
    {
      method: 'GET',
      signal,
      cache: 'no-store',
      headers: {
        'Accept': 'application/json',
      },
    }
  );

  if (!response.ok) {
    throw new Error(`Failed to load workspace details: ${response.status}`);
  }

  return await response.json();
}

export async function fetchWorkspaceTasks(
  workspaceId: string,
  signal: AbortSignal
): Promise<Task[] | null> {
  const response = await sharedGetFetch(
    `${getApiUrl()}/api/v1/workspaces/${workspaceId}/tasks?limit=20&include_completed=true`,
    { method: 'GET', signal }
  );

  if (!response.ok) {
    if (response.status === 429) {
      console.warn('[WorkspaceDataContext] Rate limited, will retry later');
      return null;
    }
    throw new Error(`Failed to load tasks: ${response.status}`);
  }

  const data = await response.json();
  return data.tasks || [];
}

export async function fetchWorkspaceExecutions(
  workspaceId: string,
  signal: AbortSignal
): Promise<ExecutionSession[]> {
  const response = await sharedGetFetch(
    `${getApiUrl()}/api/v1/workspaces/${workspaceId}/tasks?limit=100&include_completed=true&task_type=execution`,
    { method: 'GET', signal }
  );

  if (!response.ok) {
    throw new Error(`Failed to load executions: ${response.status}`);
  }

  const data = await response.json();
  return (data.tasks || []).map((task: any) => ({
    execution_id: task.id,
    status: task.status,
    workspace_id: task.workspace_id,
    project_id: task.project_id,
    playbook_code: task.pack_id,
    created_at: task.created_at,
    started_at: task.started_at,
    completed_at: task.completed_at,
    current_step_index: 0,
    total_steps: 0,
    task,
    steps: []
  }));
}

export async function fetchWorkspaceHealth(
  workspaceId: string,
  signal: AbortSignal
): Promise<SystemStatus | null> {
  const response = await sharedGetFetch(
    `${getApiUrl()}/api/v1/workspaces/${workspaceId}/health`,
    { method: 'GET', signal },
    { dedupKey: `workspace-health:${workspaceId}` }
  );

  if (!response.ok) return null;

  const data = await response.json();
  return {
    llm_configured: data.llm_configured,
    llm_provider: data.llm_provider,
    vector_db_connected: data.vector_db_connected,
    tools: data.tools || {},
    critical_issues_count: data.issues?.filter((issue: any) => issue.severity === 'error')?.length || 0,
    has_issues: (data.issues?.length || 0) > 0
  };
}

export async function updateWorkspaceRequest(
  workspaceId: string,
  updates: Partial<Workspace>
): Promise<Workspace> {
  const response = await fetch(
    `${getApiUrl()}/api/v1/workspaces/${workspaceId}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates)
    }
  );

  if (!response.ok) {
    throw new Error(`Failed to update workspace: ${response.status}`);
  }

  return await response.json();
}
