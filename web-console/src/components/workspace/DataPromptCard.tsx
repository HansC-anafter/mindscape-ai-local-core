'use client';

import React, { useState } from 'react';
import { t } from '@/lib/i18n';

interface DataPromptCardProps {
  taskTitle?: string;
  description: string;
  dataType: 'file' | 'text' | 'both';
  prompt?: string;
  taskId?: string;
  onDismiss?: () => void;
  onFileUpload?: () => void;
  onContinueWithText?: (text: string) => void;
}

export function DataPromptCard({
  taskTitle,
  description,
  dataType,
  prompt,
  taskId,
  onDismiss,
  onFileUpload,
  onContinueWithText
}: DataPromptCardProps) {
  const [showTextInput, setShowTextInput] = useState(false);
  const [inputText, setInputText] = useState(prompt || '');

  const handleTextSubmit = () => {
    if (inputText.trim() && onContinueWithText) {
      onContinueWithText(inputText.trim());
      setShowTextInput(false);
      setInputText('');
      if (onDismiss) onDismiss();
    }
  };

  return (
    <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 mb-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-blue-600 dark:text-blue-400 text-sm font-medium">
              {taskTitle ? `任務「${taskTitle}」需要補充資料` : '需要補充資料'}
            </span>
          </div>
          <p className="text-sm text-gray-700 dark:text-gray-300 mb-3">
            {description}
          </p>

          {!showTextInput && (
            <div className="flex items-center gap-2">
              {dataType === 'file' || dataType === 'both' ? (
                <button
                  onClick={onFileUpload}
                  className="px-3 py-1.5 text-xs font-medium bg-blue-600 hover:bg-blue-700 text-white rounded transition-colors"
                >
                  上傳檔案
                </button>
              ) : null}
              {dataType === 'text' || dataType === 'both' ? (
                <button
                  onClick={() => setShowTextInput(true)}
                  className="px-3 py-1.5 text-xs font-medium bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 text-blue-600 dark:text-blue-400 border border-blue-300 dark:border-blue-700 rounded transition-colors"
                >
                  輸入文字
                </button>
              ) : null}
            </div>
          )}

          {showTextInput && (
            <div className="space-y-2">
              <textarea
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                placeholder="請輸入補充的資料..."
                className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 resize-none"
                rows={3}
                autoFocus
              />
              <div className="flex items-center gap-2">
                <button
                  onClick={handleTextSubmit}
                  disabled={!inputText.trim()}
                  className="px-3 py-1.5 text-xs font-medium bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-white rounded transition-colors"
                >
                  發送
                </button>
                <button
                  onClick={() => {
                    setShowTextInput(false);
                    setInputText(prompt || '');
                  }}
                  className="px-3 py-1.5 text-xs font-medium bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400 border border-gray-300 dark:border-gray-600 rounded transition-colors"
                >
                  取消
                </button>
              </div>
            </div>
          )}
        </div>

        {onDismiss && (
          <button
            onClick={onDismiss}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
            title="關閉提示"
          >
            ✕
          </button>
        )}
      </div>
    </div>
  );
}





