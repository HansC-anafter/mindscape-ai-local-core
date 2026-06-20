'use client';

import React from 'react';

import { MessageItem } from '@/components/MessageItem';
import type { ChatMessage } from '@/hooks/useChatEvents';
import { parseServerTimestamp } from '@/lib/time';

import type { ExecutionChatMessage, PlaybookMetadata, QuickPrompt } from './types';

interface ExecutionChatPanelViewProps {
  t: (key: any, params?: any) => string;
  isCollapsed: boolean;
  collapsible: boolean;
  runNumber: number;
  playbookMetadata?: PlaybookMetadata;
  isLoading: boolean;
  messages: ExecutionChatMessage[];
  thinkingMessageId: string | null;
  needsContinue: boolean;
  executionStatus?: string;
  quickPrompts: QuickPrompt[];
  input: string;
  isSending: boolean;
  showScrollToBottom: boolean;
  messagesEndRef: React.RefObject<HTMLDivElement>;
  messagesScrollRef: React.RefObject<HTMLDivElement>;
  textareaRef: React.RefObject<HTMLTextAreaElement>;
  onCollapse: () => void;
  onExpand: () => void;
  onScroll: () => void;
  onScrollToBottom: () => void;
  onQuickPrompt: (prompt: string) => void | Promise<void>;
  onInputChange: (value: string) => void;
  onSend: (
    event: React.FormEvent<HTMLFormElement> | React.KeyboardEvent<HTMLTextAreaElement>
  ) => void | Promise<void>;
}

function convertToChatMessage(msg: ExecutionChatMessage): ChatMessage {
  return {
    id: msg.id,
    role: msg.role === 'user' ? 'user' : 'assistant',
    content: msg.content,
    timestamp: parseServerTimestamp(msg.created_at) ?? new Date(),
  };
}

export function ExecutionChatPanelView({
  t,
  isCollapsed,
  collapsible,
  runNumber,
  playbookMetadata,
  isLoading,
  messages,
  thinkingMessageId,
  needsContinue,
  executionStatus,
  quickPrompts,
  input,
  isSending,
  showScrollToBottom,
  messagesEndRef,
  messagesScrollRef,
  textareaRef,
  onCollapse,
  onExpand,
  onScroll,
  onScrollToBottom,
  onQuickPrompt,
  onInputChange,
  onSend,
}: ExecutionChatPanelViewProps) {
  if (isCollapsed && collapsible) {
    return (
      <div className="flex-shrink-0 border-l dark:border-gray-700 bg-surface-secondary dark:bg-gray-900">
        <button
          onClick={onExpand}
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
      <div className="flex-shrink-0 px-4 py-3 border-b dark:border-gray-700 bg-surface-secondary dark:bg-gray-900">
        <div className="flex items-center justify-between">
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">{t('playbookInspector' as any)}</h3>
            <p className="text-xs text-gray-600 dark:text-gray-400 mt-0.5">
              {playbookMetadata?.title || playbookMetadata?.playbook_code || t('unknownPlaybook' as any)} - {t('runNumber', { number: String(runNumber) })}
            </p>
          </div>
          {collapsible && (
            <button
              onClick={onCollapse}
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

      <div className="flex-1 relative" style={{ minHeight: 0 }}>
        <div
          ref={messagesScrollRef}
          onScroll={onScroll}
          className="h-full overflow-y-auto px-4 pt-4"
        >
          {isLoading ? (
            <div className="flex justify-center py-8">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600 dark:border-blue-500"></div>
            </div>
          ) : messages.length === 0 ? (
            <div className="py-6">
              <div className="text-center mb-4">
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                  {needsContinue
                    ? t('playbookWaitingForResponse' as any) || 'Playbook is waiting for your response'
                    : t('askPlaybookInspector' as any)}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {needsContinue
                    ? t('sendMessageToContinue' as any) || 'Send a message to continue to the next step.'
                    : t('itKnowsStepsEventsErrors' as any)}
                </p>
              </div>
              <div className="space-y-2">
                {quickPrompts.map((quickPrompt, idx) => {
                  const isFirstAndFailed = idx === 0 && executionStatus === 'failed';
                  return (
                    <button
                      key={idx}
                      onClick={() => onQuickPrompt(quickPrompt.prompt)}
                      className={`w-full text-left px-3 py-2 text-sm text-gray-700 dark:text-gray-300 bg-surface-accent dark:bg-gray-800 border border-default dark:border-gray-700 rounded-md hover:bg-tertiary dark:hover:bg-gray-700 hover:border-default dark:hover:border-gray-600 transition-colors ${isFirstAndFailed ? 'ring-2 ring-accent/30 dark:ring-blue-800 border-accent/30 dark:border-blue-700 bg-accent-10 dark:bg-blue-900/20' : ''
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
                    onClick={() => onQuickPrompt(quickPrompts[0].prompt)}
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
                const isThinking = message.id === thinkingMessageId;
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
          )}
        </div>

        {showScrollToBottom && (
          <button
            onClick={onScrollToBottom}
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

      <form
        onSubmit={onSend}
        className="flex-shrink-0 relative border-t dark:border-gray-700 bg-surface-secondary dark:bg-gray-800"
      >
        <textarea
          ref={textareaRef}
          name="execution-chat-input"
          placeholder={
            needsContinue
              ? t('enterResponseToContinue' as any) || 'Enter a response to continue...'
              : t('discussPlaybookExecution' as any)
          }
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              onSend(e);
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
