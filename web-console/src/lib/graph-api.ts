/**
 * Graph API client for Mind-Lens Graph feature
 * Uses SWR for data fetching and caching
 */

import useSWR from 'swr';
import { getApiBaseUrl } from './api-url';

const API_BASE = getApiBaseUrl();

const fetcher = async (url: string) => {
  console.log('[fetcher] Fetching URL:', url);
  const res = await fetch(url);
  console.log('[fetcher] Response status:', res.status, res.statusText);
  if (!res.ok) {
    const errorText = await res.text().catch(() => 'Unknown error');
    console.error('[fetcher] Error response:', errorText);
    const error = new Error(`Failed to fetch: ${res.status} ${res.statusText}`);
    (error as any).status = res.status;
    (error as any).response = errorText;
    throw error;
  }
  const data = await res.json();
  console.log('[fetcher] Response data:', data);
  return data;
};

// ============================================================================
// Types
// ============================================================================

export interface GraphNode {
  id: string;
  profile_id: string;
  category: 'direction' | 'action';
  node_type: 'value' | 'worldview' | 'aesthetic' | 'knowledge' | 'strategy' | 'role' | 'rhythm';
  label: string;
  description?: string;
  content?: string;
  icon?: string;
  color?: string;
  size: number;
  is_active: boolean;
  confidence: number;
  source_type?: string;
  source_id?: string;
  metadata: Record<string, any>;
  created_at: string;
  updated_at: string;
  linked_entity_ids: string[];
  linked_playbook_codes: string[];
  linked_intent_ids: string[];
}

export interface GraphEdge {
  id: string;
  profile_id: string;
  source_node_id: string;
  target_node_id: string;
  relation_type: 'supports' | 'conflicts' | 'depends_on' | 'related_to' | 'derived_from' | 'applied_to';
  weight: number;
  label?: string;
  is_active: boolean;
  metadata: Record<string, any>;
  created_at: string;
}

export interface GraphNodeCreate {
  category: 'direction' | 'action';
  node_type: 'value' | 'worldview' | 'aesthetic' | 'knowledge' | 'strategy' | 'role' | 'rhythm';
  label: string;
  description?: string;
  content?: string;
  icon?: string;
  color?: string;
  size?: number;
  is_active?: boolean;
  confidence?: number;
  source_type?: string;
  source_id?: string;
  metadata?: Record<string, any>;
}

export interface GraphNodeUpdate {
  label?: string;
  description?: string;
  content?: string;
  icon?: string;
  color?: string;
  size?: number;
  is_active?: boolean;
  confidence?: number;
  metadata?: Record<string, any>;
}

export interface GraphEdgeCreate {
  source_node_id: string;
  target_node_id: string;
  relation_type: 'supports' | 'conflicts' | 'depends_on' | 'related_to' | 'derived_from' | 'applied_to';
  weight?: number;
  label?: string;
  is_active?: boolean;
  metadata?: Record<string, any>;
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

export interface MindLensProfileCreate {
  name: string;
  description?: string;
  is_default?: boolean;
  active_node_ids?: string[];
}

export interface ProfileSummary {
  direction: {
    values: Array<{ id: string; label: string; icon: string }>;
    worldviews: Array<{ id: string; label: string; icon: string }>;
    aesthetics: Array<{ id: string; label: string; icon: string }>;
    knowledge_count: number;
  };
  action: {
    strategies: Array<{ id: string; label: string; icon: string }>;
    roles: Array<{ id: string; label: string; icon: string }>;
    rhythms: Array<{ id: string; label: string; icon: string }>;
  };
  summary_text: {
    direction: string;
    action: string;
  };
}

// ============================================================================
// Hooks
// ============================================================================

export function useGraphNodes(params?: {
  category?: 'direction' | 'action';
  node_type?: string;
  is_active?: boolean;
}) {
  const queryParams = new URLSearchParams();
  if (params?.category) queryParams.append('category', params.category);
  if (params?.node_type) queryParams.append('node_type', params.node_type);
  if (params?.is_active !== undefined) queryParams.append('is_active', String(params.is_active));

  const url = `${API_BASE}/api/v1/mind-lens/graph/nodes${queryParams.toString() ? `?${queryParams.toString()}` : ''}`;

  const { data, error, isLoading, mutate } = useSWR<GraphNode[]>(url, fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 5000,
  });

  return {
    nodes: data ?? [],
    isLoading,
    isError: !!error,
    error,
    refresh: mutate,
  };
}

export function useGraphEdges(params?: {
  source_node_id?: string;
  target_node_id?: string;
  relation_type?: string;
}) {
  const queryParams = new URLSearchParams();
  if (params?.source_node_id) queryParams.append('source_node_id', params.source_node_id);
  if (params?.target_node_id) queryParams.append('target_node_id', params.target_node_id);
  if (params?.relation_type) queryParams.append('relation_type', params.relation_type);

  const url = `${API_BASE}/api/v1/mind-lens/graph/edges${queryParams.toString() ? `?${queryParams.toString()}` : ''}`;

  const { data, error, isLoading, mutate } = useSWR<GraphEdge[]>(url, fetcher);

  return {
    edges: data ?? [],
    isLoading,
    isError: !!error,
    error,
    refresh: mutate,
  };
}

export function useFullGraph(workspaceId?: string) {
  const queryParams = new URLSearchParams();
  queryParams.append('profile_id', 'default-user'); // Add profile_id for v0 MVP
  if (workspaceId) queryParams.append('workspace_id', workspaceId);

  const url = `${API_BASE}/api/v1/mind-lens/graph/full?${queryParams.toString()}`;

  const { data, error, isLoading, mutate } = useSWR<{ nodes: GraphNode[]; edges: GraphEdge[] }>(url, fetcher);

  // Debug logging
  console.log('[useFullGraph] URL:', url);
  console.log('[useFullGraph] Data:', data);
  console.log('[useFullGraph] Error:', error);
  console.log('[useFullGraph] IsLoading:', isLoading);
  console.log('[useFullGraph] Nodes count:', data?.nodes?.length ?? 0);
  console.log('[useFullGraph] Edges count:', data?.edges?.length ?? 0);

  return {
    nodes: data?.nodes ?? [],
    edges: data?.edges ?? [],
    isLoading,
    isError: !!error,
    error,
    refresh: mutate,
  };
}

export function useActiveLens(workspaceId?: string) {
  const queryParams = new URLSearchParams();
  if (workspaceId) queryParams.append('workspace_id', workspaceId);

  const url = `${API_BASE}/api/v1/mind-lens/graph/lens/active${queryParams.toString() ? `?${queryParams.toString()}` : ''}`;

  const { data, error, isLoading, mutate } = useSWR<MindLensProfile | null>(url, fetcher);

  return {
    lens: data,
    isLoading,
    isError: !!error,
    error,
    refresh: mutate,
  };
}

export function useProfileSummary() {
  const url = `${API_BASE}/api/v1/mind-lens/graph/profile-summary`;

  const { data, error, isLoading, mutate } = useSWR<ProfileSummary>(url, fetcher);

  return {
    summary: data,
    isLoading,
    isError: !!error,
    error,
    refresh: mutate,
  };
}

// ============================================================================
// Mutations
// ============================================================================

export async function createNode(node: GraphNodeCreate): Promise<GraphNode> {
  const res = await fetch(`${API_BASE}/api/v1/mind-lens/graph/nodes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(node),
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to create node' }));
    throw new Error(error.detail || 'Failed to create node');
  }

  return res.json();
}

export async function updateNode(nodeId: string, updates: GraphNodeUpdate): Promise<GraphNode> {
  const res = await fetch(`${API_BASE}/api/v1/mind-lens/graph/nodes/${nodeId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to update node' }));
    throw new Error(error.detail || 'Failed to update node');
  }

  return res.json();
}

export async function deleteNode(nodeId: string, cascade: boolean = false): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/mind-lens/graph/nodes/${nodeId}?cascade=${cascade}`, {
    method: 'DELETE',
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to delete node' }));
    throw new Error(error.detail || 'Failed to delete node');
  }
}

export async function createEdge(edge: GraphEdgeCreate): Promise<GraphEdge> {
  const res = await fetch(`${API_BASE}/api/v1/mind-lens/graph/edges`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(edge),
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to create edge' }));
    throw new Error(error.detail || 'Failed to create edge');
  }

  return res.json();
}

export async function deleteEdge(edgeId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/mind-lens/graph/edges/${edgeId}`, {
    method: 'DELETE',
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to delete edge' }));
    throw new Error(error.detail || 'Failed to delete edge');
  }
}

// ============================================================================
// Playbook Links
// ============================================================================

export async function linkNodeToPlaybook(
  nodeId: string,
  playbookCode: string,
  linkType: string = 'applies',
): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/v1/mind-lens/graph/nodes/${nodeId}/link-playbook`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        playbook_code: playbookCode,
        link_type: linkType,
      }),
    }
  );

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to link playbook' }));
    throw new Error(error.detail || 'Failed to link playbook');
  }
}

export async function unlinkNodeFromPlaybook(nodeId: string, playbookCode: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/v1/mind-lens/graph/nodes/${nodeId}/link-playbook/${playbookCode}`,
    {
      method: 'DELETE',
    }
  );

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to unlink playbook' }));
    throw new Error(error.detail || 'Failed to unlink playbook');
  }
}

// ============================================================================
// Workspace Bindings
// ============================================================================

export async function bindLensToWorkspace(lensId: string, workspaceId: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/v1/mind-lens/graph/lens/bind-workspace?lens_id=${lensId}&workspace_id=${workspaceId}`,
    {
      method: 'POST',
    }
  );

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to bind lens to workspace' }));
    throw new Error(error.detail || 'Failed to bind lens to workspace');
  }
}

export async function unbindLensFromWorkspace(workspaceId: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/v1/mind-lens/graph/lens/unbind-workspace/${workspaceId}`,
    {
      method: 'DELETE',
    }
  );

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to unbind lens from workspace' }));
    throw new Error(error.detail || 'Failed to unbind lens from workspace');
  }
}

export async function createLensProfile(lens: MindLensProfileCreate): Promise<MindLensProfile> {
  const res = await fetch(`${API_BASE}/api/v1/mind-lens/graph/lens/profiles`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(lens),
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to create lens profile' }));
    throw new Error(error.detail || 'Failed to create lens profile');
  }

  return res.json();
}

export async function initializeGraph(): Promise<{ message: string; node_count: number; nodes: Array<{ id: string; label: string }> }> {
  const res = await fetch(`${API_BASE}/api/v1/mind-lens/graph/initialize`, {
    method: 'POST',
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to initialize graph' }));
    throw new Error(error.detail || 'Failed to initialize graph');
  }
  return res.json();
}

