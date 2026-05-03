import { useEffect, useState } from 'react';

import { fetchApiJson, postApiJson } from './meetingApi';
import { buildRegistryMentionItems } from './meetingMentions';
import type { MeetingMentionItem } from './meetingWorkbenchTypes';
import { isRecord } from './meetingWorkbenchUtils';

interface UseMeetingObjectRegistryMentionsArgs {
  workspaceId: string;
  apiUrl: string;
  activeMeetingId: string;
  activeMentionQuery: string | null;
}

export interface MeetingObjectRegistryMentionsState {
  registryMentionItems: MeetingMentionItem[];
  registryMentionItemsLoading: boolean;
  registryMentionItemsError: string | null;
}

export function useMeetingObjectRegistryMentions({
  workspaceId,
  apiUrl,
  activeMeetingId,
  activeMentionQuery,
}: UseMeetingObjectRegistryMentionsArgs): MeetingObjectRegistryMentionsState {
  const [registryMentionItems, setRegistryMentionItems] = useState<MeetingMentionItem[]>([]);
  const [registryMentionItemsLoading, setRegistryMentionItemsLoading] = useState(false);
  const [registryMentionItemsError, setRegistryMentionItemsError] = useState<string | null>(null);

  useEffect(() => {
    if (!workspaceId) {
      return;
    }

    const controller = new AbortController();

    async function syncObjectIndex(reason: string) {
      try {
        await postApiJson(
          apiUrl,
          `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/objects/sync`,
          {
            limit: 200,
            force: false,
            reason,
          },
          controller.signal,
        );
      } catch {
        // Mention completion uses the registry read model; sync failures surface through completion state.
      }
    }

    void syncObjectIndex('meeting_bottom_shell_open');

    function handleWorkspaceUpdate() {
      void syncObjectIndex('workspace_update');
    }

    window.addEventListener('workspace-task-updated', handleWorkspaceUpdate);

    return () => {
      controller.abort();
      window.removeEventListener('workspace-task-updated', handleWorkspaceUpdate);
    };
  }, [apiUrl, workspaceId]);

  useEffect(() => {
    let cancelled = false;

    async function fetchRegistryMentionItems() {
      if (!workspaceId || !activeMeetingId || activeMentionQuery === null) {
        setRegistryMentionItems([]);
        setRegistryMentionItemsError(null);
        setRegistryMentionItemsLoading(false);
        return;
      }

      setRegistryMentionItemsLoading(true);
      setRegistryMentionItemsError(null);

      const params = new URLSearchParams({
        query: activeMentionQuery,
        limit: '16',
      });

      try {
        const payload = await fetchApiJson(
          apiUrl,
          `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/objects/complete?${params.toString()}`,
        );
        if (!cancelled) {
          const results = isRecord(payload) ? payload.results : [];
          setRegistryMentionItems(buildRegistryMentionItems(results));
          setRegistryMentionItemsLoading(false);
        }
      } catch (error) {
        if (!cancelled) {
          setRegistryMentionItems([]);
          setRegistryMentionItemsError(error instanceof Error ? error.message : 'object registry');
          setRegistryMentionItemsLoading(false);
        }
      }
    }

    void fetchRegistryMentionItems();

    return () => {
      cancelled = true;
    };
  }, [activeMeetingId, activeMentionQuery, apiUrl, workspaceId]);

  return {
    registryMentionItems,
    registryMentionItemsLoading,
    registryMentionItemsError,
  };
}
