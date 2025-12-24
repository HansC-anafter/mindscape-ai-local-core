'use client';

import React, { useState, useEffect } from 'react';
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

interface LLMChatSettingsResponse {
  chat_model?: LLMModelConfig;
  available_chat_models: Array<{
    model_name: string;
    provider: string;
    description: string;
    is_latest?: boolean;
    is_recommended?: boolean;
    is_deprecated?: boolean;
  }>;
}

export function LLMChatSettings() {
  const [loading, setLoading] = useState(true);
  const [settings, setSettings] = useState<LLMChatSettingsResponse | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { enabledModels: enabledChatModels } = useEnabledModels('chat');

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      setLoading(true);
      const data = await settingsApi.get<LLMChatSettingsResponse>('/api/v1/system-settings/llm-models');
      setSettings(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load LLM chat settings');
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
      }>('/api/v1/system-settings/llm-models/test-chat');

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

  const updateChatModel = async (modelName: string, provider: string) => {
    try {
      setError(null);
      await settingsApi.put(`/api/v1/system-settings/llm-models/chat?model_name=${modelName}&provider=${provider}`, {});
      await loadSettings();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update chat model');
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
        <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">{t('llmChatModel') || 'LLM 推理與對話'}</h3>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
          {t('llmChatModelDescription') || '配置用於推理和對話的 LLM 模型'}
          {settings.chat_model && (
            <span className="ml-2">
              {t('currentModel')}: <strong>{settings.chat_model.model_name}</strong> ({settings.chat_model.provider})
            </span>
          )}
        </p>
      </div>

      <div className="flex items-center gap-3 mb-4">
        <button
          onClick={testConnection}
          disabled={testing}
          className="px-3 py-1.5 text-sm bg-accent dark:bg-blue-700 text-white rounded-md hover:bg-accent/90 dark:hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
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
          {t('selectChatModel') || '選擇 Chat 模型'}
        </label>
        {enabledChatModels.length === 0 ? (
          <div className="p-3 border border-gray-300 dark:border-gray-600 rounded-md bg-gray-50 dark:bg-gray-800 text-sm text-gray-500 dark:text-gray-400">
            {t('noEnabledModels') || '沒有已啟用的 Chat 模型。請在「模型與配額」中啟用至少一個模型。'}
          </div>
        ) : (
          <select
            value={settings.chat_model?.model_name || ''}
            onChange={(e) => {
              const selected = enabledChatModels.find(m => m.model_name === e.target.value);
              if (selected) {
                updateChatModel(selected.model_name, selected.provider);
              }
            }}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          >
            {enabledChatModels.map((model) => (
              <option key={model.model_name} value={model.model_name}>
                {model.display_name || model.model_name} {model.is_deprecated && `(${t('deprecated')})`} - {model.description}
              </option>
            ))}
          </select>
        )}
      </div>
    </div>
  );
}

