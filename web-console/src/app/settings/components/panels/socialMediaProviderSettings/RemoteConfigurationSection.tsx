import React from 'react';

import { t } from '../../../../../lib/i18n';
import type { RemoteConfig, SocialMediaConnection } from './types';

interface RemoteConfigurationSectionProps {
  connection: SocialMediaConnection | null;
  remoteConfig: RemoteConfig;
  savingConfig: boolean;
  onRemoteConfigChange: (config: RemoteConfig) => void;
  onSave: () => void;
}

export function RemoteConfigurationSection({
  connection,
  remoteConfig,
  savingConfig,
  onRemoteConfigChange,
  onSave,
}: RemoteConfigurationSectionProps) {
  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
      <h3 className="font-medium text-gray-900 dark:text-gray-100 mb-4">
        {t('lineCloudRemoteTools' as any)}
      </h3>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
        {t('lineCloudRemoteToolsDescription' as any)}
      </p>

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {t('cloudRemoteToolsUrl' as any)} <span className="text-red-500">*</span>
          </label>
          <input
            type="url"
            value={remoteConfig.cluster_url}
            onChange={(event) => onRemoteConfigChange({ ...remoteConfig, cluster_url: event.target.value })}
            placeholder={t('cloudRemoteToolsUrlPlaceholder' as any)}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 dark:focus:ring-purple-400 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          />
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {t('cloudRemoteToolsUrlDescription' as any)}
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {t('channelId' as any)} <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={remoteConfig.channel_id}
            onChange={(event) => onRemoteConfigChange({ ...remoteConfig, channel_id: event.target.value })}
            placeholder={t('channelIdPlaceholder' as any)}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 dark:focus:ring-purple-400 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          />
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {t('channelIdDescription' as any)}
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {t('cloudRemoteToolsApiToken' as any)}
          </label>
          <input
            type="password"
            value={remoteConfig.api_token}
            onChange={(event) => onRemoteConfigChange({ ...remoteConfig, api_token: event.target.value })}
            placeholder={connection?.config && 'api_token' in connection.config ? '******** (configured)' : t('cloudRemoteToolsApiTokenPlaceholder' as any)}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 dark:focus:ring-purple-400 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          />
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {t('cloudRemoteToolsApiTokenDescription' as any)}
          </p>
        </div>

        <button
          onClick={onSave}
          disabled={savingConfig || !remoteConfig.cluster_url || !remoteConfig.channel_id}
          className="px-4 py-2 bg-purple-600 dark:bg-purple-500 text-white rounded-md hover:bg-purple-700 dark:hover:bg-purple-600 disabled:opacity-50 text-sm font-medium"
        >
          {savingConfig ? t('saving' as any) : 'Save Cloud Remote Tools Configuration'}
        </button>
      </div>
    </div>
  );
}
