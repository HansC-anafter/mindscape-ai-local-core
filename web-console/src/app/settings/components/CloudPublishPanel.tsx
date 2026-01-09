'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../../../lib/i18n';
import { Card } from './Card';
import { BaseModal } from '../../../components/BaseModal';
import { getApiBaseUrl } from '../../../lib/api-url';

interface PublishServiceConfig {
  api_url: string;
  api_key: string;
  enabled: boolean;
  provider_id?: string;
  storage_backend?: string;
  storage_config?: Record<string, any>;
}

interface PublishTarget {
  id: string;
  tool_type: string;
  name: string;
  description: string;
  is_active: boolean;
  config?: Record<string, any>;
}

export function CloudPublishPanel() {
  const [loading, setLoading] = useState(true);
  const [config, setConfig] = useState<PublishServiceConfig | null>(null);
  const [publishTargets, setPublishTargets] = useState<PublishTarget[]>([]);
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  const [formData, setFormData] = useState<PublishServiceConfig>({
    api_url: '',
    api_key: '',
    enabled: true,
    provider_id: '',
    storage_backend: 'gcs',
    storage_config: {}
  });

  useEffect(() => {
    loadConfig();
    loadPublishTargets();
  }, []);

  const loadConfig = async () => {
    try {
      const response = await fetch('/api/v1/publish-service/config');
      if (response.ok) {
        const data = await response.json();
        if (data) {
          setConfig(data);
          setFormData({
            api_url: data.api_url || '',
            api_key: data.api_key || '',
            enabled: data.enabled !== false,
            provider_id: data.provider_id || '',
            storage_backend: data.storage_backend || 'gcs',
            storage_config: data.storage_config || {}
          });
        }
      }
    } catch (error) {
      console.error('載入發佈服務配置失敗:', error);
    }
  };

  const loadPublishTargets = async () => {
    try {
      setLoading(true);
      const apiUrl = getApiBaseUrl();
      const profileId = 'default-profile'; // TODO: Get from auth context

      // 載入所有發佈目標工具連接
      const response = await fetch(`${apiUrl}/api/v1/tools/connections?profile_id=${profileId}&tool_type=publish_dropbox,publish_google_drive,publish_private_cloud,publish_custom`);
      if (response.ok) {
        const connections = await response.json();
        const targets: PublishTarget[] = connections
          .filter((conn: any) =>
            conn.tool_type?.startsWith('publish_')
          )
          .map((conn: any) => ({
            id: conn.id,
            tool_type: conn.tool_type,
            name: conn.name || conn.tool_type,
            description: conn.description || '',
            is_active: conn.is_active !== false,
            config: conn.config || {}
          }));
        setPublishTargets(targets);
      }
    } catch (error) {
      console.error('載入發佈目標失敗:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleTestConnection = async () => {
    try {
      setTesting(true);
      setTestResult(null);
      const response = await fetch('/api/v1/publish-service/test', {
        method: 'POST'
      });
      const result = await response.json();
      setTestResult(result);
    } catch (error) {
      setTestResult({
        success: false,
        message: `測試失敗: ${error instanceof Error ? error.message : '未知錯誤'}`
      });
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      const response = await fetch('/api/v1/publish-service/config', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(formData)
      });

      if (response.ok) {
        await loadConfig();
        setShowConfigModal(false);
        setTestResult(null);
      } else {
        const error = await response.json();
        alert(`儲存失敗: ${error.detail || '未知錯誤'}`);
      }
    } catch (error) {
      alert(`儲存失敗: ${error instanceof Error ? error.message : '未知錯誤'}`);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    if (config) {
      setFormData({
        api_url: config.api_url || '',
        api_key: config.api_key || '',
        enabled: config.enabled !== false,
        provider_id: config.provider_id || '',
        storage_backend: config.storage_backend || 'gcs',
        storage_config: config.storage_config || {}
      });
    } else {
      setFormData({
        api_url: '',
        api_key: '',
        enabled: true,
        provider_id: '',
        storage_backend: 'gcs',
        storage_config: {}
      });
    }
    setTestResult(null);
  };

  if (loading) {
    return (
      <Card>
        <div className="text-center py-12 text-gray-500 dark:text-gray-400">
          {t('loading')}
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <div className="space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
              雲端發佈
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              將 Playbook 和 Capability 發佈到雲端服務。配置發佈服務的 API 端點和認證資訊。
            </p>
          </div>

          {/* 發佈服務配置狀態 */}
          <div className="border rounded-lg p-4 space-y-3">
            {config ? (
              <>
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="font-medium text-gray-900 dark:text-gray-100">
                        發佈服務
                      </h3>
                      <span className={`px-2 py-1 text-xs rounded ${
                        config.enabled
                          ? 'bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400'
                          : 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400'
                      }`}>
                        {config.enabled ? '已啟用' : '已禁用'}
                      </span>
                    </div>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                      API URL: {config.api_url}
                    </p>
                    {config.provider_id && (
                      <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                        Provider ID: {config.provider_id}
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setShowConfigModal(true)}
                    className="px-3 py-1.5 text-sm bg-gray-600 text-white rounded hover:bg-gray-700"
                  >
                    編輯配置
                  </button>
                  <button
                    type="button"
                    onClick={handleTestConnection}
                    disabled={testing}
                    className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                  >
                    {testing ? '測試中...' : '測試連接'}
                  </button>
                </div>
                {testResult && (
                  <div className={`p-3 rounded text-sm ${
                    testResult.success
                      ? 'bg-green-50 text-green-800 dark:bg-green-900/20 dark:text-green-400'
                      : 'bg-red-50 text-red-800 dark:bg-red-900/20 dark:text-red-400'
                  }`}>
                    {testResult.message}
                  </div>
                )}
              </>
            ) : (
              <div className="text-center py-8">
                <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
                  尚未配置發佈服務
                </p>
                <button
                  type="button"
                  onClick={() => setShowConfigModal(true)}
                  className="px-4 py-2 bg-orange-600 text-white rounded hover:bg-orange-700"
                >
                  配置發佈服務
                </button>
              </div>
            )}
          </div>
        </div>
      </Card>

      {/* 配置說明 */}
      <Card>
        <div className="space-y-4">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
              關於發佈服務
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              發佈服務負責處理 Playbook 和 Capability 的打包、上傳和註冊。您可以配置任何符合標準的發佈服務 API。
            </p>
          </div>
          <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 space-y-2">
            <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
              發佈目標類型：
            </h3>
            <ul className="text-sm text-gray-600 dark:text-gray-400 space-y-1 list-disc list-inside">
              <li><strong>Dropbox</strong>：發佈到 Dropbox 文件夾</li>
              <li><strong>Google Drive</strong>：發佈到 Google Drive 文件夾</li>
              <li><strong>Private Cloud</strong>：發佈到自託管雲端服務</li>
              <li><strong>自定義發佈服務</strong>：配置自定義的發佈服務 API</li>
            </ul>
            <p className="text-xs text-gray-500 dark:text-gray-500 mt-3">
              提示：發佈目標在「能力包管理」→「發佈目標」中配置和管理
            </p>
          </div>
        </div>
      </Card>

      {/* 配置對話框 */}
      <BaseModal
        isOpen={showConfigModal}
        onClose={() => {
          setShowConfigModal(false);
          handleReset();
        }}
        title="配置發佈服務"
        maxWidth="max-w-2xl"
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              API URL <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={formData.api_url}
              onChange={(e) => setFormData({ ...formData, api_url: e.target.value })}
              placeholder="https://api.mindscape-ai-cloud.com"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              API Key <span className="text-red-500">*</span>
            </label>
            <input
              type="password"
              value={formData.api_key}
              onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
              placeholder="輸入 API Key"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Provider ID（可選）
            </label>
            <input
              type="text"
              value={formData.provider_id}
              onChange={(e) => setFormData({ ...formData, provider_id: e.target.value })}
              placeholder="mindscape-ai"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Storage Backend（可選）
            </label>
            <select
              value={formData.storage_backend}
              onChange={(e) => setFormData({ ...formData, storage_backend: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            >
              <option value="gcs">Google Cloud Storage (GCS)</option>
              <option value="s3">Amazon S3</option>
              <option value="r2">Cloudflare R2</option>
            </select>
          </div>

          <div className="flex items-center">
            <input
              type="checkbox"
              id="enabled"
              checked={formData.enabled}
              onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
              className="h-4 w-4 text-orange-600 focus:ring-orange-500 border-gray-300 rounded"
            />
            <label htmlFor="enabled" className="ml-2 block text-sm text-gray-700 dark:text-gray-300">
              啟用發佈服務
            </label>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
            <button
              type="button"
              onClick={() => {
                setShowConfigModal(false);
                handleReset();
              }}
              className="px-4 py-2 text-sm text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded hover:bg-gray-200 dark:hover:bg-gray-600"
            >
              {t('cancel')}
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving || !formData.api_url || !formData.api_key}
              className="px-4 py-2 text-sm bg-orange-600 text-white rounded hover:bg-orange-700 disabled:opacity-50"
            >
              {saving ? '儲存中...' : '儲存'}
            </button>
          </div>
        </div>
      </BaseModal>
    </div>
  );
}
