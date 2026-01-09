'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
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
  project_id?: string;  // Current project ID
  thread_id?: string | null;  // 🆕 Conversation thread ID
  onChunk?: (chunk: string) => void;
  onComplete?: (fullText: string, contextTokens?: number) => void;
}

export function useSendMessage(
  workspaceId: string,
  apiUrl: string = '',
  projectId?: string,
  threadId?: string | null  // 🆕 Current thread ID
) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Track current threadId for stream validation
  const currentThreadIdRef = useRef<string | null>(threadId || null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Update current threadId ref when threadId changes
  useEffect(() => {
    currentThreadIdRef.current = threadId || null;
    // Abort any ongoing stream when threadId changes
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, [threadId]);

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
      project_id,
      thread_id,  // 🆕 從 options 獲取（優先級高於 hook 參數）
      onChunk,
      onComplete
    } = options;

    // Use project_id from options, fallback to hook parameter
    const finalProjectId = project_id || projectId;
    // Use thread_id from options, fallback to hook parameter
    const finalThreadId = thread_id !== undefined ? thread_id : threadId;  // 🆕

    // Debug logging
    console.log('[useSendMessage] Sending message:', {
      project_id_from_options: project_id,
      project_id_from_hook: projectId,
      final_project_id: finalProjectId,
      message_preview: message.substring(0, 100),
      message_full: message,
      action,
      action_params,
      mode,
      stream,
      files_count: files.length
    });

    setIsLoading(true);
    setError(null);

    try {
      // Handle streaming requests
      if (stream) {
        // Abort previous stream if exists
        if (abortControllerRef.current) {
          abortControllerRef.current.abort();
        }

        // Create new AbortController for this request
        abortControllerRef.current = new AbortController();
        const targetThreadId = finalThreadId;

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
              stream: true,
              project_id: finalProjectId,  // Pass project_id to API
              thread_id: finalThreadId  // 🆕 Pass thread_id to API
            }),
            signal: abortControllerRef.current.signal  // Add abort signal
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

          // Check if threadId has changed (stream validation)
          if (currentThreadIdRef.current !== targetThreadId) {
            console.log('[useSendMessage] Thread switched, aborting stream');
            abortControllerRef.current?.abort();
            return { streamed: true, fullText, aborted: true };
          }

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || ''; // Keep incomplete line in buffer

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));

                // Validate threadId before processing chunk
                if (currentThreadIdRef.current !== targetThreadId) {
                  console.log('[useSendMessage] Discarding chunk for old thread');
                  continue;
                }

                if (data.type === 'chunk' && data.content) {
                  fullText += data.content;
                  if (onChunk) {
                    onChunk(data.content);
                  }
                } else if (data.type === 'complete') {
                  // Only process final complete event (ignore quick_response_complete)
                  if (data.is_final !== false) {  // is_final can be true or undefined (both mean final)
                    const contextTokens = data.context_tokens;
                    if (onComplete) {
                      onComplete(fullText, contextTokens);
                    }
                    window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
                  }
                } else if (data.type === 'quick_response_complete') {
                  // QuickQA response completed, but main response will continue
                  // Don't call onComplete here - wait for final 'complete' event
                  if (process.env.NODE_ENV === 'development') {
                    console.log('[useSendMessage] QuickQA response completed, waiting for main response...');
                  }
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
                  // Dispatch event to update task list
                  window.dispatchEvent(new CustomEvent('workspace-task-updated'));
                  // Dispatch event to add summary message to workspace chat
                  window.dispatchEvent(new CustomEvent('execution-results-summary', {
                    detail: {
                      executed_tasks: data.executed_tasks || [],
                      suggestion_cards: data.suggestion_cards || []
                    }
                  }));
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
                      ai_team_members_count: data.plan?.ai_team_members?.length || 0,
                      raw_steps: JSON.stringify(data.plan?.steps, null, 2)
                    });
                    if (data.plan?.ai_team_members && data.plan.ai_team_members.length > 0) {
                      console.log('[useSendMessage] AI team members details:', JSON.stringify(data.plan.ai_team_members, null, 2));
                    } else {
                      console.warn('[useSendMessage] No ai_team_members in plan data!');
                    }
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

        // Clear abort controller on successful completion
        abortControllerRef.current = null;
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
              mode,
              project_id: finalProjectId,  // Pass project_id to API
              thread_id: finalThreadId  // 🆕 Pass thread_id to API
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
      // Handle AbortError gracefully (thread switch)
      if (err.name === 'AbortError') {
        console.log('[useSendMessage] Request aborted due to thread switch');
        setIsLoading(false);
        abortControllerRef.current = null;
        return { streamed: true, aborted: true };
      }

      const errorMessage = err.message || 'Failed to send message';
      setError(errorMessage);
      console.error('Chat error:', err);

      if (onError) {
        onError(errorMessage);
      }

      setIsLoading(false);
      abortControllerRef.current = null;
      throw err;
    }
  }, [workspaceId, apiUrl, projectId, threadId]);  // 🆕 添加 threadId 到依賴

  return {
    sendMessage,
    isLoading,
    error
  };
}



