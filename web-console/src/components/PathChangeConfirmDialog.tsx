'use client';

import React from 'react';

interface PathChangeConfirmDialogProps {
  isOpen: boolean;
  oldPath: string;
  newPath: string;
  oldArtifactsDir?: string;
  newArtifactsDir?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function PathChangeConfirmDialog({
  isOpen,
  oldPath,
  newPath,
  oldArtifactsDir,
  newArtifactsDir,
  onConfirm,
  onCancel
}: PathChangeConfirmDialogProps) {
  if (!isOpen) return null;

  const artifactsDirChanged = oldArtifactsDir !== newArtifactsDir;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div
        className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-6">
          {/* Header */}
          <div className="flex items-start mb-4">
            <div className="flex-shrink-0">
              <svg className="h-6 w-6 text-yellow-400" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3 flex-1">
              <h3 className="text-lg font-semibold text-gray-900">確認變更存儲路徑</h3>
            </div>
          </div>

          {/* Warning Message */}
          <div className="mb-4">
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
              <p className="text-sm text-yellow-800 mb-3">
                <strong>警告：</strong>變更存儲路徑會影響後續檔案歸檔，舊檔案可能無法自動找到。
              </p>
              <ul className="text-sm text-yellow-700 space-y-1 list-disc list-inside">
                <li>現有產物檔案仍保留在原路徑，但系統無法自動找到</li>
                <li>後續新產物將存儲在新路徑</li>
                <li>如需遷移舊檔案，請手動移動或使用系統工具</li>
              </ul>
            </div>
          </div>

          {/* Path Changes */}
          <div className="mb-4 space-y-3">
            {oldPath !== newPath && (
              <div>
                <p className="text-sm font-medium text-gray-700 mb-1">基礎存儲路徑變更：</p>
                <div className="bg-gray-50 rounded p-2 space-y-1">
                  <div className="text-xs text-gray-600">
                    <span className="font-medium">舊路徑：</span>
                    <code className="ml-1 text-red-600">{oldPath || '(未設定)'}</code>
                  </div>
                  <div className="text-xs text-gray-600">
                    <span className="font-medium">新路徑：</span>
                    <code className="ml-1 text-green-600">{newPath}</code>
                  </div>
                </div>
              </div>
            )}

            {artifactsDirChanged && (
              <div>
                <p className="text-sm font-medium text-gray-700 mb-1">產物目錄變更：</p>
                <div className="bg-gray-50 rounded p-2 space-y-1">
                  <div className="text-xs text-gray-600">
                    <span className="font-medium">舊目錄：</span>
                    <code className="ml-1 text-red-600">{oldArtifactsDir || 'artifacts'}</code>
                  </div>
                  <div className="text-xs text-gray-600">
                    <span className="font-medium">新目錄：</span>
                    <code className="ml-1 text-green-600">{newArtifactsDir || 'artifacts'}</code>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-3">
            <button
              onClick={onCancel}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
            >
              取消
            </button>
            <button
              onClick={onConfirm}
              className="px-4 py-2 text-sm font-medium text-white bg-yellow-600 rounded-md hover:bg-yellow-700 transition-colors"
            >
              確認變更
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

