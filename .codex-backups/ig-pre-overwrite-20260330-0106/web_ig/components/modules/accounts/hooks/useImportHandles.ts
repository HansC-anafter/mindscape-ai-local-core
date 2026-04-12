import { useMemo } from 'react';
import { MindscapeAPIClient } from '@/api/client';

import { executeWorkspacePlaybook } from '../api';

export function useImportHandles(params: {
  apiUrl: string;
  workspaceId: string;
  onStarted: (result: { execution_id?: string }) => void;
  onError: (message: string) => void;
  onFinally: () => void;
  onSetLoading: (value: boolean) => void;
  onCloseDialog: () => void;
  onClearInput: () => void;
  onScheduleRefresh: (delayMs: number) => void;
}) {
  const {
    apiUrl,
    workspaceId,
    onStarted,
    onError,
    onFinally,
    onSetLoading,
    onCloseDialog,
    onClearInput,
    onScheduleRefresh,
  } = params;

  const client = useMemo(() => MindscapeAPIClient.fromBaseUrl(apiUrl), [apiUrl]);

  const importHandles = async (rawText: string) => {
    if (!rawText.trim()) {
      onError('Please enter account handle(s)');
      return;
    }

    onSetLoading(true);
    try {
      const handles = rawText
        .split('\n')
        .map((h) => h.trim())
        .filter((h) => h.length > 0);

      const response = await executeWorkspacePlaybook(client, workspaceId, {
        playbook_code: 'ig_analyze_following',
        inputs: {
          workspace_id: workspaceId,
          target_username: handles[0],
          max_accounts: handles.length,
          visit_account_pages: true,
        },
        execution_mode: 'async',
      });

      if (response.ok) {
        const data = await response.json();
        onStarted(data);

        // Notify the workbench sidebar immediately so the status card appears right away.
        try {
          const execId = (data?.execution_id || '').toString();
          if (execId && typeof window !== 'undefined') {
            window.dispatchEvent(
              new CustomEvent('mindscape:execution_started', {
                detail: {
                  workspaceId,
                  executionId: execId,
                  playbookCode: 'ig_analyze_following',
                  startedAt: new Date().toISOString(),
                },
              })
            );
          }
        } catch {
          // ignore
        }

        onCloseDialog();
        onClearInput();
        onScheduleRefresh(2000);
      } else {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to import accounts');
      }
    } catch (err) {
      onError(`Import failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      onSetLoading(false);
      onFinally();
    }
  };

  return { importHandles };
}

