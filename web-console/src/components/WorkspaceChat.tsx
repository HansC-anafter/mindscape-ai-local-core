'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { t } from '@/lib/i18n';
import SystemHealthCard from './SystemHealthCard';
import MultiAICollaborationCard from './MultiAICollaborationCard';
import { MessageItem } from './MessageItem';
import { MessageWithSuggestions } from './workspace/MessageWithSuggestions';
import type { Suggestion } from './workspace/SuggestionChip';
import { useChatEvents, ChatMessage } from '@/hooks/useChatEvents';
import { useSendMessage } from '@/hooks/useSendMessage';
import { useFileHandling } from '@/hooks/useFileHandling';
import { UploadedFile } from '@/hooks/useFileUpload';
import { useExecutionState } from '@/hooks/useExecutionState';
import IntentChips from '../app/workspaces/components/IntentChips';
import { ExecutionTree } from './execution';
import { CurrentExecutionBar } from './workspace/CurrentExecutionBar';
import { useCurrentExecution } from '@/hooks/useCurrentExecution';
import { DataPromptCard } from './workspace/DataPromptCard';
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
import { eventBus } from '@/services/EventBus';
import { LLMNotConfiguredOverlay } from './workspace/LLMNotConfiguredOverlay';
import { MessagesContainer } from './workspace/MessagesContainer';
import { InputArea } from './workspace/InputArea';
import { ExecutionModeNotice } from './workspace/ExecutionModeNotice';
import { ErrorDisplay } from './workspace/ErrorDisplay';
import { ProcessingIndicator } from './workspace/ProcessingIndicator';
import { formatExecutionSummary, createPlaybookErrorMessage, createAgentModeMessage, createExecutionModeMessage } from '@/utils/messageUtils';

type ExecutionMode = 'qa' | 'execution' | 'hybrid' | null;

interface WorkspaceChatProps {
  workspaceId: string;
  apiUrl?: string;
  onFileAnalyzed?: () => void;
  executionMode?: ExecutionMode;
  expectedArtifacts?: string[];
  projectId?: string;  // Current project ID (if user is in a project context)
}

function WorkspaceChatContent({
  workspaceId,
  apiUrl = '',
  onFileAnalyzed,
  executionMode,
  expectedArtifacts,
  projectId
}: WorkspaceChatProps) {
  // Use Context for state management
  const {
    input,
    setInput,
    llmConfigured,
    setLlmConfigured,
    isStreaming,
    setIsStreaming,
    copiedAll,
    setCopiedAll,
    dataPrompt,
    setDataPrompt,
    analyzingFile,
    setAnalyzingFile,
  } = useUIState();

  const {
    workspaceTitle,
    setWorkspaceTitle,
    systemHealth,
    setSystemHealth,
    contextTokenCount,
    setContextTokenCount,
    currentChatModel,
    setCurrentChatModel,
    availableChatModels,
    setAvailableChatModels,
  } = useWorkspaceMetadata();

  const { messagesScrollRef, textareaRef, fileInputRef, messagesEndRef, messagesContainerRef } = useWorkspaceRefs();

  const {
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
    pipelineStage,
    executionTree,
    currentExecution,
    handleViewDetail,
    handlePause,
    handleCancel,
  } = useMessages();

  const [showHealthCard, setShowHealthCard] = useState(false);
  const selectedMessageRef = useRef<string | null>(null);
  const prevMessagesLoadingRef = useRef<boolean>(true);
  const scrollTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Use new Hooks for LLM configuration and chat model
  useLLMConfiguration(apiUrl, {
    workspaceId,
    enabled: true,
  });

  const { selectModel } = useChatModel(apiUrl, {
    workspaceId,
    enabled: true,
  });

  // Use new Hooks for message handling, workspace data, and textarea auto-resize
  const messageHandling = useMessageHandling(workspaceId, apiUrl, {
    projectId,
    onFileAnalyzed,
  });
  const {
    handleSend: handleSendMessage,
    handleCopyAll: handleCopyAllMessages,
    handleCopyMessage,
    isLoading: messageHandlingLoading,
    error: messageHandlingError,
  } = messageHandling;

  // Get sendMessage from useSendMessage for suggestion execution
  const { sendMessage } = useSendMessage(workspaceId, apiUrl, projectId);

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

  useWorkspaceData(workspaceId, apiUrl, {
    enabled: true,
  });

  useTextareaAutoResize(textareaRef, input, {
    minHeight: 40,
    maxHeight: 200,
    lineHeight: 20,
  });

  // Use new Hooks
  const { scrollToBottom, showScrollToBottom } = useScrollManagement();
  const { setIsInitialLoad } = useScrollState();

  const fileHandling = useFileHandling(workspaceId, apiUrl, {
    onFileAnalyzed,
    onAnalysisError: (error, file) => {
      // Error handling is done in handleAnalyzeFileWithError wrapper
      console.error(`[useFileHandling] Failed to analyze file ${file.name}:`, error);
    },
  });
  const {
    uploadedFiles,
    analyzingFiles,
    handleAnalyzeFile,
    clearFiles,
    setUploadedFiles,
  } = fileHandling;

  const isLoading = messageHandlingLoading || messagesLoading;
  const error = messageHandlingError || messagesError;


  // Use useWindowEvents to replace old event listeners
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


  // Note: availableChatModels is managed by useChatModel hook internally


  // Cleanup file preview URLs and toast timeout on unmount
  useEffect(() => {
    return () => {
      setUploadedFiles(prev => {
        prev.forEach(file => {
          if (file.preview) {
            URL.revokeObjectURL(file.preview);
          }
        });
        return [];
      });
    };
  }, []);



  // Cleanup scroll timeout on unmount
  useEffect(() => {
    return () => {
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }
    };
  }, []);



  // Wrapper for handleAnalyzeFile to add error message handling
  const handleAnalyzeFileWithError = async (file: UploadedFile) => {
    try {
      const result = await handleAnalyzeFile(file);
      setFileAnalysisResult(result);
      setTimeout(() => {
        scrollToBottom();
      }, 100);
      return result;
    } catch (err: any) {
      console.error('Failed to analyze file:', err);
      const errorMessage = err.message || t('workspaceFileAnalysisFailed');
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

      // Extract user-friendly error message, preserving URLs
      let errorMessage = err.message || t('workspaceSendMessageFailed');

      // Handle specific error types with user-friendly messages, but preserve original message with URLs
      if (errorMessage.includes('429') || errorMessage.includes('quota') || errorMessage.includes('insufficient_quota')) {
        // Keep original message if it contains helpful URLs, otherwise use simplified message
        if (errorMessage.includes('http') || errorMessage.includes('docs')) {
          // Preserve original message with URLs
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

      // Scroll to show error message
      setTimeout(() => {
        scrollToBottom();
      }, 100);
    } finally {
      scrollToBottom();
    }
  };

  const handleSend = async (e: React.FormEvent) => {
    await handleSendMessage(e, uploadedFiles, analyzingFiles, handleAnalyzeFileWithError);
    clearFiles();
  };


  // Reset initial load flag when workspace changes
  useEffect(() => {
    setIsInitialLoad(true);
    prevMessagesLoadingRef.current = true;
  }, [workspaceId, setIsInitialLoad]);

  // Auto-resize textarea based on content


  // Copy all messages

  // Use useKeyboardShortcuts to replace old keyboard event listener
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

  const handleMessageCopy = (content: string) => {
    // Optional: Show toast notification
    if (process.env.NODE_ENV === 'development') {
      console.log('Message copied:', content.substring(0, 50) + '...');
    }
  };


  return (
    <div className="flex flex-col h-full bg-white dark:bg-gray-900 relative">
      <LLMNotConfiguredOverlay visible={llmConfigured === false} />


      {/* Messages */}
      <div
        ref={messagesContainerRef}
        className="flex-1 overflow-hidden relative px-4 pt-4"
        style={{ minWidth: 0, maxWidth: '100%' }}
      >

        {analyzingFile && (
          <div className="flex justify-start">
            <div className="bg-gray-100 dark:bg-gray-800 rounded-lg px-6 py-4">
              <div className="flex items-center gap-3">
                <div className="flex space-x-1">
                  <div className="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0s' }} />
                  <div className="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                  <div className="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }} />
                </div>
                <span className="text-sm text-gray-600 dark:text-gray-300">{t('thinking')}</span>
              </div>
            </div>
          </div>
        )}

        {/* Debug: Log when fileAnalysisResult exists but no collaboration_results */}
        {fileAnalysisResult && !fileAnalysisResult.collaboration_results && (() => {
          console.log('fileAnalysisResult exists but no collaboration_results:', fileAnalysisResult);
          return null;
        })()}

        {/* Debug: Show raw result if no collaboration results */}
        {fileAnalysisResult && !fileAnalysisResult.collaboration_results && (
          <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-700 rounded-lg p-4 mb-4">
            <p className="text-sm text-yellow-800 dark:text-yellow-300">
              {t('workspaceAnalysisNoResults')}
            </p>
            <details className="mt-2">
              <summary className="text-xs text-yellow-600 dark:text-yellow-400 cursor-pointer">{t('viewOriginalResponse') || '查看原始回應'}</summary>
              <pre className="text-xs mt-2 overflow-auto text-gray-900 dark:text-gray-100">{JSON.stringify(fileAnalysisResult, null, 2)}</pre>
            </details>
          </div>
        )}

        <MessagesContainer
          workspaceId={workspaceId}
          apiUrl={apiUrl}
          executionMode={executionMode || undefined}
          expectedArtifacts={expectedArtifacts}
          onExecuteSuggestion={handleExecuteSuggestion}
          currentExecution={currentExecution}
          onViewDetail={currentExecution ? () => handleViewDetail(currentExecution.executionId) : undefined}
        />
      </div>

      {/* Error message */}
      {error && (
        <div className="px-4 py-2 bg-red-50 border-t border-red-200">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Current Execution Bar - Above input box */}
      <CurrentExecutionBar
        execution={currentExecution}
        onViewDetail={currentExecution ? () => handleViewDetail(currentExecution.executionId) : () => {}}
        onPause={currentExecution ? () => handlePause(currentExecution.executionId) : () => {}}
        onCancel={currentExecution ? () => handleCancel(currentExecution.executionId) : () => {}}
      />

      {/* Data Prompt Card - Show when task requires additional data */}
      {dataPrompt && (
        <div className="px-3 pt-2">
          <DataPromptCard
            taskTitle={dataPrompt.taskTitle}
            description={dataPrompt.description}
            dataType={dataPrompt.dataType}
            prompt={dataPrompt.prompt}
            taskId={dataPrompt.taskId}
            onDismiss={() => setDataPrompt(null)}
            onFileUpload={() => {
              // Trigger file upload input
              if (fileInputRef.current) {
                fileInputRef.current.click();
                // Note: After file upload, the file upload handler will process it
                // We keep the prompt visible until user dismisses it or file is successfully uploaded
              }
            }}
            onContinueWithText={(text) => {
              // Send the text as a message
              setInput(text);
              // Auto submit if there's text
              if (text.trim()) {
                setTimeout(() => {
                  const form = document.querySelector('form[onSubmit]') as HTMLFormElement;
                  if (form) {
                    // Trigger form submit
                    const event = new Event('submit', { bubbles: true, cancelable: true });
                    form.dispatchEvent(event);
                  }
                }, 100);
              }
              setDataPrompt(null);
            }}
          />
        </div>
      )}

      {/* Quick Start Suggestions - Above input box */}
      {quickStartSuggestions.length > 0 && (
        <div className="px-3 pt-2 pb-1 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/60">
          <div className="flex flex-wrap gap-2">
            {quickStartSuggestions.map((suggestion, idx) => (
              <button
                key={idx}
                onClick={() => {
                  setInput(suggestion);
                  // Auto focus on input after setting
                  setTimeout(() => {
                    const textarea = document.querySelector('textarea[name="workspace-chat-input"]') as HTMLTextAreaElement;
                    if (textarea) {
                      textarea.focus();
                    }
                  }, 100);
                }}
                className="px-2.5 py-1 text-xs bg-white dark:bg-gray-800 border border-blue-300 dark:border-gray-600 text-blue-700 dark:text-gray-100 rounded-md hover:bg-blue-50 dark:hover:bg-gray-700 hover:border-blue-400 transition-colors"
              >
                {suggestion.startsWith('suggestion.') || suggestion.startsWith('suggestions.') ? t(suggestion as any) || suggestion : suggestion}
              </button>
            ))}
          </div>
        </div>
      )}

      <InputArea
        workspaceId={workspaceId}
        apiUrl={apiUrl}
        onSend={handleSend}
        onFileAnalyzed={onFileAnalyzed}
        onCopyAll={handleCopyAllMessages}
        isLoading={isLoading}
        canSend={(!input.trim() && uploadedFiles.length === 0) ? false : true}
      />
    </div>
  );
}

export default function WorkspaceChat(props: WorkspaceChatProps) {
  return (
    <WorkspaceChatProvider workspaceId={props.workspaceId} apiUrl={props.apiUrl || ''}>
      <WorkspaceChatContent {...props} />
    </WorkspaceChatProvider>
  );
}
