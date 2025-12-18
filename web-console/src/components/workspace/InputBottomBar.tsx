'use client';

import React from 'react';
import { t } from '@/lib/i18n';
import { ChatModelInfo } from '@/contexts/WorkspaceMetadataContext';

interface InputBottomBarProps {
  messagesCount: number;
  copiedAll: boolean;
  onCopyAll: () => void;
  currentChatModel: string;
  availableChatModels: ChatModelInfo[];
  contextTokenCount: number | null;
  onModelChange: (modelName: string, provider: string) => Promise<void>;
  onFileUpload: () => void;
  onSend: () => void;
  isLoading: boolean;
  canSend: boolean;
  llmConfigured: boolean | null;
}

/**
 * InputBottomBar Component
 * Displays the bottom bar of the input area with copy button, model selector, and action buttons.
 *
 * @param messagesCount Number of messages in the conversation.
 * @param copiedAll Whether all messages have been copied.
 * @param onCopyAll Callback function when copy all button is clicked.
 * @param currentChatModel Currently selected chat model.
 * @param availableChatModels Array of available chat models.
 * @param contextTokenCount Current context token count.
 * @param onModelChange Callback function when model is changed.
 * @param onFileUpload Callback function when file upload button is clicked.
 * @param onSend Callback function when send button is clicked.
 * @param isLoading Whether a message is being sent.
 * @param canSend Whether the send button should be enabled.
 * @param llmConfigured Whether LLM is configured.
 */
export function InputBottomBar({
  messagesCount,
  copiedAll,
  onCopyAll,
  currentChatModel,
  availableChatModels,
  contextTokenCount,
  onModelChange,
  onFileUpload,
  onSend,
  isLoading,
  canSend,
  llmConfigured,
}: InputBottomBarProps) {
  return (
    <div className="flex items-center justify-between px-4 pb-3 pt-2 border-t border-gray-200/30 dark:border-gray-700/30">
      {/* Left: Copy all button and Model selector */}
      <div className="flex items-center gap-2">
        {/* Copy all messages button */}
        {messagesCount > 0 && (
          <button
            onClick={onCopyAll}
            className={`text-xs px-2 py-1 border rounded transition-colors ${
              copiedAll
                ? 'bg-green-50 dark:bg-green-900/30 border-green-300 dark:border-green-700 text-green-700 dark:text-green-300'
                : 'bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
            }`}
            title={t('copyAllMessages') + ' (Cmd/Ctrl+Shift+C)'}
          >
            {copiedAll ? (
              <span className="flex items-center gap-1">
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                {t('copied')}
              </span>
            ) : (
              <span className="flex items-center gap-1">
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
                {t('copyAll')}
              </span>
            )}
          </button>
        )}
        <select
          value={currentChatModel || ''}
          onChange={async (e) => {
            const selectedModel = e.target.value;
            const model = availableChatModels.find(m => m.model_name === selectedModel);
            if (model) {
              await onModelChange(model.model_name, model.provider);
            }
          }}
          className="text-xs px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:focus:ring-blue-400"
          title={t('workspaceSelectChatModel')}
        >
          {availableChatModels.length > 0 ? (
            availableChatModels.map((model) => (
              <option key={model.model_name} value={model.model_name}>
                {model.model_name}
              </option>
            ))
          ) : (
            <option value="">{'No models available'}</option>
          )}
        </select>
        {currentChatModel && (
          <>
            <span className="text-xs text-gray-500 dark:text-gray-300">✓ {currentChatModel}</span>
            {contextTokenCount !== null && (
              <span className="text-xs text-gray-400 dark:text-gray-400" title="Context tokens">
                {contextTokenCount >= 1000
                  ? `${(contextTokenCount / 1000).toFixed(1)}k`
                  : contextTokenCount.toLocaleString()} tokens
              </span>
            )}
          </>
        )}
      </div>

      {/* Right: Action buttons */}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onFileUpload}
          disabled={llmConfigured === false}
          className="p-2 rounded-lg text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors disabled:bg-gray-50 dark:disabled:bg-gray-800 disabled:text-gray-400 dark:disabled:text-gray-500 disabled:cursor-not-allowed"
          title={t('uploadFile')}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
          </svg>
        </button>
        <button
          type="submit"
          onClick={onSend}
          disabled={!canSend || llmConfigured === false}
          className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            !canSend || llmConfigured === false
              ? 'bg-gray-200 dark:bg-gray-700 text-gray-400 dark:text-gray-500 cursor-not-allowed'
              : isLoading
              ? 'bg-blue-500 text-white cursor-wait'
              : 'bg-blue-600 text-white hover:bg-blue-700'
          }`}
        >
          {isLoading ? t('sending') : t('send')}
        </button>
      </div>
    </div>
  );
}

