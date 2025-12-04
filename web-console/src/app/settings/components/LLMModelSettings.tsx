'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../../../lib/i18n';
import { settingsApi } from '../utils/settingsApi';
import { InlineAlert } from './InlineAlert';

interface LLMModelConfig {
  model_name: string;
  provider: string;
  model_type: 'chat' | 'embedding';
  api_key_setting_key?: string;
  metadata?: Record<string, any>;
}

interface LLMModelSettingsResponse {
  chat_model?: LLMModelConfig;
  embedding_model?: LLMModelConfig;
  available_chat_models: Array<{
    model_name: string;
    provider: string;
    description: string;
    is_latest?: boolean;
    is_recommended?: boolean;
    is_deprecated?: boolean;
  }>;
  available_embedding_models: Array<{
    model_name: string;
    provider: string;
    description: string;
    is_latest?: boolean;
    is_recommended?: boolean;
    dimensions?: number;
  }>;
}

export function LLMModelSettings() {
  const [loading, setLoading] = useState(true);
  const [settings, setSettings] = useState<LLMModelSettingsResponse | null>(null);
  const [testingChat, setTestingChat] = useState(false);
  const [testingEmbedding, setTestingEmbedding] = useState(false);
  const [chatTestResult, setChatTestResult] = useState<string | null>(null);
  const [embeddingTestResult, setEmbeddingTestResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      setLoading(true);
      const data = await settingsApi.get<LLMModelSettingsResponse>('/api/v1/system-settings/llm-models');
      setSettings(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load model settings');
    } finally {
      setLoading(false);
    }
  };

  const testChatConnection = async () => {
    try {
      setTestingChat(true);
      setChatTestResult(null);
      const result = await settingsApi.post<{
        success: boolean;
        message: string;
        model_name: string;
        provider: string;
      }>('/api/v1/system-settings/llm-models/test-chat');

      if (result.success) {
        setChatTestResult(`✅ ${result.message}`);
      } else {
        setChatTestResult(`❌ ${result.message}`);
      }
    } catch (err) {
      setChatTestResult(`❌ ${t('testFailedWithError')}: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setTestingChat(false);
    }
  };

  const testEmbeddingConnection = async () => {
    try {
      setTestingEmbedding(true);
      setEmbeddingTestResult(null);
      const result = await settingsApi.post<{
        success: boolean;
        message: string;
        model_name: string;
        provider: string;
        dimensions?: number;
      }>('/api/v1/system-settings/llm-models/test-embedding');

      if (result.success) {
        setEmbeddingTestResult(`✅ ${result.message}`);
      } else {
        setEmbeddingTestResult(`❌ ${result.message}`);
      }
    } catch (err) {
      setEmbeddingTestResult(`❌ ${t('testFailedWithError')}: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setTestingEmbedding(false);
    }
  };

  const updateChatModel = async (modelName: string, provider: string) => {
    try {
      await settingsApi.put(`/api/v1/system-settings/llm-models/chat?model_name=${modelName}&provider=${provider}`, {});
      await loadSettings();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update chat model');
    }
  };

  const updateEmbeddingModel = async (modelName: string, provider: string) => {
    try {
      await settingsApi.put(`/api/v1/system-settings/llm-models/embedding?model_name=${modelName}&provider=${provider}`, {});
      await loadSettings();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update embedding model');
    }
  };

  if (loading) {
    return <div className="text-center py-4">{t('loading')}</div>;
  }

  if (!settings) {
    return <InlineAlert type="error" message="Failed to load model settings" />;
  }

  return (
    <div className="space-y-6">
      {error && <InlineAlert type="error" message={error} onDismiss={() => setError(null)} />}

      {/* Chat Model Configuration */}
      <div className="border rounded-lg p-4">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-sm font-medium text-gray-900">{t('chatModel')}</h3>
            <p className="text-xs text-gray-500 mt-1">
              {t('chatModelDescription')}
              {settings.chat_model && (
                <span className="ml-2">
                  {t('currentModel')}: <strong>{settings.chat_model.model_name}</strong> ({settings.chat_model.provider})
                </span>
              )}
            </p>
          </div>
          <button
            onClick={testChatConnection}
            disabled={testingChat}
            className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {testingChat ? t('testing') : t('testConnection')}
          </button>
        </div>

        {chatTestResult && (
          <div className={`mb-3 p-2 rounded text-sm ${chatTestResult.startsWith('✅') ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>
            {chatTestResult}
          </div>
        )}

        <select
          value={settings.chat_model?.model_name || ''}
          onChange={(e) => {
            const selected = settings.available_chat_models.find(m => m.model_name === e.target.value);
            if (selected) {
              updateChatModel(selected.model_name, selected.provider);
            }
          }}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500"
        >
          {settings.available_chat_models.map((model) => (
            <option key={model.model_name} value={model.model_name}>
              {model.model_name} {model.is_latest && '⭐'} {model.is_recommended && '✨'} {model.is_deprecated && `(${t('deprecated')})`} - {model.description}
            </option>
          ))}
        </select>
      </div>

      {/* Embedding Model Configuration */}
      <div className="border rounded-lg p-4">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-sm font-medium text-gray-900">{t('embeddingModel')}</h3>
            <p className="text-xs text-gray-500 mt-1">
              {t('embeddingModelDescription')}
              {settings.embedding_model && (
                <span className="ml-2">
                  {t('currentModel')}: <strong>{settings.embedding_model.model_name}</strong> ({settings.embedding_model.provider})
                </span>
              )}
            </p>
          </div>
          <button
            onClick={testEmbeddingConnection}
            disabled={testingEmbedding}
            className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {testingEmbedding ? t('testing') : t('testConnection')}
          </button>
        </div>

        {embeddingTestResult && (
          <div className={`mb-3 p-2 rounded text-sm ${embeddingTestResult.startsWith('✅') ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>
            {embeddingTestResult}
          </div>
        )}

        <select
          value={settings.embedding_model?.model_name || ''}
          onChange={(e) => {
            const selected = settings.available_embedding_models.find(m => m.model_name === e.target.value);
            if (selected) {
              updateEmbeddingModel(selected.model_name, selected.provider);
            }
          }}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500"
        >
          {settings.available_embedding_models.map((model) => (
            <option key={model.model_name} value={model.model_name}>
              {model.model_name} {model.is_latest && '⭐'} {model.is_recommended && '✨'} - {model.description}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
