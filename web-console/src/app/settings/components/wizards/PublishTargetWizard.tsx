'use client';

import React, { useState } from 'react';
import { BaseModal } from '../../../../components/BaseModal';
import { t } from '../../../../lib/i18n';
import { getApiBaseUrl } from '../../../../lib/api-url';

interface PublishTargetWizardProps {
  toolType: string;
  onClose: () => void;
  onSuccess: () => void;
}

export function PublishTargetWizard({ toolType, onClose, onSuccess }: PublishTargetWizardProps) {
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    api_url: '',
    api_key: '',
    folder_path: '',
    provider_id: '',
    storage_backend: 'gcs',
    storage_config: {} as Record<string, any>,
  });

  const getToolInfo = () => {
    switch (toolType) {
      case 'publish_dropbox':
        return {
          name: 'Dropbox',
          defaultName: 'Dropbox 發佈',
          description: '發佈到 Dropbox 文件夾',
          icon: '📦',
        };
      case 'publish_google_drive':
        return {
          name: 'Google Drive',
          defaultName: 'Google Drive 發佈',
          description: '發佈到 Google Drive 文件夾',
          icon: '☁️',
        };
      case 'publish_private_cloud':
        return {
          name: 'Private Cloud',
          defaultName: '私有雲端發佈',
          description: '發佈到自託管雲端服務',
          icon: '🏢',
        };
      case 'publish_custom':
        return {
          name: '自定義發佈服務',
          defaultName: '自定義發佈服務',
          description: '配置自定義的發佈服務 API',
          icon: '🔧',
        };
      default:
        return {
          name: '發佈目標',
          defaultName: '發佈目標',
          description: '配置發佈目標',
          icon: '📤',
        };
    }
  };

  const toolInfo = getToolInfo();

  const handleSave = async () => {
    try {
      setSaving(true);
      const apiUrl = getApiBaseUrl();
      const profileId = 'default-profile'; // TODO: Get from auth context

      // 創建工具連接
      const connectionResponse = await fetch(`${apiUrl}/api/v1/tools/connections?profile_id=${profileId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          tool_type: toolType,
          connection_type: 'api',
          name: formData.name || toolInfo.defaultName,
          description: formData.description || toolInfo.description,
          api_key: formData.api_key,
          base_url: formData.api_url,
          config: {
            folder_path: formData.folder_path,
            provider_id: formData.provider_id,
            storage_backend: formData.storage_backend,
            storage_config: formData.storage_config,
          },
        }),
      });

      if (!connectionResponse.ok) {
        const error = await connectionResponse.json();
        throw new Error(error.detail || '創建連接失敗');
      }

      // 同時更新發佈服務配置（用於向後兼容）
      if (formData.api_url) {
        await fetch(`${apiUrl}/api/v1/publish-service/config`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            api_url: formData.api_url,
            api_key: formData.api_key,
            enabled: true,
            provider_id: formData.provider_id,
            storage_backend: formData.storage_backend,
            storage_config: formData.storage_config,
          }),
        });
      }

      onSuccess();
      onClose();
    } catch (error) {
      alert(`配置失敗: ${error instanceof Error ? error.message : '未知錯誤'}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BaseModal
      isOpen={true}
      onClose={onClose}
      title={`配置 ${toolInfo.name}`}
      maxWidth="max-w-2xl"
    >
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            名稱
          </label>
          <input
            type="text"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            placeholder={toolInfo.defaultName}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            描述
          </label>
          <input
            type="text"
            value={formData.description}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
            placeholder={toolInfo.description}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          />
        </div>

        {toolType === 'publish_custom' && (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                API URL <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={formData.api_url}
                onChange={(e) => setFormData({ ...formData, api_url: e.target.value })}
                placeholder="https://api.example.com"
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
          </>
        )}

        {toolType === 'publish_dropbox' && (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Dropbox Access Token <span className="text-red-500">*</span>
              </label>
              <input
                type="password"
                value={formData.api_key}
                onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                placeholder="Dropbox Access Token"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                目標文件夾路徑
              </label>
              <input
                type="text"
                value={formData.folder_path}
                onChange={(e) => setFormData({ ...formData, folder_path: e.target.value })}
                placeholder="/Apps/Mindscape/Publish"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              />
            </div>
          </>
        )}

        {toolType === 'publish_google_drive' && (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Google Drive API Key <span className="text-red-500">*</span>
              </label>
              <input
                type="password"
                value={formData.api_key}
                onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                placeholder="Google Drive API Key"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                目標文件夾 ID
              </label>
              <input
                type="text"
                value={formData.folder_path}
                onChange={(e) => setFormData({ ...formData, folder_path: e.target.value })}
                placeholder="Google Drive Folder ID"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              />
            </div>
          </>
        )}

        {toolType === 'publish_private_cloud' && (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                API URL <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={formData.api_url}
                onChange={(e) => setFormData({ ...formData, api_url: e.target.value })}
                placeholder="https://your-private-cloud.com/api"
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
                placeholder="API Key"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Storage Backend
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
          </>
        )}

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

        <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded hover:bg-gray-200 dark:hover:bg-gray-600"
          >
            {t('cancel' as any)}
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || (toolType === 'publish_custom' && (!formData.api_url || !formData.api_key)) || (toolType !== 'publish_custom' && !formData.api_key)}
            className="px-4 py-2 text-sm bg-orange-600 text-white rounded hover:bg-orange-700 disabled:opacity-50"
          >
            {saving ? '儲存中...' : '儲存'}
          </button>
        </div>
      </div>
    </BaseModal>
  );
}

