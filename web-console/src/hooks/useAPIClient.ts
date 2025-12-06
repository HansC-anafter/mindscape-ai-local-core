/**
 * useAPIClient - Hook to get MindscapeAPIClient instance
 *
 * This hook provides a MindscapeAPIClient instance that automatically
 * handles Local/Cloud differences. Playbook components should use this
 * instead of directly calling fetch.
 *
 * @example
 * ```tsx
 * const apiClient = useAPIClient();
 * const response = await apiClient.get(`/api/v1/workspaces/${workspaceId}/books/current`);
 * const data = await response.json();
 * ```
 */

import { useExecutionContext } from '@/contexts/ExecutionContextContext';
import { MindscapeAPIClient } from '@/api/client';
import { useMemo } from 'react';

export function useAPIClient(): MindscapeAPIClient {
  const context = useExecutionContext();

  return useMemo(() => {
    return new MindscapeAPIClient(context);
  }, [context]);
}

