'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { t } from '@/lib/i18n';
import type { Suggestion } from './workspace/SuggestionChip';
import { useChatEvents, ChatMessage } from '@/hooks/useChatEvents';
import { useSendMessage } from '@/hooks/useSendMessage';
import { UploadedFile } from '@/hooks/useFileUpload';
import { WorkspaceChatProvider } from '@/contexts/WorkspaceChatContext';
import { useUIState } from '@/contexts/UIStateContext';
import { useScrollState } from '@/contexts/ScrollStateContext';
import { useWorkspaceMetadata } from '@/contexts/WorkspaceMetadataContext';
import { useWorkspaceRefs } from '@/contexts/WorkspaceRefsContext';
import { useMessages } from '@/contexts/MessagesContext';
import { useWindowEvents } from '@/hooks/useWindowEvents';
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts';
import { useScrollManagement } from '@/hooks/useScrollManagement';
import { useLLMConfiguration } from '@/hooks/useLLMConfiguration';
import { useChatModel } from '@/hooks/useChatModel';
import { useMessageHandling } from '@/hooks/useMessageHandling';
import { useWorkspaceData } from '@/hooks/useWorkspaceData';
import { useTextareaAutoResize } from '@/hooks/useTextareaAutoResize';
import { WorkspaceChatContentView } from './workspaceChat/WorkspaceChatContentView';
import { formatExecutionSummary, createPlaybookErrorMessage, createAgentModeMessage, createExecutionModeMessage } from '@/utils/messageUtils';

type ExecutionMode = 'qa' | 'execution' | 'hybrid' | 'meeting' | null;
type WorkspaceChatLayoutVariant = 'default' | 'meeting_pane';
type WorkspaceChatMeetingSidebarComponent = React.ComponentType<{
  workspaceId: string;
  apiUrl?: string;
}>;

interface WorkspaceChatProps {
  workspaceId: string;
  apiUrl?: string;
  onFileAnalyzed?: () => void;
  executionMode?: ExecutionMode;
  expectedArtifacts?: string[];
  projectId?: string;  // Current project ID (if user is in a project context)
  threadId?: string | null;
  meetingId?: string | null;
  layoutVariant?: WorkspaceChatLayoutVariant;
}

function WorkspaceChatContent({
  workspaceId,
  apiUrl = '',
  onFileAnalyzed,
  executionMode,
  expectedArtifacts,
  projectId,
  threadId,
  meetingId,
  layoutVariant = 'default',
}: WorkspaceChatProps) {
  // Use Context for state management
  const {
    input,
    setInput,
    llmConfigured,
    dataPrompt,
    setDataPrompt,
    analyzingFile,
  } = useUIState();

  useWorkspaceMetadata();

  const { textareaRef, fileInputRef, messagesContainerRef } = useWorkspaceRefs();

  const {
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
    currentExecution,
    handleViewDetail,
    handlePause,
    handleCancel,
  } = useMessages();

  const prevMessagesLoadingRef = useRef<boolean>(true);

  useLLMConfiguration(apiUrl, {
    workspaceId,
    enabled: true,
  });

  const { selectModel } = useChatModel(apiUrl, {
    workspaceId,
    enabled: true,
  });

  const messageHandling = useMessageHandling(workspaceId, apiUrl, {
    projectId,
    threadId,
    onFileAnalyzed,
  });
  const {
    handleSend: handleSendMessage,
    handleCopyAll: handleCopyAllMessages,
    handleCopyMessage,
    isLoading: messageHandlingLoading,
    error: messageHandlingError,
  } = messageHandling;

  const { sendMessage } = useSendMessage(workspaceId, apiUrl, projectId, threadId);

  const handleExecuteSuggestion = async (suggestion: Suggestion) => {
    try {
      await sendMessage({
        action: 'execute_playbook',
        action_params: {
          playbook_code: suggestion.playbookCode || suggestion.title,
        },
        mode: 'auto',
        stream: true,
      });
    } catch (err) {
      console.error('Failed to execute suggestion:', err);
    }
  };

  const handleRetry = useCallback(async (retryData: { message: string; agent_id?: string }) => {
    try {
      await sendMessage({
        message: retryData.message,
        mode: 'auto',
        stream: true,
      });
    } catch (err) {
      console.error('Retry failed:', err);
    }
  }, [sendMessage]);

  useWorkspaceData(workspaceId, apiUrl, {
    enabled: true,
    loadSystemHealthOnMount: false,
  });

  useTextareaAutoResize(textareaRef, input, {
    minHeight: 40,
    maxHeight: 200,
    lineHeight: 20,
  });

  const { scrollToBottom } = useScrollManagement();
  const { setIsInitialLoad } = useScrollState();

  const [uploadedFiles, setUploadedFilesState] = useState<UploadedFile[]>([]);
  const [analyzingFiles, setAnalyzingFiles] = useState<Set<string>>(new Set());
  const handleAnalyzeFileRef = useRef<(file: UploadedFile) => Promise<any>>(
    async () => { }
  );
  const clearFilesRef = useRef<() => void>(() => { });

  const handleFilesChanged = useCallback((
    files: UploadedFile[],
    analyzing: Set<string>,
    analyzeFile: (file: UploadedFile) => Promise<any>,
    clearFiles: () => void
  ) => {
    setUploadedFilesState(files);
    setAnalyzingFiles(analyzing);
    handleAnalyzeFileRef.current = analyzeFile;
    clearFilesRef.current = clearFiles;
  }, []);

  const isLoading = messageHandlingLoading || messagesLoading;
  const error = messageHandlingError || messagesError;
  const showInlineQuickStartSuggestions =
    quickStartSuggestions.length > 0 && layoutVariant !== 'meeting_pane';

  useWindowEvents(
    {
      onContinueConversation: (data: any) => {
        const { intentId, taskId, context } = data || {};
        if (context?.suggestedMessage) {
          setInput(context.suggestedMessage);
          textareaRef.current?.focus();
          scrollToBottom(true);
        } else if (context?.requiresData?.prompt) {
          setInput(context.requiresData.prompt);
          textareaRef.current?.focus();
          scrollToBottom(true);
        }
        if (context?.requiresData) {
          setDataPrompt({
            taskTitle: context.topic,
            description: context.requiresData.description,
            dataType: context.requiresData.type || 'both',
            prompt: context.requiresData.prompt,
            taskId: taskId,
          });
          scrollToBottom(true);
        }
      },
      onPlaybookTriggerError: (data: any) => {
        const { playbook_code, error } = data;
        const errorMessage = createPlaybookErrorMessage(playbook_code, error);
        setMessages((prev: ChatMessage[]) => [...prev, errorMessage]);
      },
      onAgentModeParsed: (data: any) => {
        const { part1, part2, executable_tasks } = data;
        const agentMessage = createAgentModeMessage(part1, part2, executable_tasks || []);
        setMessages((prev: ChatMessage[]) => [...prev, agentMessage]);
        if (executable_tasks && executable_tasks.length > 0) {
          window.dispatchEvent(new CustomEvent('workspace-task-updated'));
        }
      },
      onExecutionModePlaybookExecuted: (data: any) => {
        const { playbook_code, execution_id } = data;
        const execMessage = createExecutionModeMessage(playbook_code, execution_id);
        setMessages((prev: ChatMessage[]) => [...prev, execMessage]);
        window.dispatchEvent(new CustomEvent('workspace-task-updated'));
      },
      onExecutionResultsSummary: (data: any) => {
        const { executed_tasks, suggestion_cards } = data || {};
        const summaryContent = formatExecutionSummary(executed_tasks || [], suggestion_cards || []);
        if (!summaryContent) return;
        const summaryMessage: ChatMessage = {
          id: `execution-summary-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
          role: 'assistant',
          content: summaryContent.trim(),
          timestamp: new Date(),
          event_type: 'execution_results',
        };
        setMessages((prev: ChatMessage[]) => [...prev, summaryMessage]);
        setTimeout(() => {
          scrollToBottom(true);
        }, 100);
      },
    },
    {
      enabled: true,
    }
  );
  useEffect(() => {
    return () => {
      // Cleanup is handled by InputArea's useFileHandling instance
    };
  }, []);

  const handleAnalyzeFileWithError = async (file: UploadedFile) => {
    try {
      const result = await handleAnalyzeFileRef.current(file);
      setFileAnalysisResult(result);
      setTimeout(() => {
        scrollToBottom();
      }, 100);
      return result;
    } catch (err: any) {
      console.error('Failed to analyze file:', err);
      const errorMessage = err.message || t('workspaceFileAnalysisFailed' as any);
      const errorChatMessage: ChatMessage = {
        id: `file-error-${Date.now()}`,
        role: 'assistant',
        content: errorMessage,
        timestamp: new Date(),
        event_type: 'error'
      };
      setMessages((prev: ChatMessage[]) => [...prev, errorChatMessage]);
      throw err;
    }
  };

  const handlePathSelection = async (path: { type: string; action: string; data?: any }) => {
    setFileAnalysisResult(null);

    const fileIds = uploadedFiles
      .filter(f => f.analysisStatus === 'completed' && f.fileId)
      .map(f => f.fileId!)
      .filter(Boolean);

    try {
      const action = path.action || 'execute_playbook';
      const actionParams: Record<string, any> = {
        ...path.data
      };

      if (action === 'execute_playbook' && !actionParams.playbook_code) {
        actionParams.playbook_code = path.type;
        if (path.type === 'content_drafting' && path.data?.suggested_formats?.[0]) {
          actionParams.output_type = path.data.suggested_formats[0];
        }
      }

      await sendMessage({
        action: action,
        action_params: actionParams,
        files: fileIds,
        mode: 'auto',
        stream: true  // Enable streaming for execution_plan generation
      });

      if (onFileAnalyzed) {
        onFileAnalyzed();
      }
    } catch (err: any) {
      console.error('Failed to send message:', err);
      let errorMessage = err.message || t('workspaceSendMessageFailed' as any);

      if (errorMessage.includes('429') || errorMessage.includes('quota') || errorMessage.includes('insufficient_quota')) {
        if (errorMessage.includes('http') || errorMessage.includes('docs')) {
          errorMessage = errorMessage;
        } else {
          errorMessage = 'API quota exceeded. Please check your plan and billing details.';
        }
      } else if (errorMessage.includes('401') || errorMessage.includes('unauthorized')) {
        errorMessage = 'API authentication failed. Please check your API key.';
      } else if (errorMessage.includes('500') || errorMessage.includes('internal server error')) {
        errorMessage = 'Server error. Please try again later.';
      }

      const errorChatMessage: ChatMessage = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: errorMessage,
        timestamp: new Date(),
        event_type: 'error'
      };
      setMessages((prev: ChatMessage[]) => [...prev, errorChatMessage]);

      setTimeout(() => {
        scrollToBottom();
      }, 100);
    } finally {
      scrollToBottom();
    }
  };

  const handleSend = async (e: React.FormEvent) => {
    await handleSendMessage(e, uploadedFiles, analyzingFiles, handleAnalyzeFileWithError);
    clearFilesRef.current();
  };
  useEffect(() => {
    setIsInitialLoad(true);
    prevMessagesLoadingRef.current = true;
  }, [workspaceId, setIsInitialLoad]);

  useKeyboardShortcuts(
    {
      onCopyAll: handleCopyAllMessages,
      onCopySelected: (messageId: string) => {
        handleCopyMessage(messageId);
      },
    },
    {
      enabled: true,
    }
  );
  const handleDataPromptDismiss = useCallback(() => {
    setDataPrompt(null);
  }, [setDataPrompt]);

  const handleDataPromptFileUpload = useCallback(() => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  }, [fileInputRef]);

  const handleDataPromptContinueWithText = useCallback((text: string) => {
    setInput(text);
    if (text.trim()) {
      setTimeout(() => {
        const form = document.querySelector('form[onSubmit]') as HTMLFormElement;
        if (form) {
          const event = new Event('submit', { bubbles: true, cancelable: true });
          form.dispatchEvent(event);
        }
      }, 100);
    }
    setDataPrompt(null);
  }, [setDataPrompt, setInput]);

  const handleQuickStartSuggestionSelect = useCallback((suggestion: string) => {
    setInput(suggestion);
    setTimeout(() => {
      const textarea = document.querySelector('textarea[name="workspace-chat-input"]') as HTMLTextAreaElement;
      if (textarea) {
        textarea.focus();
      }
    }, 100);
  }, [setInput]);

  return (
    <WorkspaceChatContentView
      analyzingFile={analyzingFile}
      apiUrl={apiUrl}
      canSend={(!input.trim() && uploadedFiles.length === 0) ? false : true}
      currentExecution={currentExecution}
      dataPrompt={dataPrompt}
      error={error}
      executionMode={executionMode}
      expectedArtifacts={expectedArtifacts}
      fileAnalysisResult={fileAnalysisResult}
      input={input}
      isLoading={isLoading}
      layoutVariant={layoutVariant}
      llmConfigured={llmConfigured}
      meetingId={meetingId}
      messagesContainerRef={messagesContainerRef}
      onCancelExecution={handleCancel}
      onCopyAllMessages={handleCopyAllMessages}
      onDataPromptContinueWithText={handleDataPromptContinueWithText}
      onDataPromptDismiss={handleDataPromptDismiss}
      onDataPromptFileUpload={handleDataPromptFileUpload}
      onExecuteSuggestion={handleExecuteSuggestion}
      onFileAnalyzed={onFileAnalyzed}
      onFilesChanged={handleFilesChanged}
      onPauseExecution={handlePause}
      onQuickStartSuggestionSelect={handleQuickStartSuggestionSelect}
      onRetry={handleRetry}
      onSend={handleSend}
      onViewExecutionDetail={handleViewDetail}
      quickStartSuggestions={quickStartSuggestions}
      showInlineQuickStartSuggestions={showInlineQuickStartSuggestions}
      threadId={threadId}
      uploadedFiles={uploadedFiles}
      workspaceId={workspaceId}
    />
  );
}

export default function WorkspaceChat(props: WorkspaceChatProps) {
  const [MeetingSidebar, setMeetingSidebar] = useState<WorkspaceChatMeetingSidebarComponent | null>(null);

  useEffect(() => {
    if (props.layoutVariant !== 'meeting_pane') {
      setMeetingSidebar(null);
      return;
    }

    let cancelled = false;
    void import('./workspace/WorkspaceChatMeetingSidebar')
      .then((module) => {
        if (!cancelled) {
          setMeetingSidebar(() => module.default);
        }
      })
      .catch((error) => {
        console.error('[WorkspaceChat] Failed to load meeting sidebar:', error);
      });

    return () => {
      cancelled = true;
    };
  }, [props.layoutVariant]);

  return (
    <WorkspaceChatProvider
      workspaceId={props.workspaceId}
      apiUrl={props.apiUrl || ''}
      threadId={props.threadId}
    >
      {props.layoutVariant === 'meeting_pane' ? (
        <div className="flex h-full min-h-0 min-w-0">
          <div className="min-w-0 flex-1">
            <WorkspaceChatContent {...props} />
          </div>
          {MeetingSidebar ? (
            <MeetingSidebar
              workspaceId={props.workspaceId}
              apiUrl={props.apiUrl}
            />
          ) : (
            <aside
              className="h-full w-[min(272px,25vw)] shrink-0 border-l border-[#dcc9a5] bg-[#f6edd8] dark:border-slate-800 dark:bg-slate-950"
              aria-hidden="true"
            />
          )}
        </div>
      ) : (
        <WorkspaceChatContent {...props} />
      )}
    </WorkspaceChatProvider>
  );
}
