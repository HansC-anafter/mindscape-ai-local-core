'use client';

import React from 'react';
import { ConflictInfo } from '@/hooks/useConflictHandler';

interface ConflictDialogProps {
  isOpen: boolean;
  conflict: ConflictInfo;
  onConfirm: () => void;
  onCancel: () => void;
  onUseNewVersion?: () => void;
}

export default function ConflictDialog({
  isOpen,
  conflict,
  onConfirm,
  onCancel,
  onUseNewVersion
}: ConflictDialogProps) {
  if (!isOpen) return null;

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      onCancel();
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      onClick={onCancel}
      onKeyDown={handleKeyPress}
      role="dialog"
      aria-modal="true"
      aria-labelledby="conflict-dialog-title"
    >
      <div
        className="bg-white rounded-lg p-6 max-w-md w-full mx-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start mb-4">
          <div className="flex-shrink-0">
            <svg className="h-6 w-6 text-yellow-500" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
          </div>
          <div className="ml-3 flex-1">
            <h2 id="conflict-dialog-title" className="text-lg font-semibold text-gray-900">
              檔案衝突警告
            </h2>
          </div>
        </div>

        <div className="mb-4">
          <p className="text-sm text-gray-600 mb-3">
            {conflict.message || '目標檔案已存在，是否要覆蓋？'}
          </p>

          {conflict.path && (
            <div className="bg-gray-50 border border-gray-200 rounded p-2 mb-3">
              <p className="text-xs text-gray-500 mb-1">檔案路徑：</p>
              <code className="text-xs font-mono text-gray-800 break-all">{conflict.path}</code>
            </div>
          )}

          {conflict.suggestedVersion && (
            <div className="bg-blue-50 border border-blue-200 rounded p-3 mb-3">
              <p className="text-sm text-blue-800">
                <strong>建議：</strong>使用新版本號 <code className="font-mono font-semibold">v{conflict.suggestedVersion}</code> 以避免覆蓋現有檔案
              </p>
            </div>
          )}

          <div className="bg-yellow-50 border border-yellow-200 rounded p-3">
            <p className="text-sm text-yellow-800">
              <strong>注意：</strong>覆蓋現有檔案將永久刪除舊版本，此操作無法復原。
            </p>
          </div>
        </div>

        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm text-gray-700 hover:text-gray-900 border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
          >
            取消
          </button>
          {conflict.suggestedVersion && onUseNewVersion ? (
            <button
              onClick={() => {
                onUseNewVersion();
                onCancel();
              }}
              className="px-4 py-2 text-sm text-white bg-blue-600 hover:bg-blue-700 rounded-md transition-colors"
            >
              使用新版本 (v{conflict.suggestedVersion})
            </button>
          ) : null}
          <button
            onClick={onConfirm}
            className="px-4 py-2 text-sm text-white bg-red-600 hover:bg-red-700 rounded-md transition-colors"
          >
            強制覆蓋
          </button>
        </div>
      </div>
    </div>
  );
}

