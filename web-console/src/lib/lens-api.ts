/**
 * Lens API client for Mind-Lens unified implementation
 * Uses SWR for data fetching and caching
 */

import useSWR from 'swr';
import { getApiBaseUrl } from './api-url';

const API_BASE = getApiBaseUrl();

const fetcher = async (url: string) => {
  const res = await fetch(url);
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to fetch' }));
    throw new Error(error.detail || `Failed to fetch: ${res.status}`);
  }
  return res.json();
};

// ============================================================================
// Types
// ============================================================================

export type LensNodeState = 'off' | 'keep' | 'emphasize';

export interface LensNode {
  node_id: string;
  node_label: string;
  node_type: string;
  category: string;
  state: LensNodeState;
  weight: number;
  effective_scope: 'global' | 'workspace' | 'session';
  is_overridden: boolean;
  overridden_from?: 'global' | 'workspace';
}

export interface EffectiveLens {
  profile_id: string;
  workspace_id?: string;
  session_id?: string;
  nodes: LensNode[];
  global_preset_id: string;
  global_preset_name: string;
  workspace_override_count: number;
  session_override_count: number;
  hash: string;
  computed_at: string;
}

export interface NodeStateChange {
  node_id: string;
  node_label: string;
  node_type: string;
  category: string;
  from_state: LensNodeState;
  to_state: LensNodeState;
  change_type: 'strengthened' | 'weakened' | 'disabled' | 'enabled' | 'changed';
}

export interface PresetDiff {
  preset_a_id: string;
  preset_a_name: string;
  preset_b_id: string;
  preset_b_name: string;
  changes: NodeStateChange[];
  strengthened_count?: number;
  weakened_count?: number;
  disabled_count?: number;
  enabled_count?: number;
  // Computed properties from backend

}

export interface ChangeSet {
  id: string;
  profile_id: string;
  session_id: string;
  workspace_id?: string;
  changes: NodeChange[];
  summary: string;
  created_at: string;
}

export interface NodeChange {
  node_id: string;
  node_label: string;
  from_state: LensNodeState;
  to_state: LensNodeState;
}

export interface PreviewResult {
  base_output: string;
  lens_output: string;
  diff_summary: string;
  triggered_nodes: Array<{
    node_id: string;
    node_label: string;
    state: LensNodeState;
    effective_scope: string;
  }>;
}

export interface LensReceipt {
  id: string;
  execution_id: string;
  workspace_id: string;
  effective_lens_hash: string;
  triggered_nodes: Array<{
    node_id: string;
    node_label: string;
    state: LensNodeState;
    effective_scope: string;
    contribution?: string;
  }>;
  base_output?: string;
  lens_output?: string;
  diff_summary?: string;
  created_at: string;
}

export interface MindLensProfile {
  id: string;
  profile_id: string;
  name: string;
  description?: string;
  is_default: boolean;
  active_node_ids: string[];
  linked_workspace_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface DriftReport {
  profile_id: string;
  days: number;
  total_executions: number;
  node_drift: Array<{
    node_id: string;
    node_label: string;
    trigger_count: number;
    trigger_rate: number;
    trend: 'increasing' | 'decreasing' | 'stable';
  }>;
  created_at: string;
}

// ============================================================================
// Hooks
// ============================================================================

export function useEffectiveLens(params?: {
  profile_id: string;
  workspace_id?: string;
  session_id?: string;
}) {
  if (!params?.profile_id) {
    return {
      lens: null,
      isLoading: false,
      isError: false,
      error: null,
      refresh: () => { },
    };
  }

  const queryParams = new URLSearchParams();
  queryParams.append('profile_id', params.profile_id);
  if (params.workspace_id) queryParams.append('workspace_id', params.workspace_id);
  if (params.session_id) queryParams.append('session_id', params.session_id);

  const url = `${API_BASE}/api/v1/mindscape/lens/effective-lens?${queryParams.toString()}`;

  const { data, error, isLoading, mutate } = useSWR<EffectiveLens>(url, fetcher);

  return {
    lens: data ?? null,
    isLoading,
    isError: !!error,
    error,
    refresh: mutate,
  };
}

export function useLensProfiles(profileId: string) {
  const url = `${API_BASE}/api/v1/mind-lens/graph/lens/profiles?profile_id=${profileId}`;

  const { data, error, isLoading, mutate } = useSWR<MindLensProfile[]>(url, fetcher);

  return {
    profiles: data ?? [],
    isLoading,
    isError: !!error,
    error,
    refresh: mutate,
  };
}

export function useWorkspaceOverrides(workspaceId: string) {
  const url = `${API_BASE}/api/v1/mindscape/lens/workspaces/${workspaceId}/lens-overrides`;

  const { data, error, isLoading, mutate } = useSWR<any[]>(url, fetcher);

  return {
    overrides: data ?? [],
    isLoading,
    isError: !!error,
    error,
    refresh: mutate,
  };
}

export function useSessionOverrides(sessionId: string) {
  const url = `${API_BASE}/api/v1/mindscape/lens/session/${sessionId}/overrides`;

  const { data, error, isLoading, mutate } = useSWR<{ overrides: Record<string, LensNodeState> }>(url, fetcher);

  return {
    overrides: data?.overrides ?? {},
    isLoading,
    isError: !!error,
    error,
    refresh: mutate,
  };
}

export function useLensReceipt(executionId: string) {
  const url = `${API_BASE}/api/v1/mindscape/lens/receipts/${executionId}`;

  const { data, error, isLoading, mutate } = useSWR<LensReceipt>(url, fetcher);

  return {
    receipt: data ?? null,
    isLoading,
    isError: !!error,
    error,
    refresh: mutate,
  };
}

// ============================================================================
// Mutations
// ============================================================================

export async function setWorkspaceOverride(
  workspaceId: string,
  nodeId: string,
  state: LensNodeState
): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/v1/mindscape/lens/workspaces/${workspaceId}/lens-overrides/${nodeId}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state }),
    }
  );

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to set workspace override' }));
    throw new Error(error.detail || 'Failed to set workspace override');
  }
}

export async function removeWorkspaceOverride(workspaceId: string, nodeId: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/v1/mindscape/lens/workspaces/${workspaceId}/lens-overrides/${nodeId}`,
    {
      method: 'DELETE',
    }
  );

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to remove workspace override' }));
    throw new Error(error.detail || 'Failed to remove workspace override');
  }
}

export async function setSessionOverride(
  sessionId: string,
  nodeId: string,
  state: LensNodeState
): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/v1/mindscape/lens/session/${sessionId}/overrides/${nodeId}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state }),
    }
  );

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to set session override' }));
    throw new Error(error.detail || 'Failed to set session override');
  }
}

export async function clearSessionOverrides(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/mindscape/lens/session/${sessionId}/overrides`, {
    method: 'DELETE',
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to clear session overrides' }));
    throw new Error(error.detail || 'Failed to clear session overrides');
  }
}

export async function createChangeSet(params: {
  profile_id: string;
  session_id: string;
  workspace_id?: string;
}): Promise<ChangeSet> {
  const res = await fetch(`${API_BASE}/api/v1/mindscape/lens/changesets`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to create changeset' }));
    throw new Error(error.detail || 'Failed to create changeset');
  }

  return res.json();
}

export async function applyChangeSet(
  changeset: ChangeSet,
  applyTo: 'session_only' | 'workspace' | 'preset',
  targetWorkspaceId?: string
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/mindscape/lens/changesets/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      changeset,
      apply_to: applyTo,
      target_workspace_id: targetWorkspaceId,
    }),
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to apply changeset' }));
    throw new Error(error.detail || 'Failed to apply changeset');
  }
}

export async function createPresetSnapshot(params: {
  profile_id: string;
  name: string;
  workspace_id?: string;
  session_id?: string;
  description?: string;
}): Promise<MindLensProfile> {
  const res = await fetch(`${API_BASE}/api/v1/mindscape/lens/profiles/snapshot`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to create preset snapshot' }));
    throw new Error(error.detail || 'Failed to create preset snapshot');
  }

  return res.json();
}

export async function generatePreview(params: {
  profile_id: string;
  input_text: string;
  preview_type?: string;
  workspace_id?: string;
  session_id?: string;
}): Promise<PreviewResult> {
  const queryParams = new URLSearchParams();
  queryParams.append('profile_id', params.profile_id);

  const res = await fetch(`${API_BASE}/api/v1/mindscape/lens/preview?${queryParams.toString()}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      input_text: params.input_text,
      preview_type: params.preview_type || 'rewrite',
      workspace_id: params.workspace_id,
      session_id: params.session_id,
    }),
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to generate preview' }));
    throw new Error(error.detail || 'Failed to generate preview');
  }

  return res.json();
}

export function useDriftReport(profileId: string, days: number = 30) {
  const { data, error, isLoading, mutate } = useSWR<DriftReport>(
    profileId ? `${API_BASE}/api/v1/mindscape/lens/evidence/drift?profile_id=${profileId}&days=${days}` : null,
    fetcher,
    { revalidateOnFocus: false }
  );

  return {
    driftReport: data || null,
    isLoading,
    isError: !!error,
    refresh: mutate,
  };
}
