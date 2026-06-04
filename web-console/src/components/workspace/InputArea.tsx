'use client';

import React, { useEffect } from 'react';
import { t } from '@/lib/i18n';
import { useUIState } from '@/contexts/UIStateContext';
import { useWorkspaceRefs } from '@/contexts/WorkspaceRefsContext';
import { useFileHandling } from '@/hooks/useFileHandling';
import { FilePreviewGrid } from './FilePreviewGrid';
import { InputBottomBar } from './InputBottomBar';
import { useMessages } from '@/contexts/MessagesContext';
import IntentChips from '../../app/workspaces/components/IntentChips';
import { WorkspaceChatRuntimeControls } from './WorkspaceChatRuntimeControls';
import { getApiBaseUrl } from '@/lib/api-url';

const LazyMeetingVoiceTurnButton = React.lazy(() => (
  import('./MeetingVoiceTurnButton').then((module) => ({
    default: module.MeetingVoiceTurnButton,
  }))
));
const LazyRealtimeVoiceSessionButton = React.lazy(() => (
  import('./RealtimeVoiceSessionButton').then((module) => ({
    default: module.RealtimeVoiceSessionButton,
  }))
));

interface InputAreaProps {
  workspaceId: string;
  apiUrl: string;
  onSend: (e: React.FormEvent) => void;
  onFileAnalyzed?: () => void;
  onCopyAll?: () => void;
  isLoading: boolean;
  canSend: boolean;
  layoutVariant?: 'default' | 'meeting_pane';
  meetingId?: string | null;
  onFilesChanged?: (files: any[], analyzingFiles: Set<string>, analyzeFile: (file: any) => Promise<any>, clearFiles: () => void) => void;
}

export function InputArea({
  workspaceId,
  apiUrl,
  onSend,
  onFileAnalyzed,
  onCopyAll,
  isLoading,
  canSend,
  layoutVariant = 'default',
  meetingId,
  onFilesChanged,
}: InputAreaProps) {
  const { input, setInput, llmConfigured, duplicateFileToast, copiedAll } = useUIState();
  const { textareaRef, fileInputRef } = useWorkspaceRefs();
  const { messages } = useMessages();

  const fileHandling = useFileHandling(workspaceId, apiUrl, {
    onFileAnalyzed,
  });

  const {
    uploadedFiles,
    analyzingFiles,
    handleAnalyzeFile,
    clearFiles,
    isDragging,
    handleFileInputChange,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    removeFile,
  } = fileHandling;

  useEffect(() => {
    onFilesChanged?.(uploadedFiles, analyzingFiles, handleAnalyzeFile, clearFiles);
  }, [uploadedFiles, analyzingFiles, handleAnalyzeFile, clearFiles, onFilesChanged]);

  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSend(e as any);
    }
  };
  const isMeetingPaneLayout = layoutVariant === 'meeting_pane';
  const resolvedApiUrl = apiUrl || getApiBaseUrl();

  return (
    <form
      onSubmit={onSend}
      className="relative border-t bg-surface-secondary dark:bg-gray-900"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {llmConfigured === false && (
        <div className="mb-3 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
          <p className="text-sm text-yellow-800 mb-2">
            {t('apiKeyNotConfigured' as any)}
          </p>
          <a
            href="/settings"
            className="text-sm text-blue-600 hover:text-blue-800 underline"
          >
            {t('goToSettings' as any)} &gt;
          </a>
        </div>
      )}

      <FilePreviewGrid
        files={uploadedFiles}
        onRemove={removeFile}
      />

      {isDragging && (
        <div className="absolute inset-0 bg-blue-50/95 border-2 border-dashed border-blue-400 rounded-lg flex items-center justify-center z-10 backdrop-blur-sm">
          <div className="text-center">
            <svg className="w-16 h-16 text-blue-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <p className="text-lg font-medium text-blue-600">{t('dropFilesHere' as any)}</p>
          </div>
        </div>
      )}

      {duplicateFileToast && (
        <div className="absolute top-4 left-1/2 transform -translate-x-1/2 z-50 animate-in fade-in slide-in-from-top-2 duration-200">
          <div className="bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-700 rounded-lg px-4 py-2 shadow-lg flex items-center gap-2">
            <svg className="w-4 h-4 text-amber-600 dark:text-amber-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <span className="text-sm text-amber-800 dark:text-amber-200">{duplicateFileToast.message}</span>
          </div>
        </div>
      )}

      <div className="flex flex-col border-t border-default/60 dark:border-gray-700/60 backdrop-blur-sm">
        <div className="flex-1 relative px-4 pt-3">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
            }}
            onKeyDown={handleKeyPress}
            placeholder={llmConfigured === false ? t('configureApiKeyFirst' as any) : t('typeMessageOrDropFiles' as any)}
            disabled={llmConfigured === false}
            className="w-full resize-none border border-default/50 dark:border-gray-700/50 rounded-lg px-3 py-2 bg-surface-accent dark:bg-gray-800/80 focus:outline-none focus:ring-2 focus:ring-accent/50 dark:focus:ring-blue-400/50 focus:border-accent dark:focus:border-blue-600 disabled:bg-surface-secondary/50 dark:disabled:bg-gray-800/50 disabled:cursor-not-allowed overflow-y-auto text-xs text-primary dark:text-gray-100 placeholder-tertiary dark:placeholder-gray-500 transition-all"
            style={{ minHeight: '2.5rem', maxHeight: '200px', lineHeight: '1.25rem' }}
            autoComplete="off"
            data-lpignore="true"
            data-form-type="other"
            data-1p-ignore="true"
            name="workspace-chat-input"
          />
          <input
            ref={fileInputRef}
            type="file"
            multiple
            onChange={handleFileInputChange}
            className="hidden"
            id="file-upload-input"
            disabled={llmConfigured === false}
          />
        </div>

        {!isMeetingPaneLayout ? (
          <IntentChips
            workspaceId={workspaceId}
            apiUrl={resolvedApiUrl}
          />
        ) : null}

        <InputBottomBar
          messagesCount={messages.length}
          copiedAll={copiedAll}
          onCopyAll={onCopyAll || (() => { })}
          leadingContent={
            !isMeetingPaneLayout ? (
              <WorkspaceChatRuntimeControls
                workspaceId={workspaceId}
                apiUrl={resolvedApiUrl}
                layout="inline"
              />
            ) : null
          }
          actionContent={
            meetingId ? (
              <React.Suspense fallback={null}>
                <div className="flex items-center gap-1">
                  <LazyRealtimeVoiceSessionButton
                    workspaceId={workspaceId}
                    meetingId={meetingId}
                    apiUrl={resolvedApiUrl}
                    disabled={llmConfigured === false}
                  />
                  <LazyMeetingVoiceTurnButton
                    workspaceId={workspaceId}
                    meetingId={meetingId}
                    apiUrl={resolvedApiUrl}
                    disabled={llmConfigured === false}
                  />
                </div>
              </React.Suspense>
            ) : null
          }
          onFileUpload={() => fileInputRef.current?.click()}
          onSend={() => onSend({ preventDefault: () => { } } as React.FormEvent)}
          isLoading={isLoading}
          canSend={canSend}
          llmConfigured={llmConfigured}
        />
      </div>
    </form>
  );
}
