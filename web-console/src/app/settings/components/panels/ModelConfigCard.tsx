'use client';

import React, { useState } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';

interface ModelItem {
  id: string | number;
  model_name: string;
  provider: string;
  model_type: 'chat' | 'embedding';
  display_name: string;
  description: string;
  enabled: boolean;
  icon?: string;
  is_latest?: boolean;
  is_recommended?: boolean;
  dimensions?: number;
  context_window?: number;
}

interface ModelConfigCardData {
  model: ModelItem;
  api_key_configured: boolean;
  base_url?: string;
  quota_info?: {
    used: number;
    limit: number;
    reset_date?: string;
  };
}

interface ModelConfigCardProps {
  card: ModelConfigCardData;
}

export function ModelConfigCard({ card }: ModelConfigCardProps) {
  const { model, api_key_configured, base_url, quota_info } = card;
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState(base_url || '');
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  const handleSaveApiKey = async () => {
    try {
      setSaving(true);
      await settingsApi.put(`/api/v1/system-settings/models/${model.id}/api-key`, { api_key: apiKey });
    } catch (err) {
      console.error('Failed to save API key:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleTestConnection = async () => {
    try {
      setTesting(true);
      setTestResult(null);
      const result = await settingsApi.post<{ success: boolean; message: string }>(
        `/api/v1/system-settings/models/${model.id}/test`,
        {}
      );
      if (result.success) {
        setTestResult(result.message);
      } else {
        setTestResult(`${t('testFailedWithError')}: ${result.message}`);
      }
    } catch (err) {
      setTestResult(`${t('testFailedWithError')}: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
      <div className="flex items-center gap-3 mb-4">
        {model.icon && <span className="text-2xl">{model.icon}</span>}
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {model.display_name}
          </h3>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {model.provider} • {model.model_type === 'chat' ? 'Chat Model' : 'Embedding Model'}
          </p>
        </div>
      </div>

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            {t('apiKey')} ({model.provider})
          </label>
          <div className="flex items-center gap-2">
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={api_key_configured ? '••••••••' : (t('enterApiKey') || 'Enter API Key')}
              className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 dark:focus:ring-purple-400 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            />
            <button
              onClick={handleSaveApiKey}
              disabled={saving}
              className="px-4 py-2 bg-blue-600 dark:bg-blue-700 text-white rounded-md hover:bg-blue-700 dark:hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {api_key_configured ? t('update') : t('configure')}
            </button>
          </div>
          {api_key_configured && (
            <span className="text-xs text-green-600 dark:text-green-400 mt-1 block">
              {t('apiKeyConfigured') || 'API Key configured'}
            </span>
          )}
        </div>

        {model.provider === 'ollama' && (
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {t('baseUrl') || 'Base URL'} ({t('optional') || 'Optional'})
            </label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="http://localhost:11434"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 dark:focus:ring-purple-400 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            />
          </div>
        )}

        <div className="grid grid-cols-2 gap-4">
          {model.dimensions && (
            <div>
              <span className="text-xs text-gray-500 dark:text-gray-400">{t('dimensions') || 'Dimensions'}</span>
              <div className="text-sm font-medium text-gray-900 dark:text-gray-100">{model.dimensions}</div>
            </div>
          )}
          {model.context_window && (
            <div>
              <span className="text-xs text-gray-500 dark:text-gray-400">{t('contextWindow') || 'Context Window'}</span>
              <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                {model.context_window.toLocaleString()}
              </div>
            </div>
          )}
        </div>

        <div>
          <button
            onClick={handleTestConnection}
            disabled={testing}
            className="w-full px-4 py-2 bg-purple-600 dark:bg-purple-700 text-white rounded-md hover:bg-purple-700 dark:hover:bg-purple-600 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {testing ? t('testing') : t('testConnection')}
          </button>
          {testResult && (
            <div className={`mt-2 p-2 rounded text-sm ${
              testResult.includes('success') || testResult.includes('Success')
                ? 'bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-300'
                : 'bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-300'
            }`}>
              {testResult}
            </div>
          )}
        </div>

        {quota_info && (
          <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                {t('quotaUsage')}
              </span>
              <span className="text-sm text-gray-500 dark:text-gray-400">
                {quota_info.used} / {quota_info.limit}
              </span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
              <div
                className="bg-purple-600 h-2 rounded-full"
                style={{ width: `${(quota_info.used / quota_info.limit) * 100}%` }}
              />
            </div>
            {quota_info.reset_date && (
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                {t('resetDate') || 'Reset Date'}: {quota_info.reset_date}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

