'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  subscribeEventStream,
  type UnifiedEvent,
} from '@/components/workspace/eventProjector';
import { fetchProductIterationSummary } from './api';
import type { ProductIterationReviewSummary } from './types';

const OUTCOME_EVENT_TYPES = [
  'product_iteration_state_changed',
  'product_iteration_evidence_changed',
  'product_iteration_evaluation_completed',
  'product_iteration_promotion_changed',
  'product_release_state_changed',
  'product_release_health_changed',
  'evidence_lifecycle_changed',
];

interface Options {
  active: boolean;
  apiUrl: string;
  workspaceId: string;
  iterationId: string;
}

export function useProductOutcomeReview({
  active,
  apiUrl,
  workspaceId,
  iterationId,
}: Options) {
  const [summary, setSummary] =
    useState<ProductIterationReviewSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const refreshQueued = useRef(false);

  const refresh = useCallback(() => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setError(null);
    return fetchProductIterationSummary(
      apiUrl,
      workspaceId,
      iterationId,
      controller.signal,
    )
      .then(setSummary)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : String(reason));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
  }, [apiUrl, iterationId, workspaceId]);

  useEffect(() => {
    if (!active) {
      controllerRef.current?.abort();
      setSummary(null);
      setLoading(false);
      return;
    }
    void refresh();
    return () => controllerRef.current?.abort();
  }, [active, refresh]);

  useEffect(() => {
    if (!active) return;
    let disposed = false;
    const unsubscribe = subscribeEventStream(workspaceId, {
      apiUrl,
      eventTypes: OUTCOME_EVENT_TYPES,
      onEvent: (event: UnifiedEvent) => {
        const eventIterationId = String(
          (event.payload as Record<string, unknown>).iteration_id || '',
        );
        if (eventIterationId !== iterationId || refreshQueued.current) return;
        refreshQueued.current = true;
        queueMicrotask(() => {
          refreshQueued.current = false;
          if (!disposed) void refresh();
        });
      },
      onError: (reason) => setError(reason.message),
    });
    return () => {
      disposed = true;
      refreshQueued.current = false;
      unsubscribe();
    };
  }, [active, apiUrl, iterationId, refresh, workspaceId]);

  return { summary, loading, error, refresh };
}
