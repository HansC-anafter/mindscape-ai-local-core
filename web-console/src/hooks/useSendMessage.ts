'use client';

import { useState, useCallback } from 'react';
import { ChatMessage } from './useChatEvents';

interface SendMessageOptions {
  message?: string;
  files?: string[];
  action?: string;
  action_params?: Record<string, any>;
  timeline_item_id?: string;
  confirm?: boolean;
  mode?: string;
  stream?: boolean;
  onChunk?: (chunk: string) => void;
  onComplete?: (fullText: string, contextTokens?: number) => void;
}

export function useSendMessage(workspaceId: string, apiUrl: string = '') {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendMessage = useCallback(async (
    options: SendMessageOptions,
    onSuccess?: (data: any) => void,
    onError?: (error: string) => void
  ) => {
    const {
      message = '',
      files = [],
      action,
      action_params,
      timeline_item_id,
      confirm,
      mode = 'auto',
      stream = false,
      onChunk,
      onComplete
    } = options;

    setIsLoading(true);
    setError(null);

    try {
      // Handle streaming requests
      if (stream) {
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/chat`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              message,
              files,
              action,
              action_params,
              timeline_item_id,
              confirm,
              mode,
              stream: true
            })
          }
        );

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.detail || `API error: ${response.status}`);
        }

        // Process streaming response
        const reader = response.body?.getReader();
        const decoder = new TextDecoder();
        let fullText = '';
        let buffer = '';

        if (!reader) {
          throw new Error('No response body reader available');
        }

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || ''; // Keep incomplete line in buffer

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));
                if (data.type === 'chunk' && data.content) {
                  fullText += data.content;
                  if (onChunk) {
                    onChunk(data.content);
                  }
                } else if (data.type === 'complete') {
                  const contextTokens = data.context_tokens;
                  if (onComplete) {
                    onComplete(fullText, contextTokens);
                  }
                  window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
                } else if (data.type === 'task_update') {
                  // Notify frontend about task creation/update
                  if (process.env.NODE_ENV === 'development') {
                    console.log('[useSendMessage] Received task_update event:', data.event_type, data.task);
                  }
                  window.dispatchEvent(new CustomEvent('workspace-task-updated', {
                    detail: {
                      event_type: data.event_type,
                      task: data.task
                    }
                  }));
                } else if (data.type === 'execution_results') {
                  // Notify frontend about execution results (playbook tasks created)
                  if (process.env.NODE_ENV === 'development') {
                    console.log('[useSendMessage] Received execution_results event:', data.executed_tasks?.length || 0, 'executed tasks,', data.suggestion_cards?.length || 0, 'suggestions');
                  }
                  window.dispatchEvent(new CustomEvent('workspace-task-updated'));
                } else if (data.type === 'error') {
                  throw new Error(data.message || 'Streaming error');
                }
              } catch (e) {
                console.error('Failed to parse SSE data:', e, line);
              }
            }
          }
        }

        setIsLoading(false);
        return { streamed: true, fullText };
      } else {
        // Non-streaming mode (existing logic)
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/chat`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              message,
              files,
              action,
              action_params,
              timeline_item_id,
              confirm,
              mode
            })
          }
        );

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.detail || `API error: ${response.status}`);
        }

        const data = await response.json();

        window.dispatchEvent(new CustomEvent('workspace-chat-updated'));

        if (onSuccess) {
          onSuccess(data);
        }

        setIsLoading(false);
        return data;
      }
    } catch (err: any) {
      const errorMessage = err.message || 'Failed to send message';
      setError(errorMessage);
      console.error('Chat error:', err);

      if (onError) {
        onError(errorMessage);
      }

      setIsLoading(false);
      throw err;
    }
  }, [workspaceId, apiUrl]);

  return {
    sendMessage,
    isLoading,
    error
  };
}



