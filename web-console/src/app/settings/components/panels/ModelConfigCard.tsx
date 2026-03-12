'use client';

import React, { useState } from 'react';
import { useRef, useEffect } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { showNotification } from '../../hooks/useSettingsNotification';

interface ModelItem {
  id: string | number;
  model_name: string;
  provider: string;
  model_type: 'chat' | 'embedding' | 'multimodal';
  display_name: string;
  description: string;
  enabled: boolean;
  icon?: string;
  is_latest?: boolean;
  is_recommended?: boolean;
  dimensions?: number;
  context_window?: number;
  metadata?: Record<string, any>;
}

interface ProviderConfig {
  api_key_configured: boolean;
  api_key?: string;
  base_url?: string;
  project_id?: string;
  location?: string;
}

interface ModelConfigCardData {
  model: ModelItem;
  api_key_configured: boolean;
  base_url?: string;
  project_id?: string;
  location?: string;
  provider_config?: ProviderConfig;
  quota_info?: {
    used: number;
    limit: number;
    reset_date?: string;
  };
}

export interface PullState {
  taskId: string;
  progress: number;
  status: string;
  message: string;
  totalBytes: number;
  downloadedBytes: number;
}

interface ModelConfigCardProps {
  card: ModelConfigCardData;
  onConfigSaved?: () => void;
  pullState?: PullState | null;
  onPullModel?: (model: ModelItem) => void;
  onCancelPull?: (taskId: string) => void;
  onRemoveModel?: (modelId: string | number) => void;
}

export function ModelConfigCard({ card, onConfigSaved, pullState, onPullModel, onCancelPull, onRemoveModel }: ModelConfigCardProps) {
  const { model, api_key_configured, base_url, project_id, location, provider_config, quota_info } = card;
  const [showModelOverride, setShowModelOverride] = useState(false);

  const providerApiKey = provider_config?.api_key || '';
  const providerBaseUrl = provider_config?.base_url || base_url || '';
  const providerProjectId = provider_config?.project_id || project_id || '';
  const providerLocation = provider_config?.location || location || 'us-central1';

  const [apiKey, setApiKey] = useState(providerApiKey);
  const [baseUrl, setBaseUrl] = useState(providerBaseUrl);
  const [projectId, setProjectId] = useState(providerProjectId);
  const [vertexLocation, setVertexLocation] = useState(providerLocation);

  const [modelApiKey, setModelApiKey] = useState('');
  const [modelBaseUrl, setModelBaseUrl] = useState('');
  const [modelProjectId, setModelProjectId] = useState('');
  const [modelLocation, setModelLocation] = useState('');

  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [jsonFile, setJsonFile] = useState<File | null>(null);
  const [jsonFileName, setJsonFileName] = useState<string>('');

  // Derive pull status from props
  const pulling = pullState != null && (pullState.status === 'starting' || pullState.status === 'downloading');
  const pullProgress = pullState?.progress ?? 0;
  const pullStatus = pullState?.status ?? '';
  const pullMessage = pullState?.message ?? '';
  const pullTotalBytes = pullState?.totalBytes ?? 0;
  const pullDownloadedBytes = pullState?.downloadedBytes ?? 0;

  React.useEffect(() => {
    setApiKey(providerApiKey);
    setBaseUrl(providerBaseUrl);
    setProjectId(providerProjectId);
    setVertexLocation(providerLocation);
  }, [providerApiKey, providerBaseUrl, providerProjectId, providerLocation]);

  const handleJsonFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.type !== 'application/json' && !file.name.endsWith('.json')) {
      setTestResult({ success: false, message: 'Please select a valid JSON file' as any });
      return;
    }

    setJsonFile(file);
    setJsonFileName(file.name);

    try {
      const text = await file.text();
      const jsonData = JSON.parse(text);

      if (jsonData.type !== 'service_account') {
        setTestResult({ success: false, message: 'Invalid service account JSON file' as any });
        return;
      }

      if (jsonData.project_id) {
        setProjectId(jsonData.project_id);
      }
      if (jsonData.private_key && jsonData.client_email) {
        const credentialsJson = JSON.stringify({
          type: jsonData.type,
          project_id: jsonData.project_id,
          private_key_id: jsonData.private_key_id,
          private_key: jsonData.private_key,
          client_email: jsonData.client_email,
          client_id: jsonData.client_id,
          auth_uri: jsonData.auth_uri,
          token_uri: jsonData.token_uri,
          auth_provider_x509_cert_url: jsonData.auth_provider_x509_cert_url,
          client_x509_cert_url: jsonData.client_x509_cert_url,
        });
        setApiKey(credentialsJson);
      }
    } catch (err) {
      setTestResult({ success: false, message: `Failed to parse JSON file: ${err instanceof Error ? err.message : 'Unknown error'}` });
    }
  };

  const handleSaveProviderConfig = async () => {
    try {
      setSaving(true);
      const config: any = {
        provider_level: true
      };

      if (apiKey) {
        config.api_key = apiKey;
      }

      if (model.provider === 'ollama' && baseUrl) {
        config.base_url = baseUrl;
      }

      if (model.provider === 'vertex-ai') {
        if (projectId) {
          config.project_id = projectId;
        }
        if (vertexLocation) {
          config.location = vertexLocation;
        }
        if (apiKey) {
          config.api_key = apiKey;
        }
      }

      const response = await settingsApi.put<{ success: boolean; message: string }>(`/api/v1/system-settings/models/${model.id}/config`, config);
      const message = response?.message || t('configSaved' as any) || 'Settings saved successfully';
      showNotification('success', message);
      setJsonFile(null);
      setJsonFileName('');
      if (onConfigSaved) {
        onConfigSaved();
      }
    } catch (err) {
      console.error('Failed to save provider configuration:', err);
      showNotification('error', `Failed to save: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setSaving(false);
    }
  };

  const handleSaveModelOverride = async () => {
    try {
      setSaving(true);
      const config: any = {
        provider_level: false
      };

      if (modelApiKey) {
        config.api_key = modelApiKey;
      }

      if (model.provider === 'ollama' && modelBaseUrl) {
        config.base_url = modelBaseUrl;
      }

      if (model.provider === 'vertex-ai') {
        if (modelProjectId) {
          config.project_id = modelProjectId;
        }
        if (modelLocation) {
          config.location = modelLocation;
        }
      }

      const response = await settingsApi.put<{ success: boolean; message: string }>(`/api/v1/system-settings/models/${model.id}/config`, config);
      const message = response?.message || t('configSaved' as any) || 'Settings saved successfully';
      setModelApiKey('');
      setModelBaseUrl('');
      setModelProjectId('');
      setModelLocation('');
      showNotification('success', message);
      if (onConfigSaved) {
        onConfigSaved();
      }
    } catch (err) {
      console.error('Failed to save model override:', err);
      showNotification('error', `Failed to save: ${err instanceof Error ? err.message : 'Unknown error'}`);
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
        setTestResult({ success: true, message: result.message });
      } else {
        setTestResult({ success: false, message: `${t('testFailedWithError' as any)}: ${result.message}` });
      }
    } catch (err) {
      setTestResult({ success: false, message: `${t('testFailedWithError' as any)}: ${err instanceof Error ? err.message : 'Unknown error'}` });
    } finally {
      setTesting(false);
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
    if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(0)} MB`;
    if (bytes >= 1e3) return `${(bytes / 1e3).toFixed(0)} KB`;
    return `${bytes} B`;
  };

  const handlePullModel = async () => {
    if (onPullModel) {
      onPullModel(model);
    }
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
      <div className="space-y-4">
        <div className="border-b border-gray-200 dark:border-gray-700 pb-4">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Provider Configuration ({model.provider})
            </h4>
            <button
              onClick={handleSaveProviderConfig}
              disabled={saving}
              className="px-4 py-1.5 text-sm bg-accent dark:bg-purple-600 text-white rounded-md hover:bg-accent/90 dark:hover:bg-purple-500 disabled:opacity-50 flex items-center gap-2"
            >
              {saving && (
                <svg className="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
              )}
              {saving ? (t('saving' as any) || 'Saving...') : (t('saveConfiguration' as any) || 'Save Configuration')}
            </button>
          </div>
          {model.provider === 'vertex-ai' && ((provider_config?.api_key_configured || (projectId && vertexLocation)) && !jsonFileName) && (
            <span className="text-xs text-green-600 dark:text-green-400 block mb-3">
              ✓ {t('serviceAccountConfigured' as any)}
            </span>
          )}

          <div className="space-y-3">
            {model.provider === 'vertex-ai' ? (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  {t('serviceAccountJsonFile' as any)}
                </label>
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <input
                      type="file"
                      accept=".json,application/json"
                      onChange={handleJsonFileChange}
                      className="hidden"
                      id="vertex-ai-json-upload"
                    />
                    <label
                      htmlFor="vertex-ai-json-upload"
                      className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md cursor-pointer bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 hover:bg-gray-50 dark:hover:bg-gray-700 text-sm"
                    >
                      {jsonFileName || t('chooseJsonFile' as any)}
                    </label>
                    <button
                      onClick={() => document.getElementById('vertex-ai-json-upload')?.click()}
                      className="px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600"
                    >
                      {t('browse' as any)}
                    </button>
                  </div>
                  {jsonFileName && (
                    <p className="text-xs text-green-600 dark:text-green-400">
                      ✓ {t('selected' as any)} {jsonFileName}
                    </p>
                  )}
                  <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md p-3 text-xs">
                    <p className="font-medium text-blue-900 dark:text-blue-200 mb-2">
                      {t('howToGetServiceAccountJson' as any)}
                    </p>
                    <ol className="list-decimal list-inside space-y-1 text-blue-800 dark:text-blue-300">
                      <li>
                        {t('vertexAiStep1' as any) && <>{t('vertexAiStep1' as any)} </>}
                        <a
                          href={t('vertexAiStep1Link' as any)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="underline hover:text-blue-600 dark:hover:text-blue-200"
                        >
                          {t('vertexAiStep1LinkText' as any)}
                        </a>
                      </li>
                      <li>{t('vertexAiStep2' as any)}</li>
                      <li>{t('vertexAiStep3' as any)}</li>
                      <li>{t('vertexAiStep4' as any)}</li>
                      <li>{t('vertexAiStep5' as any)}</li>
                    </ol>
                  </div>
                </div>
              </div>
            ) : (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  {t('apiKey' as any)}{['ollama', 'llama-cpp', 'llamacpp', 'huggingface'].includes(model.provider) && <span className="text-gray-400 font-normal ml-1">({t('optional' as any) || 'Optional'})</span>}
                </label>
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={provider_config?.api_key_configured ? '••••••••' : (t('enterApiKey' as any) || 'Enter API Key')}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                />
                {provider_config?.api_key_configured && (
                  <span className="text-xs text-green-600 dark:text-green-400 mt-1 block">
                    {t('apiKeyConfigured' as any) || 'API Key configured'}
                  </span>
                )}
                {model.provider === 'gemini-api' && (
                  <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md p-3 text-xs mt-3">
                    <p className="font-medium text-blue-900 dark:text-blue-200 mb-2">
                      {t('howToGetGeminiApiKey' as any) || 'How to get a Gemini API Key'}
                    </p>
                    <ol className="list-decimal list-inside space-y-1 text-blue-800 dark:text-blue-300">
                      <li>
                        {t('geminiApiStep1' as any) || 'Go to '}
                        <a
                          href="https://aistudio.google.com/apikey"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="underline hover:text-blue-600 dark:hover:text-blue-200"
                        >
                          Google AI Studio
                        </a>
                      </li>
                      <li>{t('geminiApiStep2' as any) || 'Sign in with your Google Account'}</li>
                      <li>{t('geminiApiStep3' as any) || 'Click "Create API Key" and select a project'}</li>
                      <li>{t('geminiApiStep4' as any) || 'Copy the generated key and paste it above'}</li>
                    </ol>
                    <p className="mt-2 text-blue-700 dark:text-blue-400">
                      {t('geminiApiFreeTier' as any) || 'Free tier: 1,500 requests/day for embedding models'}
                    </p>
                  </div>
                )}
                {model.provider === 'openai' && !provider_config?.api_key_configured && (
                  <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md p-3 text-xs mt-3">
                    <p className="font-medium text-blue-900 dark:text-blue-200 mb-2">
                      {t('howToGetOpenaiApiKey' as any) || 'How to get an OpenAI API Key'}
                    </p>
                    <ol className="list-decimal list-inside space-y-1 text-blue-800 dark:text-blue-300">
                      <li>
                        {t('openaiApiStep1' as any) || 'Go to '}
                        <a
                          href="https://platform.openai.com/api-keys"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="underline hover:text-blue-600 dark:hover:text-blue-200"
                        >
                          OpenAI Platform
                        </a>
                      </li>
                      <li>{t('openaiApiStep2' as any) || 'Sign in and click "Create new secret key"'}</li>
                      <li>{t('openaiApiStep3' as any) || 'Copy the key and paste it above'}</li>
                    </ol>
                  </div>
                )}
              </div>
            )}

            {model.provider === 'ollama' && (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  {t('baseUrl' as any) || 'Base URL'} ({t('optional' as any) || 'Optional'})
                </label>
                <input
                  type="text"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder="http://localhost:11434"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                />
              </div>
            )}

            {model.provider === 'vertex-ai' && (
              <>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {t('gcpProjectId' as any)} {projectId && <span className="text-xs text-gray-500">{t('fromJson' as any)}</span>}
                  </label>
                  <input
                    type="text"
                    value={projectId}
                    onChange={(e) => setProjectId(e.target.value)}
                    placeholder="your-project-id"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                    readOnly={!!jsonFileName}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Location ({t('optional' as any) || 'Optional'})
                  </label>
                  <input
                    type="text"
                    value={vertexLocation}
                    onChange={(e) => setVertexLocation(e.target.value)}
                    placeholder="us-central1"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Default: us-central1. Other options: us-east1, us-west1, europe-west1, asia-northeast1
                  </p>
                </div>
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
          {model.icon && <span className="text-2xl">{model.icon}</span>}
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                {model.display_name}
                {model.enabled && ['ollama', 'huggingface', 'llama-cpp'].includes(model.provider) && (!pullStatus || !['pulling', 'starting', 'processing'].includes(pullStatus)) && (
                  <span className="px-2 py-0.5 text-[10px] font-medium rounded-full bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 border border-green-200 dark:border-green-800 tracking-wider">
                    {t('modelReady' as any) || '已就緒'}
                  </span>
                )}
                {model.enabled && ['openai', 'anthropic', 'vertex-ai'].includes(model.provider) && (
                  <span className="px-2 py-0.5 text-[10px] font-medium rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 border border-blue-200 dark:border-blue-800 tracking-wider">
                    {t('modelCloudConnected' as any) || '雲端串接'}
                  </span>
                )}
              </h3>
              {onRemoveModel && (
                <button
                  onClick={() => { if (confirm(`確定要移除「${model.display_name}」嗎？`)) onRemoveModel(model.id); }}
                  className="text-gray-400 hover:text-red-500 dark:hover:text-red-400 transition-colors p-1 rounded"
                  title="移除模型"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              )}
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {model.provider} • {model.model_type === 'chat' ? 'Chat Model' : model.model_type === 'multimodal' ? 'Multimodal Model' : 'Embedding Model'}
            </p>
            {/* HuggingFace rich metadata */}
            {model.provider === 'huggingface' && model.metadata?.hf_author && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {/* Format badge */}
                {model.metadata.hf_format && (
                  <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                    model.metadata.hf_format === 'GGUF' ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300' :
                    model.metadata.hf_format === 'MLX' ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300' :
                    'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                  }`}>
                    {model.metadata.hf_format}
                  </span>
                )}
                {/* Quantization */}
                {model.metadata.hf_quantization && (
                  <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300">
                    {model.metadata.hf_quantization}
                  </span>
                )}
                {/* Author */}
                <span className="px-2 py-0.5 text-xs rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
                  👤 {model.metadata.hf_author}
                </span>
                {/* Parameters */}
                {model.metadata.hf_parameters && (
                  <span className="px-2 py-0.5 text-xs rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
                    {(model.metadata.hf_parameters / 1e9).toFixed(1)}B params
                  </span>
                )}
                {/* Downloads */}
                {model.metadata.hf_downloads > 0 && (
                  <span className="px-2 py-0.5 text-xs rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
                    ⬇ {model.metadata.hf_downloads > 1000000 ? `${(model.metadata.hf_downloads / 1000000).toFixed(1)}M` : model.metadata.hf_downloads > 1000 ? `${(model.metadata.hf_downloads / 1000).toFixed(0)}K` : model.metadata.hf_downloads}
                  </span>
                )}
                {/* Storage */}
                {model.metadata.hf_storage_bytes && (
                  <span className="px-2 py-0.5 text-xs rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
                    💾 {(model.metadata.hf_storage_bytes / (1024 * 1024 * 1024)).toFixed(1)} GB
                  </span>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
          <div className="flex items-center justify-between mb-3">
            <button
              onClick={() => setShowModelOverride(!showModelOverride)}
              className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100"
            >
              <span>{t('modelOverride' as any) || 'Model Override (Advanced)'}</span>
              <svg
                className={`w-4 h-4 transition-transform ${showModelOverride ? 'rotate-180' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {showModelOverride && (
              <button
                onClick={handleSaveModelOverride}
                disabled={saving}
                className="px-4 py-1.5 text-sm bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300 border border-purple-300 dark:border-purple-700 rounded-md hover:bg-purple-100 dark:hover:bg-purple-900/30 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {saving ? (t('saving' as any) || 'Saving...') : (t('saveModelOverride' as any) || 'Save Model Override')}
              </button>
            )}
          </div>

          {showModelOverride && (
            <div className="mt-3 space-y-3 pt-3 border-t border-gray-200 dark:border-gray-700">
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                {t('modelOverrideDescription' as any) || 'Override provider settings for this specific model (usually not needed)'}
              </p>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  {t('apiKey' as any)} ({t('override' as any) || 'Override'}){['ollama', 'llama-cpp', 'llamacpp', 'huggingface'].includes(model.provider) && <span className="text-gray-400 font-normal ml-1">({t('optional' as any) || 'Optional'})</span>}
                </label>
                <input
                  type="password"
                  value={modelApiKey}
                  onChange={(e) => setModelApiKey(e.target.value)}
                  placeholder={t('enterApiKey' as any) || 'Enter API Key'}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                />
              </div>

              {model.provider === 'ollama' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {t('baseUrl' as any) || 'Base URL'} ({t('override' as any) || 'Override'})
                  </label>
                  <input
                    type="text"
                    value={modelBaseUrl}
                    onChange={(e) => setModelBaseUrl(e.target.value)}
                    placeholder="http://localhost:11434"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                  />
                </div>
              )}

              {model.provider === 'vertex-ai' && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      {t('gcpProjectId' as any)} ({t('override' as any) || 'Override'})
                    </label>
                    <input
                      type="text"
                      value={modelProjectId}
                      onChange={(e) => setModelProjectId(e.target.value)}
                      placeholder="your-project-id"
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      {t('location' as any) || 'Location'} ({t('override' as any) || 'Override'})
                    </label>
                    <input
                      type="text"
                      value={modelLocation}
                      onChange={(e) => setModelLocation(e.target.value)}
                      placeholder="us-central1"
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                    />
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 gap-4">
          {model.dimensions && (
            <div>
              <span className="text-xs text-gray-500 dark:text-gray-400">{t('dimensions' as any) || 'Dimensions'}</span>
              <div className="text-sm font-medium text-gray-900 dark:text-gray-100">{model.dimensions}</div>
            </div>
          )}
          {model.context_window && (
            <div>
              <span className="text-xs text-gray-500 dark:text-gray-400">{t('contextWindow' as any) || 'Context Window'}</span>
              <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                {model.context_window.toLocaleString()}
              </div>
            </div>
          )}
        </div>

        <div>
          <div className="flex gap-3">
            <button
              onClick={handleTestConnection}
              disabled={testing || pulling}
              className="flex-1 px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {testing ? t('testing' as any) : t('testConnection' as any)}
            </button>
            {['ollama', 'huggingface'].includes(model.provider) && (
              <button
                onClick={handlePullModel}
                disabled={testing || pulling}
                className="flex-1 px-4 py-2 bg-accent dark:bg-blue-600 text-white rounded-md hover:bg-accent/90 dark:hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {pulling ? (
                  <>
                    <svg className="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    {pullProgress > 0 ? `${pullProgress}%` : '下載中...'}
                  </>
                ) : pullStatus === 'completed' ? (
                  <>
                    <span>✅</span>
                    下載完成
                  </>
                ) : pullStatus === 'failed' ? (
                  <>
                    <span>❌</span>
                    下載失敗
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    下載模型
                  </>
                )}
              </button>
            )}
          </div>
          {/* Download Progress Bar */}
          {pulling && (
            <div className="mt-3">
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2.5 overflow-hidden">
                <div
                  className="h-2.5 rounded-full transition-all duration-500 ease-out"
                  style={{
                    width: `${pullProgress}%`,
                    background: pullStatus === 'failed'
                      ? '#ef4444'
                      : pullStatus === 'completed'
                        ? '#22c55e'
                        : 'linear-gradient(90deg, #3b82f6, #8b5cf6)',
                  }}
                />
              </div>
              <div className="flex justify-between items-center mt-1">
                <span className="text-xs text-gray-500 dark:text-gray-400 truncate max-w-[60%]">
                  {pullMessage}
                </span>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-600 dark:text-gray-300 font-medium whitespace-nowrap">
                    {pullTotalBytes > 0
                      ? `${formatBytes(pullDownloadedBytes)} / ${formatBytes(pullTotalBytes)}`
                      : pullProgress > 0
                        ? `${pullProgress}%`
                        : '準備中...'}
                  </span>
                  {onCancelPull && pullState?.taskId && (
                    <button
                      onClick={() => onCancelPull(pullState.taskId)}
                      className="text-xs text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300 font-medium px-1.5 py-0.5 rounded hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                      title="取消下載"
                    >
                      ✕ 取消
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}
          {testResult && (
            <div className={`mt-2 p-2 rounded text-sm ${testResult.success
                ? 'bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-300'
                : 'bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-300'
              }`}>
              {testResult.message}
            </div>
          )}
        </div>

        {quota_info && (
          <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                {t('quotaUsage' as any)}
              </span>
              <span className="text-sm text-gray-500 dark:text-gray-400">
                {quota_info.used} / {quota_info.limit}
              </span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
              <div
                className="bg-gray-600 h-2 rounded-full"
                style={{ width: `${(quota_info.used / quota_info.limit) * 100}%` }}
              />
            </div>
            {quota_info.reset_date && (
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                {t('resetDate' as any) || 'Reset Date'}: {quota_info.reset_date}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

