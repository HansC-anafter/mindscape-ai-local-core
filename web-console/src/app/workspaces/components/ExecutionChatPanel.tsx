'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useT } from '@/lib/i18n';
import { MessageItem } from '@/components/MessageItem';
import { ChatMessage } from '@/hooks/useChatEvents';

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
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesScrollRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const userScrolledRef = useRef(false);
  const autoScrollRef = useRef(true);
  const scrollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  // Load initial messages
  useEffect(() => {
    const loadMessages = async () => {
      try {
        setIsLoading(true);
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/chat`
        );
        if (response.ok) {
          const data = await response.json();
          const loadedMessages = data.messages || [];
          setMessages(loadedMessages);
          // Auto scroll to bottom after loading messages (instant)
          setTimeout(() => {
            scrollToBottom(true, true);
          }, 50);
        } else {
          console.error('Failed to load execution chat messages:', response.status);
        }
      } catch (err) {
        console.error('Failed to load execution chat messages:', err);
      } finally {
        setIsLoading(false);
      }
    };

    loadMessages();
  }, [executionId, workspaceId, apiUrl, scrollToBottom]);

  // Connect to SSE stream for real-time updates
  useEffect(() => {
    if (!executionId) return;

    const streamUrl = `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/stream`;
    const eventSource = new EventSource(streamUrl);
    eventSourceRef.current = eventSource;

    eventSource.onmessage = (event) => {
      try {
        const update = JSON.parse(event.data);

        if (update.type === 'execution_chat') {
          const newMessage = update.message as ExecutionChatMessage;
          setMessages(prev => {
            // Check if message already exists
            const exists = prev.some(m => m.id === newMessage.id);
            if (exists) {
              // Update existing message (replace thinking placeholder)
              const updated = prev.map(m => {
                if (m.id === newMessage.id) {
                  // Remove thinking state when real message arrives
                  if (m.id === thinkingMessageIdRef.current) {
                    setIsWaitingForReply(false);
                    thinkingMessageIdRef.current = null;
                  }
                  return newMessage;
                }
                return m;
              });
              // Trigger scroll after update
              setTimeout(() => {
                if (autoScrollRef.current && !userScrolledRef.current) {
                  scrollToBottom(false, true);
                }
              }, 10);
              return updated;
            } else {
              // Add new message
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
                if (autoScrollRef.current && !userScrolledRef.current) {
                  scrollToBottom(false, true);
                }
              }, 10);
              return updated;
            }
          });
        }
      } catch (err) {
        console.error('Failed to parse SSE message:', err);
      }
    };

    eventSource.onerror = (error) => {
      if (eventSourceRef.current && eventSourceRef.current.readyState === EventSource.CLOSED) {
        console.warn('SSE connection closed');
      }
    };

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [executionId, workspaceId, apiUrl]);

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
      scrollTimeoutRef.current = setTimeout(() => {
        scrollToBottom(false, true);
      }, 10) as ReturnType<typeof setTimeout>;
    }
    return () => {
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }
    };
  }, [messages.length, scrollToBottom]);

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
    setInput('');
    setIsSending(true);

    try {
      const response = await fetch(
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

      if (!response.ok) {
        const errorText = await response.text();
        console.error('Failed to send message:', response.status, errorText);
        // Restore input on error
        setInput(content);
        setIsWaitingForReply(false);
        if (thinkingMessageIdRef.current) {
          setMessages(prev => prev.filter(m => m.id !== thinkingMessageIdRef.current));
          thinkingMessageIdRef.current = null;
        }
      } else {
        // Message sent successfully
        // Add thinking placeholder message immediately
        const thinkingId = `thinking-${Date.now()}`;
        thinkingMessageIdRef.current = thinkingId;
        const thinkingMessage: ExecutionChatMessage = {
          id: thinkingId,
          execution_id: executionId,
          role: 'assistant',
          content: t('aiThinking'),
          message_type: 'question',
          created_at: new Date().toISOString(),
        };

        setMessages(prev => {
          // User message will be added by SSE, we just add thinking placeholder
          const updated = [...prev, thinkingMessage].sort((a, b) =>
            new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
          );
          return updated;
        });

        setIsWaitingForReply(true);

        // Scroll to bottom immediately (instant, no smooth)
        setUserScrolled(false);
        setAutoScroll(true);
        userScrolledRef.current = false;
        autoScrollRef.current = true;
        setTimeout(() => {
          scrollToBottom(true, true);
        }, 10);
      }
    } catch (err) {
      console.error('Failed to send message:', err);
      // Restore input on error
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
      label: t('explainWhyFailed'),
      prompt: executionStatus === 'failed'
        ? t('explainWhyFailedPrompt')
        : t('explainWhyFailedPromptAlt')
    },
    {
      label: t('suggestNextSteps'),
      prompt: t('suggestNextStepsPrompt')
    },
    {
      label: t('reviewPlaybookSteps'),
      prompt: t('reviewPlaybookStepsPrompt')
    },
  ];

  if (isCollapsed && collapsible) {
    return (
      <div className="flex-shrink-0 border-l bg-white">
        <button
          onClick={() => setIsCollapsed(false)}
          className="w-full px-4 py-3 text-left hover:bg-gray-50 border-b transition-colors"
        >
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-gray-900">{t('playbookInspector')}</h3>
              <p className="text-xs text-gray-500 mt-0.5">{t('runNumber', { number: String(runNumber) })}</p>
            </div>
            <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </div>
        </button>
      </div>
    );
  }

  return (
    <div className="execution-chat-container flex flex-col h-full border-l bg-white">
      {/* Header */}
      <div className="flex-shrink-0 px-4 py-3 border-b bg-white">
        <div className="flex items-center justify-between">
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-gray-900">{t('playbookInspector')}</h3>
            <p className="text-xs text-gray-600 mt-0.5">
              {playbookMetadata?.title || playbookMetadata?.playbook_code || t('unknownPlaybook')} · {t('runNumber', { number: String(runNumber) })}
            </p>
          </div>
          {collapsible && (
            <button
              onClick={() => setIsCollapsed(true)}
              className="ml-2 text-gray-400 hover:text-gray-600 transition-colors"
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
        {isLoading ? (
          <div className="flex justify-center py-8">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
          </div>
        ) : messages.length === 0 ? (
          <div className="py-6">
            <div className="text-center mb-4">
              <p className="text-sm text-gray-600 mb-2">
                {t('askPlaybookInspector')}
              </p>
              <p className="text-xs text-gray-500">
                {t('itKnowsStepsEventsErrors')}
              </p>
            </div>
            <div className="space-y-2">
              {quickPrompts.map((quickPrompt, idx) => {
                const isFirstAndFailed = idx === 0 && executionStatus === 'failed';
                return (
                  <button
                    key={idx}
                    onClick={() => handleQuickPrompt(quickPrompt.prompt)}
                    className={`w-full text-left px-3 py-2 text-sm text-gray-700 bg-gray-50 border border-gray-200 rounded-md hover:bg-gray-100 hover:border-gray-300 transition-colors ${
                      isFirstAndFailed ? 'ring-2 ring-blue-200 border-blue-300 bg-blue-50' : ''
                    }`}
                  >
                    {quickPrompt.label}
                    {isFirstAndFailed && (
                      <span className="ml-2 text-xs text-blue-600">{t('recommended')}</span>
                    )}
                  </button>
                );
              })}
            </div>
            {executionStatus === 'failed' && quickPrompts.length > 0 && (
              <div className="mt-4 pt-4 border-t border-gray-200">
                <button
                  onClick={() => handleQuickPrompt(quickPrompts[0].prompt)}
                  className="w-full px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 transition-colors"
                >
                  {t('autoStart')} {quickPrompts[0].label}
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
                    <div className="flex items-center gap-2 mt-1 ml-4 text-xs text-gray-500">
                      <div className="w-1 h-1 bg-gray-400 rounded-full animate-pulse" style={{ animationDelay: '0ms' }} />
                      <div className="w-1 h-1 bg-gray-400 rounded-full animate-pulse" style={{ animationDelay: '150ms' }} />
                      <div className="w-1 h-1 bg-gray-400 rounded-full animate-pulse" style={{ animationDelay: '300ms' }} />
                    </div>
                  )}
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>
        )}
        </div>

        {/* Scroll to bottom button - fixed to visible viewport center bottom */}
        {showScrollToBottom && (
          <button
            onClick={() => scrollToBottom(true, true)}
            className="absolute bottom-4 left-1/2 transform -translate-x-1/2 z-50 bg-blue-500 hover:bg-blue-600 text-white rounded-full p-1.5 shadow-lg transition-all duration-200 hover:scale-110"
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
        className="flex-shrink-0 relative border-t bg-gray-50"
      >
        <textarea
          ref={textareaRef}
          name="execution-chat-input"
          placeholder={t('discussPlaybookExecution')}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend(e);
            }
          }}
          className="w-full px-4 py-3 resize-none border-0 focus:outline-none focus:ring-0 bg-transparent"
          rows={1}
          style={{ minHeight: '3rem', maxHeight: '12rem' }}
          disabled={isSending}
        />
        {!input.trim() && !isSending && (
          <div className="absolute right-4 bottom-3 text-gray-400">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
          </div>
        )}
        {isSending && (
          <div className="absolute right-4 bottom-3 p-2">
            <div className="w-5 h-5 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
          </div>
        )}
      </form>
    </div>
  );
}

