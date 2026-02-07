'use client';

import React, { useRef, useEffect } from 'react';
import { t } from '@/lib/i18n';
import { useMessages } from '@/contexts/MessagesContext';
import { useUIState } from '@/contexts/UIStateContext';
import { useWorkspaceRefs } from '@/contexts/WorkspaceRefsContext';
import { useScrollManagement } from '@/hooks/useScrollManagement';
import { ChatMessage } from '@/hooks/useChatEvents';
import { MessageWithSuggestions } from './MessageWithSuggestions';
import type { Suggestion } from './SuggestionChip';
import { ExecutionTree } from '../execution';
import { ExecutionModeNotice } from './ExecutionModeNotice';
import { ErrorDisplay } from './ErrorDisplay';
import { ProcessingIndicator } from './ProcessingIndicator';

interface MessagesContainerProps {
  workspaceId: string;
  apiUrl: string;
  executionMode?: 'qa' | 'execution' | 'hybrid';
  expectedArtifacts?: string[];
  onExecuteSuggestion?: (suggestion: Suggestion) => Promise<void>;
  currentExecution?: any;
  onViewDetail?: () => void;
}

/**
 * MessagesContainer Component
 * Container for displaying messages, execution tree, and related UI elements.
 *
 * @param workspaceId The workspace ID.
 * @param apiUrl The base API URL.
 * @param executionMode Optional execution mode.
 * @param expectedArtifacts Optional array of expected artifact types.
 * @param onExecuteSuggestion Optional callback for executing suggestions.
 * @param currentExecution Optional current execution data.
 * @param onViewDetail Optional callback for viewing execution details.
 */
export function MessagesContainer({
  workspaceId,
  apiUrl,
  executionMode,
  expectedArtifacts,
  onExecuteSuggestion,
  currentExecution,
  onViewDetail,
}: MessagesContainerProps) {
  const {
    messages,
    messagesLoading,
    messagesError,
    loadingMore,
    reloadMessages,
    executionTree,
    pipelineStage,
  } = useMessages();

  const { isStreaming, firstChunkReceived } = useUIState();

  const { messagesScrollRef } = useWorkspaceRefs();
  const { showScrollToBottom, scrollToBottom } = useScrollManagement();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const handleExecuteSuggestion = async (suggestion: Suggestion) => {
    if (onExecuteSuggestion) {
      await onExecuteSuggestion(suggestion);
    }
  };

  return (
    <div
      ref={messagesScrollRef}
      className="flex-1 overflow-y-auto"
      style={{ height: '100%', minHeight: 0 }}
    >
      {loadingMore && (
        <div className="flex justify-center py-2">
          <div className="text-xs text-secondary dark:text-gray-300 flex items-center gap-2">
            <div
              className="w-4 h-4 border-2 border-tertiary dark:border-gray-200 border-t-transparent rounded-full"
              style={{ animation: 'spin 1s linear infinite' }}
            />
            <span>Loading older messages...</span>
          </div>
        </div>
      )}

      <ExecutionModeNotice
        executionMode={executionMode || 'qa'}
        expectedArtifacts={expectedArtifacts}
      />

      <ErrorDisplay
        error={messagesError}
        onRetry={reloadMessages}
      />

      {messages.length === 0 && !messagesLoading && !messagesError ? (
        <div className="text-center text-secondary dark:text-gray-300 mt-8">
          <p>{t('noMessagesYet' as any)}</p>
        </div>
      ) : messages.length > 0 ? (
        <div className="space-y-2 pb-4">
          {messages
            .filter((message) => message.event_type !== 'playbook_step')
            .map((message) => {
              const suggestions: Suggestion[] | undefined = message.suggestions
                ? message.suggestions.map((s, idx) => {
                  if (typeof s === 'string') {
                    return {
                      id: `suggestion-${message.id}-${idx}`,
                      title: s,
                      playbookCode: s,
                    };
                  }
                  return s as Suggestion;
                })
                : undefined;

              return (
                <MessageWithSuggestions
                  key={message.id}
                  message={message}
                  suggestions={suggestions}
                  onExecuteSuggestion={handleExecuteSuggestion}
                  workspaceId={workspaceId}
                  apiUrl={apiUrl}
                />
              );
            })}
        </div>
      ) : null}

      {executionTree && executionTree.length > 0 && (
        <div className="mt-4 mb-2">
          <div className="bg-gradient-to-r from-accent-10 to-purple-50/80 dark:from-blue-900/20 dark:to-purple-900/20 rounded-lg border border-accent/30 dark:border-blue-800 shadow-sm">
            <div className="px-4 py-3">
              <ExecutionTree
                steps={executionTree}
                isCollapsed={false}
                executionId={currentExecution?.executionId}
                onHeaderClick={() => {
                  if (currentExecution && onViewDetail) {
                    onViewDetail();
                  }
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Thinking / Processing indicator */}
      <ProcessingIndicator
        visible={isStreaming || !!pipelineStage}
        isStreaming={isStreaming}
        firstChunkReceived={firstChunkReceived}
        pipelineStage={pipelineStage?.message}
      />

      <div ref={messagesEndRef} />

      {showScrollToBottom && (
        <button
          onClick={() => scrollToBottom(true)}
          className="absolute bottom-4 left-1/2 transform -translate-x-1/2 z-50 bg-accent dark:bg-blue-500 hover:bg-accent/90 dark:hover:bg-blue-600 text-white rounded-full p-1.5 shadow-lg transition-all duration-200 hover:scale-110"
          aria-label="Scroll to bottom"
          title="Scroll to bottom"
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
  );
}

