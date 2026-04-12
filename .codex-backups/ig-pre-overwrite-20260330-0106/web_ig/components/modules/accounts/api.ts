import { MindscapeAPIClient } from '@/api/client';

export type ExecutionBackendHint = 'auto' | 'runner';

function sanitizeExecutionBackendHint(rawValue: string): ExecutionBackendHint {
  const raw = (rawValue || '').trim().toLowerCase();
  if (raw === 'runner') return 'runner';
  return 'auto';
}

export function getExecutionBackendHint(workspaceId: string): ExecutionBackendHint {
  if (typeof window === 'undefined') return 'auto';
  try {
    const key = `ig.following_analyzer.execution_backend:${workspaceId}`;
    const raw = window.localStorage.getItem(key) || '';
    const hint = sanitizeExecutionBackendHint(raw);
    if (raw && hint === 'auto' && raw.trim().toLowerCase() !== 'auto') {
      window.localStorage.setItem(key, hint);
    }
    return hint;
  } catch {
    // ignore
  }
  return 'auto';
}

export function applyExecutionBackendHint(
  params: URLSearchParams,
  workspaceId: string,
  override?: ExecutionBackendHint
): URLSearchParams {
  const hint = (override || getExecutionBackendHint(workspaceId) || 'auto').trim();
  params.set('execution_backend', hint);
  return params;
}

export function buildBrowserProfileStatusUrl(
  apiUrl: string,
  params: { profilePath?: string; profileName?: string }
): string {
  const profilePath = (params.profilePath || '').trim();
  if (profilePath) {
    return `${apiUrl}/api/v1/ig/browser-profile-status?profile_path=${encodeURIComponent(profilePath)}`;
  }

  const profileName = (params.profileName || '').trim() || 'default';
  return `${apiUrl}/api/v1/ig/browser-profile-status?profile_name=${encodeURIComponent(profileName)}`;
}

export async function fetchBrowserProfileStatus(
  client: MindscapeAPIClient,
  params: { profilePath?: string; profileName?: string }
): Promise<Response> {
  const profilePath = (params.profilePath || '').trim();
  if (profilePath) {
    return client.get(`/api/v1/ig/browser-profile-status?profile_path=${encodeURIComponent(profilePath)}`);
  }
  const profileName = (params.profileName || '').trim() || 'default';
  return client.get(`/api/v1/ig/browser-profile-status?profile_name=${encodeURIComponent(profileName)}`);
}

export async function fetchBrowserProfiles(
  client: MindscapeAPIClient
): Promise<Response> {
  return client.get('/api/v1/ig/browser-profiles');
}

export async function fetchSiteHubInstagramChannels(
  client: MindscapeAPIClient,
  workspaceId: string
): Promise<Response> {
  // Channel bindings managed by mindscape_cloud_integration capability pack
  return client.get(
    `/api/v1/capabilities/mindscape_cloud_integration/channel-bindings?workspace_id=${workspaceId}`
  );
}

export async function fetchWorkspaceArtifacts(
  client: MindscapeAPIClient,
  workspaceId: string,
  query: Record<string, string | number | boolean | undefined>
): Promise<Response> {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value === undefined) return;
    params.set(key, String(value));
  });
  return client.get(`/api/v1/workspaces/${workspaceId}/artifacts?${params.toString()}`);
}

export async function executeWorkspacePlaybook(
  client: MindscapeAPIClient,
  workspaceId: string,
  payload: unknown
): Promise<Response> {
  return client.post(`/api/v1/workspaces/${workspaceId}/playbooks/execute`, payload);
}

export async function executePlaybookStart(
  client: MindscapeAPIClient,
  params: URLSearchParams,
  payload: unknown
): Promise<Response> {
  return client.post(`/api/v1/playbooks/execute/start?${params.toString()}`, payload);
}

export async function fetchTargets(
  client: MindscapeAPIClient,
  query: {
    workspace_id: string;
    seed?: string;
    source_handle?: string;
    search?: string;
    handle?: string;
    limit?: number;
    offset?: number;
    request_key?: string;
    signal?: AbortSignal;
  }
): Promise<Response> {
  const params = new URLSearchParams();
  params.set('workspace_id', query.workspace_id);
  if (query.seed) params.set('seed', query.seed);
  if (query.source_handle) params.set('source_handle', query.source_handle);
  if (query.search) params.set('search', query.search);
  if (query.handle) params.set('handle', query.handle);
  if (query.limit !== undefined) params.set('limit', String(query.limit));
  if (query.offset !== undefined) params.set('offset', String(query.offset));
  if (query.request_key) params.set('_request_key', query.request_key);
  return client.get(`/api/v1/ig/insights/targets?${params.toString()}`, {
    signal: query.signal,
  });
}
