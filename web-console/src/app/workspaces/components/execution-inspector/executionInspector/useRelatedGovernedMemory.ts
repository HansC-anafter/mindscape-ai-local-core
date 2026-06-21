import { useEffect, useMemo, useState } from 'react';

import type { RelatedGovernedMemoryLink } from '../types/execution';

export interface UseRelatedGovernedMemoryResult {
  relatedMemory: RelatedGovernedMemoryLink | null;
  relatedMemoryHref: string | null;
  relatedMemoryLoading: boolean;
}

export function useRelatedGovernedMemory({
  apiUrl,
  executionId,
  executionThreadId,
  workspaceId,
}: {
  apiUrl: string;
  executionId: string;
  executionThreadId: string | null;
  workspaceId: string;
}): UseRelatedGovernedMemoryResult {
  const [relatedMemory, setRelatedMemory] = useState<RelatedGovernedMemoryLink | null>(null);
  const [relatedMemoryLoading, setRelatedMemoryLoading] = useState(false);

  const relatedMemoryHref = useMemo(() => {
    if (!relatedMemory?.memoryItemId) {
      return null;
    }
    const params = new URLSearchParams();
    params.set('tab', 'memory');
    params.set('memoryId', relatedMemory.memoryItemId);
    return `/workspaces/${workspaceId}/governance?${params.toString()}`;
  }, [relatedMemory?.memoryItemId, workspaceId]);

  useEffect(() => {
    if (!workspaceId || !executionThreadId) {
      setRelatedMemory(null);
      setRelatedMemoryLoading(false);
      return;
    }

    let cancelled = false;

    const loadRelatedMemory = async () => {
      try {
        setRelatedMemoryLoading(true);
        const params = new URLSearchParams();
        params.set('event_types', 'memory_writeback');
        params.set('thread_id', executionThreadId);
        params.set('limit', '10');

        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/events?${params.toString()}`
        );
        if (!response.ok) {
          throw new Error(`Failed to load related governed memory: ${response.status}`);
        }

        const data = await response.json();
        const latestMemoryEvent = (data.events || []).find(
          (event: any) => typeof event?.payload?.memory_item_id === 'string' && event.payload.memory_item_id
        );

        if (!cancelled) {
          setRelatedMemory(
            latestMemoryEvent
              ? {
                  eventId: latestMemoryEvent.id,
                  memoryItemId: latestMemoryEvent.payload.memory_item_id,
                  lifecycleStatus: latestMemoryEvent.payload.lifecycle_status,
                  verificationStatus: latestMemoryEvent.payload.verification_status,
                }
              : null
          );
        }
      } catch (error) {
        console.error('[ExecutionInspector] Failed to load related governed memory:', error);
        if (!cancelled) {
          setRelatedMemory(null);
        }
      } finally {
        if (!cancelled) {
          setRelatedMemoryLoading(false);
        }
      }
    };

    void loadRelatedMemory();

    return () => {
      cancelled = true;
    };
  }, [apiUrl, executionId, executionThreadId, workspaceId]);

  return {
    relatedMemory,
    relatedMemoryHref,
    relatedMemoryLoading,
  };
}
