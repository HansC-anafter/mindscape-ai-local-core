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
  const [showGuide, setShowGuide] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [installStatus, setInstallStatus] = useState<string | null>(null);

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
      setTestResult(`${t('testFailedWithError' as any)}: ${err instanceof Error ? err.message : 'Unknown error'}`);
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

  const handleInstallModel = async () => {
    try {
      setInstalling(true);
      setInstallStatus(t('modelInstallStarted' as any) || 'Installation started...');

      const result = await settingsApi.post<{
        success: boolean;
        message: string;
      }>('/api/v1/system-settings/llm-models/pull', {
        model_name: 'llama3',
        provider: 'ollama'
      });

      if (result.success) {
        setInstallStatus(`✅ ${t('modelInstallStarted' as any)}`);
      } else {
        setInstallStatus(`❌ ${t('modelInstallFailed' as any)}: ${result.message}`);
      }
    } catch (err) {
      setInstallStatus(`❌ ${t('modelInstallFailed' as any)}: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setInstalling(false);
    }
  };

  if (loading) {
    return <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">{t('loading' as any)}</div>;
  }

  if (!settings) {
    return <div className="text-sm text-red-600 dark:text-red-400">{error || t('failedToLoad' as any)}</div>;
  }

  return (
    <div className="space-y-4">
      {error && <InlineAlert type="error" message={error} onDismiss={() => setError(null)} />}

      <div>
        <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">{t('llmChatModel' as any) || 'LLM 推理與對話'}</h3>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
          {t('llmChatModelDescription' as any) || '配置用於推理和對話的 LLM 模型'}
          {settings.chat_model && (
            <span className="ml-2">
              {t('currentModel' as any)}: <strong>{settings.chat_model.model_name}</strong> ({settings.chat_model.provider})
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
          {testing ? t('testing' as any) : t('testConnection' as any)}
        </button>
      </div>

      {testResult && (
        <div className={`mb-3 p-2 rounded text-sm ${testResult.includes('success') || testResult.includes('Success') ? 'bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-300' : 'bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-300'}`}>
          {testResult}
        </div>
      )}

      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          {t('selectChatModel' as any) || '選擇 Chat 模型'}
        </label>
        {enabledChatModels.length === 0 ? (
          <div className="p-3 border border-gray-300 dark:border-gray-600 rounded-md bg-gray-50 dark:bg-gray-800 text-sm text-gray-500 dark:text-gray-400">
            {t('noEnabledModels' as any) || '沒有已啟用的 Chat 模型。請在「模型與配額」中啟用至少一個模型。'}
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
                {model.display_name || model.model_name} {model.is_deprecated && `(${t('deprecated' as any)})`} - {model.description}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Ollama Guide Section */}
      <div className="border border-blue-200 dark:border-blue-800 rounded-lg bg-blue-50 dark:bg-blue-900/20 overflow-hidden">
        <button
          onClick={() => setShowGuide(!showGuide)}
          className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-colors"
        >
          <div className="flex items-center gap-2">
            <span className="text-xl">🦙</span>
            <span className="text-sm font-medium text-blue-900 dark:text-blue-100">
              {t('ollamaSetup' as any) || 'Ollama Setup Guide'}
            </span>
          </div>
          <svg
            className={`w-4 h-4 text-blue-500 transform transition-transform duration-200 ${showGuide ? 'rotate-180' : ''}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {showGuide && (
          <div className="px-4 pb-4 space-y-3 text-sm text-blue-800 dark:text-blue-200 border-t border-blue-200 dark:border-blue-800 pt-3">
            <div className="flex gap-3">
              <span className="flex-shrink-0 w-5 h-5 flex items-center justify-center rounded-full bg-blue-200 dark:bg-blue-800 text-blue-800 dark:text-blue-200 text-xs font-bold">1</span>
              <div className="flex-1">
                <span>{t('ollamaSetupStep1' as any) || 'Install & Run Ollama: Install Ollama on your host and run "ollama serve"'}</span>
              </div>
            </div>

            <div className="flex gap-3">
              <span className="flex-shrink-0 w-5 h-5 flex items-center justify-center rounded-full bg-blue-200 dark:bg-blue-800 text-blue-800 dark:text-blue-200 text-xs font-bold">2</span>
              <div className="flex-1">
                <span className="block mb-1">{t('ollamaSetupStep2' as any) || 'Download Model:'}</span>
                <div className="flex items-center gap-2 mb-2">
                  <code className="flex-1 bg-gray-900 text-gray-100 px-3 py-2 rounded font-mono text-xs select-all cursor-pointer hover:bg-gray-800 transition-colors">
                    ollama pull llama3
                  </code>
                  <button
                    onClick={handleInstallModel}
                    disabled={installing}
                    className="px-3 py-2 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
                  >
                    {installing ? (t('installingModel' as any) || 'Installing...') : (t('installModel' as any) || 'Install Model')}
                  </button>
                </div>
                {installStatus && (
                  <div className={`text-xs p-2 rounded ${installStatus.includes('❌') ? 'bg-red-50 text-red-800' : 'bg-green-50 text-green-800'}`}>
                    {installStatus}
                  </div>
                )}
              </div>
            </div>

            <div className="flex gap-3">
              <span className="flex-shrink-0 w-5 h-5 flex items-center justify-center rounded-full bg-blue-200 dark:bg-blue-800 text-blue-800 dark:text-blue-200 text-xs font-bold">3</span>
              <div className="flex-1">
                <span className="block mb-1">{t('ollamaSetupStep3' as any) || 'Restart Mindscape:'}</span>
                <code className="block w-full bg-gray-900 text-gray-100 px-3 py-2 rounded font-mono text-xs select-all cursor-pointer hover:bg-gray-800 transition-colors">
                  docker-compose up -d
                </code>
              </div>
            </div>

            <div className="flex gap-3">
              <span className="flex-shrink-0 w-5 h-5 flex items-center justify-center rounded-full bg-blue-200 dark:bg-blue-800 text-blue-800 dark:text-blue-200 text-xs font-bold">4</span>
              <div className="flex-1">
                <span>{t('ollamaSetupStep4' as any) || 'Configure Mindscape: Set Chat Model to "llama3"'}</span>
              </div>
            </div>

            <div className="flex gap-3">
              <span className="flex-shrink-0 w-5 h-5 flex items-center justify-center rounded-full bg-blue-200 dark:bg-blue-800 text-blue-800 dark:text-blue-200 text-xs font-bold">5</span>
              <div className="flex-1">
                <span>{t('ollamaSetupStep5' as any) || 'Run Agent: Use any agent feature'}</span>
              </div>
            </div>

            <div className="mt-2 text-xs opacity-75 pt-2 border-t border-blue-200 dark:border-blue-800 italic">
              {t('ollamaSetupNote' as any) || 'Note: Ensure Ollama keeps running on your host.'}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

