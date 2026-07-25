'use client';

import { useEffect, useState } from 'react';
import {
  subscribeEventStream,
  type UnifiedEvent,
} from '@/components/workspace/eventProjector';
import { fetchDurabilitySummary } from './api';
import type { DurableWorkflowSummary } from './types';

interface DurableWorkflowReviewOptions {
  active: boolean;
  apiUrl: string;
  workspaceId: string;
  executionId: string;
}

interface DurableSummaryEventPayload {
  execution_id?: string;
  durability_summary?: DurableWorkflowSummary;
}

export function useDurableWorkflowReview({
  active,
  apiUrl,
  workspaceId,
  executionId,
}: DurableWorkflowReviewOptions) {
  const [summary, setSummary] = useState<DurableWorkflowSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchDurabilitySummary(
      apiUrl,
      workspaceId,
      executionId,
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
    return () => controller.abort();
  }, [active, apiUrl, workspaceId, executionId]);

  useEffect(() => {
    if (!active || !summary || summary.terminal) return;
    return subscribeEventStream(workspaceId, {
      apiUrl,
      eventTypes: ['durable_workflow_projection_changed'],
      onEvent: (event: UnifiedEvent) => {
        const payload = event.payload as DurableSummaryEventPayload;
        if (
          payload.execution_id === executionId &&
          payload.durability_summary?.workflow_id === summary.workflow_id
        ) {
          setSummary(payload.durability_summary);
        }
      },
      onError: (reason) => setError(reason.message),
    });
  }, [active, apiUrl, workspaceId, executionId, summary]);

  return { summary, loading, error };
}
