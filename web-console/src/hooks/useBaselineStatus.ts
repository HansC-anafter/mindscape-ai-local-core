'use client';

/**
 * useBaselineStatus - Hook for managing Design Snapshot baseline status
 *
 * This hook provides a state machine-based interface for managing baseline
 * status with the following states:
 * - absent: No snapshots exist
 * - present-not-applied: Snapshots exist but no baseline set
 * - applied-unlocked: Baseline exists, lock_mode = "advisory"
 * - applied-locked: Baseline exists, lock_mode = "locked"
 * - stale: Baseline exists but is stale (version mismatch)
 * - error: Error state
 *
 * @example
 * ```tsx
 * const { status, context, isLoading, setBaseline, refresh } = useBaselineStatus(workspaceId, projectId);
 *
 * if (status === 'stale') {
 *   // Show re-sync prompt
 * }
 *
 * await setBaseline('snapshot-id', 'variant-a', true); // Set with lock
 * ```
 */

import { useState, useEffect, useCallback } from 'react';
import { useAPIClient } from './useAPIClient';

// ============================================================================
// Types
// ============================================================================

export type BaselineStatus =
  | 'absent'
  | 'present-not-applied'
  | 'applied-unlocked'
  | 'applied-locked'
  | 'stale'
  | 'error';

export interface BaselineContext {
  status: BaselineStatus;
  snapshotId?: string;
  snapshotVersion?: string;
  variantId?: string;
  activeVariant?: string;
  lockMode?: 'locked' | 'advisory';
  baselineFor?: string;
  extractionQuality?: 'low' | 'medium' | 'high';
  boundSpecVersion?: string;
  boundOutlineVersion?: string;
  lastSyncAt?: string;
  error?: string;
  staleInfo?: {
    is_stale: boolean;
    severity?: 'high' | 'medium';
    reason?: string;
    spec_diff?: any;
    outline_diff?: any;
  };
}

export interface AvailableSnapshot {
  id: string;
  version: string;
  variantId?: string;
  sourceTool?: string;
  snapshotDate?: string;
  extractionQuality?: 'low' | 'medium' | 'high';
}

// ============================================================================
// API Response Types
// ============================================================================

interface BaselineStatusResponse {
  status: BaselineStatus;
  context: BaselineContext | null;
  available_snapshots: AvailableSnapshot[];
  stale_info?: {
    is_stale: boolean;
    severity?: 'high' | 'medium';
    reason?: string;
    spec_diff?: any;
    outline_diff?: any;
  };
}

interface SetBaselineRequest {
  snapshot_id: string;
  variant_id?: string;
  project_id?: string;
  lock_mode?: 'locked' | 'advisory';
  reason?: string;
}

// ============================================================================
// Hook Implementation
// ============================================================================

export function useBaselineStatus(
  workspaceId: string,
  projectId?: string
): {
  status: BaselineStatus;
  context: BaselineContext | null;
  availableSnapshots: AvailableSnapshot[];
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  setBaseline: (
    snapshotId: string,
    variantId?: string,
    lock?: boolean,
    reason?: string
  ) => Promise<void>;
  unlock: (reason?: string) => Promise<void>;
  sync: (reason?: string) => Promise<void>;
} {
  const apiClient = useAPIClient();

  const [status, setStatus] = useState<BaselineStatus>('absent');
  const [context, setContext] = useState<BaselineContext | null>(null);
  const [availableSnapshots, setAvailableSnapshots] = useState<AvailableSnapshot[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // ========================================================================
  // Fetch Baseline Status
  // ========================================================================

  const fetchBaselineStatus = useCallback(async () => {
    if (!workspaceId) {
      setError('Workspace ID is required');
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const queryParams = projectId ? `?project_id=${encodeURIComponent(projectId)}` : '';
      const response = await apiClient.get(
        `/api/v1/workspaces/${workspaceId}/web-generation/baseline${queryParams}`
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to fetch baseline status: ${response.statusText}`);
      }

      const data: BaselineStatusResponse = await response.json();

      setStatus(data.status);
      setContext(data.context || null);
      setAvailableSnapshots(data.available_snapshots || []);

      // If context is provided, merge stale_info
      if (data.context && data.stale_info) {
        setContext({
          ...data.context,
          staleInfo: data.stale_info,
        });
      }

    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      setStatus('error');
      setContext({
        status: 'error',
        error: errorMessage,
      });
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId, projectId, apiClient]);

  // ========================================================================
  // Set Baseline
  // ========================================================================

  const setBaseline = useCallback(async (
    snapshotId: string,
    variantId?: string,
    lock: boolean = false,
    reason?: string
  ) => {
    if (!workspaceId) {
      throw new Error('Workspace ID is required');
    }

    setIsLoading(true);
    setError(null);

    try {
      const requestBody: SetBaselineRequest = {
        snapshot_id: snapshotId,
        variant_id: variantId,
        project_id: projectId,
        lock_mode: lock ? 'locked' : 'advisory',
        reason: reason,
      };

      const response = await apiClient.post(
        `/api/v1/workspaces/${workspaceId}/web-generation/baseline`,
        requestBody
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to set baseline: ${response.statusText}`);
      }

      // Refresh status after setting baseline
      await fetchBaselineStatus();

    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      setStatus('error');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId, projectId, apiClient, fetchBaselineStatus]);

  // ========================================================================
  // Unlock Baseline
  // ========================================================================

  const unlock = useCallback(async (reason?: string) => {
    if (!workspaceId || !context?.snapshotId) {
      throw new Error('Cannot unlock: no baseline set');
    }

    setIsLoading(true);
    setError(null);

    try {
      const requestBody: SetBaselineRequest = {
        snapshot_id: context.snapshotId,
        variant_id: context.variantId,
        project_id: projectId,
        lock_mode: 'advisory',
        reason: reason || 'Unlocked by user',
      };

      const response = await apiClient.post(
        `/api/v1/workspaces/${workspaceId}/web-generation/baseline`,
        requestBody
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to unlock baseline: ${response.statusText}`);
      }

      // Refresh status after unlocking
      await fetchBaselineStatus();

    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      setStatus('error');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId, projectId, context, apiClient, fetchBaselineStatus]);

  // ========================================================================
  // Sync Baseline (Re-sync to latest versions)
  // ========================================================================

  const sync = useCallback(async (reason?: string) => {
    if (!workspaceId || !context?.snapshotId) {
      throw new Error('Cannot sync: no baseline set');
    }

    setIsLoading(true);
    setError(null);

    try {
      // Re-sync means updating the baseline with current snapshot
      // This is essentially a re-set with the same snapshot but updated bound versions
      const requestBody: SetBaselineRequest = {
        snapshot_id: context.snapshotId,
        variant_id: context.variantId,
        project_id: projectId,
        lock_mode: context.lockMode || 'advisory',
        reason: reason || 'Re-synced to latest versions',
      };

      const response = await apiClient.post(
        `/api/v1/workspaces/${workspaceId}/web-generation/baseline`,
        requestBody
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to sync baseline: ${response.statusText}`);
      }

      // Refresh status after syncing
      await fetchBaselineStatus();

    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      setStatus('error');
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId, projectId, context, apiClient, fetchBaselineStatus]);

  // ========================================================================
  // Initial Load & Refresh
  // ========================================================================

  const refresh = useCallback(async () => {
    await fetchBaselineStatus();
  }, [fetchBaselineStatus]);

  // Initial load
  useEffect(() => {
    fetchBaselineStatus();
  }, [fetchBaselineStatus]);

  // ========================================================================
  // Return
  // ========================================================================

  return {
    status,
    context,
    availableSnapshots,
    isLoading,
    error,
    refresh,
    setBaseline,
    unlock,
    sync,
  };
}
