'use client';

import { useEffect, useState } from 'react';

import {
  fetchRunObservationsSummary,
  type RunObservationsSummary,
} from './run-observations-api';

interface UseRunObservationsSummaryParams {
  apiUrl: string;
  workspaceId: string;
  activeOnly?: boolean;
  limit?: number;
  enabled?: boolean;
  pollIntervalMs?: number;
}

export interface UseRunObservationsSummaryResult {
  summary: RunObservationsSummary | null;
  isLoading: boolean;
  error: string | null;
  externalActiveCount: number;
}

export function useRunObservationsSummary({
  apiUrl,
  workspaceId,
  activeOnly = true,
  limit = 20,
  enabled = true,
  pollIntervalMs = 30_000,
}: UseRunObservationsSummaryParams): UseRunObservationsSummaryResult {
  const [summary, setSummary] = useState<RunObservationsSummary | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled || !workspaceId) {
      setSummary(null);
      setIsLoading(false);
      setError(null);
      return undefined;
    }

    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    const load = async () => {
      setIsLoading(true);
      try {
        const nextSummary = await fetchRunObservationsSummary({
          apiUrl,
          workspaceId,
          activeOnly,
          limit,
        });
        if (!cancelled) {
          setSummary(nextSummary);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load run observations');
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
          timeoutId = setTimeout(load, pollIntervalMs);
        }
      }
    };

    void load();

    return () => {
      cancelled = true;
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [activeOnly, apiUrl, enabled, limit, pollIntervalMs, workspaceId]);

  return {
    summary,
    isLoading,
    error,
    externalActiveCount: summary?.external_active_count ?? 0,
  };
}
