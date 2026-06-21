import React from 'react';

import { t } from '../../../../../lib/i18n';
import { getOAuthCallbackUrl } from './constants';
import type { OAuthConfig, SocialMediaConnection } from './types';

interface OAuthConfigurationSectionProps {
  connection: SocialMediaConnection | null;
  oauthConfig: OAuthConfig;
  provider: string;
  savingConfig: boolean;
  onOauthConfigChange: (config: OAuthConfig) => void;
  onSave: () => void;
}

export function OAuthConfigurationSection({
  connection,
  oauthConfig,
  provider,
  savingConfig,
  onOauthConfigChange,
  onSave,
}: OAuthConfigurationSectionProps) {
  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
      <h3 className="font-medium text-gray-900 dark:text-gray-100 mb-4">
        {'OAuth Configuration'}
      </h3>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
        {'Configure OAuth Client ID and Secret for this platform'}
      </p>

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {'Client ID'} <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={oauthConfig.client_id}
            onChange={(event) => onOauthConfigChange({ ...oauthConfig, client_id: event.target.value })}
            placeholder="Enter OAuth Client ID"
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {'Client Secret'} <span className="text-red-500">*</span>
          </label>
          <input
            type="password"
            value={oauthConfig.client_secret}
            onChange={(event) => onOauthConfigChange({ ...oauthConfig, client_secret: event.target.value })}
            placeholder={connection?.config?.client_secret ? '******** (configured)' : 'Enter OAuth Client Secret'}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          />
          {connection?.config?.client_secret && !oauthConfig.client_secret && (
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {'Leave blank to keep existing secret'}
            </p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {t('redirectURI' as any) || 'Redirect URI'}
          </label>
          <input
            type="url"
            value={oauthConfig.redirect_uri}
            onChange={(event) => onOauthConfigChange({ ...oauthConfig, redirect_uri: event.target.value })}
            placeholder={getOAuthCallbackUrl(provider)}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          />
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {t('redirectURIDescription' as any) || 'OAuth callback URL. Default will be used if not specified.'}
          </p>
        </div>

        <button
          onClick={onSave}
          disabled={savingConfig || !oauthConfig.client_id || (!oauthConfig.client_secret && !connection?.config?.client_secret)}
          className="px-4 py-2 bg-gray-600 dark:bg-gray-500 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50 text-sm font-medium"
        >
          {savingConfig ? t('saving' as any) : 'Save OAuth Configuration'}
        </button>
      </div>
    </div>
  );
}
