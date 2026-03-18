'use client';

import { useState, useMemo, useCallback } from 'react';
import { useExecutionStream } from '@/hooks/useExecutionStream';

/**
 * Debug info parsed from SSE progress events.
 * Generic fields applicable to all runner tasks.
 */
export interface RunnerDebugInfo {
  status: string | null;
  progress: Record<string, any> | null;
  queuePosition: number | null;
  queueTotal: number | null;
  dependencyHold: { deps: string[]; checked_at: string } | null;
  heartbeatAt: string | null;
  runnerId: string | null;
  isConnected: boolean;
}

const EMPTY_DEBUG: RunnerDebugInfo = {
  status: null,
  progress: null,
  queuePosition: null,
  queueTotal: null,
  dependencyHold: null,
  heartbeatAt: null,
  runnerId: null,
  isConnected: false,
};

/**
 * Hook that wraps useExecutionStream to provide parsed runner debug info.
 * Subscribes to SSE stream and extracts generic runner fields.
 */
export function useRunnerTaskDebug(
  executionId: string | null | undefined,
  workspaceId: string,
  apiUrl: string,
): RunnerDebugInfo {
  const [lastEvent, setLastEvent] = useState<Record<string, any> | null>(null);

  const onEvent = useCallback((data: { type: string; [key: string]: any }) => {
    if (data.type === 'progress') {
      setLastEvent(data);
    }
  }, []);

  const { isConnected } = useExecutionStream(executionId, workspaceId, apiUrl, onEvent);

  const debugInfo = useMemo((): RunnerDebugInfo => {
    if (!lastEvent) return { ...EMPTY_DEBUG, isConnected };
    return {
      status: lastEvent.status ?? null,
      progress: lastEvent.progress ?? null,
      queuePosition: lastEvent.queue_position ?? null,
      queueTotal: lastEvent.queue_total ?? null,
      dependencyHold: lastEvent.dependency_hold ?? null,
      heartbeatAt: lastEvent.heartbeat_at ?? null,
      runnerId: lastEvent.runner_id ?? null,
      isConnected,
    };
  }, [lastEvent, isConnected]);

  return debugInfo;
}
