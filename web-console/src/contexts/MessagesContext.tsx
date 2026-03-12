'use client';

import React, { createContext, useContext, useMemo, useEffect, ReactNode } from 'react';
import { useChatEvents, ChatMessage } from '@/hooks/useChatEvents';
import { useMessageStream } from '@/hooks/useMessageStream';
import { useExecutionState, ExecutionUIState, PipelineStage, TreeStep } from '@/hooks/useExecutionState';
import { useCurrentExecution } from '@/hooks/useCurrentExecution';
import type { CurrentExecution } from '@/components/workspace/CurrentExecutionBar';

const OPTIMISTIC_WINDOW_MS = 30_000;

function getTimestampMs(message: ChatMessage): number {
  if (message.timestamp instanceof Date) {
    return message.timestamp.getTime();
  }
  const parsed = new Date(message.timestamp as any).getTime();
  return Number.isFinite(parsed) ? parsed : Date.now();
}

function isOptimisticMessage(message: ChatMessage, nowMs: number): boolean {
  if (!(message.id.startsWith('user-') || message.id.startsWith('assistant-'))) {
    return false;
  }
  return nowMs - getTimestampMs(message) < OPTIMISTIC_WINDOW_MS;
}

function normalizeContent(content: string): string {
  return (content || '').trim().replace(/\s+/g, ' ');
}

function isLikelyOptimisticDuplicate(optimistic: ChatMessage, incoming: ChatMessage): boolean {
  if (optimistic.role !== incoming.role) {
    return false;
  }

  const a = normalizeContent(optimistic.content);
  const b = normalizeContent(incoming.content);
  if (!a || !b) {
    return false;
  }

  if (optimistic.role === 'user') {
    return a === b;
  }

  if (a === b) {
    return true;
  }

  // Assistant optimistic text is often streamed and may be truncated
  // when SSE final message arrives; allow prefix/contain matching.
  const minLen = 20;
  if (a.length >= minLen && b.length >= minLen) {
    return a.startsWith(b) || b.startsWith(a) || a.includes(b) || b.includes(a);
  }
  return false;
}

export function mergeInitialAndStreamedMessages(
  initialMessages: ChatMessage[],
  streamedMessages: ChatMessage[],
  nowMs: number = Date.now()
): ChatMessage[] {
  if (streamedMessages.length === 0) {
    return initialMessages;
  }

  const existingIds = new Set(initialMessages.map(m => m.id));
  const optimisticPool = initialMessages.filter(m => isOptimisticMessage(m, nowMs));
  const replacedOptimisticIds = new Set<string>();
  const acceptedStreamed: ChatMessage[] = [];
  const acceptedIds = new Set<string>();

  for (const incoming of streamedMessages) {
    if (existingIds.has(incoming.id) || acceptedIds.has(incoming.id)) {
      continue;
    }

    const matchIndex = optimisticPool.findIndex(
      msg =>
        !replacedOptimisticIds.has(msg.id) &&
        isLikelyOptimisticDuplicate(msg, incoming)
    );

    if (matchIndex >= 0) {
      replacedOptimisticIds.add(optimisticPool[matchIndex].id);
      optimisticPool.splice(matchIndex, 1);
    }

    acceptedIds.add(incoming.id);
    acceptedStreamed.push(incoming);
  }

  if (acceptedStreamed.length === 0 && replacedOptimisticIds.size === 0) {
    return initialMessages;
  }

  const baseMessages = replacedOptimisticIds.size > 0
    ? initialMessages.filter(m => !replacedOptimisticIds.has(m.id))
    : initialMessages;

  return [...baseMessages, ...acceptedStreamed].sort(
    (a, b) => getTimestampMs(a) - getTimestampMs(b)
  );
}

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

  // Meeting real-time streaming
  streamingText: string;
  isStreaming: boolean;
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
    streamingText,
    isStreaming,
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
    const merged = mergeInitialAndStreamedMessages(initialMessages, streamedMessages);
    const newCount = merged.length - initialMessages.length;
    if (newCount > 0) {
      console.log(`[MessagesContext] Merging ${newCount} new SSE messages`);
    }
    return merged;
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

      // Meeting real-time streaming
      streamingText,
      isStreaming,
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
      streamingText,
      isStreaming,
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

