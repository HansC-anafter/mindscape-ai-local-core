'use client';

import React, { useState } from 'react';
import { BaseModal } from '../../../../components/BaseModal';
import { useT } from '../../../../lib/i18n';
import { getApiBaseUrl } from '../../../../lib/api-url';

interface PublishTargetWizardProps {
  toolType: string;
  onClose: () => void;
  onSuccess: () => void;
}

export function PublishTargetWizard({ toolType, onClose, onSuccess }: PublishTargetWizardProps) {
  const t = useT();
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
          defaultName: 'Dropbox Publish',
          description: 'Publish to a Dropbox folder',
        };
      case 'publish_google_drive':
        return {
          name: 'Google Drive',
          defaultName: 'Google Drive Publish',
          description: 'Publish to a Google Drive folder',
        };
      case 'publish_private_cloud':
        return {
          name: 'Private Cloud',
          defaultName: 'Private Cloud Publish',
          description: 'Publish to a self-hosted cloud service',
        };
      case 'publish_custom':
        return {
          name: 'Custom Publish Service',
          defaultName: 'Custom Publish Service',
          description: 'Configure a custom publish service API',
        };
      default:
        return {
          name: 'Publish Target',
          defaultName: 'Publish Target',
          description: 'Configure a publish target',
        };
    }
  };

  const toolInfo = getToolInfo();

  const handleSave = async () => {
    try {
      setSaving(true);
      const apiUrl = getApiBaseUrl();
      const profileId = 'default-profile';

      // Create the tool connection.
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
        throw new Error(error.detail || 'Failed to create connection');
      }

      // Keep legacy publish-service configuration in sync.
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
      alert(`Configuration failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BaseModal
      isOpen={true}
      onClose={onClose}
      title={`Configure ${toolInfo.name}`}
      maxWidth="max-w-2xl"
    >
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Name
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
            Description
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
                placeholder="Enter API key"
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
                Target Folder Path
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
                Target Folder ID
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
            Provider ID (optional)
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
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </BaseModal>
  );
}
