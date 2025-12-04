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
                } else if (data.type === 'playbook_triggered') {
                  // Notify frontend about playbook trigger result
                  if (process.env.NODE_ENV === 'development') {
                    console.log('[useSendMessage] Received playbook_triggered event:', data.status, data.playbook_code);
                  }
                  if (data.status === 'error') {
                    // Show error message to user
                    console.error('[useSendMessage] Playbook trigger failed:', data.message);
                    // Dispatch error event for UI to display
                    window.dispatchEvent(new CustomEvent('playbook-trigger-error', {
                      detail: {
                        playbook_code: data.playbook_code,
                        message: data.message
                      }
                    }));
                  } else if (data.status === 'triggered') {
                    // Successfully triggered playbook
                    window.dispatchEvent(new CustomEvent('playbook-triggered', {
                      detail: {
                        playbook_code: data.playbook_code,
                        playbook_name: data.playbook_name,
                        execution_id: data.execution_id
                      }
                    }));
                  }
                } else if (data.type === 'pipeline_stage') {
                  // Notify frontend about pipeline stage (for thinking context streaming)
                  if (process.env.NODE_ENV === 'development') {
                    console.log('[useSendMessage] Received pipeline_stage event:', data.stage, data.message);
                  }
                  window.dispatchEvent(new CustomEvent('execution-event', {
                    detail: {
                      type: 'pipeline_stage',
                      run_id: data.run_id,
                      stage: data.stage,
                      message: data.message,
                      metadata: data.metadata
                    }
                  }));
                } else if (data.type === 'execution_plan') {
                  // Notify frontend about execution plan (Chain-of-Thought)
                  if (process.env.NODE_ENV === 'development') {
                    console.log('[useSendMessage] Received execution_plan event:', data.plan?.step_count || 0, 'steps');
                    console.log('[useSendMessage] Plan data:', {
                      plan_id: data.plan?.id,
                      plan_summary: data.plan?.plan_summary,
                      step_count: data.plan?.step_count,
                      steps: data.plan?.steps,
                      ai_team_members: data.plan?.ai_team_members,
                      raw_steps: JSON.stringify(data.plan?.steps, null, 2)
                    });
                  }
                  const mappedSteps = (data.plan?.steps || []).map((s: any) => {
                    const step = {
                      id: s.step_id || s.id || `step-${Math.random().toString(36).substr(2, 9)}`,
                      name: s.intent || s.name || 'Unknown Step',
                      icon: s.artifacts?.[0] === 'pptx' ? '📊' :
                            s.artifacts?.[0] === 'xlsx' ? '📊' :
                            s.artifacts?.[0] === 'docx' ? '📝' : '📋',
                      status: 'pending' as const
                    };
                    if (process.env.NODE_ENV === 'development') {
                      console.log('[useSendMessage] Mapped step:', step, 'from raw:', s);
                    }
                    return step;
                  });
                  if (process.env.NODE_ENV === 'development') {
                    console.log('[useSendMessage] Dispatching execution-event with', mappedSteps.length, 'mapped steps');
                  }
                  window.dispatchEvent(new CustomEvent('execution-event', {
                    detail: {
                      type: 'execution_plan',
                      plan: {
                        id: data.plan?.id,
                        summary: data.plan?.plan_summary,
                        steps: mappedSteps,
                        ai_team_members: data.plan?.ai_team_members || []
                      }
                    }
                  }));
                } else if (data.type === 'thinking_start') {
                  // Notify frontend that AI is starting to think
                  window.dispatchEvent(new CustomEvent('execution-event', {
                    detail: { type: 'thinking_start' }
                  }));
                } else if (data.type === 'thinking_step') {
                  // Notify frontend about a thinking step
                  window.dispatchEvent(new CustomEvent('execution-event', {
                    detail: { type: 'thinking_step', step: data.step }
                  }));
                } else if (data.type === 'task_update') {
                  // Forward task_update events to execution state
                  window.dispatchEvent(new CustomEvent('execution-event', {
                    detail: {
                      type: 'task_update',
                      event_type: data.event_type,
                      task: data.task
                    }
                  }));
                } else if (data.type === 'step_start' || data.type === 'step_progress' ||
                           data.type === 'step_complete' || data.type === 'step_error') {
                  // Forward step events to execution state
                  window.dispatchEvent(new CustomEvent('execution-event', {
                    detail: data
                  }));
                } else if (data.type === 'artifact_created') {
                  // Notify frontend about artifact creation
                  window.dispatchEvent(new CustomEvent('execution-event', {
                    detail: {
                      type: 'artifact_created',
                      artifact: data.artifact
                    }
                  }));
                } else if (data.type === 'execution_complete') {
                  // Notify frontend about execution completion
                  window.dispatchEvent(new CustomEvent('execution-event', {
                    detail: {
                      type: 'execution_complete',
                      summary: data.summary
                    }
                  }));
                } else if (data.type === 'agent_mode_parsed') {
                  // Agent Mode: Two-part response parsed result
                  if (process.env.NODE_ENV === 'development') {
                    console.log('[useSendMessage] Received agent_mode_parsed event:', {
                      part1_length: data.part1?.length || 0,
                      part2_length: data.part2?.length || 0,
                      executable_tasks_count: data.executable_tasks?.length || 0
                    });
                  }
                  window.dispatchEvent(new CustomEvent('agent-mode-parsed', {
                    detail: {
                      part1: data.part1 || '',
                      part2: data.part2 || '',
                      executable_tasks: data.executable_tasks || []
                    }
                  }));
                } else if (data.type === 'execution_mode_playbook_executed') {
                  // Execution Mode: Direct playbook.run execution result
                  if (process.env.NODE_ENV === 'development') {
                    console.log('[useSendMessage] Received execution_mode_playbook_executed event:', {
                      status: data.status,
                      playbook_code: data.playbook_code,
                      execution_id: data.execution_id
                    });
                  }
                  if (data.status === 'executed') {
                    window.dispatchEvent(new CustomEvent('execution-mode-playbook-executed', {
                      detail: {
                        status: data.status,
                        playbook_code: data.playbook_code,
                        execution_id: data.execution_id,
                        execution_mode: data.execution_mode || 'direct_playbook_run'
                      }
                    }));
                  }
                } else if (data.type === 'error') {
                  // Parse error message - support both structured and legacy formats
                  let errorMessage = 'Streaming error';

                  if (data.error && typeof data.error === 'object') {
                    // Structured error format (new)
                    errorMessage = data.error.user_message || data.error.message || 'An error occurred';
                  } else if (data.message) {
                    // Legacy format - try to extract user-friendly message
                    errorMessage = data.message;

                    // Remove hardcoded error code patterns
                    errorMessage = errorMessage.replace(/Error code: \d+\s*-\s*/, '');

                    // Try to extract user-friendly message from error object if present
                    try {
                      const errorMatch = errorMessage.match(/'error':\s*\{'message':\s*'([^']+)'/);
                      if (errorMatch) {
                        errorMessage = errorMatch[1];
                      }
                    } catch (parseErr) {
                      // If parsing fails, use cleaned message
                    }
                  }

                  // Throw error with parsed message
                  const error = new Error(errorMessage);
                  (error as any).errorData = data;
                  throw error;
                }
              } catch (e) {
                // Re-throw error events so they can be handled by the caller
                if (e instanceof Error && (e as any).errorData) {
                  throw e;
                }
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



