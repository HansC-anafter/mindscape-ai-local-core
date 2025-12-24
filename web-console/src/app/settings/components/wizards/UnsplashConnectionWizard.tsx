'use client';

import React, { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { WizardShell } from './WizardShell';
import { useWorkspaceDataOptional } from '../../../../contexts/WorkspaceDataContext';

interface UnsplashConnectionWizardProps {
  onClose: () => void;
  onSuccess: () => void;
}

interface Workspace {
  id: string;
  title: string;
  description?: string;
  unsplashConfigured?: boolean;
  unsplashStatus?: string;
}

export function UnsplashConnectionWizard({
  onClose,
  onSuccess,
}: UnsplashConnectionWizardProps) {
  const params = useParams();
  const workspaceData = useWorkspaceDataOptional();

  // Try to get workspace ID from multiple sources
  const urlWorkspaceId = params?.workspaceId as string | undefined;
  const contextWorkspaceId = workspaceData?.workspace?.id;
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string>('');
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loadingWorkspaces, setLoadingWorkspaces] = useState(false);

  // Final workspace ID: selected > context > URL params
  const workspaceId = selectedWorkspaceId || contextWorkspaceId || urlWorkspaceId;

  const [form, setForm] = useState({
    application_id: '',
    access_key: '',
    secret_key: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [currentConfig, setCurrentConfig] = useState<{
    configured: boolean;
    status?: string;
    configured_at?: string;
    application_id?: string;
  } | null>(null);

  useEffect(() => {
    loadWorkspaces();
  }, []);

  useEffect(() => {
    if (workspaceId) {
      loadCurrentConfig();
    }
  }, [workspaceId]);

  const loadWorkspaces = async () => {
    setLoadingWorkspaces(true);
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const ownerUserId = 'default-user'; // TODO: Get from auth context
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces?owner_user_id=${ownerUserId}&limit=50`,
        {
          headers: {
            'Content-Type': 'application/json',
          }
        }
      );
      if (response.ok) {
        const data = await response.json();
        const workspaceList = Array.isArray(data) ? data : [];

        // Load Unsplash config status for each workspace
        const workspacesWithConfig = await Promise.all(
          workspaceList.map(async (ws: Workspace) => {
            try {
              const configResponse = await fetch(
                `${apiUrl}/api/v1/workspaces/${ws.id}/web-generation/unsplash/config`
              );
              if (configResponse.ok) {
                const config = await configResponse.json();
                return {
                  ...ws,
                  unsplashConfigured: config.configured || false,
                  unsplashStatus: config.status || undefined,
                };
              }
            } catch (err) {
              console.error(`Failed to load config for workspace ${ws.id}:`, err);
            }
            return {
              ...ws,
              unsplashConfigured: false,
            };
          })
        );

        setWorkspaces(workspacesWithConfig);

        // Auto-select workspace if only one available
        if (workspacesWithConfig.length === 1 && !workspaceId) {
          setSelectedWorkspaceId(workspacesWithConfig[0].id);
        } else if (workspaceId) {
          setSelectedWorkspaceId(workspaceId);
        }
      } else {
        console.error('Failed to load workspaces:', response.status, response.statusText);
      }
    } catch (err) {
      console.error('Failed to load workspaces:', err);
    } finally {
      setLoadingWorkspaces(false);
    }
  };

  const loadCurrentConfig = async () => {
    if (!workspaceId) return;

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/web-generation/unsplash/config`
      );
      if (response.ok) {
        const config = await response.json();
        setCurrentConfig(config);
      }
    } catch (err) {
      console.error('Failed to load Unsplash config:', err);
    }
  };

  const handleSave = async () => {
    if (!workspaceId) {
      setError('Workspace ID is required');
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/web-generation/unsplash/config`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            application_id: form.application_id,
            access_key: form.access_key,
            secret_key: form.secret_key || undefined,
          }),
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to save Unsplash configuration');
      }

      setSuccess('Unsplash API Key 配置成功');
      setTimeout(() => {
        onSuccess();
      }, 1500);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '配置失敗';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!workspaceId) {
      setError('Workspace ID is required');
      return;
    }

    if (!confirm('確定要刪除 Unsplash 配置嗎？')) {
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/web-generation/unsplash/config`,
        {
          method: 'DELETE',
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to delete Unsplash configuration');
      }

      setSuccess('Unsplash 配置已刪除');
      setCurrentConfig({ configured: false });
      setForm({ application_id: '', access_key: '', secret_key: '' });
      setTimeout(() => {
        onSuccess();
      }, 1500);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '刪除失敗';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const footer = (
    <>
      {currentConfig?.configured && (
        <button
          onClick={handleDelete}
          disabled={loading}
          className="px-4 py-2 text-red-600 dark:text-red-400 border border-red-300 dark:border-red-600 rounded-md hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          刪除配置
        </button>
      )}
      <button
        onClick={onClose}
        className="px-4 py-2 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 bg-white dark:bg-gray-800"
      >
        {t('cancel')}
      </button>
      <button
        onClick={handleSave}
        disabled={loading || !workspaceId || !form.application_id.trim() || !form.access_key.trim()}
        className="px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {loading ? '儲存中...' : currentConfig?.configured ? '更新配置' : '儲存配置'}
      </button>
    </>
  );

  return (
    <WizardShell
      title="配置 Unsplash"
      onClose={onClose}
      error={error}
      success={success}
      footer={footer}
    >
      <div className="space-y-6">
        <div>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
            Unsplash 是一個免費的圖片平台，提供高品質的攝影作品。配置 API Key 後，可以使用 Unsplash 圖片來生成 Visual Lens。
          </p>

          {/* Workspace Selector */}
          {workspaces.length > 1 && (
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                選擇 Workspace <span className="text-red-500">*</span>
              </label>
              <select
                value={selectedWorkspaceId}
                onChange={(e) => setSelectedWorkspaceId(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-400"
                disabled={loadingWorkspaces}
              >
                <option value="">請選擇 Workspace</option>
                {workspaces.map((ws) => (
                  <option key={ws.id} value={ws.id}>
                    {ws.title} {ws.description ? `(${ws.description})` : ''}
                    {ws.unsplashConfigured ? ` - ✓ 已配置${ws.unsplashStatus ? ` [${ws.unsplashStatus}]` : ''}` : ''}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                每個 Workspace 可以配置獨立的 Unsplash API Key
              </p>
            </div>
          )}

          {workspaceId && workspaces.length === 1 && (
            <div className="mb-4 p-2 bg-accent-10 dark:bg-blue-900/20 border border-accent/30 dark:border-blue-800 rounded">
              <p className="text-xs text-accent dark:text-blue-300">
                Workspace: {workspaces.find(w => w.id === workspaceId)?.title || workspaceId}
              </p>
            </div>
          )}

          {!workspaceId && workspaces.length === 0 && !loadingWorkspaces && (
            <div className="mb-4 p-3 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded">
              <p className="text-sm text-yellow-700 dark:text-yellow-300">
                ⚠️ 無法獲取 Workspace 列表。請確保您已登入並有權限訪問 Workspace。
              </p>
            </div>
          )}

          {currentConfig?.configured && (
            <div className="mb-4 p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded">
              <p className="text-sm text-green-700 dark:text-green-300">
                ✓ 已配置（狀態：{currentConfig.status || 'active'}）
                {currentConfig.configured_at && (
                  <span className="text-xs ml-2">
                    配置時間：{new Date(currentConfig.configured_at).toLocaleString('zh-TW')}
                  </span>
                )}
              </p>
            </div>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Application ID <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={form.application_id}
            onChange={(e) => setForm({ ...form, application_id: e.target.value })}
            placeholder="輸入您的 Unsplash Application ID"
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-400"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Access Key (Client-ID) <span className="text-red-500">*</span>
          </label>
          <input
            type="password"
            value={form.access_key}
            onChange={(e) => setForm({ ...form, access_key: e.target.value })}
            placeholder="輸入您的 Unsplash Access Key"
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-400"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Secret Key <span className="text-gray-400 text-xs">(選填，用於 OAuth)</span>
          </label>
          <input
            type="password"
            value={form.secret_key}
            onChange={(e) => setForm({ ...form, secret_key: e.target.value })}
            placeholder="輸入您的 Unsplash Secret Key（選填）"
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-400"
          />
        </div>

        <div className="mt-2">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            您可以在{' '}
            <a
              href="https://unsplash.com/developers"
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent dark:text-blue-400 hover:underline"
            >
              Unsplash Developers
            </a>{' '}
            申請並取得這些憑證
          </p>
        </div>

        <div className="p-4 bg-accent-10 dark:bg-blue-900/20 border border-accent/30 dark:border-blue-800 rounded">
          <h4 className="text-sm font-medium text-accent dark:text-blue-300 mb-2">
            重要提示
          </h4>
          <ul className="text-xs text-accent dark:text-blue-200 space-y-1 list-disc list-inside">
            <li>API Key 將儲存在 Workspace Settings 中</li>
            <li>使用 Unsplash 圖片時，必須遵守 Unsplash 的使用條款</li>
            <li>必須回報圖片下載（系統會自動處理）</li>
            <li>必須顯示攝影師資訊（系統會自動處理）</li>
          </ul>
        </div>
      </div>
    </WizardShell>
  );
}

