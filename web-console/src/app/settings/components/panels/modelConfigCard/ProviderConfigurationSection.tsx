'use client';

import { t } from '../../../../../lib/i18n';
import type { ProviderConfigurationSectionProps } from './types';

export function ProviderConfigurationSection({
  model,
  providerConfig,
  apiKey,
  baseUrl,
  projectId,
  vertexLocation,
  jsonFileName,
  saving,
  onApiKeyChange,
  onBaseUrlChange,
  onProjectIdChange,
  onVertexLocationChange,
  onJsonFileChange,
  onSaveProviderConfig,
}: ProviderConfigurationSectionProps) {
  return (
    <div className="border-b border-gray-200 dark:border-gray-700 pb-3">
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          Provider Configuration ({model.provider})
        </h4>
        <button
          onClick={onSaveProviderConfig}
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

      {model.provider === 'vertex-ai' && ((providerConfig?.api_key_configured || (projectId && vertexLocation)) && !jsonFileName) && (
        <span className="text-xs text-green-600 dark:text-green-400 block mb-3">
          {t('serviceAccountConfigured' as any)}
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
                  onChange={onJsonFileChange}
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
                  {t('selected' as any)} {jsonFileName}
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
              onChange={(event) => onApiKeyChange(event.target.value)}
              placeholder={providerConfig?.api_key_configured ? '********' : (t('enterApiKey' as any) || 'Enter API Key')}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-gray-500 dark:focus:ring-gray-500 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            />
            {providerConfig?.api_key_configured && (
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
            {model.provider === 'openai' && !providerConfig?.api_key_configured && (
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
              onChange={(event) => onBaseUrlChange(event.target.value)}
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
                onChange={(event) => onProjectIdChange(event.target.value)}
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
                onChange={(event) => onVertexLocationChange(event.target.value)}
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
  );
}
