'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { InlineAlert } from '../InlineAlert';
import { useEnabledModels } from '../../hooks/useEnabledModels';

interface LLMModelConfig {
  model_name: string;
  provider: string;
  model_type: 'chat' | 'embedding';
  api_key_setting_key?: string;
  metadata?: Record<string, any>;
}

interface EmbeddingSettingsResponse {
  embedding_model?: LLMModelConfig;
  available_embedding_models: Array<{
    model_name: string;
    provider: string;
    description: string;
    is_latest?: boolean;
    is_recommended?: boolean;
    dimensions?: number;
  }>;
}

export function EmbeddingSettings() {
  const [loading, setLoading] = useState(true);
  const [settings, setSettings] = useState<EmbeddingSettingsResponse | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { enabledModels: enabledEmbeddingModels } = useEnabledModels('embedding');

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      setLoading(true);
      const data = await settingsApi.get<EmbeddingSettingsResponse>('/api/v1/system-settings/llm-models');
      setSettings(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load embedding settings');
    } finally {
      setLoading(false);
    }
  };

  const testConnection = async () => {
    try {
      setTesting(true);
      setTestResult(null);
      const result = await settingsApi.post<{
        success: boolean;
        message: string;
        model_name: string;
        provider: string;
        dimensions?: number;
      }>('/api/v1/system-settings/llm-models/test-embedding');

      if (result.success) {
        setTestResult(result.message);
      } else {
        setTestResult(result.message);
      }
    } catch (err) {
      setTestResult(`${t('testFailedWithError')}: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setTesting(false);
    }
  };

  const updateEmbeddingModel = async (modelName: string, provider: string) => {
    try {
      setError(null);
      await settingsApi.put(`/api/v1/system-settings/llm-models/embedding?model_name=${modelName}&provider=${provider}`, {});
      await loadSettings();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update embedding model');
    }
  };

  if (loading) {
    return <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">{t('loading')}</div>;
  }

  if (!settings) {
    return <div className="text-sm text-red-600 dark:text-red-400">{error || t('failedToLoad')}</div>;
  }

  return (
    <div className="space-y-4">
      {error && <InlineAlert type="error" message={error} onDismiss={() => setError(null)} />}

      <div>
        <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">{t('embeddingModel')}</h3>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
          {t('embeddingModelDescription')}
          {settings.embedding_model && (
            <span className="ml-2">
              {t('currentModel')}: <strong>{settings.embedding_model.model_name}</strong> ({settings.embedding_model.provider})
            </span>
          )}
        </p>
      </div>

      <div className="flex items-center gap-3 mb-4">
        <button
          onClick={testConnection}
          disabled={testing}
          className="px-3 py-1.5 text-sm bg-blue-600 dark:bg-blue-700 text-white rounded-md hover:bg-blue-700 dark:hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {testing ? t('testing') : t('testConnection')}
        </button>
      </div>

      {testResult && (
        <div className={`mb-3 p-2 rounded text-sm ${testResult.includes('success') || testResult.includes('Success') ? 'bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-300' : 'bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-300'}`}>
          {testResult}
        </div>
      )}

      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          {t('selectEmbeddingModel') || '選擇 Embedding 模型'}
        </label>
        {enabledEmbeddingModels.length === 0 ? (
          <div className="p-3 border border-gray-300 dark:border-gray-600 rounded-md bg-gray-50 dark:bg-gray-800 text-sm text-gray-500 dark:text-gray-400">
            {t('noEnabledModels') || '沒有已啟用的 Embedding 模型。請在「模型與配額」中啟用至少一個模型。'}
          </div>
        ) : (
          <select
            value={settings.embedding_model?.model_name || ''}
            onChange={(e) => {
              const selected = enabledEmbeddingModels.find(m => m.model_name === e.target.value);
              if (selected) {
                updateEmbeddingModel(selected.model_name, selected.provider);
              }
            }}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 dark:focus:ring-purple-400 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          >
            {enabledEmbeddingModels.map((model) => (
              <option key={model.model_name} value={model.model_name}>
                {model.display_name || model.model_name} - {model.description}
              </option>
            ))}
          </select>
        )}
      </div>
    </div>
  );
}

