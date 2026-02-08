'use client';

import React, { useState } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { showNotification } from '../../hooks/useSettingsNotification';

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

interface ModelConfigCardProps {
  card: ModelConfigCardData;
  onConfigSaved?: () => void;
}

export function ModelConfigCard({ card, onConfigSaved }: ModelConfigCardProps) {
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
  const [testResult, setTestResult] = useState<string | null>(null);
  const [jsonFile, setJsonFile] = useState<File | null>(null);
  const [jsonFileName, setJsonFileName] = useState<string>('');

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
      setTestResult('Please select a valid JSON file' as any);
      return;
    }

    setJsonFile(file);
    setJsonFileName(file.name);

    try {
      const text = await file.text();
      const jsonData = JSON.parse(text);

      if (jsonData.type !== 'service_account') {
        setTestResult('Invalid service account JSON file' as any);
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
      setTestResult(`Failed to parse JSON file: ${err instanceof Error ? err.message : 'Unknown error'}`);
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
        setTestResult(result.message);
      } else {
        setTestResult(`${t('testFailedWithError' as any)}: ${result.message}`);
      }
    } catch (err) {
      setTestResult(`${t('testFailedWithError' as any)}: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 relative">
      <div className="absolute top-6 right-6">
        {model.provider === 'vertex-ai' && (
          <button
            onClick={handleSaveProviderConfig}
            disabled={saving || !jsonFileName}
            className="px-4 py-1.5 text-sm bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300 border border-purple-300 dark:border-purple-700 rounded-md hover:bg-purple-100 dark:hover:bg-purple-900/30 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? (t('saving' as any) || 'Saving...') : (provider_config?.api_key_configured ? t('update' as any) : t('saveConfiguration' as any))}
          </button>
        )}
        {model.provider !== 'vertex-ai' && (
          <button
            onClick={handleSaveProviderConfig}
            disabled={saving}
            className="px-4 py-1.5 text-sm bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300 border border-purple-300 dark:border-purple-700 rounded-md hover:bg-purple-100 dark:hover:bg-purple-900/30 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? (t('saving' as any) || 'Saving...') : (provider_config?.api_key_configured ? t('update' as any) : t('saveConfiguration' as any))}
          </button>
        )}
      </div>
      <div className="space-y-4">
        <div className="border-b border-gray-200 dark:border-gray-700 pb-4">
          <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
            Provider Configuration ({model.provider})
          </h4>
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
                  {t('apiKey' as any)}
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
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              {model.display_name}
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {model.provider} • {model.model_type === 'chat' ? 'Chat Model' : 'Embedding Model'}
            </p>
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
                  {t('apiKey' as any)} ({t('override' as any) || 'Override'})
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
          <button
            onClick={handleTestConnection}
            disabled={testing}
            className="w-full px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {testing ? t('testing' as any) : t('testConnection' as any)}
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

