'use client';

import React, { useState, useEffect } from 'react';
import PathChangeConfirmDialog from '@/components/PathChangeConfirmDialog';

interface Workspace {
  id: string;
  title: string;
  storage_base_path?: string;
  artifacts_dir?: string;
  storage_config?: any;
}

interface WorkspaceSettingsProps {
  workspace: Workspace | null;
  workspaceId: string;
  apiUrl: string;
  onUpdate?: () => void;
}

export default function WorkspaceSettings({
  workspace,
  workspaceId,
  apiUrl,
  onUpdate
}: WorkspaceSettingsProps) {
  const [storageBasePath, setStorageBasePath] = useState('');
  const [artifactsDir, setArtifactsDir] = useState('artifacts');
  const [originalStorageBasePath, setOriginalStorageBasePath] = useState('');
  const [originalArtifactsDir, setOriginalArtifactsDir] = useState('');
  const [storagePathChanged, setStoragePathChanged] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);

  useEffect(() => {
    if (workspace) {
      const basePath = workspace.storage_base_path || '';
      const dir = workspace.artifacts_dir || 'artifacts';
      setStorageBasePath(basePath);
      setArtifactsDir(dir);
      setOriginalStorageBasePath(basePath);
      setOriginalArtifactsDir(dir);
      setStoragePathChanged(false);
    }
  }, [workspace]);

  useEffect(() => {
    const pathChanged =
      storageBasePath !== originalStorageBasePath ||
      artifactsDir !== originalArtifactsDir;
    setStoragePathChanged(pathChanged);
  }, [storageBasePath, artifactsDir, originalStorageBasePath, originalArtifactsDir]);

  const handleOpenFolder = async () => {
    if (!storageBasePath) {
      alert('請先設定基礎存儲路徑');
      return;
    }

    try {
      // Call backend API to open folder
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/open-folder`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: storageBasePath })
        }
      );

      if (!response.ok) {
        throw new Error('Failed to open folder');
      }
      // TODO: Show success toast
    } catch (err) {
      console.error('Failed to open folder:', err);
      // Fallback: Show path in alert
      alert(`路徑: ${storageBasePath}\n\n請手動在檔案管理器中開啟此路徑。`);
    }
  };

  const handleSaveStorageSettings = async () => {
    if (!storageBasePath.trim()) {
      setError('請輸入基礎存儲路徑');
      return;
    }

    // If path changed, show confirmation dialog
    if (storagePathChanged) {
      setShowConfirmDialog(true);
      return;
    }

    // If no change, save directly
    await performSave();
  };

  const performSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(false);
    setShowConfirmDialog(false);

    try {
      const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          storage_base_path: storageBasePath.trim(),
          artifacts_dir: artifactsDir.trim() || 'artifacts',
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to update workspace' }));
        throw new Error(errorData.detail || 'Failed to update workspace');
      }

      const updatedWorkspace = await response.json();
      setOriginalStorageBasePath(updatedWorkspace.storage_base_path || '');
      setOriginalArtifactsDir(updatedWorkspace.artifacts_dir || 'artifacts');
      setStoragePathChanged(false);
      setSuccess(true);

      // Clear success message after 3 seconds
      setTimeout(() => setSuccess(false), 3000);

      if (onUpdate) {
        onUpdate();
      }
    } catch (err: any) {
      setError(err.message || '儲存失敗，請稍後再試');
      console.error('Failed to save storage settings:', err);
    } finally {
      setSaving(false);
    }
  };

  if (!workspace) {
    return (
      <div className="p-6">
        <div className="text-gray-500">載入中...</div>
      </div>
    );
  }

  return (
    <>
      {/* Path Change Confirmation Dialog */}
      <PathChangeConfirmDialog
        isOpen={showConfirmDialog}
        oldPath={originalStorageBasePath}
        newPath={storageBasePath}
        oldArtifactsDir={originalArtifactsDir}
        newArtifactsDir={artifactsDir}
        onConfirm={performSave}
        onCancel={() => setShowConfirmDialog(false)}
      />

      <div className="p-6 space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-gray-900 mb-2">存儲設定</h2>
        <p className="text-sm text-gray-600">
          設定 Workspace 的檔案存儲路徑，所有 Playbook 產物將存儲在此路徑下。
        </p>
      </div>

      {/* Warning if no storage path */}
      {!workspace.storage_base_path && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <div className="flex items-start">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-yellow-400" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3 flex-1">
              <h3 className="text-sm font-medium text-yellow-800">警告：尚未設定存儲路徑</h3>
              <p className="mt-1 text-sm text-yellow-700">
                Workspace 尚未設定儲存路徑。請設定儲存路徑，或前往{' '}
                <a href="/settings" className="underline font-medium">系統設定</a>{' '}
                開啟 Local File System 權限。
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Storage Settings Form */}
      <div className="space-y-4">
        {/* Storage Base Path */}
        <div>
          <label htmlFor="storage-base-path" className="block text-sm font-medium text-gray-700 mb-1">
            基礎存儲路徑
          </label>
          <div className="flex items-center gap-2">
            <input
              id="storage-base-path"
              type="text"
              value={storageBasePath}
              onChange={(e) => setStorageBasePath(e.target.value)}
              placeholder="/path/to/storage"
              className="flex-1 px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
            {storageBasePath && (
              <button
                onClick={handleOpenFolder}
                className="px-3 py-2 text-sm bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 transition-colors"
                title="開啟所在資料夾"
              >
                開啟資料夾
              </button>
            )}
          </div>
          <p className="mt-1 text-xs text-gray-500">
            所有 Playbook 產物將存儲在此路徑下的子目錄中
          </p>
        </div>

        {/* Artifacts Directory */}
        <div>
          <label htmlFor="artifacts-dir" className="block text-sm font-medium text-gray-700 mb-1">
            產物目錄
          </label>
          <input
            id="artifacts-dir"
            type="text"
            value={artifactsDir}
            onChange={(e) => setArtifactsDir(e.target.value)}
            placeholder="artifacts"
            className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
          <p className="mt-1 text-xs text-gray-500">
            產物將存儲在「基礎存儲路徑」下的此目錄中（預設：artifacts）
          </p>
        </div>

        {/* Path Change Warning */}
        {storagePathChanged && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-yellow-400" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3 flex-1">
                <h3 className="text-sm font-medium text-yellow-800">變更存儲路徑警告</h3>
                <p className="mt-1 text-sm text-yellow-700">
                  變更存儲路徑會影響後續檔案歸檔，舊檔案可能無法自動找到。
                  請確認您了解此變更的影響。
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Error Message */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3 flex-1">
                <p className="text-sm text-red-700">{error}</p>
              </div>
            </div>
          </div>
        )}

        {/* Success Message */}
        {success && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-4">
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-green-400" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3 flex-1">
                <p className="text-sm text-green-700">存儲設定已成功儲存</p>
              </div>
            </div>
          </div>
        )}

        {/* Save Button */}
        <div className="flex items-center justify-end gap-2">
          <button
            onClick={handleSaveStorageSettings}
            disabled={saving || !storagePathChanged}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            {saving ? '儲存中...' : '儲存'}
          </button>
        </div>
      </div>
      </div>
    </>
  );
}

