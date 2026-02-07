/**
 * Execution Graph API Hook
 *
 * Fetches graph data from the /api/v1/execution-graph endpoint
 * which uses the "derived graph + overlay" architecture.
 */

import useSWR from 'swr';
import { getApiBaseUrl } from './api-url';

const API_BASE = getApiBaseUrl();

// ============================================================================
// Types matching backend MindscapeGraph response
// ============================================================================

export type NodeType = 'intent' | 'execution' | 'artifact' | 'playbook' | 'step';
export type NodeStatus = 'suggested' | 'accepted' | 'rejected';
export type EdgeType = 'temporal' | 'causal' | 'dependency' | 'spawns' | 'produces' | 'refers_to';
export type EdgeOrigin = 'derived' | 'user';

export interface MindscapeNode {
    id: string;
    type: NodeType;
    label: string;
    status: NodeStatus;
    metadata: Record<string, any>;
    created_at: string;
}

export interface MindscapeEdge {
    id: string;
    from_id: string;
    to_id: string;
    type: EdgeType;
    origin: EdgeOrigin;
    confidence: number;
    status: NodeStatus;
    metadata: Record<string, any>;
}

export interface GraphOverlay {
    node_positions: Record<string, { x: number; y: number; scale?: number }>;
    collapsed_state: Record<string, boolean>;
    viewport?: { x: number; y: number; zoom: number };
    version: number;
}

export interface MindscapeGraphResponse {
    nodes: MindscapeNode[];
    edges: MindscapeEdge[];
    overlay: GraphOverlay;
    scope_type: 'workspace' | 'workspace_group';
    scope_id: string;
    derived_at: string;
}

// ============================================================================
// Fetcher
// ============================================================================

const fetcher = async (url: string): Promise<MindscapeGraphResponse> => {
    const res = await fetch(url);
    if (!res.ok) {
        const errorText = await res.text().catch(() => 'Unknown error');
        console.error('[useMindscapeGraph] Fetch error:', res.status, errorText);
        throw new Error(`Failed to fetch mindscape graph: ${res.status}`);
    }
    return res.json();
};

// ============================================================================
// Hook
// ============================================================================

export interface UseMindscapeGraphOptions {
    workspaceId?: string;
    workspaceGroupId?: string;
    enabled?: boolean;
}

export function useMindscapeGraph(options: UseMindscapeGraphOptions = {}) {
    const { workspaceId, workspaceGroupId, enabled = true } = options;

    // Build URL with query params
    const queryParams = new URLSearchParams();
    if (workspaceId) {
        queryParams.append('workspace_id', workspaceId);
    } else if (workspaceGroupId) {
        queryParams.append('workspace_group_id', workspaceGroupId);
    }

    // Use the /api/v1/execution-graph endpoint for workspace execution visualization
    const url = enabled && (workspaceId || workspaceGroupId)
        ? `${API_BASE}/api/v1/execution-graph/graph?${queryParams.toString()}`
        : null;

    const { data, error, isLoading, mutate } = useSWR<MindscapeGraphResponse>(
        url,
        fetcher,
        {
            revalidateOnFocus: false,
            dedupingInterval: 5000,
        }
    );

    return {
        graph: data,
        nodes: data?.nodes ?? [],
        edges: data?.edges ?? [],
        overlay: data?.overlay,
        isLoading,
        isError: !!error,
        error,
        refresh: mutate,
    };
}

export default useMindscapeGraph;


// ============================================================================
// Playbook DAG Types and Hook
// ============================================================================

export interface PlaybookStep {
    id: string;
    tool?: string;
    tool_slot?: string;
    depends_on: string[];
    has_gate: boolean;
    gate_type?: string;
}

export interface PlaybookDAGResponse {
    playbook_code: string;
    name: string;
    description?: string;
    steps: PlaybookStep[];
    inputs: Record<string, any>;
    outputs: Record<string, any>;
}

const playbookFetcher = async (url: string): Promise<PlaybookDAGResponse> => {
    const res = await fetch(url);
    if (!res.ok) {
        const errorText = await res.text().catch(() => 'Unknown error');
        console.error('[usePlaybookDAG] Fetch error:', res.status, errorText);
        throw new Error(`Failed to fetch playbook DAG: ${res.status}`);
    }
    return res.json();
};

export function usePlaybookDAG(playbookCode?: string) {
    const url = playbookCode
        ? `${API_BASE}/api/v1/execution-graph/playbook/${encodeURIComponent(playbookCode)}`
        : null;

    const { data, error, isLoading, mutate } = useSWR<PlaybookDAGResponse>(
        url,
        playbookFetcher,
        {
            revalidateOnFocus: false,
            dedupingInterval: 10000,
        }
    );

    return {
        playbook: data,
        steps: data?.steps ?? [],
        isLoading,
        isError: !!error,
        error,
        refresh: mutate,
    };
}

