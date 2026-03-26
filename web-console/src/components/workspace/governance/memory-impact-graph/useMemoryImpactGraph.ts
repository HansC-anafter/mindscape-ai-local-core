'use client';

import { useEffect, useMemo, useState } from 'react';
import type {
  MemoryImpactGraphQuery,
  MemoryImpactGraphResponse,
} from './types';

interface MemoryImpactGraphState {
  data: MemoryImpactGraphResponse | null;
  loading: boolean;
  error: string | null;
}

export function useMemoryImpactGraph({
  workspaceId,
  apiUrl,
  sessionId,
  executionId,
  threadId,
}: MemoryImpactGraphQuery): MemoryImpactGraphState {
  const [data, setData] = useState<MemoryImpactGraphResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const requestUrl = useMemo(() => {
    if (!workspaceId || !apiUrl) {
      return null;
    }

    const params = new URLSearchParams();
    if (sessionId) {
      params.set('session_id', sessionId);
    } else if (executionId) {
      params.set('execution_id', executionId);
    } else if (threadId) {
      params.set('thread_id', threadId);
    } else {
      return null;
    }

    return `${apiUrl}/api/v1/workspaces/${workspaceId}/governance/memory-impact-graph?${params.toString()}`;
  }, [apiUrl, executionId, sessionId, threadId, workspaceId]);

  useEffect(() => {
    if (!requestUrl) {
      setData(null);
      setLoading(false);
      setError(null);
      return;
    }

    const controller = new AbortController();
    let cancelled = false;

    const load = async () => {
      try {
        setLoading(true);
        setError(null);
        const response = await fetch(requestUrl, {
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`Failed to load memory impact graph: ${response.status}`);
        }
        const payload: MemoryImpactGraphResponse = await response.json();
        if (!cancelled) {
          setData(payload);
        }
      } catch (err) {
        if (controller.signal.aborted || cancelled) {
          return;
        }
        setData(null);
        setError(
          err instanceof Error
            ? err.message
            : 'Failed to load memory impact graph'
        );
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void load();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [requestUrl]);

  return {
    data,
    loading,
    error,
  };
}
