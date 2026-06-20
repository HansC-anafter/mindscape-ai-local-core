'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useT } from '@/lib/i18n';
import { useExecutionStream } from '@/hooks/useExecutionStream';
import { toTimestampMs } from '@/lib/time';

import { ExecutionChatPanelView } from './executionChat/ExecutionChatPanelView';
import { buildExecutionChatQuickPrompts } from './executionChat/quickPrompts';
import type { ExecutionChatMessage, ExecutionChatPanelProps } from './executionChat/types';

export default function ExecutionChatPanel({
  executionId,
  workspaceId,
  apiUrl,
  playbookMetadata,
  executionStatus,
  runNumber = 1,
  collapsible = false,
  defaultCollapsed = false,
}: ExecutionChatPanelProps) {
  const t = useT();
  const [messages, setMessages] = useState<ExecutionChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isWaitingForReply, setIsWaitingForReply] = useState(false);
  const thinkingMessageIdRef = useRef<string | null>(null);
  const [isCollapsed, setIsCollapsed] = useState(defaultCollapsed);
  const [userScrolled, setUserScrolled] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [needsContinue, setNeedsContinue] = useState(false);
  const [currentStepStatus, setCurrentStepStatus] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesScrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const userScrolledRef = useRef(false);
  const autoScrollRef = useRef(true);
  const scrollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scrollToBottomRef = useRef<((force?: boolean, instant?: boolean) => void) | null>(null);

  const scrollToBottom = useCallback((force: boolean = false, instant: boolean = false) => {
    if (!messagesScrollRef.current) return;

    if (force || instant) {
      messagesScrollRef.current.scrollTop = messagesScrollRef.current.scrollHeight;
      setAutoScroll(true);
      setUserScrolled(false);
      userScrolledRef.current = false;
      autoScrollRef.current = true;
      setShowScrollToBottom(false);
    } else if (autoScrollRef.current && !userScrolledRef.current && messages.length > 0) {
      const { scrollTop, scrollHeight, clientHeight } = messagesScrollRef.current;
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;
      if (isNearBottom) {
        messagesScrollRef.current.scrollTop = messagesScrollRef.current.scrollHeight;
      }
    }
  }, [messages.length]);

  useEffect(() => {
    scrollToBottomRef.current = scrollToBottom;
  }, [scrollToBottom]);

  useEffect(() => {
    const checkExecutionStatus = async () => {
      try {
        const execResponse = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}`
        );
        if (!execResponse.ok) {
          throw new Error(`Failed to fetch execution: ${execResponse.status}`);
        }
        const exec = await execResponse.json();

        const stepsResponse = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/steps`
        );

        let currentStepStatus: string | null = null;
        let currentStepRequiresConfirmation = false;
        let currentStepConfirmationStatus: string | null = null;
        if (stepsResponse.ok) {
          const stepsData = await stepsResponse.json();
          const stepsArray = stepsData.steps || [];

          const currentStepIndex = exec.current_step_index ?? 0;
          const currentStep = stepsArray.find((s: any) => s.step_index === currentStepIndex + 1);
          if (currentStep) {
            currentStepStatus = currentStep.status;
            currentStepRequiresConfirmation = currentStep.requires_confirmation === true;
            currentStepConfirmationStatus = currentStep.confirmation_status || null;
          }
        }

        const execStatus = exec.status || exec.task?.status || executionStatus;
        const pausedAt = exec.paused_at;
        const executionContext = exec.task?.execution_context || exec.execution_context || {};
        const pausedAtFromContext = executionContext.paused_at;

        const shouldContinue =
          execStatus === 'waiting_confirmation' ||
          execStatus === 'paused' ||
          pausedAt !== null ||
          pausedAtFromContext !== null ||
          currentStepStatus === 'waiting_confirmation' ||
          (currentStepRequiresConfirmation && currentStepConfirmationStatus === 'pending');

        setNeedsContinue(shouldContinue);
        setCurrentStepStatus(currentStepStatus);
      } catch (err) {
        console.error('[ExecutionChatPanel] Failed to check execution status:', err);
        const shouldContinue =
          executionStatus === 'waiting_confirmation' ||
          executionStatus === 'paused';
        setNeedsContinue(shouldContinue);
      }
    };

    checkExecutionStatus();

    const interval = setInterval(checkExecutionStatus, 2000);
    return () => clearInterval(interval);
  }, [executionId, workspaceId, apiUrl, executionStatus]);

  useEffect(() => {
    if (!executionId || executionId === 'undefined') {
      setIsLoading(false);
      setMessages([]);
      return;
    }

    setMessages([]);
    setIsLoading(true);
    setIsSending(false);
    setIsWaitingForReply(false);
    thinkingMessageIdRef.current = null;
    setInput('' as any);
    setUserScrolled(false);
    setAutoScroll(true);
    userScrolledRef.current = false;
    autoScrollRef.current = true;
    setShowScrollToBottom(false);

    let cancelled = false;
    const currentExecutionId = executionId;

    const loadMessages = async () => {
      const url = `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${currentExecutionId}/chat`;

      try {
        const fetchPromise = fetch(url);

        const timeoutPromise = new Promise((_, reject) => {
          setTimeout(() => {
            reject(new Error(`Fetch timeout for executionId: ${currentExecutionId}`));
          }, 10000);
        });

        const response = await Promise.race([fetchPromise, timeoutPromise]) as Response;

        if (cancelled) {
          return;
        }

        if (response.ok) {
          const data = await response.json();
          const loadedMessages = data.messages || [];

          if (!cancelled) {
            setMessages(loadedMessages);
            setTimeout(() => {
              if (scrollToBottomRef.current && !cancelled) {
                scrollToBottomRef.current(true, true);
              }
            }, 50);
          }
        } else {
          if (!cancelled) {
            console.error('[ExecutionChatPanel] Failed to load execution chat messages:', response.status);
          }
        }
      } catch (err) {
        if (!cancelled) {
          console.error('[ExecutionChatPanel] Failed to load execution chat messages:', err);
          setIsLoading(false);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    loadMessages();

    return () => {
      cancelled = true;
    };
  }, [executionId, workspaceId, apiUrl]);

  useExecutionStream(
    executionId,
    workspaceId,
    apiUrl,
    (update) => {
      if (update.type === 'execution_chat') {
        const newMessage = update.message as ExecutionChatMessage;
        setMessages(prev => {
          const exists = prev.some(m => {
            if (m.id === newMessage.id) return true;
            if (m.role === 'user' && newMessage.role === 'user' &&
              m.content === newMessage.content &&
              Math.abs((toTimestampMs(m.created_at) ?? 0) - (toTimestampMs(newMessage.created_at) ?? 0)) < 5000) {
              return true;
            }
            return false;
          });

          if (exists) {
            const updated = prev.map(m => {
              if (m.id === newMessage.id) {
                if (m.id === thinkingMessageIdRef.current) {
                  setIsWaitingForReply(false);
                  thinkingMessageIdRef.current = null;
                }
                return newMessage;
              }
              if (m.role === 'user' && newMessage.role === 'user' &&
                m.content === newMessage.content &&
                Math.abs((toTimestampMs(m.created_at) ?? 0) - (toTimestampMs(newMessage.created_at) ?? 0)) < 5000) {
                return newMessage;
              }
              return m;
            });
            setTimeout(() => {
              if (autoScrollRef.current && !userScrolledRef.current && scrollToBottomRef.current) {
                scrollToBottomRef.current(false, true);
              }
            }, 10);
            return updated;
          } else {
            const updated = [...prev, newMessage].sort((a, b) =>
              (toTimestampMs(a.created_at) ?? 0) - (toTimestampMs(b.created_at) ?? 0)
            );
            if (newMessage.role === 'assistant' && thinkingMessageIdRef.current) {
              setIsWaitingForReply(false);
              thinkingMessageIdRef.current = null;
            }
            setTimeout(() => {
              if (autoScrollRef.current && !userScrolledRef.current && scrollToBottomRef.current) {
                scrollToBottomRef.current(false, true);
              }
            }, 10);
            return updated;
          }
        });
      }
    }
  );

  const handleScroll = useCallback(() => {
    if (!messagesScrollRef.current) return;

    const { scrollTop, scrollHeight, clientHeight } = messagesScrollRef.current;
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 150;

    if (isNearBottom) {
      setUserScrolled(false);
      setAutoScroll(true);
      userScrolledRef.current = false;
      autoScrollRef.current = true;
      setShowScrollToBottom(false);
    } else {
      setUserScrolled(true);
      setAutoScroll(false);
      userScrolledRef.current = true;
      autoScrollRef.current = false;
      setShowScrollToBottom(true);
    }
  }, []);

  useEffect(() => {
    if (messages.length > 0 && autoScrollRef.current && !userScrolledRef.current) {
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }
      scrollTimeoutRef.current = setTimeout(() => {
        if (scrollToBottomRef.current) {
          scrollToBottomRef.current(false, true);
        }
      }, 10) as ReturnType<typeof setTimeout>;
    }
    return () => {
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }
    };
  }, [messages.length]);

  useEffect(() => {
    return () => {
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 192)}px`;
    }
  }, [input]);

  const handleSend = async (
    e: React.FormEvent<HTMLFormElement> | React.KeyboardEvent<HTMLTextAreaElement>
  ) => {
    e.preventDefault();
    if (!input.trim() || isSending) return;

    const content = input.trim();
    setInput('' as any);
    setIsSending(true);

    const userMessageId = `user-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    const userMessage: ExecutionChatMessage = {
      id: userMessageId,
      execution_id: executionId,
      role: 'user',
      content: content,
      message_type: 'question',
      created_at: new Date().toISOString(),
    };

    setMessages(prev => {
      const updated = [...prev, userMessage].sort((a, b) =>
        (toTimestampMs(a.created_at) ?? 0) - (toTimestampMs(b.created_at) ?? 0)
      );
      return updated;
    });

    setUserScrolled(false);
    setAutoScroll(true);
    userScrolledRef.current = false;
    autoScrollRef.current = true;
    setTimeout(() => {
      if (scrollToBottomRef.current) {
        scrollToBottomRef.current(true, true);
      }
    }, 10);

    try {
      let response: Response;

      if (needsContinue) {
        response = await fetch(
          `${apiUrl}/api/v1/playbooks/execute/${executionId}/continue`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              user_message: content,
            }),
          }
        );
      } else {
        response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/chat`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              content,
              message_type: 'question',
            }),
          }
        );
      }

      if (!response.ok) {
        const errorText = await response.text();
        console.error('Failed to send message:', response.status, errorText);
        setMessages(prev => prev.filter(m => m.id !== userMessageId));
        setInput(content);
        setIsWaitingForReply(false);
        if (thinkingMessageIdRef.current) {
          setMessages(prev => prev.filter(m => m.id !== thinkingMessageIdRef.current));
          thinkingMessageIdRef.current = null;
        }
      } else {
        if (needsContinue) {
          const thinkingId = `thinking-${Date.now()}`;
          thinkingMessageIdRef.current = thinkingId;
          const thinkingMessage: ExecutionChatMessage = {
            id: thinkingId,
            execution_id: executionId,
            role: 'assistant',
            content: t('aiThinking' as any) || 'AI is thinking...',
            message_type: 'question',
            created_at: new Date().toISOString(),
          };

          setMessages(prev => {
            const updated = [...prev, thinkingMessage].sort((a, b) =>
              (toTimestampMs(a.created_at) ?? 0) - (toTimestampMs(b.created_at) ?? 0)
            );
            return updated;
          });

          setIsWaitingForReply(true);
        } else {
          const thinkingId = `thinking-${Date.now()}`;
          thinkingMessageIdRef.current = thinkingId;
          const thinkingMessage: ExecutionChatMessage = {
            id: thinkingId,
            execution_id: executionId,
            role: 'assistant',
            content: t('aiThinking' as any) || 'AI is thinking...',
            message_type: 'question',
            created_at: new Date().toISOString(),
          };

          setMessages(prev => {
            const updated = [...prev, thinkingMessage].sort((a, b) =>
              (toTimestampMs(a.created_at) ?? 0) - (toTimestampMs(b.created_at) ?? 0)
            );
            return updated;
          });

          setIsWaitingForReply(true);
        }

        setTimeout(() => {
          if (scrollToBottomRef.current) {
            scrollToBottomRef.current(true, true);
          }
        }, 10);
      }
    } catch (err) {
      console.error('Failed to send message:', err);
      setMessages(prev => prev.filter(m => m.id !== userMessageId));
      setInput(content);
    } finally {
      setIsSending(false);
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleQuickPrompt = async (prompt: string) => {
    setInput(prompt);
    setTimeout(() => {
      const form = document.querySelector('form') as HTMLFormElement;
      if (form) {
        form.requestSubmit();
      }
    }, 100);
  };

  return (
    <ExecutionChatPanelView
      t={t}
      isCollapsed={isCollapsed}
      collapsible={collapsible}
      runNumber={runNumber}
      playbookMetadata={playbookMetadata}
      isLoading={isLoading}
      messages={messages}
      thinkingMessageId={thinkingMessageIdRef.current}
      needsContinue={needsContinue}
      executionStatus={executionStatus}
      quickPrompts={buildExecutionChatQuickPrompts(t, executionStatus)}
      input={input}
      isSending={isSending}
      showScrollToBottom={showScrollToBottom}
      messagesEndRef={messagesEndRef}
      messagesScrollRef={messagesScrollRef}
      textareaRef={textareaRef}
      onCollapse={() => setIsCollapsed(true)}
      onExpand={() => setIsCollapsed(false)}
      onScroll={handleScroll}
      onScrollToBottom={() => scrollToBottom(true, true)}
      onQuickPrompt={handleQuickPrompt}
      onInputChange={setInput}
      onSend={handleSend}
    />
  );
}
