'use client';

import React, { createContext, useContext, useMemo, useEffect, ReactNode } from 'react';
import { useChatEvents, ChatMessage } from '@/hooks/useChatEvents';
import { useMessageStream } from '@/hooks/useMessageStream';
import { useExecutionState, ExecutionUIState, PipelineStage, TreeStep } from '@/hooks/useExecutionState';
import { useCurrentExecution } from '@/hooks/useCurrentExecution';
import type { CurrentExecution } from '@/components/workspace/CurrentExecutionBar';

export interface MessagesState {
  messages: ChatMessage[];
  setMessages: (messages: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])) => void;
  messagesLoading: boolean;
  messagesError: string | null;
  quickStartSuggestions: string[];
  fileAnalysisResult: any;
  setFileAnalysisResult: (value: any) => void;
  hasMore: boolean;
  loadingMore: boolean;
  loadMore: () => Promise<void>;
  reloadMessages: () => Promise<void>;
  sseConnected: boolean;  // 🆕 SSE connection status

  executionState: ExecutionUIState;
  pipelineStage: PipelineStage | null;
  executionTree: TreeStep[];

  currentExecution: CurrentExecution | null;
  handleViewDetail: (executionId: string) => void;
  handlePause: (executionId: string) => void;
  handleCancel: (executionId: string) => void;
}

interface MessagesProviderProps {
  children: ReactNode;
  workspaceId: string;
  apiUrl?: string;
  threadId?: string | null;
}

const MessagesContext = createContext<MessagesState | null>(null);

export function MessagesProvider({
  children,
  workspaceId,
  apiUrl = '',
  threadId
}: MessagesProviderProps) {
  // HTTP-based initial load
  const chatEvents = useChatEvents(workspaceId, apiUrl, { threadId });

  // 🆕 SSE-based real-time stream
  const messageStream = useMessageStream(workspaceId, apiUrl, { threadId, enabled: true });

  const executionStateHook = useExecutionState(workspaceId, apiUrl);
  const currentExecutionHook = useCurrentExecution(workspaceId, apiUrl);

  const {
    messages: initialMessages,
    setMessages,
    loading: messagesLoading,
    error: messagesError,
    quickStartSuggestions,
    fileAnalysisResult,
    setFileAnalysisResult,
    hasMore,
    loadingMore,
    loadMore,
    reload: reloadMessages,
  } = chatEvents;

  const {
    streamedMessages,
    connected: sseConnected,
    markManyAsSeen,
    clearStreamedMessages,
  } = messageStream;

  // 🆕 Mark initial messages as seen to prevent duplicates from SSE
  useEffect(() => {
    if (initialMessages.length > 0) {
      markManyAsSeen(initialMessages.map(m => m.id));
    }
  }, [initialMessages, markManyAsSeen]);

  // 🆕 Clear streamed messages when doing a full reload
  useEffect(() => {
    if (messagesLoading) {
      clearStreamedMessages();
    }
  }, [messagesLoading, clearStreamedMessages]);

  // 🆕 Merge initial messages with SSE streamed messages
  const messages = useMemo(() => {
    if (streamedMessages.length === 0) {
      return initialMessages;
    }

    // Create a Set of existing message IDs for deduplication
    const existingIds = new Set(initialMessages.map(m => m.id));

    // Add only new messages from SSE stream
    const newMessages = streamedMessages.filter(m => !existingIds.has(m.id));

    if (newMessages.length === 0) {
      return initialMessages;
    }

    console.log(`[MessagesContext] Merging ${newMessages.length} new SSE messages`);

    // Combine and sort by timestamp
    return [...initialMessages, ...newMessages].sort(
      (a, b) => a.timestamp.getTime() - b.timestamp.getTime()
    );
  }, [initialMessages, streamedMessages]);

  const executionStateHookResult = executionStateHook || {} as ExecutionUIState;
  const {
    executionTree = [],
    pipelineStage = null,
    ...execState
  } = executionStateHookResult;

  const executionState: ExecutionUIState = {
    ...execState,
    executionTree: executionTree || [],
    pipelineStage: pipelineStage || null,
  } as ExecutionUIState;

  const {
    currentExecution: currentExec,
    handleViewDetail,
    handlePause,
    handleCancel,
  } = currentExecutionHook || {};

  const value = useMemo(
    () => ({
      messages,
      setMessages,
      messagesLoading,
      messagesError,
      quickStartSuggestions,
      fileAnalysisResult,
      setFileAnalysisResult,
      hasMore,
      loadingMore,
      loadMore,
      reloadMessages,
      sseConnected,  // 🆕

      executionState,
      pipelineStage: pipelineStage || null,
      executionTree: executionTree || [],

      currentExecution: currentExec,
      handleViewDetail,
      handlePause,
      handleCancel,
    }),
    [
      messages,
      setMessages,
      messagesLoading,
      messagesError,
      quickStartSuggestions,
      fileAnalysisResult,
      setFileAnalysisResult,
      hasMore,
      loadingMore,
      loadMore,
      reloadMessages,
      sseConnected,
      execState,
      pipelineStage,
      executionTree,
      currentExec,
      handleViewDetail,
      handlePause,
      handleCancel,
    ]
  );

  return <MessagesContext.Provider value={value}>{children}</MessagesContext.Provider>;
}

export function useMessages() {
  const context = useContext(MessagesContext);
  if (!context) {
    throw new Error('useMessages must be used within MessagesProvider');
  }
  return context;
}


