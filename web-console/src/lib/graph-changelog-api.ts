/**
 * Mindscape Graph Changelog API Hook
 *
 * Provides hooks for managing pending changes, changelog history,
 * and graph version control operations.
 */

import useSWR from 'swr';
import { getApiBaseUrl } from './api-url';

const API_BASE = getApiBaseUrl();

// ============================================================================
// Types
// ============================================================================

export interface PendingChange {
    id: string;
    workspace_id: string;
    version: number;
    operation: 'create_node' | 'update_node' | 'delete_node' | 'create_edge' | 'delete_edge' | 'update_overlay';
    target_type: 'node' | 'edge' | 'overlay';
    target_id: string;
    before_state?: Record<string, any>;
    after_state: Record<string, any>;
    actor: 'user' | 'llm' | 'system' | 'playbook';
    actor_context?: string;
    status: 'pending' | 'applied' | 'rejected' | 'undone';
    created_at?: string;
}

export interface PendingChangesResponse {
    success: boolean;
    workspace_id: string;
    total_pending: number;
    changes: PendingChange[];
}

export interface HistoryEntry {
    id: string;
    workspace_id: string;
    version: number;
    operation: string;
    target_type: string;
    target_id: string;
    actor: string;
    status: string;
    created_at?: string;
    applied_at?: string;
    applied_by?: string;
}

export interface HistoryResponse {
    success: boolean;
    workspace_id: string;
    current_version: number;
    total_entries: number;
    history: HistoryEntry[];
}

export interface ApproveResult {
    change_id: string;
    action: 'approve' | 'reject';
    success: boolean;
    error?: string;
}

export interface ApproveResponse {
    success: boolean;
    processed: number;
    success_count: number;
    error_count: number;
    results: ApproveResult[];
}

// ============================================================================
// Fetchers
// ============================================================================

const pendingFetcher = async (url: string): Promise<PendingChangesResponse> => {
    const res = await fetch(url);
    if (!res.ok) {
        const errorText = await res.text().catch(() => 'Unknown error');
        console.error('[usePendingChanges] Fetch error:', res.status, errorText);
        throw new Error(`Failed to fetch pending changes: ${res.status}`);
    }
    return res.json();
};

const historyFetcher = async (url: string): Promise<HistoryResponse> => {
    const res = await fetch(url);
    if (!res.ok) {
        const errorText = await res.text().catch(() => 'Unknown error');
        console.error('[useGraphHistory] Fetch error:', res.status, errorText);
        throw new Error(`Failed to fetch graph history: ${res.status}`);
    }
    return res.json();
};

// ============================================================================
// Hooks
// ============================================================================

export interface UsePendingChangesOptions {
    workspaceId?: string;
    actorFilter?: 'llm' | 'user' | 'system' | 'playbook';
    enabled?: boolean;
}

/**
 * Hook for fetching pending changes for a workspace
 */
export function usePendingChanges(options: UsePendingChangesOptions = {}) {
    const { workspaceId, actorFilter, enabled = true } = options;

    const queryParams = new URLSearchParams();
    if (actorFilter) {
        queryParams.append('actor_filter', actorFilter);
    }

    const url = enabled && workspaceId
        ? `${API_BASE}/api/v1/execution-graph/changelog/pending/${workspaceId}?${queryParams.toString()}`
        : null;

    const { data, error, isLoading, mutate } = useSWR<PendingChangesResponse>(
        url,
        pendingFetcher,
        {
            revalidateOnFocus: true,
            dedupingInterval: 2000,
            refreshInterval: 5000, // Poll every 5 seconds for pending changes
        }
    );

    return {
        pendingChanges: data?.changes ?? [],
        totalPending: data?.total_pending ?? 0,
        isLoading,
        isError: !!error,
        error,
        refresh: mutate,
    };
}

export interface UseGraphHistoryOptions {
    workspaceId?: string;
    limit?: number;
    includePending?: boolean;
    enabled?: boolean;
}

/**
 * Hook for fetching graph changelog history
 */
export function useGraphHistory(options: UseGraphHistoryOptions = {}) {
    const { workspaceId, limit = 50, includePending = false, enabled = true } = options;

    const queryParams = new URLSearchParams();
    queryParams.append('limit', String(limit));
    if (includePending) {
        queryParams.append('include_pending', 'true');
    }

    const url = enabled && workspaceId
        ? `${API_BASE}/api/v1/execution-graph/changelog/history/${workspaceId}?${queryParams.toString()}`
        : null;

    const { data, error, isLoading, mutate } = useSWR<HistoryResponse>(
        url,
        historyFetcher,
        {
            revalidateOnFocus: false,
            dedupingInterval: 5000,
        }
    );

    return {
        history: data?.history ?? [],
        currentVersion: data?.current_version ?? 0,
        totalEntries: data?.total_entries ?? 0,
        isLoading,
        isError: !!error,
        error,
        refresh: mutate,
    };
}

// ============================================================================
// Mutation Functions
// ============================================================================

/**
 * Approve or reject pending changes
 */
export async function approveChanges(
    workspaceId: string,
    changeIds: string[],
    action: 'approve' | 'reject'
): Promise<ApproveResponse> {
    const res = await fetch(`${API_BASE}/api/v1/execution-graph/changelog/pending/${workspaceId}/approve`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            change_ids: changeIds,
            action,
        }),
    });

    if (!res.ok) {
        const errorText = await res.text().catch(() => 'Unknown error');
        throw new Error(`Failed to ${action} changes: ${res.status} - ${errorText}`);
    }

    return res.json();
}

/**
 * Undo an applied change
 */
export async function undoChange(changeId: string): Promise<{ success: boolean; message?: string; error?: string }> {
    const res = await fetch(`${API_BASE}/api/v1/execution-graph/changelog/undo`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            change_id: changeId,
        }),
    });

    if (!res.ok) {
        const errorText = await res.text().catch(() => 'Unknown error');
        throw new Error(`Failed to undo change: ${res.status} - ${errorText}`);
    }

    return res.json();
}

/**
 * Get current applied version for a workspace
 */
export async function getCurrentVersion(workspaceId: string): Promise<number> {
    const res = await fetch(`${API_BASE}/api/v1/execution-graph/changelog/version/${workspaceId}`);

    if (!res.ok) {
        throw new Error(`Failed to get version: ${res.status}`);
    }

    const data = await res.json();
    return data.current_version;
}
