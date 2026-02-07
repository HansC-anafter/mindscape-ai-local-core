'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useT } from '@/lib/i18n';
import { MessageItem } from '@/components/MessageItem';
import { ChatMessage } from '@/hooks/useChatEvents';
import { useExecutionStream } from '@/hooks/useExecutionStream';

interface ExecutionChatMessage {
  id: string;
  execution_id: string;
  step_id?: string;
  role: 'user' | 'assistant' | 'agent';
  speaker?: string;
  content: string;
  message_type: 'question' | 'note' | 'route_proposal' | 'system_hint';
  created_at: string;
}

interface PlaybookMetadata {
  playbook_code: string;
  title?: string;
  description?: string;
  supports_execution_chat?: boolean;
  discussion_agent?: string;
  [key: string]: any;
}

interface ExecutionChatPanelProps {
  executionId: string;
  workspaceId: string;
  apiUrl: string;
  playbookMetadata?: PlaybookMetadata;
  executionStatus?: string;
  runNumber?: number;
  collapsible?: boolean;
  defaultCollapsed?: boolean;
}

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
  const eventSourceRef = useRef<EventSource | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const userScrolledRef = useRef(false);
  const autoScrollRef = useRef(true);
  const scrollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scrollToBottomRef = useRef<((force?: boolean, instant?: boolean) => void) | null>(null);

  // Scroll to bottom function - optimized to avoid jumping to top
  const scrollToBottom = useCallback((force: boolean = false, instant: boolean = false) => {
    if (!messagesScrollRef.current) return;

    if (force || instant) {
      // Direct scroll without smooth behavior to avoid jumping
      messagesScrollRef.current.scrollTop = messagesScrollRef.current.scrollHeight;
      setAutoScroll(true);
      setUserScrolled(false);
      userScrolledRef.current = false;
      autoScrollRef.current = true;
      setShowScrollToBottom(false);
    } else if (autoScrollRef.current && !userScrolledRef.current && messages.length > 0) {
      // Only use smooth scroll if already near bottom
      const { scrollTop, scrollHeight, clientHeight } = messagesScrollRef.current;
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;
      if (isNearBottom) {
        messagesScrollRef.current.scrollTop = messagesScrollRef.current.scrollHeight;
      }
    }
  }, [messages.length]);

  // Keep scrollToBottom ref in sync
  useEffect(() => {
    scrollToBottomRef.current = scrollToBottom;
  }, [scrollToBottom]);

  // Check execution status to determine if we need to continue execution
  useEffect(() => {
    const checkExecutionStatus = async () => {
      try {
        // Get execution details
        const execResponse = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}`
        );
        if (!execResponse.ok) {
          throw new Error(`Failed to fetch execution: ${execResponse.status}`);
        }
        const exec = await execResponse.json();

        // Get execution steps to find current step
        const stepsResponse = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/steps`
        );

        let currentStepStatus: string | null = null;
        let currentStepRequiresConfirmation = false;
        let currentStepConfirmationStatus: string | null = null;
        if (stepsResponse.ok) {
          const stepsData = await stepsResponse.json();
          const stepsArray = stepsData.steps || [];

          // Find current step based on current_step_index
          const currentStepIndex = exec.current_step_index ?? 0;
          const currentStep = stepsArray.find((s: any) => s.step_index === currentStepIndex + 1);
          if (currentStep) {
            currentStepStatus = currentStep.status;
            currentStepRequiresConfirmation = currentStep.requires_confirmation === true;
            currentStepConfirmationStatus = currentStep.confirmation_status || null;
          }
        }

        // Get status from execution or task
        const execStatus = exec.status || exec.task?.status || executionStatus;
        const pausedAt = exec.paused_at;
        const executionContext = exec.task?.execution_context || exec.execution_context || {};
        const pausedAtFromContext = executionContext.paused_at;

        // Determine if we need to continue execution
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
        // Fallback: use executionStatus prop
        const shouldContinue =
          executionStatus === 'waiting_confirmation' ||
          executionStatus === 'paused';
        setNeedsContinue(shouldContinue);
      }
    };

    checkExecutionStatus();

    // Poll execution status if execution is running (every 2 seconds)
    const interval = setInterval(checkExecutionStatus, 2000);
    return () => clearInterval(interval);
  }, [executionId, workspaceId, apiUrl, executionStatus]);

  // Load initial messages
  useEffect(() => {
    // Skip if executionId is invalid
    if (!executionId || executionId === 'undefined') {
      setIsLoading(false);
      setMessages([]);
      return;
    }

    // Reset state when executionId changes
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

        // Add timeout and error handling
        const timeoutPromise = new Promise((_, reject) => {
          setTimeout(() => {
            reject(new Error(`Fetch timeout for executionId: ${currentExecutionId}`));
          }, 10000); // 10 second timeout
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
            // Auto scroll to bottom after loading messages (instant)
            // Use ref to avoid dependency on scrollToBottom function
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
          // Still set loading to false even on error
          setIsLoading(false);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    loadMessages();

    // Cleanup function to cancel request if executionId changes
    return () => {
      cancelled = true;
    };
  }, [executionId, workspaceId, apiUrl]);

  // Connect to SSE stream for real-time updates using unified stream manager
  useExecutionStream(
    executionId,
    workspaceId,
    apiUrl,
    (update) => {
      if (update.type === 'execution_chat') {
        const newMessage = update.message as ExecutionChatMessage;
        setMessages(prev => {
          // Check if message already exists (by id or by content for user messages)
          const exists = prev.some(m => {
            if (m.id === newMessage.id) return true;
            // For user messages, also check by content and timestamp to avoid duplicates
            if (m.role === 'user' && newMessage.role === 'user' &&
                m.content === newMessage.content &&
                Math.abs(new Date(m.created_at).getTime() - new Date(newMessage.created_at).getTime()) < 5000) {
              return true;
            }
            return false;
          });

          if (exists) {
            // Update existing message (replace thinking placeholder or update user message)
            const updated = prev.map(m => {
              if (m.id === newMessage.id) {
                // Remove thinking state when real message arrives
                if (m.id === thinkingMessageIdRef.current) {
                  setIsWaitingForReply(false);
                  thinkingMessageIdRef.current = null;
                }
                return newMessage;
              }
              // Also update user message if content matches (SSE returned the same user message)
              if (m.role === 'user' && newMessage.role === 'user' &&
                  m.content === newMessage.content &&
                  Math.abs(new Date(m.created_at).getTime() - new Date(newMessage.created_at).getTime()) < 5000) {
                // Use the server's version which has the correct id
                return newMessage;
              }
              return m;
            });
            // Trigger scroll after update
            setTimeout(() => {
              if (autoScrollRef.current && !userScrolledRef.current && scrollToBottomRef.current) {
                scrollToBottomRef.current(false, true);
              }
            }, 10);
            return updated;
          } else {
            // Add new message (from SSE)
            const updated = [...prev, newMessage].sort((a, b) =>
              new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
            );
            // Remove thinking state when real message arrives
            if (newMessage.role === 'assistant' && thinkingMessageIdRef.current) {
              setIsWaitingForReply(false);
              thinkingMessageIdRef.current = null;
            }
            // Trigger scroll after adding new message
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

  // Handle scroll events to detect user manual scrolling
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

  // Auto scroll to bottom when new messages arrive (only if user is at bottom)
  useEffect(() => {
    if (messages.length > 0 && autoScrollRef.current && !userScrolledRef.current) {
      // Clear any existing timeout
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }
      // Use instant scroll for better UX
      // Use ref to avoid dependency on scrollToBottom function
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

  // Cleanup scroll timeout on unmount
  useEffect(() => {
    return () => {
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }
    };
  }, []);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 192)}px`;
    }
  }, [input]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isSending) return;

    const content = input.trim();
    setInput('' as any);
    setIsSending(true);

    // Immediately add user message to UI for instant feedback
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
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
      );
      return updated;
    });

    // Scroll to bottom immediately after adding user message
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

      // Determine which API to use based on execution status
      if (needsContinue) {
        // Scenario A: Continue execution
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
        // Scenario B: Discussion and optimization
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
        // Remove user message on error and restore input
        setMessages(prev => prev.filter(m => m.id !== userMessageId));
        setInput(content);
        setIsWaitingForReply(false);
        if (thinkingMessageIdRef.current) {
          setMessages(prev => prev.filter(m => m.id !== thinkingMessageIdRef.current));
          thinkingMessageIdRef.current = null;
        }
      } else {
        // Message sent successfully
        if (needsContinue) {
          // For continue API, add thinking placeholder to show LLM is processing
          const thinkingId = `thinking-${Date.now()}`;
          thinkingMessageIdRef.current = thinkingId;
          const thinkingMessage: ExecutionChatMessage = {
            id: thinkingId,
            execution_id: executionId,
            role: 'assistant',
            content: t('aiThinking' as any) || 'AI 正在思考...',
            message_type: 'question',
            created_at: new Date().toISOString(),
          };

          setMessages(prev => {
            const updated = [...prev, thinkingMessage].sort((a, b) =>
              new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
            );
            return updated;
          });

          setIsWaitingForReply(true);
        } else {
          // For chat API, add thinking placeholder
          const thinkingId = `thinking-${Date.now()}`;
          thinkingMessageIdRef.current = thinkingId;
          const thinkingMessage: ExecutionChatMessage = {
            id: thinkingId,
            execution_id: executionId,
            role: 'assistant',
            content: t('aiThinking' as any) || 'AI 正在思考...',
            message_type: 'question',
            created_at: new Date().toISOString(),
          };

          setMessages(prev => {
            const updated = [...prev, thinkingMessage].sort((a, b) =>
              new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
            );
            return updated;
          });

          setIsWaitingForReply(true);
        }

        // Scroll to bottom after adding thinking message
        setTimeout(() => {
          if (scrollToBottomRef.current) {
            scrollToBottomRef.current(true, true);
          }
        }, 10);
      }
    } catch (err) {
      console.error('Failed to send message:', err);
      // Remove user message on error and restore input
      setMessages(prev => prev.filter(m => m.id !== userMessageId));
      setInput(content);
    } finally {
      setIsSending(false);
      // Reset textarea height
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  // Convert ExecutionChatMessage to ChatMessage for MessageItem
  const convertToChatMessage = (msg: ExecutionChatMessage): ChatMessage => {
    return {
      id: msg.id,
      role: msg.role === 'user' ? 'user' : 'assistant',
      content: msg.content,
      timestamp: new Date(msg.created_at),
    };
  };

  const handleQuickPrompt = async (prompt: string) => {
    setInput(prompt);
    // Auto-submit after a short delay
    setTimeout(() => {
      const form = document.querySelector('form') as HTMLFormElement;
      if (form) {
        form.requestSubmit();
      }
    }, 100);
  };

  const quickPrompts = [
    {
      label: t('explainWhyFailed' as any),
      prompt: executionStatus === 'failed'
        ? t('explainWhyFailedPrompt' as any)
        : t('explainWhyFailedPromptAlt' as any)
    },
    {
      label: t('suggestNextSteps' as any),
      prompt: t('suggestNextStepsPrompt' as any)
    },
    {
      label: t('reviewPlaybookSteps' as any),
      prompt: t('reviewPlaybookStepsPrompt' as any)
    },
  ];

  if (isCollapsed && collapsible) {
    return (
      <div className="flex-shrink-0 border-l dark:border-gray-700 bg-surface-secondary dark:bg-gray-900">
        <button
          onClick={() => setIsCollapsed(false)}
          className="w-full px-4 py-3 text-left hover:bg-tertiary dark:hover:bg-gray-800 border-b dark:border-gray-700 transition-colors"
        >
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">{t('playbookInspector' as any)}</h3>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{t('runNumber', { number: String(runNumber) })}</p>
            </div>
            <svg className="w-5 h-5 text-gray-400 dark:text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </div>
        </button>
      </div>
    );
  }

  return (
    <div className="execution-chat-container flex flex-col h-full border-l dark:border-gray-700 bg-surface-secondary dark:bg-gray-900">
      {/* Header */}
      <div className="flex-shrink-0 px-4 py-3 border-b dark:border-gray-700 bg-surface-secondary dark:bg-gray-900">
        <div className="flex items-center justify-between">
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">{t('playbookInspector' as any)}</h3>
            <p className="text-xs text-gray-600 dark:text-gray-400 mt-0.5">
              {playbookMetadata?.title || playbookMetadata?.playbook_code || t('unknownPlaybook' as any)} · {t('runNumber', { number: String(runNumber) })}
            </p>
          </div>
          {collapsible && (
            <button
              onClick={() => setIsCollapsed(true)}
              className="ml-2 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
              title="Collapse"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Messages List Container - with relative positioning for scroll button */}
      <div className="flex-1 relative" style={{ minHeight: 0 }}>
        <div
          ref={messagesScrollRef}
          onScroll={handleScroll}
          className="h-full overflow-y-auto px-4 pt-4"
        >
        {(() => {
          return isLoading ? (
            <div className="flex justify-center py-8">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600 dark:border-blue-500"></div>
            </div>
          ) : messages.length === 0 ? (
          <div className="py-6">
            <div className="text-center mb-4">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                {needsContinue
                  ? t('playbookWaitingForResponse' as any) || 'Playbook 正在等待您的回應'
                  : t('askPlaybookInspector' as any)}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {needsContinue
                  ? t('sendMessageToContinue' as any) || '發送消息將繼續執行下一步。'
                  : t('itKnowsStepsEventsErrors' as any)}
              </p>
            </div>
            <div className="space-y-2">
              {quickPrompts.map((quickPrompt, idx) => {
                const isFirstAndFailed = idx === 0 && executionStatus === 'failed';
                return (
                  <button
                    key={idx}
                    onClick={() => handleQuickPrompt(quickPrompt.prompt)}
                    className={`w-full text-left px-3 py-2 text-sm text-gray-700 dark:text-gray-300 bg-surface-accent dark:bg-gray-800 border border-default dark:border-gray-700 rounded-md hover:bg-tertiary dark:hover:bg-gray-700 hover:border-default dark:hover:border-gray-600 transition-colors ${
                      isFirstAndFailed ? 'ring-2 ring-accent/30 dark:ring-blue-800 border-accent/30 dark:border-blue-700 bg-accent-10 dark:bg-blue-900/20' : ''
                    }`}
                  >
                    {quickPrompt.label}
                    {isFirstAndFailed && (
                      <span className="ml-2 text-xs text-blue-600 dark:text-blue-400">{t('recommended' as any)}</span>
                    )}
                  </button>
                );
              })}
            </div>
            {executionStatus === 'failed' && quickPrompts.length > 0 && (
              <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                <button
                  onClick={() => handleQuickPrompt(quickPrompts[0].prompt)}
                  className="w-full px-4 py-2 text-sm font-medium text-white bg-blue-600 dark:bg-blue-700 rounded-md hover:bg-blue-700 dark:hover:bg-blue-600 transition-colors"
                >
                  {t('autoStart' as any)} {quickPrompts[0].label}
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-2 pb-4">
            {messages.map((message) => {
              const isThinking = message.id === thinkingMessageIdRef.current;
              const chatMessage = convertToChatMessage(message);
              return (
                <div key={message.id} className={isThinking ? 'opacity-70' : ''}>
                  <MessageItem message={chatMessage} />
                  {isThinking && (
                    <div className="flex items-center gap-2 mt-1 ml-4 text-xs text-gray-500 dark:text-gray-400">
                      <div className="w-1 h-1 bg-gray-400 dark:bg-gray-500 rounded-full animate-pulse" style={{ animationDelay: '0ms' }} />
                      <div className="w-1 h-1 bg-gray-400 dark:bg-gray-500 rounded-full animate-pulse" style={{ animationDelay: '150ms' }} />
                      <div className="w-1 h-1 bg-gray-400 dark:bg-gray-500 rounded-full animate-pulse" style={{ animationDelay: '300ms' }} />
                    </div>
                  )}
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>
        );
        })()}
        </div>

        {/* Scroll to bottom button - fixed to visible viewport center bottom */}
        {showScrollToBottom && (
          <button
            onClick={() => {
              if (scrollToBottomRef.current) {
                scrollToBottomRef.current(true, true);
              }
            }}
            className="absolute bottom-4 left-1/2 transform -translate-x-1/2 z-50 bg-blue-500 dark:bg-blue-600 hover:bg-blue-600 dark:hover:bg-blue-500 text-white rounded-full p-1.5 shadow-lg transition-all duration-200 hover:scale-110"
            aria-label="Scroll to bottom"
            title="Scroll to bottom"
            style={{ pointerEvents: 'auto' }}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-3 w-3"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 14l-7 7m0 0l-7-7m7 7V3"
              />
            </svg>
          </button>
        )}
      </div>

      {/* Input Form */}
      <form
        onSubmit={handleSend}
        className="flex-shrink-0 relative border-t dark:border-gray-700 bg-surface-secondary dark:bg-gray-800"
      >
        <textarea
          ref={textareaRef}
          name="execution-chat-input"
          placeholder={
            needsContinue
              ? t('enterResponseToContinue' as any) || '輸入回應以繼續執行...'
              : t('discussPlaybookExecution' as any)
          }
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend(e);
            }
          }}
          className="w-full px-4 py-3 resize-none border-0 focus:outline-none focus:ring-0 bg-transparent text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
          rows={1}
          style={{ minHeight: '3rem', maxHeight: '12rem' }}
          disabled={isSending}
        />
        {!input.trim() && !isSending && (
          <div className="absolute right-4 bottom-3 text-gray-400 dark:text-gray-500">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
          </div>
        )}
        {isSending && (
          <div className="absolute right-4 bottom-3 p-2">
            <div className="w-5 h-5 border-2 border-gray-400 dark:border-gray-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}
      </form>
    </div>
  );
}

