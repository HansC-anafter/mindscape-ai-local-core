'use client';

import React, { createContext, useContext, useMemo, ReactNode } from 'react';
import { useChatEvents, ChatMessage } from '@/hooks/useChatEvents';
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
}

const MessagesContext = createContext<MessagesState | null>(null);

export function MessagesProvider({ children, workspaceId, apiUrl = '' }: MessagesProviderProps) {
  const chatEvents = useChatEvents(workspaceId, apiUrl);
  const executionStateHook = useExecutionState(workspaceId, apiUrl);
  const currentExecutionHook = useCurrentExecution(workspaceId, apiUrl);

  const {
    messages,
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

  const executionStateHookResult = executionStateHook || {} as ExecutionUIState;
  const {
    executionTree = [],
    pipelineStage = null,
    ...execState
  } = executionStateHookResult;

  // Ensure executionTree is included in execState for type compatibility
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

