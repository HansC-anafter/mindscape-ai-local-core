import React from 'react';

import { useT } from '@/lib/i18n';
import type { Suggestion } from '../workspace/SuggestionChip';
import type { UploadedFile } from '@/hooks/useFileUpload';
import { CurrentExecutionBar } from '../workspace/CurrentExecutionBar';
import { DataPromptCard } from '../workspace/DataPromptCard';
import { LLMNotConfiguredOverlay } from '../workspace/LLMNotConfiguredOverlay';
import { MessagesContainer } from '../workspace/MessagesContainer';
import { InputArea } from '../workspace/InputArea';

type ExecutionMode = 'qa' | 'execution' | 'hybrid' | 'meeting' | null;
type WorkspaceChatLayoutVariant = 'default' | 'meeting_pane';

interface DataPromptView {
  taskTitle?: string;
  description: string;
  dataType: 'file' | 'text' | 'both';
  prompt?: string;
  taskId?: string;
}

interface CurrentExecutionView {
  executionId: string;
}

interface WorkspaceChatContentViewProps {
  analyzingFile: boolean;
  apiUrl: string;
  canSend: boolean;
  currentExecution: CurrentExecutionView | null;
  dataPrompt: DataPromptView | null;
  error: unknown;
  executionMode?: ExecutionMode;
  expectedArtifacts?: string[];
  fileAnalysisResult: any;
  input: string;
  isLoading: boolean;
  layoutVariant: WorkspaceChatLayoutVariant;
  llmConfigured: boolean | null;
  meetingId?: string | null;
  messagesContainerRef: React.RefObject<HTMLDivElement>;
  onCancelExecution: (executionId: string) => void;
  onCopyAllMessages: () => void;
  onDataPromptContinueWithText: (text: string) => void;
  onDataPromptDismiss: () => void;
  onDataPromptFileUpload: () => void;
  onExecuteSuggestion: (suggestion: Suggestion) => Promise<void>;
  onFileAnalyzed?: () => void;
  onFilesChanged: (
    files: UploadedFile[],
    analyzing: Set<string>,
    analyzeFile: (file: UploadedFile) => Promise<any>,
    clearFiles: () => void
  ) => void;
  onPauseExecution: (executionId: string) => void;
  onQuickStartSuggestionSelect: (suggestion: string) => void;
  onRetry: (retryData: { message: string; agent_id?: string }) => void;
  onSend: (event: React.FormEvent) => void;
  onViewExecutionDetail: (executionId: string) => void;
  quickStartSuggestions: string[];
  showInlineQuickStartSuggestions: boolean;
  threadId?: string | null;
  uploadedFiles: UploadedFile[];
  workspaceId: string;
}

export function WorkspaceChatContentView({
  analyzingFile,
  apiUrl,
  canSend,
  currentExecution,
  dataPrompt,
  error,
  executionMode,
  expectedArtifacts,
  fileAnalysisResult,
  input,
  isLoading,
  layoutVariant,
  llmConfigured,
  meetingId,
  messagesContainerRef,
  onCancelExecution,
  onCopyAllMessages,
  onDataPromptContinueWithText,
  onDataPromptDismiss,
  onDataPromptFileUpload,
  onExecuteSuggestion,
  onFileAnalyzed,
  onFilesChanged,
  onPauseExecution,
  onQuickStartSuggestionSelect,
  onRetry,
  onSend,
  onViewExecutionDetail,
  quickStartSuggestions,
  showInlineQuickStartSuggestions,
  threadId,
  uploadedFiles,
  workspaceId,
}: WorkspaceChatContentViewProps) {
  const t = useT();
  const errorMessage = error ? String(error) : null;

  return (
    <div className="flex flex-col h-full bg-surface-secondary dark:bg-gray-900 relative">
      <LLMNotConfiguredOverlay visible={llmConfigured === false} />

      <div
        ref={messagesContainerRef}
        className="flex-1 overflow-hidden relative px-4 pt-4"
        style={{ minWidth: 0, maxWidth: '100%' }}
      >
        {analyzingFile && (
          <div className="flex justify-start">
            <div className="bg-surface-secondary dark:bg-gray-800 rounded-lg px-6 py-4">
              <div className="flex items-center gap-3">
                <div className="flex space-x-1">
                  <div className="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0s' }} />
                  <div className="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                  <div className="w-2 h-2 bg-gray-400 dark:bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }} />
                </div>
                <span className="text-sm text-secondary dark:text-gray-300">{t('thinking' as any)}</span>
              </div>
            </div>
          </div>
        )}

        {fileAnalysisResult && !fileAnalysisResult.collaboration_results && (() => {
          console.log('fileAnalysisResult exists but no collaboration_results:', fileAnalysisResult);
          return null;
        })()}

        {fileAnalysisResult && !fileAnalysisResult.collaboration_results && (
          <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-700 rounded-lg p-4 mb-4">
            <p className="text-sm text-yellow-800 dark:text-yellow-300">
              {t('workspaceAnalysisNoResults' as any)}
            </p>
            <details className="mt-2">
              <summary className="text-xs text-yellow-600 dark:text-yellow-400 cursor-pointer">{t('viewOriginalResponse' as any) || 'View original response'}</summary>
              <pre className="text-xs mt-2 overflow-auto text-primary dark:text-gray-100">{JSON.stringify(fileAnalysisResult, null, 2)}</pre>
            </details>
          </div>
        )}

        <MessagesContainer
          workspaceId={workspaceId}
          apiUrl={apiUrl}
          executionMode={executionMode || undefined}
          expectedArtifacts={expectedArtifacts}
          onExecuteSuggestion={onExecuteSuggestion}
          onRetry={onRetry}
          currentExecution={currentExecution as any}
          onViewDetail={currentExecution ? () => onViewExecutionDetail(currentExecution.executionId) : undefined}
        />
      </div>

      {errorMessage && (
        <div className="px-4 py-2 bg-red-50 border-t border-red-200">
          <p className="text-sm text-red-700">{errorMessage}</p>
        </div>
      )}

      <CurrentExecutionBar
        execution={currentExecution as any}
        onViewDetail={currentExecution ? () => onViewExecutionDetail(currentExecution.executionId) : () => { }}
        onPause={currentExecution ? () => onPauseExecution(currentExecution.executionId) : () => { }}
        onCancel={currentExecution ? () => onCancelExecution(currentExecution.executionId) : () => { }}
      />

      {dataPrompt && (
        <div className="px-3 pt-2">
          <DataPromptCard
            taskTitle={dataPrompt.taskTitle}
            description={dataPrompt.description}
            dataType={dataPrompt.dataType}
            prompt={dataPrompt.prompt}
            taskId={dataPrompt.taskId}
            onDismiss={onDataPromptDismiss}
            onFileUpload={onDataPromptFileUpload}
            onContinueWithText={onDataPromptContinueWithText}
          />
        </div>
      )}

      {showInlineQuickStartSuggestions && (
        <div className="px-3 pt-2 pb-1 border-t border-default dark:border-gray-700 bg-surface dark:bg-gray-800/60">
          <div className="flex flex-wrap gap-2">
            {quickStartSuggestions.map((suggestion, idx) => (
              <button
                key={idx}
                onClick={() => onQuickStartSuggestionSelect(suggestion)}
                className="px-2.5 py-1 text-xs bg-surface-accent dark:bg-gray-800 border border-accent dark:border-gray-600 text-accent dark:text-gray-100 rounded-md hover:bg-accent-10 dark:hover:bg-gray-700 hover:border-accent dark:hover:border-gray-500 transition-colors"
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
        onSend={onSend}
        onFileAnalyzed={onFileAnalyzed}
        onCopyAll={onCopyAllMessages}
        isLoading={isLoading}
        canSend={canSend}
        layoutVariant={layoutVariant}
        onFilesChanged={onFilesChanged}
      />
    </div>
  );
}
